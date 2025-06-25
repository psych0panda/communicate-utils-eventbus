import abc
import json
import logging
import os
import re
from typing import List, Optional, Any

logger = logging.getLogger("config_builder")
STORAGE = {}


class BaseConfigBuilder(abc.ABC):
    _config: dict

    @property
    @abc.abstractmethod
    def config(self):
        pass

    @abc.abstractmethod
    def add_in_memory_collection(self, obj: dict):
        pass

    @abc.abstractmethod
    def add_json_file(self, file, abs_path=False):
        pass

    @abc.abstractmethod
    def add_environment_variables(self):
        pass

    @abc.abstractmethod
    def add_vault_source(self, *args, **kwargs):
        pass

    @abc.abstractmethod
    def add_command_line(self, args: list):
        pass

    @abc.abstractmethod
    def read_value(
            self,
            path: str,
            default=None,
            delimiter=".",
            lookup_prefixes: Optional[List] = None,
    ):
        pass


class TemplateParser:
    tag_start: str
    _tag_start_len: int
    tag_end: str
    _tag_end_len: int
    tag_re: re.Pattern

    def __init__(
            self,
            inventory: BaseConfigBuilder,
            tag_start: str = "{{",
            tag_end: str = "}}",
    ):
        self.inventory = inventory
        self.tag_re = re.compile(
            f"({re.escape(tag_start)}.*?{re.escape(tag_end)})"
        )
        self.tag_start = tag_start
        self._tag_start_len = len(tag_start)
        self.tag_end = tag_end
        self._tag_end_len = len(tag_end)

    def __call__(self, obj: any, *args, **kwargs):
        if isinstance(obj, str):
            obj = self._parse(obj)
        return obj

    def _parse_item(self, entry: str) -> any:
        if entry.startswith(self.tag_start):
            x_path: str = entry[
                          self._tag_start_len: -self._tag_end_len
                          ].strip()
            entry = self.inventory.read_value(x_path)
        return entry

    def _parse(self, line: str) -> any:
        _res = []

        for entry in self.tag_re.split(line):
            if entry:
                _res.append(self._parse_item(entry))

        res = _res[0] if len(_res) == 1 else "".join(map(str, _res))

        return res


class NotEnoughCLIArguments(Exception):
    pass


