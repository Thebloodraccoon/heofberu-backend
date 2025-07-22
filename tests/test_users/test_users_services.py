from app.users.repository import UserRepository
from app.users.services import UserService


def test_register_user(db_session):
    service = UserService(UserRepository(db_session))
    user = service.register_user(
        username="service_user",
        email="service@example.com",
        password="password",
        role="player",
    )
    assert user.email == "service@example.com"


def test_get_user(db_session, test_user):
    service = UserService(UserRepository(db_session))
    fetched = service.get_user(user_id=test_user.id)
    assert fetched.email == test_user.email


def test_update_user_service(db_session, test_user):
    service = UserService(UserRepository(db_session))
    updated = service.update_user(user_id=test_user.id, user_data={"username": "updated"})
    assert updated.username == "updated"


def test_delete_user_service(db_session, test_user):
    service = UserService(UserRepository(db_session))
    service.delete_user(user_id=test_user.id)
    assert service.get_user(user_id=test_user.id) is None