import abc
import copy
import fnmatch
import importlib
import re
from collections import OrderedDict
from communicate.utils.eventbus.configuration import ConfigInjector
from communicate.utils.eventbus.exceptions import ApplicationError
from communicate.utils.eventbus.exceptions import (
    InvalidProvider,
    InvalidRoute,
)
from communicate.utils.eventbus.publisher.providers import (
    NullProvider,
    Provider,
    ProviderOutboxDjango,
    ProviderS3,
    ProviderSNS,
)
from typing import MutableMapping, Type
from logging import getLogger

logger = getLogger(__name__)

class RouteResolve:
    mapping: dict
    patterns: MutableMapping

    def __init__(self, mapping: dict = None):
        self.mapping = {}
        self.patterns = OrderedDict()

        if mapping:
            self.configure(mapping)

    def configure(self, mapping: dict):
        for _route, _config in mapping.items():
            self.add_route(_route, _config)

    def add_route(self, route: str, config: dict):
        if "*" in route:
            self.patterns[re.compile(fnmatch.translate(route))] = config
        else:
            self.mapping[route] = config

    def __call__(self, route) -> dict:
        try:
            return self.mapping[route]
        except KeyError:
            pass

        sorted_mapping = sorted(
            self.patterns.keys(), key=lambda k: -len(k.pattern)
        )
        for _pattern in sorted_mapping:
            if _pattern.match(route):
                return self.patterns[_pattern]

        raise InvalidRoute


class RouteResolveV2(RouteResolve):
    mapping: dict
    patterns: MutableMapping

    def configure(self, mapping: dict):
        for _, _config in mapping.items():
            _route = _config["route"]
            self.add_route(_route, _config)


class BaseRouter(abc.ABC):
    resolver: RouteResolve

    @abc.abstractmethod
    def resolve(
            self, publisher_name: str, event_name: str, is_outbox=False
    ) -> Provider:
        pass


class Router(ConfigInjector, BaseRouter):
    """Singleton"""

    instance: "Router"
    config: dict
    resolver_cls: Type[RouteResolve]
    resolver: RouteResolve
    providers: MutableMapping[str, Type[Provider]]
    _default_providers = OrderedDict(
        s3=ProviderS3,
        sns=ProviderSNS,
        outboxDjango=ProviderOutboxDjango,
        null=NullProvider,
        local=NullProvider,  # this is needed for ConfigBuilder parser
    )

    def __new__(cls, *args, **kwargs):
        if not hasattr(cls, "instance"):
            cls.instance = super(Router, cls).__new__(cls)
        return cls.instance

    def __init__(
            self,
            config: dict = None,
            providers: MutableMapping[str, Type[Provider]] = None,
    ):

        if not config:
            self.setup_configuration()
        else:
            self.config = config

        self.resolver = self.get_resolver()
        self.providers = providers or self.get_default_providers()

    @classmethod
    def get_default_providers(cls) -> OrderedDict:
        return copy.deepcopy(cls._default_providers)

    def get_resolver_cls(self) -> Type[RouteResolve]:
        if not self.resolver_cls:
            raise ApplicationError("Undefined Resolver")
        return self.resolver_cls

    def get_resolver(self) -> RouteResolve:
        try:
            resolver_config = self.config["eventBus"]["publisher"][
                "eventsTargets"
            ]
            self.resolver_cls = RouteResolve
        except KeyError:
            resolver_config = self.config["eventBus"]["publisher"]["targets"]
            self.resolver_cls = RouteResolveV2
        return self.get_resolver_cls()(resolver_config)

    @property
    def aws_auth(self):
        return self.config["awsAuth"]

    @staticmethod
    def _construct_route(publisher_name, event_name) -> str:
        return f"{publisher_name}.{event_name}"

    @staticmethod
    def _get_outbox_config(config: dict) -> dict:
        config_ = {}  # TODO GET DEFAULT
        try:
            config_ = config["wraps"]
        except KeyError:
            pass

        return config_

    def resolve(
            self, publisher_name: str, event_name: str, is_outbox=False
    ) -> "Provider":
        _route = self._construct_route(publisher_name, event_name)
        _config = self.resolver(_route)

        if is_outbox:
            _config = self._get_outbox_config(_config)

        return self.get_provider(_config)

    def get_provider(self, config) -> Provider:
        try:
            provider_type = config["provider"]
            provider_cls = self.providers.get(provider_type)
            if not provider_cls:
                provider_cls = self.__load_provider_from_module(provider_type)
        except (KeyError, AttributeError) as err:
            raise InvalidProvider from err

        return self.construct_provider(provider_cls, config)

    def __load_provider_from_module(self, provider_type: str):
        """Lazy load of provider cls for event publishing
        Configuration Example:
            ...
              "provider": "communicate.utils.eventbus.tests.TestProvider",
            ...
        """
        if isinstance(provider_type, str) and "." in provider_type:
            module_str, _, cls_name = provider_type.rpartition(".")
            module = importlib.import_module(module_str)
            provider_cls = getattr(module, cls_name)
            self.providers[provider_type] = provider_cls
            return provider_cls
        raise KeyError(f"No such provider {provider_type}")

    def construct_provider(self, provider_cls: Type[Provider], config: dict):
        profile_name = config.get("profile", "default")
        profile = self.aws_auth["profiles"].get(profile_name)
        return provider_cls(**config, **profile)
