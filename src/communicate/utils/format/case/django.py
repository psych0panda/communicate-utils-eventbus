import re
from collections import OrderedDict
from django.utils.encoding import force_str
from django.utils.functional import Promise
from djangorestframework_camel_case.util import (
    camelize_re,
    is_iterable,
    underscore_to_camel,
)
from rest_framework.utils.serializer_helpers import ReturnDict
from typing import Dict, Iterable, Type, Union


def camelize_object(
        data: Union[Type[Promise], Dict, Iterable, str], **options
):
    # Handle lazy translated strings.
    ignore_fields = options.get("ignore_fields") or ()
    if isinstance(data, Promise):
        data = force_str(data)
    if isinstance(data, dict):
        if isinstance(data, ReturnDict):
            new_dict = ReturnDict(serializer=data.serializer)
        else:
            new_dict = OrderedDict()
        for key, value in data.items():
            if isinstance(key, Promise):
                key = force_str(key)
            if isinstance(key, str) and "_" in key:
                new_key = re.sub(camelize_re, underscore_to_camel, key)
            else:
                new_key = key
            if key not in ignore_fields and new_key not in ignore_fields:
                new_dict[new_key] = camelize_object(value, **options)
            else:
                new_dict[key] = value
        return new_dict
    if is_iterable(data) and not isinstance(data, str):
        return [camelize_object(item, **options) for item in data]
    return data
