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
    game: str | None = None


class UndoBody(BaseModel):
    to_user_id: int
    game: str | None = None


class RateBody(BaseModel):
    to_user_id: int
    kind: Literal["aura", "vibe"]
    game: str | None = None


class ReportBody(BaseModel):
    to_user_id: int
    reason: Literal["ads", "offensive", "nsfw", "political"]
    comment: str | None = Field(default=None, max_length=500)
    game: str | None = None


class FeedbackBody(BaseModel):
    text: str = Field(min_length=3, max_length=2000)


class RatingInput(BaseModel):
    kind: str
    value: int


class ProfileUpdateBody(BaseModel):
    name: str | None = Field(default=None, max_length=50)
    age: int | None = Field(default=None, ge=12, le=60)
    city: str | None = Field(default=None, max_length=50)
    roles: list[int] | None = None
    ratings: list[RatingInput] | None = None
    bio: str | None = Field(default=None, max_length=500)
    photo_file_id: str | None = Field(default=None, min_length=1)
    game: str | None = None
    mmr: int | None = Field(default=None, ge=0, le=20000)
    positions: list[int] | None = None


class SettingsUpdateBody(BaseModel):
    wanted_roles: list[int] | None = None
    wanted_rating_kind: str | None = None
    min_age: int | None = Field(default=None, ge=12, le=60)
    max_age: int | None = Field(default=None, ge=12, le=60)
    min_skill: int | None = None
    max_skill: int | None = None
    game: str | None = None
    wanted_positions: list[int] | None = None
    min_mmr: int | None = Field(default=None, ge=0, le=20000)
    max_mmr: int | None = Field(default=None, ge=0, le=20000)


class RegisterBody(BaseModel):
    game: str = "dota"
    name: str | None = Field(default=None, min_length=1, max_length=50)
    age: int | None = Field(default=None, ge=12, le=60)
    city: str | None = Field(default=None, min_length=1, max_length=50)
    roles: list[int] | None = None
    ratings: list[RatingInput] | None = None
    bio: str = Field(default="", max_length=500)
    photo_file_id: str | None = Field(default=None, min_length=1)
    copy_card_from: str | None = None
    wanted_roles: list[int] | None = None
    wanted_rating_kind: str | None = None
    min_age: int | None = None
    max_age: int | None = None
    min_skill: int | None = None
    max_skill: int | None = None
    mmr: int | None = Field(default=None, ge=0, le=20000)
    positions: list[int] | None = None
    wanted_positions: list[int] | None = None
    min_mmr: int | None = None
    max_mmr: int | None = None


class CopyCardBody(BaseModel):
    from_game: str
    to_games: list[str] | None = None
    bio: bool = True
    photo: bool = True


class GameSwitchBody(BaseModel):
    game: str


class StatusUpdateBody(BaseModel):
    status: Literal["active", "hidden"]
    game: str | None = None
