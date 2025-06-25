import logging
from typing import Any, Callable, Dict, List

from .base import Event
from .exceptions import ApplicationError

logging = logging.getLogger(__package__)


class HookRegistry:
    _pre_hooks: Dict[Any, List[Callable[[Event], Event]]]
    _post_hooks: Dict[Any, List[Callable[[Event], Event]]]

    class HookError(ApplicationError):
        pass

    def __init__(self):
        self._pre_hooks = {}
        self._post_hooks = {}

    def register(self, event_slug: str, hook: Callable, post: bool = False):
        if post:
            self.register_post(event_slug, hook)
        else:
            self.register_pre(event_slug, hook)

    def register_post(self, event_slug: str, hook: Callable):
        if event_slug not in self._post_hooks:
            self._post_hooks[event_slug] = []
        self._post_hooks[event_slug].append(hook)

    def register_pre(self, event_slug: str, hook: Callable):
        if event_slug not in self._pre_hooks:
            self._pre_hooks[event_slug] = []
        self._pre_hooks[event_slug].append(hook)

    def unregister(self, event_slug: str, hook: Callable):
        if event_slug in self._pre_hooks:
            self._pre_hooks[event_slug].remove(hook)
            if len(self._pre_hooks[event_slug]) == 0:
                del self._pre_hooks[event_slug]

        if event_slug in self._post_hooks:
            self._post_hooks[event_slug].remove(hook)
            if len(self._post_hooks[event_slug]) == 0:
                del self._post_hooks[event_slug]

    def unregister_all(self, event_slug: str):
        if event_slug in self._pre_hooks:
            del self._pre_hooks[event_slug]
        if event_slug in self._post_hooks:
            del self._post_hooks[event_slug]

    def unregister_all_events(self):
        self._pre_hooks = {}
        self._post_hooks = {}

    @staticmethod
    def get_event_slug(event: Event) -> Any:
        return event.metadata.event_name

    def run_hooks(self, event: Event, hooks: []) -> Event:
        event_slug = self.get_event_slug(event)
        if event_slug not in hooks:
            return event
        for hook in hooks[event_slug]:
            event = self.run_hook(event, hook)
        return event

    def run_hook(self, event: Event, hook: Callable) -> Event:
        try:
            event = hook(event)
        except self.HookError:
            raise
        except Exception as err:  # noqa, pylint: disable=broad-except
            logging.getLogger(__package__).exception(
                f"Hook {hook} failed: {err}"
            )
        return event

    def run_pre_hooks(self, event: Event) -> Event:
        return self.run_hooks(event, self._pre_hooks)

    def run_post_hooks(self, event: Event) -> Event:
        return self.run_hooks(event, self._post_hooks)

    __call__ = run_hooks


default_registry = HookRegistry()

registries = {
    "default": default_registry,
}


def get_default_registry() -> HookRegistry:
    return default_registry


def get_registry(name: str = "default") -> HookRegistry:
    if name not in registries:
        registries[name] = HookRegistry()
    return registries[name]


def register_event(event: Event, registry: HookRegistry = None):
    if not registry:
        registry = get_default_registry()

    def register_decorator(func: Callable) -> Callable:
        def wrapper(self, *args, **kwargs):
            registry.register(event, func)
            return func(self, *args, **kwargs)

        return wrapper

    return register_decorator
