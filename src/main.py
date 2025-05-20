import tools
from app.mcp import mcp
from utils.logging import configure_logging, get_logger

__all__ = ["tools"]

logger = get_logger(__name__)


@mcp.tool()
def ping() -> str:
    """Simple health check tool. Returns 'pong'."""
    return "pong"


if __name__ == "__main__":
    configure_logging()
    logger.info("MCP server is running, awaiting connections...")
    mcp.run(transport="streamable-http")
