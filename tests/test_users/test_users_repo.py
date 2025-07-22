import pytest
from app.users.repository import UserRepository
from datetime import datetime


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


def test_update_otp_secret(db_session, test_user):
    repo = UserRepository(db_session)
    updated_user = repo.update_otp_secret(test_user, "new_otp_secret")
    assert updated_user.otp_secret == "new_otp_secret"


def test_enable_2fa(db_session, test_user):
    repo = UserRepository(db_session)
    updated_user = repo.enable_2fa(test_user)
    assert updated_user.is_2fa_enabled is True


def test_update_last_login(db_session, test_user):
    repo = UserRepository(db_session)
    old_login = test_user.last_login
    updated_user = repo.update_last_login(test_user)
    assert updated_user.last_login is not None
    assert isinstance(updated_user.last_login, datetime)
    if old_login:
        assert updated_user.last_login > old_login


def test_setup_2fa(db_session, test_user):
    repo = UserRepository(db_session)
    updated_user = repo.setup_2fa(test_user, "setup_secret")
    assert updated_user.otp_secret == "setup_secret"


def test_complete_2fa_setup(db_session, test_user):
    repo = UserRepository(db_session)
    updated_user = repo.complete_2fa_setup(test_user)
    assert updated_user.is_2fa_enabled is True
    assert isinstance(updated_user.last_login, datetime)
