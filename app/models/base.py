"""SQLAlchemy Declarative Base。

所有数据库 Model 都继承 Base，使 SQLAlchemy 和 Alembic 可以统一收集表结构。
NAMING_CONVENTION 用于让索引、唯一约束、检查约束、外键和主键命名保持稳定。
"""

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",                  #索引
    "uq": "uq_%(table_name)s_%(column_0_name)s",    #唯一约束
    "ck": "ck_%(table_name)s_%(constraint_name)s",  #检查约束
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",    #外键
    "pk": "pk_%(table_name)s",  #主键
}

class Base(DeclarativeBase):
    """项目所有 SQLAlchemy ORM Model 的基类。"""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)
