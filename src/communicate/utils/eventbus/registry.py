import json
from collections import OrderedDict
from communicate.utils.eventbus import Event
from pydantic.schema import schema

config = {}
app_name = "CommonEvents"
app_version = "0.0.1a"
_schema = "http://json-schema.org/draft-04/schema#"


class EventRegistry:
    _registry = OrderedDict()
    _instance = None
    ref_prefix = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super().__new__(cls, *args, **kwargs)
        return cls._instance

    @classmethod
    def register(cls, payload, name: str = None):
        name = name or payload.get_event_name()
        cls._registry[name] = cls._build_event(payload, name)

    @classmethod
    def _build_event(cls, payload, name) -> type:
        _bootstrap = {
            "__annotations__": {"payload": payload},
        }
        event = type(name, (Event,), _bootstrap)
        return event

    @staticmethod
    def construct_id(name: str, version: str):
        return f"Events.{name}.{version}"

    def generate_schema(
            self,
            service_name: str = app_name,
            version: str = app_version,
            **kwargs,
    ):
        kwargs.setdefault(
            "title", f"Events for {service_name} service, version of {version}"
        )
        schema_ = schema(
            self.events_list(),
            ref_prefix=self.ref_prefix,
            by_alias=True,
            **kwargs,
        )
        schema_["id"] = self.construct_id(service_name, version)
        schema_["$schema"] = _schema
        return schema_

    def generate_json_schema(
            self,
            indent=None,
            service_name: str = app_name,
            version: str = app_version,
            **kwargs,
    ):
        return json.dumps(
            self.generate_schema(service_name, version, **kwargs),
            indent=indent,
        )

    def events_list(self):
        return list(self._registry.values())

    def get_event_by_name(self, name) -> Event:
        return self._registry.get(name)
