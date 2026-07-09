from sqlalchemy import BigInteger, String, Integer, Text, Boolean, ForeignKey, Enum, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import declarative_base, Mapped, mapped_column, relationship
import enum
from datetime import datetime

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


class User(Base):
    __tablename__ = "users"

    telegram_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str | None] = mapped_column(String, nullable=True)
    name: Mapped[str] = mapped_column(String(50))
    age: Mapped[int] = mapped_column(Integer)
    city: Mapped[str | None] = mapped_column(String(50), nullable=True)
    normalized_city: Mapped[str | None] = mapped_column(String(50), nullable=True)
    mmr: Mapped[int] = mapped_column(Integer)
    positions: Mapped[list[int]] = mapped_column(ARRAY(Integer))
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    photo_file_id: Mapped[str] = mapped_column(String)
    status: Mapped[ProfileStatus] = mapped_column(Enum(ProfileStatus), default=ProfileStatus.INCOMPLETE)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    # Связь с таблицей настроек
    settings = relationship("SearchSettings", back_populates="user", uselist=False, cascade="all, delete-orphan")


class SearchSettings(Base):
    __tablename__ = "search_settings"

    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.telegram_id", ondelete="CASCADE"),
                                         primary_key=True)
    min_age: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_age: Mapped[int | None] = mapped_column(Integer, nullable=True)
    min_mmr: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_mmr: Mapped[int | None] = mapped_column(Integer, nullable=True)
    wanted_positions: Mapped[list[int] | None] = mapped_column(ARRAY(Integer), nullable=True)

    user = relationship("User", back_populates="settings")


class Swipe(Base):
    __tablename__ = "swipes"
    __table_args__ = (
        # Запрещаем дублировать лайки/дизлайки между одними и теми же людьми
        UniqueConstraint("from_user_id", "to_user_id", name="uq_swipe_from_to"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    from_user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.telegram_id", ondelete="CASCADE"))
    to_user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.telegram_id", ondelete="CASCADE"))
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


class BannedUser(Base):
    """Заблокированные пользователи. Запись сохраняется даже после удаления анкеты."""
    __tablename__ = "banned_users"

    telegram_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    banned_by: Mapped[int] = mapped_column(BigInteger)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    banned_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)


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