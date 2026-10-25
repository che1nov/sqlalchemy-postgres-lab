"""Позитивные и негативные сценарии ORM CRUD на PostgreSQL."""
import pytest
from sqlalchemy.exc import IntegrityError

from orm_lab import crud


@pytest.mark.positive
def test_create_and_read_user(db, user_data):
    user = crud.create_user(db, **user_data)
    user_id = user.id
    db.commit()  # Проверяем commit без сохранения данных после teardown фикстуры.
    db.expunge_all()  # Чтение из БД, а не из identity map SQLAlchemy.
    loaded = crud.get_user(db, user_id)
    assert loaded is not None
    assert (loaded.name, loaded.email, loaded.age) == tuple(user_data.values())


@pytest.mark.positive
def test_list_users(db, user, user_data):
    other = crud.create_user(db, **dict(user_data, email="other." + user_data["email"]))
    ids = [row.id for row in crud.list_users(db)]
    assert user.id in ids and other.id in ids
    assert ids == sorted(ids)


@pytest.mark.positive
def test_update_user(db, user, fake):
    user_id = user.id
    changes = {"name": fake.name(), "email": "updated." + user.email, "age": 35}
    assert crud.update_user(db, user_id, **changes).id == user_id
    db.expunge_all()
    loaded = crud.get_user(db, user_id)
    assert (loaded.name, loaded.email, loaded.age) == tuple(changes.values())


@pytest.mark.positive
def test_delete_user(db, user):
    user_id = user.id
    assert crud.delete_user(db, user_id) is True
    db.expunge_all()
    assert crud.get_user(db, user_id) is None


@pytest.mark.positive
def test_create_read_and_list_posts(db, user, post_data):
    user_id = user.id
    post = crud.create_post(db, user_id, **post_data)
    post_id = post.id
    db.expunge_all()
    loaded = crud.get_post(db, post_id)
    assert (loaded.title, loaded.content) == (post_data["title"], post_data["content"])
    assert loaded.user_id == user_id
    assert loaded.is_published is False
    assert [p.id for p in crud.list_posts(db, user_id)] == [post_id]
    assert [p.id for p in crud.get_user(db, user_id).posts] == [post_id]


@pytest.mark.positive
def test_update_post(db, post, fake):
    post_id = post.id
    title, content = fake.sentence(), fake.paragraph()
    crud.update_post(db, post_id, title=title, content=content, is_published=True)
    db.expunge_all()
    loaded = crud.get_post(db, post_id)
    assert (loaded.title, loaded.content, loaded.is_published) == (title, content, True)


@pytest.mark.positive
def test_delete_post_keeps_user(db, post):
    post_id, user_id = post.id, post.user_id
    assert crud.delete_post(db, post_id) is True
    db.expunge_all()
    assert crud.get_post(db, post_id) is None
    assert crud.get_user(db, user_id) is not None


@pytest.mark.positive
@pytest.mark.parametrize("load_posts", [False, True], ids=["database-cascade", "orm-cascade"])
def test_delete_user_cascades_posts(db, post, load_posts):
    user_id, post_id = post.user_id, post.id
    db.expunge_all()
    if load_posts:
        loaded = crud.get_user(db, user_id)
        assert len(loaded.posts) == 1
    crud.delete_user(db, user_id)
    db.expunge_all()
    assert crud.get_user(db, user_id) is None
    assert crud.get_post(db, post_id) is None


@pytest.mark.negative
@pytest.mark.parametrize("field,value,sqlstate", [
    ("age", -1, "23514"),
    ("name", None, "23502"),
    ("email", None, "23502"),
    ("age", None, "23502"),
], ids=["negative-age", "null-name", "null-email", "null-age"])
def test_create_user_rejects_invalid_data(db, user_data, field, value, sqlstate):
    with pytest.raises(IntegrityError) as error:
        with db.begin_nested():
            crud.create_user(db, **dict(user_data, **{field: value}))
    assert error.value.orig.sqlstate == sqlstate
    # SAVEPOINT откатан: та же сессия снова пригодна для корректной операции.
    assert crud.create_user(db, **user_data).id is not None


@pytest.mark.negative
def test_duplicate_email_rejected(db, user, user_data):
    with pytest.raises(IntegrityError) as error:
        with db.begin_nested():
            crud.create_user(db, **user_data)
    assert error.value.orig.sqlstate == "23505"
    assert crud.get_user(db, user.id).email == user_data["email"]


@pytest.mark.negative
def test_update_duplicate_email_rolls_back(db, user, user_data):
    other = crud.create_user(db, **dict(user_data, email="other." + user.email))
    other_id, original_email = other.id, other.email
    with pytest.raises(IntegrityError) as error:
        with db.begin_nested():
            crud.update_user(db, other_id, name=other.name, email=user.email, age=other.age)
    assert error.value.orig.sqlstate == "23505"
    db.expunge_all()
    assert crud.get_user(db, other_id).email == original_email


@pytest.mark.negative
def test_failed_update_rolls_back_whole_scenario(db, user, post_data):
    user_id, original_name, original_age = user.id, user.name, user.age
    with pytest.raises(IntegrityError) as error:
        with db.begin_nested():
            created = crud.create_post(db, user_id, **post_data)
            post_id = created.id
            crud.update_user(db, user_id, name="Не должно сохраниться", email=user.email, age=-1)
    assert error.value.orig.sqlstate == "23514"
    db.expunge_all()
    loaded = crud.get_user(db, user_id)
    assert (loaded.name, loaded.age) == (original_name, original_age)
    assert crud.get_post(db, post_id) is None


@pytest.mark.negative
def test_post_rejects_missing_parent(db, user, post_data):
    user_id = user.id
    crud.delete_user(db, user_id)
    with pytest.raises(IntegrityError) as error:
        with db.begin_nested():
            crud.create_post(db, user_id, **post_data)
    assert error.value.orig.sqlstate == "23503"


@pytest.mark.negative
@pytest.mark.parametrize("field", ["title", "content"])
def test_post_rejects_null_fields(db, user, post_data, field):
    with pytest.raises(IntegrityError) as error:
        with db.begin_nested():
            crud.create_post(db, user.id, **dict(post_data, **{field: None}))
    assert error.value.orig.sqlstate == "23502"


@pytest.mark.negative
def test_missing_user_operations(db, user, user_data):
    user_id = user.id
    crud.delete_user(db, user_id)
    assert crud.get_user(db, user_id) is None
    assert crud.update_user(db, user_id, **user_data) is None
    assert crud.delete_user(db, user_id) is False


@pytest.mark.negative
def test_missing_post_operations(db, post, post_data):
    post_id = post.id
    crud.delete_post(db, post_id)
    assert crud.get_post(db, post_id) is None
    assert crud.update_post(db, post_id, **post_data, is_published=True) is None
    assert crud.delete_post(db, post_id) is False
