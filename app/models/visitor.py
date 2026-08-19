from sqlalchemy import String, Date, Index
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import UUIDMixin, TimestampMixin
from app.core.database import Base


class Visitor(Base, UUIDMixin, TimestampMixin):
    """A person attending a programme (e.g. Friday all-night service) who is
    NOT a church member. Intentionally separate from `Profile`/`User`: no
    CMS account, no login, no roles — just a lightweight attendance record.
    """

    __tablename__ = "visitors"

    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone_number: Mapped[str] = mapped_column(String(20), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    gender: Mapped[str | None] = mapped_column(String(10), nullable=True)

    # Free-text name of the programme/event ("Friday All-Night", etc.) rather
    # than a foreign key, since visitor programmes aren't modeled elsewhere.
    programme: Mapped[str] = mapped_column(String(150), nullable=False)
    visit_date: Mapped[Date] = mapped_column(Date, nullable=False)

    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)

    __table_args__ = (
        # Admin visitor list is typically filtered/sorted by date and programme.
        Index("ix_visitor_date", "visit_date"),
        Index("ix_visitor_programme_date", "programme", "visit_date"),
    )
