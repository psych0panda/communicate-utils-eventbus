import abc
import warnings
from communicate.utils.format import camelize
from communicate.utils.format.time import get_time_now
from datetime import datetime
from humps import decamelize
from pydantic import BaseModel, Field
from typing import Any, Dict, Optional, Type, Union
from uuid import UUID, uuid4


class ModelConfig:  # pylint: disable=too-few-public-methods
    alias_generator = camelize
    allow_population_by_field_name = True
    allow_population_by_alias = True


class EventMeta(BaseModel):
    contains_personal_data: bool = False
    tracestate: str = ""
    traceparent: str = (
        "00-00000000000000000000000000000000-0000000000000000-01"
    )

    authorization: Optional[str] = ""
    publish_date: datetime = Field(default_factory=get_time_now)
    entity_id: Union[UUID, str] = Field(default_factory=uuid4)
    entity_name: str
    publisher_name: str
    event_name: str
    _routing_keys: Optional[dict] = {}

    def __init__(self, **kwargs):
        self._routing_keys = kwargs.pop("routing_keys", {})
        super().__init__(**kwargs)

    @classmethod
    def create(
            cls,
            contains_personal_data: bool = False,
            **kwargs,
    ):
        instance = cls(contains_personal_data=contains_personal_data, **kwargs)
        return instance

    class Config(ModelConfig):
        underscore_attrs_are_private = True

    def add_routing_key(self, name: str, value: str):
        self._routing_keys[name] = value

    def update_routing_keys(self, attrs: dict):
        self._routing_keys.update(attrs)

    def get_routing_keys(self) -> dict:
        return self._routing_keys


class Payload(BaseModel, abc.ABC):
    __expose__ = True

    @classmethod
    def is_exposed(cls) -> bool:
        return cls.__expose__

    @classmethod
    def get_event_name(cls):
        name = camelize(cls.__name__)
        return str(name).replace("Payload", "")

    @classmethod
    def get_entity_name(cls):
        name = decamelize(cls.__name__)
        name = str(name).split("_", maxsplit=1)[0]
        return name

    def get_entity_id(self):
        return getattr(self, "id", uuid4())

    @classmethod
    def create_from_dict(
            cls, event_name: str, payload: dict
    ) -> Type["Payload"]:
        payload_cls = type(
            f"{event_name}Payload",
            (cls,),
            {
                "__annotations__": {k: type(v) for k, v in payload.items()},
            },
        )
        return payload_cls(**payload)

    Config = ModelConfig


class Event(BaseModel):  # pylint: disable=too-few-public-methods
    metadata: EventMeta
    payload: Any

    @classmethod
    def create(
            cls,
            event_name: str,
            publisher_name: str,
            payload: Payload,
            metadata: dict = None,
    ):  # pylint: disable=too-many-arguments

        if isinstance(payload, dict):
            warnings.warn(
                "Raw `dict` events are deprecated and will be erased in future releases please use `Payload` instead",
                DeprecationWarning,
            )
            payload = Payload.create_from_dict(event_name, payload)

        if metadata is None:
            metadata = {}

        metadata.setdefault("entity_name", payload.get_entity_name())
        metadata.setdefault("entity_id", payload.get_entity_id())

        return cls(
            metadata=EventMeta.create(
                event_name=event_name,
                publisher_name=publisher_name,
                **metadata,
            ),
            payload=payload,
        )

    class Config(ModelConfig):
        @staticmethod
        def schema_extra(schema: Dict[str, Any], model: Type["Event"]) -> None:
            schema.update(
                {
                    "z-event-name": model.__name__,
                    "z-publisher": "examplePublisherName",
                }
            )

    @property
    def routing_keys(self) -> dict:
        return {
            "entityName": self.metadata.entity_name,
            "publisherName": self.metadata.publisher_name,
            "eventName": self.metadata.event_name,
            **self.metadata.get_routing_keys(),
        }


class CeleryEvent(Event):
    @property
    def celery_payload(self) -> dict:
        return {
            "id": self.metadata.entity_id,  # pylint: disable=no-member
            "task": self.metadata.event_name,  # pylint: disable=no-member
            "args": [self],
            "kwargs": {},
            "retries": 0,
        }


__all__ = ["Event", "CeleryEvent", "EventMeta", "Payload"]
