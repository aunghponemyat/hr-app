import pytest

from tests.database import validate_test_database_url


@pytest.mark.parametrize(
    "test_url",
    [
        "mysql+pymysql://user:pass@localhost:3306/hr_app",
        "mysql+pymysql://user:pass@localhost:3306/hr_app_test",
        "mysql+pymysql://user:pass@127.0.0.1:3306/hr_app_test",
    ],
)
def test_fixture_refuses_unsafe_database(test_url: str) -> None:
    with pytest.raises(ValueError):
        validate_test_database_url(test_url, "mysql+pymysql://user:pass@localhost:3306/hr_app_test")


def test_separate_test_database_allowed() -> None:
    validate_test_database_url(
        "mysql+pymysql://hr_test:pass@localhost:3307/hr_app_test",
        "mysql+pymysql://hr_user:pass@localhost:3306/hr_app",
    )
