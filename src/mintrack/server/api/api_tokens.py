import datetime as dt
import typing
import uuid

import fastapi
import pydantic

from mintrack.core.api_tokens.managers import ApiTokenManager
from mintrack.db.dependencies import DbSessionDepType
from mintrack.server.api.dependencies import CurrentUserDepType

router = fastapi.APIRouter(prefix="/api-tokens", tags=["api-tokens"])


class ApiTokenResponse(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    created_at: dt.datetime
    last_used_at: dt.datetime | None


class CreatedApiTokenResponse(ApiTokenResponse):
    token: str


class CreateApiTokenRequest(pydantic.BaseModel):
    name: typing.Annotated[str, pydantic.StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


@router.get("")
async def list_api_tokens(user: CurrentUserDepType, session: DbSessionDepType) -> list[ApiTokenResponse]:
    tokens = await ApiTokenManager(session).list_for(user)
    return [ApiTokenResponse.model_validate(token) for token in tokens]


@router.post("", status_code=fastapi.status.HTTP_201_CREATED)
async def create_api_token(
    body: CreateApiTokenRequest, user: CurrentUserDepType, session: DbSessionDepType, response: fastapi.Response
) -> CreatedApiTokenResponse:
    token, raw_token = await ApiTokenManager(session).create(user, body.name, dt.datetime.now(dt.UTC))
    await session.commit()
    response.headers["Cache-Control"] = "no-store"
    return CreatedApiTokenResponse(**ApiTokenResponse.model_validate(token).model_dump(), token=raw_token)


@router.delete("/{token_id}", status_code=fastapi.status.HTTP_204_NO_CONTENT)
async def revoke_api_token(token_id: uuid.UUID, user: CurrentUserDepType, session: DbSessionDepType) -> None:
    if not await ApiTokenManager(session).revoke(user, token_id):
        raise fastapi.HTTPException(fastapi.status.HTTP_404_NOT_FOUND)
    await session.commit()
