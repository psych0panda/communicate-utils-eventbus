from communicate.utils.eventbus import Event
from communicate.utils.eventbus.attribute import (
    Attribute,
    get_attribute_type,
)
from typing import Any


class AmazonMessageExtender:
    """Utility class for converting event routing attributes to Amazon SNS message attributes format.

    This class is responsible for transforming event routing keys into the specific format
    required by Amazon SNS MessageAttributes. This enables several important features:

    1. Message Filtering: Allows filtering messages at the AWS SNS/SQS level without
       deserializing the message body
    2. Message Routing: Enables routing messages to different queues based on attributes
    3. Monitoring & Debugging: Makes message metadata visible in AWS Console
    4. Pub/Sub Patterns: Supports implementing pub/sub with broker-side filtering

    Example:
        # Create an event with routing keys
        event = Event(
            metadata=EventMeta(
                entity_name="User",
                publisher_name="UserService",
                event_name="UserCreated"
            )
        )

        # Convert to SNS message attributes
        message_attrs = AmazonMessageExtender.get_msg_attrs(event)
        # Result:
        # {
        #     "entityName": {"DataType": "String", "StringValue": "User"},
        #     "publisherName": {"DataType": "String", "StringValue": "UserService"},
        #     "eventName": {"DataType": "String", "StringValue": "UserCreated"}
        # }

        # These attributes can then be used in SNS subscription filters like:
        # { "entityName": ["User"], "eventName": ["UserCreated"] }
    """

    @classmethod
    def resolve(cls, value: Any) -> dict:
        attribute_type: Attribute = get_attribute_type(value)
        return attribute_type.convert(value)

    @classmethod
    def get_msg_attrs(cls, event: Event) -> dict:
        """Convert event routing keys to SNS message attributes format.
        
        Args:
            event: The event containing routing keys to convert

        Returns:
            dict: SNS-compatible message attributes dictionary where each value
                 is wrapped in a type descriptor (e.g. {"DataType": "String", "StringValue": value})
        """
        attrs = {}
        for name, value in event.routing_keys.items():
            attrs[name] = cls.resolve(value)
        return attrs
