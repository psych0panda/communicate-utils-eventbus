import abc

import boto3
from botocore.config import Config

from communicate.utils.eventbus.base import Event
from communicate.utils.eventbus.publisher.routing import Router
from communicate.utils.eventbus.publisher.utils import (
    AmazonMessageExtender,
)
from communicate.utils.format import camelize


class AbstractPublisher(abc.ABC):
    conn: any
    config: dict
    name: str

    @abc.abstractmethod
    def publish_event(self, event: Event):
        pass

    @abc.abstractmethod
    def publish(self, name: str, data: any, routing_attrs: dict = None):
        pass

    @abc.abstractmethod
    def _load_config(self, conf: any = None):
        pass

    @abc.abstractmethod
    def _setup_connection(self):
        pass

    @property
    @abc.abstractmethod
    def topic(self) -> str:
        pass


class AmazonSNSPublisher(AmazonMessageExtender):
    _default_region = "us-east-1"

    def _load_config(self, conf: any = None):
        if conf:
            self.config = conf

    def _setup_connection(self):

        access_key_id = self.config.pop("key", "test")
        secret_access_key = self.config.pop("secret", "test")
        session_token = self.config.pop("session_token", None)
        region = self.config.pop("region", self._default_region)

        session = boto3.session.Session(
            region_name=region,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            aws_session_token=session_token,
        )
        client_kwargs = {
            "use_ssl": True,
            "endpoint_url": self.config.get("endpoint_url") or self.config.get("endpoint", "http://localhost:4566"),
        }

        config = Config(**self.config.pop("aws", {}))

        self.conn = session.client("sns", config=config, **client_kwargs)

    def __init__(self, name: str, config: dict = None):
        """
        :param name: Publisher Name
        :param config: Publisher configuration
            - key: AWS SNS access key
            - secret: AWS SNS access secret
            - region: AWS default region
            - endpoint_url: AWS default entrypoint
            - aws: AWS custom configuration
        """
        self.name = name
        self._load_config(config)
        self._setup_connection()

    def publish_event(self, event: Event) -> dict:
        return self.conn.publish(
            TopicArn=self.topic,
            Message=event.json(by_alias=True),
            MessageAttributes=self.get_msg_attrs(event),
        )

    def publish(
            self, name: str, data: any, routing_attrs: dict = None
    ) -> dict:
        event = Event.create(
            name,
            publisher_name=camelize(self.name),
            payload=data,
        )
        if isinstance(routing_attrs, dict):
            event.metadata.update_routing_keys(routing_attrs)
        return self.publish_event(event)

    @property
    def topic(self) -> str:
        return self.config["topic_arn"]


class PublisherWithRouting:
    name: str
    router: Router

    def __init__(self, router: Router = None, name=None):
        self.name = name or self.__class__.__name__

        if not router:
            router = Router()

        self.router = router

    def publish(
            self, name: str, data: any, routing_attrs: dict = None
    ) -> dict:
        event = Event.create(name, publisher_name=self.name, payload=data)
        if isinstance(routing_attrs, dict):
            event.metadata.update_routing_keys(routing_attrs)
        return self.publish_event(event)

    def publish_event(self, event: Event) -> dict:
        return self._publish(event)

    def publish_outbox_event(self, event: Event) -> dict:
        return self._publish(event, is_outbox=True)

    def _publish(self, event: Event, is_outbox=False) -> dict:
        provider = self.router.resolve(
            self.name, event.metadata.event_name, is_outbox=is_outbox
        )
        return provider.publish(event)
