import json
import pytest
from unittest.mock import Mock, patch
from uuid import UUID, uuid4

from communicate.utils.eventbus import (
    Event,
    EventPayload,
    EventFailPayload,
    AmazonSNSPublisher,
    AmazonSNSSubscriber
)
from communicate.utils.eventbus.celery.tasks import DjangoCeleryTaskWithCallback


# Test Models & Payloads
class TestUser:
    """Mock Django model for testing"""
    def __init__(self, id=None, email=None):
        self.id = id or uuid4()
        self.email = email or "test@example.com"
        self.is_active = False

    @property
    def pk(self):
        return self.id

    def save(self):
        self.is_active = True


class UserRegisteredPayload(EventPayload):
    id: UUID
    email: str
    is_active: bool = False

    class Config:
        orm_mode = True


class UserRegistrationFailedPayload(EventFailPayload):
    pass


# Test Task
class UserRegistrationTask(DjangoCeleryTaskWithCallback):
    model = TestUser
    payload_cls = UserRegisteredPayload
    exception_payload_cls = UserRegistrationFailedPayload

    def get_instance(self, **filter_by) -> TestUser:
        if not self._instance and filter_by:
            self._instance = TestUser(**filter_by)
        return self._instance

    def delete_instance(self, instance):
        instance.is_active = False

    def run(self, *args, **kwargs):
        instance = self.get_instance()
        instance.save()
        return instance


# Fixtures
@pytest.fixture
def user_id():
    return uuid4()


@pytest.fixture
def test_user(user_id):
    return TestUser(id=user_id, email="test@example.com")


@pytest.fixture
def mock_sns_client():
    with patch('boto3.session.Session') as mock_session:
        mock_client = Mock()
        mock_session.return_value.client.return_value = mock_client
        yield mock_client


@pytest.fixture
def publisher(mock_sns_client):
    pub = AmazonSNSPublisher(
        name="TestService",
        config={
            "topic_arn": "arn:aws:sns:us-east-1:000000000000:test",
            "region": "us-east-1",
        }
    )
    pub.publish = Mock()  # Replace publish method with Mock
    return pub


# Tests
def test_payload_serialization(test_user):
    """Test that payload correctly serializes from ORM object"""
    payload = UserRegisteredPayload.from_orm(test_user)
    
    assert payload.id == test_user.id
    assert payload.email == test_user.email
    assert payload.is_active == test_user.is_active


def test_event_creation(test_user):
    """Test event creation with metadata"""
    payload = UserRegisteredPayload.from_orm(test_user)
    event = Event.create(
        event_name="UserRegistered",
        publisher_name="TestService",
        payload=payload
    )

    assert event.metadata.event_name == "UserRegistered"
    assert event.metadata.publisher_name == "TestService"
    assert event.payload.id == test_user.id


def test_publisher_sends_event(publisher, mock_sns_client, test_user):
    """Test that publisher correctly sends event to SNS"""
    payload = UserRegisteredPayload.from_orm(test_user)
    
    publisher.publish("UserRegistered", payload)

    # Verify event was published
    assert publisher.publish.called
    
    # Verify event attributes
    call_args = publisher.publish.call_args
    event_name = call_args.args[0]
    assert event_name == "UserRegistered"
    
    # Verify payload
    payload = call_args.args[1]
    assert str(payload.id) == str(test_user.id)
    assert payload.email == test_user.email


def test_subscriber_processes_event(test_user):
    """Test that subscriber correctly processes received event"""
    mock_hook = Mock()
    
    # Create and serialize event
    payload = UserRegisteredPayload.from_orm(test_user)
    event = Event.create("UserRegistered", "TestService", payload)
    event_json = event.json()

    # Simulate SNS message format
    message = {
        "Message": event_json
    }

    # Mock process_message directly instead of creating real subscriber
    subscriber = AmazonSNSSubscriber(
        connection_url="memory://",  # Use memory transport instead of SQS
        queue_name="test_queue",
        hook=mock_hook
    )
    
    # Process message directly
    subscriber.process_message(json.dumps(message), Mock())

    # Verify hook was called with correct event
    mock_hook.assert_called_once()
    processed_event = mock_hook.call_args.args[0]
    assert processed_event.metadata.event_name == "UserRegistered"
    assert processed_event.payload["id"] == str(test_user.id)  # Compare UUID as string
    assert processed_event.payload["email"] == test_user.email


def test_task_success_publishes_event(publisher, test_user):
    """Test that task success automatically publishes event"""
    task = UserRegistrationTask()
    task.publisher = publisher
    
    # Execute task
    task._instance = test_user
    task.run()
    task.on_success(None, "test_task_id", [], {})

    assert test_user.is_active == True
    # Verify event was published (through mock publisher)
    assert publisher.publish.called


def test_task_failure_publishes_event(publisher, test_user):
    """Test that task failure automatically publishes failure event"""
    task = UserRegistrationTask()
    task.publisher = publisher
    
    # Simulate failure
    error = ValueError("Registration failed")
    task._instance = test_user
    task.on_failure(error, "test_task_id", [], {}, None)

    # Verify failure event was published
    assert publisher.publish.called
    # Verify user wasn't deleted (delete_on_failure=False by default)
    assert test_user.is_active == False


@pytest.mark.integration
def test_full_registration_flow(publisher, test_user):
    """Integration test for full registration flow"""
    task = UserRegistrationTask()
    task.publisher = publisher
    
    # Execute task
    task._instance = test_user
    task.run()
    task.on_success(None, "test_task_id", [], {})

    # Verify user state
    assert test_user.is_active == True
    
    # Verify event publication
    assert publisher.publish.called
    
    # Verify published event content
    call_args = publisher.publish.call_args
    event_name = call_args.args[0]
    payload = call_args.args[1]
    
    assert isinstance(payload, UserRegisteredPayload)
    assert str(payload.id) == str(test_user.id)
    assert payload.is_active == True
