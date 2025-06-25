from datetime import datetime, timezone


def get_time_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)
