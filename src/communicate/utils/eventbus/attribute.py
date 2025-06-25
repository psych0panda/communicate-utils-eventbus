import json
from abc import ABC
from typing import Any

from .exceptions import ApplicationError


class UnsupportedDataType(ApplicationError):
    pass


class ConversionError(ApplicationError):
    pass


class Attribute(ABC):
    data_type = None

    @classmethod
    def convert(cls, value: Any) -> dict:
        data_type = cls.data_type
        data_value = cls._validate(value)
        return {"DataType": data_type, "StringValue": data_value}

    @classmethod
    def _validate(cls, value: Any) -> str:
        return str(value)


class StringAttribute(Attribute):
    data_type = "String"


class NumberAttribute(Attribute):
    data_type = "Number"


class StringArrayAttribute(Attribute):
    data_type = "String.Array"

    @classmethod
    def _validate(cls, value: Any) -> str:
        if not isinstance(value, list):
            raise ConversionError(f"{value} should be a list")
        if any(
                not isinstance(item, (str, int, bool, type(None)))
                for item in value
        ):
            raise ConversionError(
                f"{value} item should be one of types str, int, bool, None"
            )
        return json.dumps(value)


ATTRIBUTE_TYPES: dict = {
    str: StringAttribute,
    int: NumberAttribute,
    list: StringArrayAttribute,
}


def get_attribute_type(value):
    try:
        return ATTRIBUTE_TYPES[type(value)]
    except KeyError as err:
        raise UnsupportedDataType(value) from err
