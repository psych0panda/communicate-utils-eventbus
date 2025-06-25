import logging

from celery import shared_task

from communicate.utils.format import camelize

logger = logging.getLogger(__package__)


def subscribe(
        *args, name: str = None, bind: bool = False, caller=shared_task, **kwargs
):
    if not callable(caller):
        logger.warning(
            f"Function {caller} is not callable. Falling back to shared_task"
        )
        caller = shared_task

    if kwargs:
        logger.warning("Celery kwargs support is experimental feature")

    def create_shared_task(fun):
        return caller(
            fun, name=name or camelize(fun.__name__), bind=bind, **kwargs
        )

    if len(args) == 1 and callable(args[0]):
        return create_shared_task(args[0])

    return create_shared_task
