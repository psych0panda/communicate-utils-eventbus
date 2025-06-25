import json
import logging
import socket
from communicate.utils.eventbus.base import Event
from kombu import Connection, Consumer, Exchange, Queue
from pydantic import ValidationError

logger = logging.getLogger(__package__)


class AmazonSNSSubscriber:
    """
    Work with kombu>=5.1
    """

    consumer: any
    exchange: any
    queue: any
    conn: any
    channel: any

    def __init__(
            self,
            connection_url: str,
            queue_name: str,
            hook: callable = None,
            region="us-east-2",
    ):
        self.region = region
        self.hook = hook
        self.conn = Connection(
            connection_url,
            heartbeat=10,
            transport_options={"default_region": region},
        )
        self.exchange = Exchange(queue_name, type="direct")
        self.queue = Queue(
            name=queue_name, exchange=self.exchange, routing_key=queue_name
        )
        self.consumer = Consumer(
            self.conn,
            queues=self.queue,
            callbacks=[
                self.process_message,
            ],
            accept=["text/plain"],
        )

    def process_message(self, body, message):
        try:
            msg = json.loads(body)["Message"]
            event = Event.parse_raw(msg)
        except (ValidationError, KeyError) as err:
            logger.warning(f"Remove Unknown message {message} {err}")
            message.ack()
            return

        dict_meta = event.metadata.dict()
        trace_ctx = None
        if callable(self.hook):
            self.hook(event, trace_ctx=trace_ctx)
        message.ack()

    def establish_connection(self):
        revived_connection = self.conn.clone()
        revived_connection.ensure_connection(max_retries=3)
        self.channel = revived_connection.channel()
        self.consumer.revive(self.channel)
        self.consumer.consume()
        return revived_connection

    def consume(self):
        new_conn = self.establish_connection()
        while True:
            self.get_one(conn=new_conn, timeout=20)

    def get_one(self, conn=None, timeout=20):
        conn = conn or self.establish_connection()
        try:
            conn.drain_events(timeout=timeout)
        except socket.timeout as err:
            logger.warning(f"timeout: {err}")
            conn.heartbeat_check()

    def run(self):
        while True:
            try:
                logger.info("Starting worker:")
                self.consume()
            except self.conn.connection_errors:
                logger.info("Connection revived")
