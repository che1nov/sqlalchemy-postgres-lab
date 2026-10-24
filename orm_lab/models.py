from typing import List

from sqlalchemy import CheckConstraint, ForeignKey, MetaData, String, Text, false
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    metadata = MetaData(schema="orm_lab")


class User(Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint("age >= 0", name="users_age_nonnegative"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(255), unique=True)
    age: Mapped[int]
    posts: Mapped[List["Post"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True,
    )


class Post(Base):
    __tablename__ = "posts"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    content: Mapped[str] = mapped_column(Text)
    is_published: Mapped[bool] = mapped_column(default=False, server_default=false())
    user_id: Mapped[int] = mapped_column(
        ForeignKey("orm_lab.users.id", ondelete="CASCADE"), index=True,
    )
    user: Mapped[User] = relationship(back_populates="posts")
