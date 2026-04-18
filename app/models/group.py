
from sqlalchemy import String, ForeignKey, Enum, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import UUIDMixin, TimestampMixin
from app.core.database import Base
from app.models.enums import GroupMembershipStatus


class Group(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "groups"

    name: Mapped[str] = mapped_column(
        String(150),
        unique=True,
        index=True,
        nullable=False,
    )

    leader_id: Mapped[str | None] = mapped_column(
        ForeignKey("user.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Relationships
    leader: Mapped["User"] = relationship(
        "User",
        back_populates="led_groups",
        foreign_keys=[leader_id],
        lazy="joined",
    )

    members: Mapped[list["GroupMember"]] = relationship(
        "GroupMember",
        back_populates="group",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class GroupMember(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "group_members"

    user_id: Mapped[str] = mapped_column(
        ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    group_id: Mapped[str] = mapped_column(
        ForeignKey("groups.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    status: Mapped[GroupMembershipStatus] = mapped_column(
        Enum(GroupMembershipStatus, name="membership_status_enum"),
        default=GroupMembershipStatus.PENDING,
        nullable=False,
        index=True,
    )

    approved_by: Mapped[str | None] = mapped_column(
        ForeignKey("user.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Relationships
    user: Mapped["User"] = relationship(
        "User",
        back_populates="memberships",
        foreign_keys=[user_id],
        lazy="joined",
    )

    group: Mapped["Group"] = relationship(
        "Group",
        back_populates="members",
        lazy="joined",
    )

    approver: Mapped["User"] = relationship(
        "User",
        foreign_keys=[approved_by],
        lazy="joined",
    )

    __table_args__ = (
        # Ensures a user cannot belong to more than one group
        UniqueConstraint("user_id", name="uq_user_single_group"),

        # Speeds up filtering members by group + status
        Index("ix_group_member_group_status", "group_id", "status"),
    )