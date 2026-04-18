from sqlalchemy import String, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.orm import relationship
from app.core.database import Base
from datetime import datetime
from sqlalchemy import ForeignKey

class Session(Base):
    __tablename__ = "session"

    id: Mapped[str] = mapped_column(String,primary_key=True,)
    userId: Mapped[str] = mapped_column(
        "userId", ForeignKey("user.id")
    )
    token: Mapped[str] = mapped_column(String, index=True)
    expiresAt: Mapped[datetime] = mapped_column(DateTime)
    userId: Mapped[str] = mapped_column(String, index=True)