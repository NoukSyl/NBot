"""
JARVIS Agent - Autonomous AI Agent
Phase 1: Core + Admin System + Telegram Bot
"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse
import uvicorn

from core.agent import JarvisAgent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)

agent = JarvisAgent()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start agent in background when server starts
    task = asyncio.create_task(agent.start())
    yield
    # Shutdown
    await agent.stop()
    task.cancel()


app = FastAPI(lifespan=lifespan)


@app.get("/health")
async def health():
    status = agent.get_status()
    return JSONResponse({"status": "ok", **status})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    uvicorn.run(app, host="0.0.0.0", port=port)
