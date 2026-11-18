import datetime as dt
import typing

import sqlalchemy as sa
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.sql.type_api import TypeEngine

# Deterministic constraint names, so migrations can drop and rename them.
_naming_convention = {
    "pk": "pk_%(table_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
    "ix": "index_%(table_name)s_on_%(column_0_N_name)s",
    "uq": "unique_%(table_name)s_%(column_0_N_name)s",
    "ck": "check_%(table_name)s_%(constraint_name)s",
}


class DatabaseModel(DeclarativeBase):
    metadata = sa.MetaData(naming_convention=_naming_convention)
    type_annotation_map: typing.ClassVar[dict[type, TypeEngine]] = {
        str: sa.TEXT(),
        dt.datetime: sa.TIMESTAMP(timezone=True),
    }
