__all__ = (
    "Provider",
    "ProviderAWS",
    "ProviderSNS",
    "ProviderS3",
    "ProviderOutboxDjango",
    "UnsupportedProvider",
    "NullProvider",
)

import abc
import boto3
import functools
import warnings
from communicate.utils.eventbus.hooks import (
    HookRegistry,
    get_default_registry,
)
from communicate.utils.eventbus.publisher.utils import (
    AmazonMessageExtender,
)


class Provider(abc.ABC):
    topic: str
    conn: any
    hook: HookRegistry = get_default_registry()

    def __init__(self, *args, topic: str = None, **kwargs):
        self.topic = topic

    def __new__(cls, *args, **kwargs):
        obj = super().__new__(cls)
        obj.publish = obj.pre_process(obj.publish, obj)
        return obj

    @staticmethod
    def pre_process(func, provider):
        @functools.wraps(func)
        def wrapper(event):
            event = provider.hook.run_pre_hooks(event)
            result = func(event)
            provider.hook.run_post_hooks(event)
            return result

        return wrapper

    @abc.abstractmethod
    def publish(self, event) -> dict:
        pass


class ProviderAWS(Provider):
    resource: str

    def __init__(
            self,
            *args,
            secret: str = "test",
            key: str = "test",
            region: str = "us-west-2",
            endpoint: str = None,
            force_key_auth: bool = False,
            **kwargs,
    ):
        self.account_id = kwargs["accountId"]
        self.force_key_auth = force_key_auth
        self.secret = secret
        self.key = key
        self.region = region
        self.endpoint = endpoint
        super().__init__(*args, **kwargs)
        self._setup_connection()

    def _setup_connection(self):
        _auth = {}

        if self.force_key_auth:
            _auth.update(
                aws_access_key_id=self.key,
                aws_secret_access_key=self.secret,
            )

        session = boto3.session.Session(region_name=self.region, **_auth)

        client_kwargs = {
            "use_ssl": True,
            "endpoint_url": self.endpoint,
        }

        self.conn = session.client(self.resource, **client_kwargs)


class ProviderSNS(AmazonMessageExtender, ProviderAWS):
    resource = "sns"

    @property
    def arn(self):
        return f"arn:aws:sns:{self.region}:{self.account_id}:{self.topic}"

    def publish(self, event) -> dict:
        return self.conn.publish(
            TopicArn=self.arn,
            Message=event.json(by_alias=True),
            MessageAttributes=self.get_msg_attrs(event),
        )


class ProviderS3(ProviderAWS):
    resource = "s3"

    def publish(self, event) -> dict:
        raise NotImplementedError("S3 Transport not supported yet")


class UnsupportedProvider(Provider):
    def publish(self, event) -> dict:
        raise NotImplementedError("Unsupported Provider")


class NullProvider(Provider):
    """For testing or lde env only"""

    def publish(self, event) -> dict:
        warnings.warn(
            f"Usage of {self.__class__.__name__}:"
            f" Please do not use this provider in production environments !!!"
        )
        print("Publishing event:")
        print(event.json(indent=3, by_alias=True))
        print()
        return event.dict()


class ProviderOutboxDjango(Provider):
    """Attention: In Progress. Not supported yet"""

    resource = "outboxDjango"

    def publish(self, event) -> dict:
        raise NotImplementedError("Outbox Django Transport not supported yet")
