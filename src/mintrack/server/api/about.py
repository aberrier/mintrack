import fastapi
import pydantic

from mintrack.config import get_config
from mintrack.server.mcp.server import MCP_PATH

router = fastapi.APIRouter(prefix="/about", tags=["about"])


class AboutResponse(pydantic.BaseModel):
    version: str
    # The MCP server's address on the configured public URL.
    mcp_url: str


@router.get("")
async def about() -> AboutResponse:
    """This server's version and addresses, for signed-in users only."""
    project = get_config().project
    return AboutResponse(version=project.version, mcp_url=f"{project.public_origin}{MCP_PATH}")
