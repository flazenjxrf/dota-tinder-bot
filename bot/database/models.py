from sqlalchemy import BigInteger, String, Integer, Text, Boolean, ForeignKey, Enum, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import declarative_base, Mapped, mapped_column, relationship
import enum
from datetime import datetime

from bot.games import DEFAULT_GAME, format_rating, normalize_game, role_labels

Base = declarative_base()


class ProfileStatus(enum.Enum):
    ACTIVE = "active"
    HIDDEN = "hidden"
    BANNED = "banned"
    INCOMPLETE = "incomplete"


class ActionType(enum.Enum):
    LIKE = "like"
    DISLIKE = "dislike"


class ReportReason(enum.Enum):
    ADS = "ads"
    OFFENSIVE = "offensive"
    NSFW = "nsfw"
    POLITICAL = "political"


class ReportStatus(enum.Enum):
    PENDING = "pending"
    REJECTED = "rejected"
    RESOLVED = "resolved"


class FeedbackStatus(enum.Enum):
    PENDING = "pending"
    READ = "read"


class UnbanRequestStatus(enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class User(Base):
    __tablename__ = "users"

    telegram_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str | None] = mapped_column(String, nullable=True)
    name: Mapped[str] = mapped_column(String(50))
    age: Mapped[int] = mapped_column(Integer)
    city: Mapped[str | None] = mapped_column(String(50), nullable=True)
    normalized_city: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status: Mapped[ProfileStatus] = mapped_column(Enum(ProfileStatus), default=ProfileStatus.INCOMPLETE)
    last_active_game: Mapped[str] = mapped_column(String(20), default=DEFAULT_GAME)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    game_profiles = relationship(
        "GameProfile",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    def display_profile(self, game: str | None = None) -> "GameProfile | None":
        game = normalize_game(game or getattr(self, "_view_game", None) or self.last_active_game)
        profiles = self.game_profiles or []
        for profile in profiles:
            if profile.game == game:
                return profile
        return profiles[0] if profiles else None

    def profile_for(self, game: str | None) -> "GameProfile | None":
        game = normalize_game(game)
        for profile in self.game_profiles or []:
            if profile.game == game:
                return profile
        return None

    @property
    def mmr(self) -> int:
        profile = self.display_profile()
        return profile.skill_value("mmr") or profile.primary_skill() or 0 if profile else 0

    @property
    def positions(self) -> list[int]:
        profile = self.display_profile()
        return list(profile.roles or []) if profile else []

    @property
    def bio(self) -> str:
        profile = self.display_profile()
        return (profile.bio or "") if profile else ""

    @property
    def photo_file_id(self) -> str:
        profile = self.display_profile()
        return profile.photo_file_id or "" if profile else ""

    @property
    def settings(self) -> "SearchSettings | None":
        profile = self.display_profile()
        return profile.settings if profile else None


class GameProfile(Base):
    __tablename__ = "game_profiles"
    __table_args__ = (
        UniqueConstraint("user_id", "game", name="uq_game_profile_user_game"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.telegram_id", ondelete="CASCADE"),
        index=True,
    )
    game: Mapped[str] = mapped_column(String(20), default=DEFAULT_GAME)
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    photo_file_id: Mapped[str | None] = mapped_column(String, nullable=True)
    roles: Mapped[list[int]] = mapped_column(ARRAY(Integer), default=list)
    # VARCHAR, не PG-enum: на Railway уже есть profilestatus у users, не плодим второй тип
    status: Mapped[ProfileStatus] = mapped_column(
        Enum(
            ProfileStatus,
            values_callable=lambda obj: [e.value for e in obj],
            native_enum=False,
        ),
        default=ProfileStatus.INCOMPLETE,
    )
    created_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow,
        server_default=text("TIMEZONE('utc', NOW())"),
    )

    user = relationship("User", back_populates="game_profiles")
    ratings = relationship("GameRating", back_populates="profile", cascade="all, delete-orphan")
    settings = relationship(
        "SearchSettings",
        back_populates="profile",
        uselist=False,
        cascade="all, delete-orphan",
    )

    def rating_map(self) -> dict[str, int]:
        return {item.kind: item.value for item in (self.ratings or [])}

    def skill_value(self, kind: str) -> int | None:
        return self.rating_map().get(kind)

    def primary_skill(self) -> int | None:
        ratings = self.ratings or []
        return ratings[0].value if ratings else None

    def ratings_display(self) -> list[str]:
        return [
            format_rating(self.game, item.kind, item.value)
            for item in (self.ratings or [])
        ]

    def role_labels(self) -> list[str]:
        return role_labels(self.game, self.roles)

    def is_complete(self) -> bool:
        return (
            self.status != ProfileStatus.INCOMPLETE
            and bool(self.photo_file_id)
            and bool(self.roles)
            and bool(self.ratings)
        )


class GameRating(Base):
    __tablename__ = "game_ratings"
    __table_args__ = (
        UniqueConstraint("profile_id", "kind", name="uq_game_rating_profile_kind"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    profile_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("game_profiles.id", ondelete="CASCADE"),
        index=True,
    )
    kind: Mapped[str] = mapped_column(String(30))
    value: Mapped[int] = mapped_column(Integer)

    profile = relationship("GameProfile", back_populates="ratings")


class SearchSettings(Base):
    __tablename__ = "game_search_settings"

    game_profile_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("game_profiles.id", ondelete="CASCADE"),
        primary_key=True,
    )
    min_age: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_age: Mapped[int | None] = mapped_column(Integer, nullable=True)
    wanted_roles: Mapped[list[int] | None] = mapped_column(ARRAY(Integer), nullable=True)
    wanted_rating_kind: Mapped[str | None] = mapped_column(String(30), nullable=True)
    min_skill: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_skill: Mapped[int | None] = mapped_column(Integer, nullable=True)

    profile = relationship("GameProfile", back_populates="settings")

    @property
    def wanted_positions(self) -> list[int] | None:
        return self.wanted_roles

    @property
    def min_mmr(self) -> int | None:
        return self.min_skill

    @property
    def max_mmr(self) -> int | None:
        return self.max_skill


class Swipe(Base):
    __tablename__ = "swipes"
    __table_args__ = (
        UniqueConstraint("from_user_id", "to_user_id", "game", name="uq_swipe_from_to_game"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    from_user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.telegram_id", ondelete="CASCADE"))
    to_user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.telegram_id", ondelete="CASCADE"))
    game: Mapped[str] = mapped_column(String(20), default=DEFAULT_GAME)
    action: Mapped[ActionType] = mapped_column(Enum(ActionType))
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_mutual: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)


class Report(Base):
    __tablename__ = "reports"
    __table_args__ = (
        UniqueConstraint("from_user_id", "to_user_id", name="uq_report_from_to"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    from_user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.telegram_id", ondelete="CASCADE"))
    to_user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.telegram_id", ondelete="CASCADE"))
    reason: Mapped[ReportReason] = mapped_column(
        Enum(ReportReason, values_callable=lambda obj: [e.value for e in obj], native_enum=False),
    )
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[ReportStatus] = mapped_column(
        Enum(ReportStatus, values_callable=lambda obj: [e.value for e in obj], native_enum=False),
        default=ReportStatus.PENDING,
    )
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)


class BugFeedback(Base):
    __tablename__ = "bug_feedback"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.telegram_id", ondelete="CASCADE"))
    text: Mapped[str] = mapped_column(Text)
    status: Mapped[FeedbackStatus] = mapped_column(
        Enum(FeedbackStatus, values_callable=lambda obj: [e.value for e in obj], native_enum=False),
        default=FeedbackStatus.PENDING,
    )
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)


class BannedUser(Base):
    """Заблокированные пользователи. Запись сохраняется даже после удаления анкеты."""
    __tablename__ = "banned_users"

    telegram_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    banned_by: Mapped[int] = mapped_column(BigInteger)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    violation_number: Mapped[int] = mapped_column(Integer, default=1)
    banned_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)


class BanHistory(Base):
    """Журнал всех банов — сохраняется после разбана."""
    __tablename__ = "ban_history"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, index=True)
    banned_by: Mapped[int] = mapped_column(BigInteger)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    violation_number: Mapped[int] = mapped_column(Integer)
    banned_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    unbanned_at: Mapped[datetime | None] = mapped_column(nullable=True)


