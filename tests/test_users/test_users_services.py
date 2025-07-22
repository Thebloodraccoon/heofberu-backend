
import pytest

from app.exceptions.user_exceptions import (
    UserEmailAlreadyExistsException,
    UserNameAlreadyExistsException,
    UserNotFoundException,
)
from app.users.schemas import UserCreate, UserUpdate
from app.users.services import UserService


def test_create_user_success(db_session):
    service = UserService(db_session)
    data = UserCreate(
        username="new_user",
        email="new_user@example.com",
        password="securepassword",
        role="player",
    )
    user = service.create_user(data)
    assert user.username == "new_user"
    assert user.email == "new_user@example.com"


def test_create_user_duplicate_email(db_session, test_user):
    service = UserService(db_session)
    data = UserCreate(
        username="another_user",
        email=test_user.email,
        password="12345678",
        role="player",
    )
    with pytest.raises(UserEmailAlreadyExistsException):
        service.create_user(data)


def test_create_user_duplicate_username(db_session, test_user):
    service = UserService(db_session)
    data = UserCreate(
        username=test_user.username,
        email="unique@example.com",
        password="12345678",
        role="player",
    )
    with pytest.raises(UserNameAlreadyExistsException):
        service.create_user(data)


def test_get_user_by_id_success(db_session, test_user):
    service = UserService(db_session)
    user = service.get_user_by_id(test_user.id)
    assert user.email == test_user.email


def test_get_user_by_id_not_found(db_session):
    service = UserService(db_session)
    with pytest.raises(UserNotFoundException):
        service.get_user_by_id(99999)


def test_get_user_by_email_success(db_session, test_user):
    service = UserService(db_session)
    user = service.get_user_by_email(test_user.email)
    assert user.username == test_user.username


def test_get_user_by_email_not_found(db_session):
    service = UserService(db_session)
    with pytest.raises(UserNotFoundException):
        service.get_user_by_email("missing@example.com")


def test_get_all_users(db_session, test_user):
    service = UserService(db_session)
    users = service.get_all_users(page=0, size=10)
    assert isinstance(users, list)
    assert any(u.email == test_user.email for u in users)


def test_update_user_success(db_session, test_user):
    service = UserService(db_session)
    data = UserUpdate(username="updated_username")
    updated = service.update_user(test_user.id, data)
    assert updated.username == "updated_username"


def test_update_user_not_found(db_session):
    service = UserService(db_session)
    data = UserUpdate(username="ghost")
    with pytest.raises(UserNotFoundException):
        service.update_user(99999, data)


def test_update_user_conflict_email(db_session, test_user, test_admin):
    service = UserService(db_session)
    data = UserUpdate(email=test_admin.email)
    with pytest.raises(UserEmailAlreadyExistsException):
        service.update_user(test_user.id, data)


def test_update_user_conflict_username(db_session, test_user, test_admin):
    service = UserService(db_session)
    data = UserUpdate(username=test_admin.username)
    with pytest.raises(UserNameAlreadyExistsException):
        service.update_user(test_user.id, data)


def test_delete_user_success(db_session, test_user):
    service = UserService(db_session)
    result = service.delete_user(test_user.id)
    assert result is True


def test_delete_user_not_found(db_session):
    service = UserService(db_session)
    with pytest.raises(UserNotFoundException):
        service.delete_user(99999)
