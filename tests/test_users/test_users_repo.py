from app.users.repository import UserRepository


def test_create_user(db_session):
    repo = UserRepository(db_session)
    user = repo.create(
        username="repo_user",
        email="repo@example.com",
        hashed_password="hashed_password",
        role="player",
    )
    assert user.id is not None
    assert user.email == "repo@example.com"

def test_get_user_by_email(db_session, test_user):
    repo = UserRepository(db_session)
    user = repo.get_by_email(test_user.email)
    assert user is not None
    assert user.email == test_user.email

def test_update_user(db_session, test_user):
    repo = UserRepository(db_session)
    user = repo.update(test_user, {"username": "updated_user"})
    assert user.username == "updated_user"


def test_delete_user(db_session, test_user):
    repo = UserRepository(db_session)
    repo.delete(test_user)
    assert repo.get_by_email(test_user.email) is None