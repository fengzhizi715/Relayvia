"""Small, explicit retry boundary for transient MySQL transaction failures."""

from __future__ import annotations

import asyncio
from functools import wraps
import time
from typing import Callable, TypeVar

from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session


T = TypeVar("T")
MYSQL_TRANSIENT_TRANSACTION_CODES = frozenset({1205, 1213})


def _rollback_sessions(args, kwargs) -> None:
    for value in (*args, *kwargs.values()):
        if isinstance(value, Session):
            value.rollback()


def is_retryable_mysql_transaction_error(exc: BaseException) -> bool:
    if not isinstance(exc, OperationalError):
        return False
    args = getattr(exc.orig, "args", ())
    return bool(args) and args[0] in MYSQL_TRANSIENT_TRANSACTION_CODES


def retry_mysql_transaction(*, attempts: int = 3, base_delay_seconds: float = 0.02):
    """Retry one database transaction after an InnoDB deadlock/lock timeout.

    Callers must keep all non-database side effects outside the decorated
    function. Each queue backend method opens a fresh Session per attempt.
    """

    def decorator(operation: Callable[..., T]) -> Callable[..., T]:
        @wraps(operation)
        def wrapped(*args, **kwargs):
            for attempt in range(attempts):
                try:
                    return operation(*args, **kwargs)
                except OperationalError as exc:
                    if not is_retryable_mysql_transaction_error(exc) or attempt + 1 >= attempts:
                        raise
                    _rollback_sessions(args, kwargs)
                    time.sleep(base_delay_seconds * (2**attempt))
            raise AssertionError("unreachable")

        return wrapped

    return decorator


def retry_mysql_transaction_async(*, attempts: int = 3, base_delay_seconds: float = 0.02):
    def decorator(operation):
        @wraps(operation)
        async def wrapped(*args, **kwargs):
            for attempt in range(attempts):
                try:
                    return await operation(*args, **kwargs)
                except OperationalError as exc:
                    if not is_retryable_mysql_transaction_error(exc) or attempt + 1 >= attempts:
                        raise
                    _rollback_sessions(args, kwargs)
                    await asyncio.sleep(base_delay_seconds * (2**attempt))
            raise AssertionError("unreachable")

        return wrapped

    return decorator
