"""Pydantic-схемы запросов Mini App API."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ConsentBody(BaseModel):
    pass


class SwipeBody(BaseModel):
    to_user_id: int
    action: Literal["like", "dislike"]
    message: str | None = Field(default=None, max_length=300)


class UndoBody(BaseModel):
    to_user_id: int


class RateBody(BaseModel):
    to_user_id: int
    kind: Literal["aura", "vibe"]


class ReportBody(BaseModel):
    to_user_id: int
    reason: Literal["ads", "offensive", "nsfw", "political"]
    comment: str | None = Field(default=None, max_length=500)


class FeedbackBody(BaseModel):
    text: str = Field(min_length=3, max_length=2000)


class ProfileUpdateBody(BaseModel):
    name: str | None = Field(default=None, max_length=50)
    age: int | None = Field(default=None, ge=12, le=60)
    city: str | None = Field(default=None, max_length=50)
    mmr: int | None = Field(default=None, ge=0, le=20000)
    positions: list[int] | None = None
    bio: str | None = Field(default=None, max_length=500)
    photo_file_id: str | None = Field(default=None, min_length=1)


class SettingsUpdateBody(BaseModel):
    wanted_positions: list[int] | None = None
    min_age: int | None = Field(default=None, ge=12, le=60)
    max_age: int | None = Field(default=None, ge=12, le=60)
    min_mmr: int | None = Field(default=None, ge=0, le=20000)
    max_mmr: int | None = Field(default=None, ge=0, le=20000)


class RegisterBody(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    age: int = Field(ge=12, le=60)
    city: str = Field(min_length=1, max_length=50)
    mmr: int = Field(ge=0, le=20000)
    positions: list[int] = Field(min_length=1)
    bio: str = Field(default="", max_length=500)
    photo_file_id: str = Field(min_length=1)
    wanted_positions: list[int] | None = None
    min_age: int | None = None
    max_age: int | None = None
    min_mmr: int | None = None
    max_mmr: int | None = None


class StatusUpdateBody(BaseModel):
    status: Literal["active", "hidden"]
