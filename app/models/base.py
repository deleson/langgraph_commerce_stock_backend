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
    metadata = MetaData(naming_convention=NAMING_CONVENTION)