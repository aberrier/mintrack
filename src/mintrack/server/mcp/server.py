import fastapi
import starlette.routing
from mcp.server.auth.settings import AuthSettings
from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations

from mintrack.config import Config
from mintrack.server.mcp import tools
from mintrack.server.mcp.auth import ApiTokenVerifier

MCP_PATH = "/mcp"

INSTRUCTIONS = (
    "Read and update the user's MinTrack tracking of movies and TV shows (anime are TV shows). "
    "Shows and movies are identified by their TMDB id: call search_media first when you don't know it."
)

READ = ToolAnnotations(read_only_hint=True, open_world_hint=False)
WRITE = ToolAnnotations(read_only_hint=False, destructive_hint=False, open_world_hint=False)
UNDO = ToolAnnotations(read_only_hint=False, destructive_hint=True, open_world_hint=False)


def build_mcp_router(config: Config) -> fastapi.APIRouter:
    """The MCP server at /mcp: Streamable HTTP, a user's API token as Bearer token, no state between requests."""
    server = MCPServer(
        "MinTrack",
        instructions=INSTRUCTIONS,
        version=config.project.version,
        token_verifier=ApiTokenVerifier(),
        # No resource_server_url: no OAuth metadata is published, so clients send their configured token.
        auth=AuthSettings(issuer_url=config.project.public_url, resource_server_url=None),
    )
    server.add_tool(tools.search_media, annotations=ToolAnnotations(read_only_hint=True, open_world_hint=True))
    server.add_tool(tools.get_show_progress, annotations=READ)
    server.add_tool(tools.mark_episode_watched, annotations=WRITE)
    server.add_tool(tools.unmark_episode_watched, annotations=UNDO)
    server.add_tool(tools.mark_movie_watched, annotations=WRITE)
    server.add_tool(tools.unmark_movie_watched, annotations=UNDO)
    server.add_tool(tools.set_show_status, annotations=WRITE)
    server.add_tool(tools.list_upcoming, annotations=READ)
    server.add_tool(tools.list_watch_list, annotations=READ)

    app = server.streamable_http_app(
        streamable_http_path=MCP_PATH,
        stateless_http=True,
        json_response=True,
        # Host checks guard servers without authentication; this one needs a Bearer token no web page can send,
        # and MinTrack answers on any address (LAN, IP, proxy).
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )
    router = fastapi.APIRouter(lifespan=app.router.lifespan_context)
    router.routes.append(starlette.routing.Route(MCP_PATH, app))
    return router
