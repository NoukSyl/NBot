"""
JARVIS Agent - Autonomous AI Agent
Phase 1: Core + Admin System + Telegram Bot
"""

import asyncio
import logging
from core.agent import JarvisAgent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)

async def main():
    agent = JarvisAgent()
    await agent.start()

if __name__ == "__main__":
    asyncio.run(main())
