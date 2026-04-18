# app/db/base.py
import uuid
from datetime import datetime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import DateTime
from sqlalchemy.sql import func

class Base(DeclarativeBase):
    pass

class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

# app/models/user.py
import enum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.db.base import Base, TimestampMixin

class RoleEnum(str, enum.Enum):
    MEMBER = "MEMBER"
    GROUP_LEADER = "GROUP_LEADER"
    FINANCE = "FINANCE"
    SUPER_ADMIN = "SUPER_ADMIN"

class User(Base, TimestampMixin):
    __tablename__ = "users"
    
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(unique=True, index=True)
    is_active: Mapped[bool] = mapped_column(default=True)
    
    profile: Mapped["Profile"] = relationship("Profile", back_populates="user", cascade="all, delete-orphan", uselist=False)

# app/models/profile.py
from sqlalchemy import ForeignKey, String, Date
from app.db.base import Base, TimestampMixin

class Profile(Base, TimestampMixin):
    __tablename__ = "profiles"
    
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    
    first_name: Mapped[str] = mapped_column(String(50), nullable=True)
    last_name: Mapped[str] = mapped_column(String(50), nullable=True)
    phone_number: Mapped[str] = mapped_column(String(20), nullable=True)
    role: Mapped[RoleEnum] = mapped_column(default=RoleEnum.MEMBER, index=True)
    
    # Additional fields omitted for brevity (address, dob, emergency_contact, etc.)
    
    user: Mapped["User"] = relationship("User", back_populates="profile")