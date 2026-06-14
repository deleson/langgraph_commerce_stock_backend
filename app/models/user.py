"""用户主表 Model。

users 表保存系统登录身份、邮箱、用户名、密码哈希和账号状态。
它是多用户隔离的根表，其他用户私有数据通常通过 user_id 关联到这里。
"""

from datetime import datetime

from sqlalchemy import Boolean,DateTime,String,func
from sqlalchemy.orm import Mapped,mapped_column

from app.models.base import Base

class User(Base):
    """系统用户表。

    hashed_password 只保存哈希值，不保存明文密码。
    """

    __tablename__ = "users"

    id:Mapped[int] = mapped_column(primary_key=True)

    email:Mapped[str] = mapped_column(String(225),unique=True,index=True,nullable=False)
    username:Mapped[str] = mapped_column(String(50),unique=True,index=True)
    hashed_password:Mapped[str] = mapped_column(String(255),nullable=False)
    is_active:Mapped[bool] = mapped_column(Boolean,default=True)
    is_superuser: Mapped[bool] = mapped_column(Boolean,default=False,nullable=False)

    status:Mapped[str] = mapped_column(String(20),default="active",nullable=False)

    created_at: Mapped[datetime] = mapped_column(
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
