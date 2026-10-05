"""Database opt-in validation does not require a live MySQL connection."""

import pytest

from test_mysql_integration import validate_test_database


@pytest.mark.parametrize(
    ("url", "confirmation"),
    [
        ("mysql+pymysql://localhost/relayvia_test", None),
        ("mysql+pymysql://localhost/relayvia", "relayvia"),
    ],
)
def test_accepts_disposable_or_explicitly_confirmed_database(url, confirmation):
    assert validate_test_database(url, confirmation).database


@pytest.mark.parametrize(
    ("url", "confirmation"),
    [
        ("mysql+pymysql://localhost/relayvia", None),
        ("mysql+pymysql://localhost/relayvia", "different"),
        ("mysql+pymysql://localhost/relayvia_test", "different"),
        ("mysql+pymysql://localhost", None),
        ("sqlite:///relayvia_test", None),
    ],
)
def test_rejects_unconfirmed_or_mismatched_database(url, confirmation):
    with pytest.raises(ValueError):
        validate_test_database(url, confirmation)
