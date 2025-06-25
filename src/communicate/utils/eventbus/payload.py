import abc
from communicate.utils.eventbus.registry import EventRegistry
from uuid import uuid4

from .base import Payload


class EventPayload(Payload, abc.ABC):
    def __init_subclass__(cls, **kwargs):
        if cls.is_exposed():
            EventRegistry.register(cls)
        super().__init_subclass__(**kwargs)


class EventConsumedPayload(EventPayload, abc.ABC):
    __expose__ = False


class EventFailPayload(EventPayload):
    code: str
    data: dict
    detail: str
    origin: str

    def get_entity_id(self):
        _id = uuid4()
        if isinstance(self.data, Payload):
            _id = self.data.get_entity_id()
        elif isinstance(self.data, dict):
            _id = self.data.get("id", _id)
        else:
            _id = getattr(self.data, "id", _id)
        return _id
