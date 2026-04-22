from datetime import datetime

from sqlalchemy import Boolean,DateTime,String,func
from sqlalchemy.orm import Mapped,mapped_column

from app.models.base import Base

class User(Base):
    __tablename__ = "users"

    id:Mapped[int] = mapped_column(primary_key=True)

    email:Mapped[str] = mapped_column(String(225),unique=True,index=True,nullable=False)
    username:Mapped[str] = mapped_column(String(50),unique=True,index=True)
    hashed_password:Mapped[str] = mapped_column(String(255),nullable=False)
    is_active:Mapped[bool] = mapped_column(Boolean,default=True)
    is_superuser: Mapped[bool] = mapped_column(Boolean,default=False,nullable=False)

    status:Mapped[str] = mapped_column(String(20),default="active",nullable=False)
    timezone:Mapped[str|None] =mapped_column(String(50),nullable=True)
    risk_preference:Mapped[str|None] = mapped_column(String(20),nullable=True)

    create_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
