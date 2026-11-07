from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

from app.models import Status

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Topic = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
Username = Annotated[str, StringConstraints(strip_whitespace=True, to_lower=True, pattern=r"^[a-z0-9_]{3,40}$")]


class InputModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Credentials(InputModel):
    username: Username
    password: str = Field(min_length=10, max_length=128)

    @field_validator("username", mode="before")
    @classmethod
    def normalize_username(cls, value):
        return value.strip().lower() if isinstance(value, str) else value


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = 86400


class TaskCreate(InputModel):
    title: Title
    description: str = Field(default="", max_length=10000)
    topic: Topic = "Общее"
    assignee_id: int | None = Field(default=None, gt=0)


class TaskPatch(InputModel):
    title: Title | None = None
    description: str | None = Field(default=None, max_length=10000)
    topic: Topic | None = None
    status: Status | None = None
    assignee_id: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def valid_patch(self):
        if not self.model_fields_set:
            raise ValueError("Укажите хотя бы одно поле")
        for name in self.model_fields_set - {"assignee_id"}:
            if getattr(self, name) is None:
                raise ValueError(f"Поле {name} не может быть null")
        return self


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    description: str
    topic: str
    status: Status
    owner_id: int
    assignee_id: int | None
    created_at: datetime
    updated_at: datetime


class TaskPage(BaseModel):
    items: list[TaskOut]
    total: int
    limit: int
    offset: int


class GroupOut(BaseModel):
    key: str
    count: int


class AnalyticsOut(BaseModel):
    total: int
    done: int
    completion_rate: float
    group_by: str
    groups: list[GroupOut]
