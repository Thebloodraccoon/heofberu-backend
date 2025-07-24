from datetime import datetime

import pytest

from app.users.repository import UserRepository


def test_get_by_email(db_session, test_user):
    repo = UserRepository(db_session)
    user = repo.get_by_email(test_user.email)
    assert user is not None
    assert user.email == test_user.email


def test_get_by_username(db_session, test_user):
    repo = UserRepository(db_session)
    user = repo.get_by_username(test_user.username)
    assert user is not None
    assert user.username == test_user.username


@pytest.mark.parametrize(
    "method,secret",
    [
        ("update_otp_secret", "new_otp_secret"),
        ("setup_2fa", "setup_secret"),
    ],
)
def test_update_or_setup_otp_secret(db_session, test_user, method, secret):
    repo = UserRepository(db_session)
    func = getattr(repo, method)
    updated_user = func(test_user, secret)
    assert updated_user.otp_secret == secret


@pytest.mark.parametrize(
    "method,check_last_login",
    [
        ("enable_2fa", False),
        ("complete_2fa_setup", True),
    ],
)
def test_2fa_methods(db_session, test_user, method, check_last_login):
    repo = UserRepository(db_session)
    func = getattr(repo, method)
    updated_user = func(test_user)
    assert updated_user.is_2fa_enabled is True
    if check_last_login:
        assert isinstance(updated_user.last_login, datetime)


def test_update_last_login(db_session, test_user):
    repo = UserRepository(db_session)
    old_login = test_user.last_login
    updated_user = repo.update_last_login(test_user)
    assert updated_user.last_login is not None
    assert isinstance(updated_user.last_login, datetime)
    if old_login:
        assert updated_user.last_login > old_login
