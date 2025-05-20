from app.mcp import mcp
import tools.metrics  # Add other tools here as you create them
from utils.logging import configure_logging, get_logger

logger = get_logger(__name__)

@mcp.tool()
def ping() -> str:
    """Simple health check tool. Returns 'pong'."""
    return "pong"

if __name__ == "__main__":
    configure_logging()
    logger.info("MCP server is running, awaiting connections...")
    mcp.run(transport="streamable-http")
