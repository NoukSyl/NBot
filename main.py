"""
JARVIS Agent - Autonomous AI Agent
"""

import asyncio
import logging
import os

from aiohttp import web
from core.agent import JarvisAgent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)

# ----------------------------
# Healthcheck server
# ----------------------------

async def health(request):
    return web.json_response({"status": "ok"})

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", health)
    app.router.add_get("/health", health)

    runner = web.AppRunner(app)
    await runner.setup()

    port = int(os.environ.get("PORT", 8080))

    site = web.TCPSite(
        runner,
        host="0.0.0.0",
        port=port
    )

    await site.start()

    logging.info(f"Health server running on port {port}")

# ----------------------------
# Main
# ----------------------------

async def main():
    await start_web_server()

    agent = JarvisAgent()
    await agent.start()

if __name__ == "__main__":
    asyncio.run(main())