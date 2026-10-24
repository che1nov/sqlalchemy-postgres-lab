"""ORM CRUD. Транзакцией управляет вызывающий код через Session.begin()."""
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from orm_lab.models import Post, User


def create_user(session: Session, name: str, email: str, age: int) -> User:
    user = User(name=name, email=email, age=age)
    session.add(user)
    session.flush()
    return user


def get_user(session: Session, user_id: int) -> Optional[User]:
    return session.scalar(
        select(User).where(User.id == user_id).options(selectinload(User.posts))
    )


def list_users(session: Session) -> List[User]:
    return list(session.scalars(select(User).options(selectinload(User.posts)).order_by(User.id)))


def update_user(session: Session, user_id: int, *, name: str, email: str, age: int) -> Optional[User]:
    user = session.get(User, user_id)
    if user is None:
        return None
    user.name, user.email, user.age = name, email, age
    session.flush()
    return user


def delete_user(session: Session, user_id: int) -> bool:
    user = session.get(User, user_id)
    if user is None:
        return False
    session.delete(user)
    session.flush()
    return True


def create_post(session: Session, user_id: int, title: str, content: str) -> Post:
    post = Post(user_id=user_id, title=title, content=content)
    session.add(post)
    session.flush()
    return post


def get_post(session: Session, post_id: int) -> Optional[Post]:
    return session.get(Post, post_id)


def list_posts(session: Session, user_id: int) -> List[Post]:
    return list(session.scalars(select(Post).where(Post.user_id == user_id).order_by(Post.id)))


def update_post(
    session: Session, post_id: int, *, title: str, content: str, is_published: bool,
) -> Optional[Post]:
    post = session.get(Post, post_id)
    if post is None:
        return None
    post.title, post.content, post.is_published = title, content, is_published
    session.flush()
    return post


def delete_post(session: Session, post_id: int) -> bool:
    post = session.get(Post, post_id)
    if post is None:
        return False
    session.delete(post)
    session.flush()
    return True
