import abc
import celery
import logging
from abc import ABC
from billiard.einfo import ExceptionInfo
from ecosystem.base.exceptions import ApplicationError, EcosystemException
from ecosystem.base.exceptions.convertor.convertors import (
    ExceptionConvertor,
    GenericExceptionConvertor,
)
from ecosystem.communication.eventbus import EventPayload
from ecosystem.communication.eventbus.publisher import AbstractPublisher
from ecosystem.utils.format import camelize
from enum import Enum
from pydantic import ValidationError
from typing import Optional, Type


class TimeStamp(Enum):
    SECOND = 1
    MINUTE = 60
    HOUR = 60 * MINUTE
    DAY = 24 * HOUR
    WEEK = 7 * DAY
    MONTH = 30 * DAY


Model = Type["Model"]


class AbstractCeleryTaskWithCallback(celery.Task, ABC):
    _instance: any = None
    publisher: AbstractPublisher = None
    delete_on_failure: bool = False
    delete_on_success: bool = False
    model: Model

    logger = logging.getLogger("celery")

    @property
    def task_name(self) -> str:
        return camelize(self.__class__.__name__)

    @abc.abstractmethod
    def get_instance(self, **filter_by) -> Model:
        pass

    @abc.abstractmethod
    def delete_instance(self, instance):
        pass

    @abc.abstractmethod
    def get_event_payload(
            self, exc: Exception = None
    ) -> Optional[EventPayload]:
        pass

    def _handle_callbacks(self, exc: Exception = None):
        self._send_event(exc)
        self._clean_db(exc)
        self._clean()

    def _clean(self):
        self._instance = None

    def _send_event(self, exc: Exception):
        payload = self.get_event_payload(exc)
        if isinstance(payload, EventPayload):
            self.publisher.publish(payload.get_event_name(), payload)

    def _clean_db(self, exc: Exception):
        instance = self.get_instance()
        if instance:
            if (exc and self.delete_on_failure) or (
                    not exc and self.delete_on_success
            ):
                self.logger.info(
                    f"Deleting instance {instance.__class__.__name__} {instance}"
                )
                self.delete_instance(instance)
                self.logger.info(
                    f"Instance {instance} was successfully deleted"
                )

    def on_success(self, retval, task_id, args, kwargs):
        self._handle_callbacks()
        super().on_success(retval, task_id, args, kwargs)

    def on_failure(
            self,
            exc: Exception,
            task_id: str,
            args: list,
            kwargs: dict,
            einfo: ExceptionInfo,
    ):
        pk = self._instance.pk if self._instance else "Unknown"

        self.logger.error(
            f"Operation {self.task_name} taskId: {task_id} instance: {self._instance} id: {pk} Failed - {exc}"
        )

        self._handle_callbacks(exc)

        super().on_failure(exc, task_id, args, kwargs, einfo)

    retry_backoff = True
    retry_backoff_max = TimeStamp.HOUR.value
    retry_kwargs = {"max_retries": 15}
    retry_jitter = True
    autoretry_for = ()

    def run(self, *args, **kwargs):
        pass


class ModelCeleryTaskWithCallback(AbstractCeleryTaskWithCallback, ABC):
    """Base Celery Task capable of automatic fail/success events
    sending.

    Attributes:
        payload_cls: used to serialize success event payload.
        exception_payload_cls: used to serialize fail event payload.
        exception_convertor: used to convert an exception raised by
            a celery task to Ecosystem one.
        model: used to get model instance, generate event payload.

    Note:
        It is possible to override generated success event payload,
        by passing custom payload data using `self.task` setter.
    """

    payload_cls: Type[EventPayload]
    payload: Optional[dict] = None
    exception_payload_cls: Type[EventPayload]
    exception_convertor: Type[ExceptionConvertor] = GenericExceptionConvertor
    model: Model

    def get_event_payload(
            self, exc: Optional[Exception] = None
    ) -> EventPayload:
        self._validate_payload_classes()

        if isinstance(exc, Exception):
            payload_getter = self._get_fail_event_payload
        else:
            payload_getter = self._get_success_event_payload

        try:
            payload = payload_getter(exc)
        except ValidationError as err:
            msg = (
                f"failed to serialize payload for event {self.payload_cls.get_event_name()} "
                f"instance {self._instance}: {err}"
            )
            self.logger.error(msg, exc_info=True)
            raise ApplicationError(msg, model=self.model) from err

        return payload

    def _get_success_event_payload(
            self, exc: Optional[Exception]  # pylint: disable=W0613
    ) -> EventPayload:
        if self.payload:
            event_payload = self.payload_cls(**self.payload)
        else:
            event_payload = self.payload_cls.from_orm(self._instance)
        return event_payload

    def _get_id_from_payload(self):
        try:
            success_payload = self._get_success_event_payload(None)
        except ValidationError:
            success_payload = None
        return getattr(success_payload, "id", None)

    def _get_fail_event_payload(
            self, exc: Optional[Exception]
    ) -> EventPayload:

        if not isinstance(exc, EcosystemException):
            exc = self.exception_convertor(exc).convert(ApplicationError)
        extra_payload = exc.data
        extra_payload["id"] = self._get_id_from_payload()

        return self.exception_payload_cls(
            detail=str(exc),
            data=extra_payload,
            code=exc.error_code,
            origin=exc.origin,
        )

    def _validate_payload_classes(self):
        if not self.payload_cls:
            raise TypeError("No payload_cls was passed")

        if not self.exception_payload_cls:
            raise TypeError("No exception_payload_cls was passed")

        if not self.payload_cls.Config.orm_mode:
            raise TypeError(f"{self.payload_cls} not support orm mode")


class DjangoCeleryTaskWithCallback(ModelCeleryTaskWithCallback):
    def get_instance(self, **filter_by) -> Model:
        if filter_by:
            self._instance = (
                self.model.objects.get(  # pylint: disable=no-member
                    **filter_by
                )
            )
        return self._instance

    def delete_instance(self, instance):
        instance.delete()