class UnbanRequest(Base):
    __tablename__ = "unban_requests"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.telegram_id", ondelete="CASCADE"))
    message: Mapped[str] = mapped_column(Text)
    status: Mapped[UnbanRequestStatus] = mapped_column(
        Enum(UnbanRequestStatus, values_callable=lambda obj: [e.value for e in obj], native_enum=False),
        default=UnbanRequestStatus.PENDING,
    )
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(nullable=True)
    resolved_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


class UserConsent(Base):
    """Журнал согласий. Записи не удаляются — каждое согласие фиксируется отдельно."""
    __tablename__ = "user_consent_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, index=True)
    username: Mapped[str | None] = mapped_column(String, nullable=True)
    consented_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)


class ProfileDeletion(Base):
    """Журнал удалений анкет — для повторного запроса согласия."""
    __tablename__ = "profile_deletions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, index=True)
    deleted_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)


class TeammateRating(Base):
    """Оценка мэтча: aura (скилл) и/или vibe (приятно общаться). Один пользователь — одна запись на мэтч."""
    __tablename__ = "teammate_ratings"
    __table_args__ = (
        UniqueConstraint("from_user_id", "to_user_id", "game", name="uq_teammate_rating_from_to_game"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    from_user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.telegram_id", ondelete="CASCADE"))
    to_user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.telegram_id", ondelete="CASCADE"))
    game: Mapped[str] = mapped_column(String(20), default=DEFAULT_GAME)
    has_aura: Mapped[bool] = mapped_column(Boolean, default=False)
    has_vibe: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, onupdate=datetime.utcnow)