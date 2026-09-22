from sqlalchemy.exc import OperationalError

from app.infrastructure.database.retry import (
    is_retryable_mysql_transaction_error,
    retry_mysql_transaction,
)


class MySQLError(Exception):
    pass


def operational_error(code: int) -> OperationalError:
    return OperationalError("statement", {}, MySQLError(code, "database error"))


def test_recognizes_only_mysql_transient_transaction_errors():
    assert is_retryable_mysql_transaction_error(operational_error(1213))
    assert is_retryable_mysql_transaction_error(operational_error(1205))
    assert not is_retryable_mysql_transaction_error(operational_error(1062))
    assert not is_retryable_mysql_transaction_error(ValueError("not a database error"))


def test_retry_boundary_retries_deadlock_but_not_other_errors():
    attempts = 0

    @retry_mysql_transaction(attempts=3, base_delay_seconds=0)
    def succeeds_on_retry():
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise operational_error(1213)
        return "ok"

    assert succeeds_on_retry() == "ok"
    assert attempts == 3
