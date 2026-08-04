"""Simple retry decorator for flaky endpoints (e.g. async processing, eventual consistency)."""
import time
from functools import wraps
from typing import Callable, Type

from src.utils.logger import get_logger

logger = get_logger(__name__)


def retry(times: int = 3, delay_seconds: float = 1.0, exceptions: tuple[Type[Exception], ...] = (AssertionError,)):
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exc = None
            for attempt in range(1, times + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as exc:
                    last_exc = exc
                    logger.warning(
                        "Attempt %s/%s failed for %s: %s", attempt, times, func.__name__, exc
                    )
                    if attempt < times:
                        time.sleep(delay_seconds)
            raise last_exc

        return wrapper

    return decorator
