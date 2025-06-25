import json
import logging
from celery.exceptions import InvalidTaskError
from celery.worker.consumer import Consumer as CeleryConsumer
from communicate.utils.eventbus import CeleryEvent
from kombu.exceptions import ContentDisallowed, DecodeError
from kombu.message import Message
from pydantic import ValidationError
from vine import promise as vine_promise

logger = logging.getLogger(__package__)


class SQSConsumer(CeleryConsumer):  # pylint: disable=too-few-public-methods

    callbacks = None

    def on_unknown_task(
            self, body, message, exc
    ):  # pylint: disable=unused-argument
        logger.info(  # pylint: disable=logging-too-many-args
            "Received unknown event %s. Acknowledging...", exc
        )
        message.ack()

    def create_task_handler(self, promise=vine_promise):
        strategies = self.strategies
        on_unknown_message = self.on_unknown_message
        on_unknown_task = self.on_unknown_task
        on_invalid_task = self.on_invalid_task
        callbacks = self.on_task_message
        call_soon = self.call_soon

        def on_task_received(  # pylint: disable=inconsistent-return-statements
                message: Message,
        ):
            try:
                body = message.decode()
                data = json.loads(body)
                payload = data["Message"]
            except Exception as exc:  # pylint: disable=broad-except
                return self.on_decode_error(message, exc)

            try:
                event = CeleryEvent.parse_raw(payload)
                message._decoded_cache = (  # pylint: disable=protected-access
                    event.celery_payload
                )
                message.body = payload
                message.headers = event.metadata.dict()
            except ValidationError:
                return on_unknown_message(payload, message)

            try:
                strategy = strategies[event.metadata.event_name]
            except KeyError as exc:
                return on_unknown_task(None, message, exc)

            try:
                strategy(
                    message,
                    event.celery_payload,
                    promise(call_soon, (message.ack_log_error,)),
                    promise(call_soon, (message.reject_log_error,)),
                    callbacks,
                )
            except (InvalidTaskError, ContentDisallowed) as exc:
                return on_invalid_task(event.celery_payload, message, exc)
            except DecodeError as exc:
                return self.on_decode_error(message, exc)

        return on_task_received
