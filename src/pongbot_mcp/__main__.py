"""Entry point: python -m pongbot_mcp"""
import logging

from pongbot_mcp.server import mcp

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

if __name__ == "__main__":
    mcp.run(transport="stdio")
