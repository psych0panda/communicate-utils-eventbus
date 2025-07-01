communicate-utils-eventbus
===========================

.. image:: https://codecov.io/gh/psych0panda/communicate-utils-eventbus/branch/master/graph/badge.svg?token=VKMSLEF4IN 
 :target: https://codecov.io/gh/psych0panda/communicate-utils-eventbus

communicate-utils-eventbus is a utility library for event-driven communication between different parts of your application.

Features
--------

- Simple API for event publishing and subscribing
- Supports synchronous and asynchronous event handling
- Lightweight and easy to integrate
- Built-in support for AWS SNS/SQS messaging
- Automatic event routing and filtering
- Celery task integration

Installation
------------

You can install with dev-mode:

.. code-block:: bash
    python -e path_to_project communicate-utils-eventbus

or use slug:

.. code-block:: bash
    python -e install ["dev"]

Usage Example (Django)
----------------------

Below is a comprehensive example showing the complete flow of event-driven communication:

1. First, define your Django model and event payloads:

.. code-block:: python

    # models.py
    from django.db import models
    from uuid import uuid4
    
    class User(models.Model):
        id = models.UUIDField(primary_key=True, default=uuid4)
        email = models.EmailField()
        is_active = models.BooleanField(default=False)

    # events.py
    from communicate.utils.eventbus import EventPayload, EventFailPayload
    
    class UserRegisteredPayload(EventPayload):
        id: UUID
        email: str
        
        class Config:
            orm_mode = True  # Enable ORM mode for Django model serialization

    class UserRegistrationFailedPayload(EventFailPayload):
        pass

2. Set up the event publisher:

.. code-block:: python

    # publishers.py
    from communicate.utils.eventbus import AmazonSNSPublisher
    
    user_publisher = AmazonSNSPublisher(
        name="UserService",
        config={
            "topic_arn": "arn:aws:sns:us-east-1:000000000000:users",
            "region": "us-east-1",
            "profile": "default",  # AWS credentials profile
        },
    )

3. Create a Celery task to handle user registration:

.. code-block:: python

    # tasks.py
    from celery import shared_task
    from communicate.utils.eventbus.celery.tasks import DjangoCeleryTaskWithCallback
    from .models import User
    from .events import UserRegisteredPayload, UserRegistrationFailedPayload
    
    @shared_task(
        bind=True,
        base=DjangoCeleryTaskWithCallback,
        model=User,
        payload_cls=UserRegisteredPayload,
        exception_payload_cls=UserRegistrationFailedPayload,
        delete_on_failure=False,  # Don't delete user on failure
        delete_on_success=False   # Don't delete user on success
    )
    def register_user_task(task: DjangoCeleryTaskWithCallback, user_id: UUID):
        # Get user instance (handled by DjangoCeleryTaskWithCallback)
        user = task.get_instance(id=user_id)
        
        # Your registration logic here
        user.is_active = True
        user.save()
        
        return user

4. Create a view to handle registration:

.. code-block:: python

    # views.py
    from django.http import JsonResponse
    from .models import User
    from .tasks import register_user_task
    
    def register_user(request):
        # Create user
        user = User.objects.create(
            email=request.POST['email']
        )
        
        # Queue async task
        register_user_task.delay(user_id=user.id)
        
        return JsonResponse({"status": "ok", "user_id": user.id})

5. Set up event subscriber for handling registration events:

.. code-block:: python

    # subscribers.py
    from communicate.utils.eventbus import AmazonSNSSubscriber
    from communicate.utils.eventbus.base import Event
    
    def handle_user_event(event: Event, trace_ctx=None):
        """Handle incoming user events"""
        if event.metadata.event_name == "UserRegistered":
            # Handle successful registration
            print(f"User {event.payload.id} registered successfully!")
        elif event.metadata.event_name == "UserRegistrationFailed":
            # Handle failed registration
            print(f"User registration failed: {event.payload.detail}")
    
    subscriber = AmazonSNSSubscriber(
        connection_url="sqs://aws_access_key_id:aws_secret_access_key@",
        queue_name="user_events",
        hook=handle_user_event,
        region="us-east-1"
    )

6. Run the subscriber worker:

.. code-block:: bash

    # Start Celery worker with SQS consumer
    celery -A your_project worker -Q user_events --consumer=communicate.utils.eventbus.celery.SQSConsumer

Flow Explanation:
----------------

1. When a POST request hits the registration endpoint, a User model instance is created
2. A Celery task is queued with the user's ID
3. The task:
   - Retrieves the user instance
   - Performs registration logic
   - On success: automatically publishes UserRegistered event
   - On failure: automatically publishes UserRegistrationFailed event
4. Events are published to SNS with routing attributes (entityName, publisherName, eventName)
5. SNS forwards events to SQS queue based on subscription filters
6. The Celery worker consumes events from SQS and processes them through the event handler

This setup provides:
- Asynchronous event-driven processing
- Automatic event publishing on task success/failure
- Message routing and filtering via SNS attributes
- Reliable message delivery via SQS
- Error handling and monitoring capabilities
