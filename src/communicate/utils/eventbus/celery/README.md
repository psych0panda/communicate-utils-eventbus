# EventBus - Celery integration

### Create tasks with the help of a `subscribe` decorator

```python
    from ecosystem.communication.eventbus.celery import subscribe

    @subscribe(bind=True, name="SomeTrickyName")
    def test(cls, *args, **kwargs):
        print(f"TASK EXECUTION =>>>>>>>>>>>>>>>>>> {cls} {args}, {kwargs}")
    

    @subscribe
    def test_some_task(cls, *args, **kwargs):
        print(f"TASK EXECUTION =>>>>>>>>>>>>>>>>>> {cls} {args}, {kwargs}")
    
```

### Create celery task with events handling callbacks

The package provides custom base celery class. The class provides a level of abstraction that eases success/fail events
handling.

```python
from uuid import UUID
from celery import shared_task

from django.db import models

from ecosystem.communication.eventbus.payload import EventPayload, EventFailPayload
from ecosystem.communication.eventbus.celery.tasks import DjangoCeleryTaskWithCallback


class Entity(models.Model):
    id = models.UUIDField()

    def do_action(self):
        pass
    
class ActionHappenedPayload(EventPayload):
    id: UUID
    
    class Config:
        orm_mode = True


class ActionHappeningFailedPayload(EventFailPayload):
    pass

@shared_task(
    bind=True,
    base=DjangoCeleryTaskWithCallback,
    model=Entity,
    payload_cls=ActionHappenedPayload,
    exception_payload_cls=ActionHappeningFailedPayload,
    delete_on_failure=True,
    delete_on_success=False
)
def do_entity_action(task: DjangoCeleryTaskWithCallback, entity_id: UUID):
    entity: Entity = task.get_instance(id=entity_id)
    entity.do_action()


do_entity_action.delay(entity_id="some_uuid")
```

Let's break down what's going on.

1. We define event payloads for success and fail flow. The payloads must inherit from
   `EventPayload` and `EventFailPayload` respectively.
2. A celery task with custom base class `DjangoCeleryTaskWithCallback` is defined.
   Success and fail events are passed as `payload_cls` and `exception_payload_cls` arguments to `shared_task` decorator.
   The flags `delete_on_failure` and `delete_on_success` define callbacks behavior.
   If `delete_on_success`/`delete_on_failure` is set
   the corresponding action will be applied to model instance on task completion.
3. After `do_entity_action.delay(entity_id="some_uuid")` is completed, a `actionHappened`/`actionHappeningFailed`
   payload will be emitted depending on the task result.

### Update Celery Consumer for a specific worker depending on env or mss configuration

```python
    app = Celery("core")
    app.conf.CELERYD_CONSUMER = "ecosystem.communication.eventbus.celery.SQSConsumer"
```

### Run worker with predefined queue

```bash
    celery -A mss_name worker -Q queue_name
```

### Test with the help of AWS CLI

#### Bootstrap env:

- Ensure yore already run `localstack` with `docker-compose -f docker-compose.deps.yaml up -d`

- Executing SNS

```bash
    aws sns create-topic --name local_sns --endpoint-url=http://localhost:4566;
```

- Executing SQS

```bash
    aws sqs create-queue --endpoint-url=http://localhost:4566 --queue-name queue_name;
    aws sqs create-queue --endpoint-url=http://localhost:4566 --queue-name production__myservice__queue;
```

- Subscribing to SNS to SQS

```bash
    aws --endpoint-url=http://localhost:4566 sns subscribe --topic-arn arn:aws:sns:eu-west-2:000000000000:local_sns --protocol sqs --notification-endpoint http://localhost:4566/queue/queue_name;
```

- Publish Events:

```bash
    aws --endpoint-url=http://localhost:4566 sns publish --topic-arn arn:aws:sns:eu-west-2:000000000000:local_sns --message '{"metadata": {"containsPersonalData": false, "tracestate": "", "traceparent": "00-00000000000000000000000000000000-0000000000000000-01", "errorOrigin": "", "errorCode": "", "authorization": "", "publishDate": "2021-03-17T16:24:23.792955", "entityId": "44f33071-e444-494f-bcff-b5e3594f7628", "publisherName": "TestPublisher", "eventName": "doGood"}, "payload": {"foo": "bar"}}'
    aws --endpoint-url=http://localhost:4566 sns publish --topic-arn arn:aws:sns:eu-west-2:000000000000:local_sns --message '{"metadata": {"containsPersonalData": true, "tracestate": "", "traceparent": "00-00000000000000000000000000000000-0000000000000000-01", "errorOrigin": "", "errorCode": "", "authorization": "", "publishDate": "2021-03-17T16:23:21.214293", "entityId": "4123a425-e234-491-bcdf-b5as59cz7611", "publisherName": "TestPublisher", "eventName": "doNice"}, "payload": {"foo": "bar"}}'
```