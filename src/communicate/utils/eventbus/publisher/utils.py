from communicate.utils.eventbus import Event
from communicate.utils.eventbus.attribute import (
    Attribute,
    get_attribute_type,
)
from typing import Any


class AmazonMessageExtender:
    @classmethod
    def resolve(cls, value: Any) -> dict:
        attribute_type: Attribute = get_attribute_type(value)
        return attribute_type.convert(value)

    @classmethod
    def get_msg_attrs(cls, event: Event) -> dict:
        attrs = {}
        for name, value in event.routing_keys.items():
            attrs[name] = cls.resolve(value)
        return attrs
