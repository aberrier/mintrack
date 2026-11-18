import typing

import fastapi

from .database import DatabaseManager, get_database

DatabaseDepType = typing.Annotated[DatabaseManager, fastapi.Depends(get_database)]