class ConfigBuilder(BaseConfigBuilder):
    """Singleton"""

    _config = STORAGE
    _base_path = None
    _parse_text = True
    _parse_quoted_strings = True

    __delimiter = "__"
    __TRUE = "TRUE"
    __FALSE = "FALSE"

    __env_marker = "z__"
    __class_name = "SETTINGS"
    __class = None

    instance: "ConfigBuilder"

    def __new__(cls, *args, **kwargs):
        if not hasattr(cls, "instance"):
            cls.instance = super(ConfigBuilder, cls).__new__(cls)
        return cls.instance

    def __init__(
            self,
            parse_text=True,
            parse_quoted_strings=True,
            base_path="./",
            parser=TemplateParser,
    ):
        self.set_base_path(base_path)
        self._parse_text = parse_text
        self._parse_quoted_strings = parse_quoted_strings
        self._parse = parser(inventory=self)

    def _add_value(self, entries: list, value: str):
        sel = self._config
        for entry in entries:

            if entry == entries[-1]:
                sel.setdefault(entry, self._parse_value(value))
            else:
                sel.setdefault(entry, {})
            sel = sel[entry]

    def _parse_value(self, value: str):
        value = value.strip()

        if not self._parse_text:
            return value

        if value.upper() == self.__TRUE:
            return True

        if value.upper() == self.__FALSE:
            return False

        try:
            return int(value)
        except ValueError:
            pass

        try:
            return json.loads(value)
        except json.JSONDecodeError:
            pass
        if self._parse_quoted_strings:
            value = value.strip("'").strip('"').strip("`")
        return value

    def set_base_path(self, path):
        self._base_path = path

    def _from_dict(self, conf: dict, obj: dict):
        for setting, value in obj.items():
            _current_value = conf.get(setting)
            if isinstance(value, dict) and isinstance(_current_value, dict):
                value = self._from_dict(_current_value, value)
            conf[setting] = value
        return self.resolve_interpolations(conf)

    def resolve_interpolations(self, config: any) -> any:
        if isinstance(config, dict):
            for settings, content in config.items():
                config[settings] = self.resolve_interpolations(content)
        elif isinstance(config, list):
            config = [self.resolve_interpolations(i) for i in config]
        elif isinstance(config, str):
            config = self._parse(config)

        return config

    def add_in_memory_collection(self, obj: dict):
        self._config = self._from_dict(self.config, obj)

    def add_json_file(self, file, abs_path=False):
        if not abs_path:
            file = os.path.join(self._base_path, file)

        if not os.path.isfile(file):
            raise FileNotFoundError(
                errno.ENOENT, os.strerror(errno.ENOENT), file
            )

        with open(file, "r", encoding="utf-8") as fh:
            _conf = json.load(fh)

        self.add_in_memory_collection(_conf)

    def add_environment_variables(self):
        for path, value in os.environ.items():
            if str(path).startswith(self.__env_marker):
                entries = (
                    str(path)  # pylint: disable=bad-str-strip-call
                    .lstrip(self.__env_marker)
                    .split(self.__delimiter)
                )
                self._add_value(entries, value)

    def add_vault_source(self, *args, **kwargs):
        raise NotImplementedError

    def add_command_line(self, args: list):
        _len = len(args)
        if _len < 3:
            raise NotEnoughCLIArguments(f"Not enough CLI arguments: {args}")

        for index in range(1, _len - 1):
            if index % 2 != 0:
                entries = (
                    str(args[index])  # pylint: disable=bad-str-strip-call
                    .lstrip("--")
                    .split(self.__delimiter)
                )
                self._add_value(entries, args[index + 1])

    def _read_value(self, path: str, default=None, delimiter="."):
        entries = path.split(delimiter)
        _sel = self.config.get(entries.pop(0))
        if _sel is not None:
            for entry in entries:
                _sel = _sel.get(entry, None)
                if _sel is None:
                    _sel = default
                    break
        else:
            _sel = default
        return _sel

    def read_value(
            self,
            path: str,
            default: Optional[Any] = None,
            delimiter: str = ".",
            lookup_prefixes: Optional[List] = None,
    ):
        for prefix in lookup_prefixes or []:
            if prefix is not None:
                lookup_path = f"{prefix}.{path}"
            else:
                lookup_path = path
            value = self._read_value(
                path=lookup_path, default=None, delimiter=delimiter
            )
            if value is not None:
                return value

        return self._read_value(
            path=path,
            default=default,
            delimiter=delimiter,
        )

    @property
    def config(self):
        return self._config

    @property
    def config_json(self):
        return json.dumps(self._config)

    @property
    def config_json_pretty(self):
        return json.dumps(self._config, indent=3)

    @property
    def config_cls(self):
        if not self.__class:
            self.__class = type(self.__class_name, (object,), self.config)
        return self.__class

    def _inject(self, obj, setter):
        for key, value in self.config.items():
            setter(obj, key, value)

    def inject_dict(self, obj: dict):
        self._inject(obj, setter=type(obj).__setitem__)

    def inject_obj(self, obj: any):
        self._inject(obj, setter=type(obj).__setattr__)


class ConfigInjector:
    config_storage: str = "communicate.utils.configuration.ConfigBuilder"
    __config_builder: BaseConfigBuilder
    config: dict

    def setup_configuration(self):
        self.__config_builder = ConfigBuilder()
        self.config = (
            self.__config_builder._config  # pylint: disable=protected-access
        )


config_builder = ConfigBuilder()
config_builder.add_environment_variables()

# Workaround for EventBus
default_topic = "events"
# default_provider = config_builder.read_value("eventBus.publisher.default.provider")
default_provider = "ProviderSNS"

# TODO: This should be moved to a separate configuration file or settings file if you use Django

event_bus = {
    "awsAuth": {
        "key": "000000000000",
        "secret": config_builder.read_value("eventBus.publisher.default.secret"),
        "region": "us-east-1",
        "profiles": {
            "default": {
                "accountId": "000000000000",
                "force_key_auth": True,
                "secret": config_builder.read_value("eventBus.publisher.default.secret"),
                "key": "000000000000",
                "region": "us-east-1",
                "endpoint": "http://localhost.localstack.cloud:4566"
            }
        }
    },
    "eventBus": {
        "publisher": {
            "targets": {
                "allEventsTarget": {
                    "route": "*",
                    "provider": "sns",
                    "wraps": {"topic": default_topic, "provider": default_provider},
                }
            }
        }
    }
}

config_builder.add_in_memory_collection(event_bus)
