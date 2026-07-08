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
    INAPPROPRIATE_PHOTO = "inappropriate_photo"
    SPAM = "spam"
    OFFENSIVE = "offensive"
    FAKE = "fake"
    OTHER = "other"


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
    reason: Mapped[ReportReason] = mapped_column(Enum(ReportReason))
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)