import argparse
import tools
from app.mcp import mcp
from utils.logging import configure_logging, get_logger


__all__ = ["tools"]

logger = get_logger(__name__)

VALID_TRANSPORTS = ["stdio", "sse", "streamable-http"]


@mcp.tool()
def ping() -> str:
    """Simple health check tool. Returns 'pong'."""
    return "pong"


def parse_args():
    parser = argparse.ArgumentParser(description="MCP Server")
    parser.add_argument(
        "--transport",
        "-t",
        choices=VALID_TRANSPORTS,
        default="streamable-http",
        help="Transport type (stdio, sse, streamable-http). Default: streamable-http",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    configure_logging()
    logger.info(
        f"MCP server is running with '{args.transport}' transport, awaiting connections..."
    )
    mcp.run(transport=args.transport)
