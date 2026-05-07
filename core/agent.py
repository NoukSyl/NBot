"""
JARVIS Core Agent
The main autonomous loop — thinks, decides, acts, reports.
Phase 1: Basic loop + approval system
Phase 2+: News monitoring, cron tasks, AutoGPT planning
"""

import asyncio
import logging
import uuid
from datetime import datetime
from core.admin import AdminSystem
from core.brain import Brain
from core.memory import Memory

logger = logging.getLogger(__name__)


class JarvisAgent:
    """
    The central agent.
    - Runs an autonomous background loop
    - Coordinates admin, brain, memory, telegram
    - Always asks superadmin before major actions
    """

    def __init__(self):
        self.admin = AdminSystem()
        self.brain = Brain()
        self.memory = Memory()
        self.telegram = None  # Set after init to avoid circular imports
        self._running = False
        self._loop_active = False
        self._pending_callbacks: dict[str, asyncio.Event] = {}
        self._approval_results: dict[str, str] = {}

    def get_status(self) -> dict:
        return {
            "running": self._running,
            "loop_active": self._loop_active,
        }

    async def start(self):
        """Start the agent — initializes all systems."""
        logger.info("🚀 JARVIS Agent starting up...")
        self.memory.log_event("system", "JARVIS agent started")
        self._running = True

        # Import here to avoid circular dependency
        from telegram.bot import TelegramBot
        self.telegram = TelegramBot(self.admin, self.brain, self.memory, self)

        # Start autonomous loop and Telegram concurrently
        await asyncio.gather(
            self.telegram.start(),
            self._autonomous_loop(),
        )

    async def _autonomous_loop(self):
        """
        The heartbeat of JARVIS.
        Runs every N seconds and performs autonomous tasks.
        Phase 1: Just heartbeat + self-reflection.
        Phase 2: Add news monitoring.
        Phase 3: Add cron tasks.
        """
        self._loop_active = True
        logger.info("🔄 Autonomous loop started")
        
        # Wait a bit for Telegram to come online
        await asyncio.sleep(5)

        # Notify superadmin on startup
        await self._notify("🟢 <b>JARVIS is online.</b>\n\nAutonomous systems active. Standing by for instructions or monitoring triggers.")

        loop_count = 0
        while self._running:
            try:
                loop_count += 1
                await self._tick(loop_count)
            except Exception as e:
                logger.error(f"Loop error: {e}", exc_info=True)
                self.memory.log_event("error", str(e))

            # Loop every 5 minutes
            await asyncio.sleep(300)

    async def _tick(self, loop_count: int):
        """
        One cycle of autonomous activity.
        Phase 1: Heartbeat + self-check
        """
        logger.info(f"🔄 Tick #{loop_count}")

        # Every 12 ticks (~1 hour): think about what to do next
        if loop_count % 12 == 0:
            await self._self_reflect()

        self.memory.log_event("tick", f"Loop tick #{loop_count}")

    async def _self_reflect(self):
        """
        Agent reflects on recent memory and decides if anything needs attention.
        Like JARVIS scanning the environment and reporting.
        """
        context = self.memory.get_context_summary()
        reflection = await self.brain.think(
            f"Review this recent activity log and determine if anything needs the superadmin's attention:\n\n{context}\n\n"
            "If everything is normal, say 'All systems nominal.' "
            "If something needs attention, briefly describe it.",
            max_tokens=256
        )
        self.memory.log_event("reflection", reflection[:200])
        if "nominal" not in reflection.lower():
            await self._notify(f"🤔 <b>JARVIS Self-Check:</b>\n\n{reflection}")

    # ─────────────────────────────────────────
    # Approval Flow
    # ─────────────────────────────────────────

    async def request_approval(self, description: str, payload: dict = None) -> bool:
        """
        Request superadmin approval before doing something.
        Waits for approve/deny (with timeout).
        Returns True if approved, False if denied/timeout.
        """
        action_id = str(uuid.uuid4())[:8]
        event = asyncio.Event()
        self._pending_callbacks[action_id] = event

        # Create record + notify
        self.admin.create_approval_request(action_id, description, payload or {})
        await self.telegram.send_approval_request(action_id, description)
        self.memory.log_event("approval_requested", f"{action_id}: {description[:80]}")

        logger.info(f"⏳ Awaiting approval for {action_id}...")

        # Wait up to 10 minutes
        try:
            await asyncio.wait_for(event.wait(), timeout=600)
        except asyncio.TimeoutError:
            logger.info(f"Approval {action_id} timed out.")
            self._pending_callbacks.pop(action_id, None)
            self._approval_results.pop(action_id, None)
            await self._notify(f"⏰ Approval request <code>{action_id}</code> timed out with no response.")
            return False

        result = self._approval_results.pop(action_id, "denied")
        self._pending_callbacks.pop(action_id, None)
        return result == "approved"

    async def on_approved(self, action_id: str):
        self._approval_results[action_id] = "approved"
        if action_id in self._pending_callbacks:
            self._pending_callbacks[action_id].set()
        self.memory.log_event("approved", f"Action {action_id} approved by superadmin")

    async def on_denied(self, action_id: str):
        self._approval_results[action_id] = "denied"
        if action_id in self._pending_callbacks:
            self._pending_callbacks[action_id].set()
        self.memory.log_event("denied", f"Action {action_id} denied by superadmin")

    # ─────────────────────────────────────────
    # Notifications
    # ─────────────────────────────────────────

    async def _notify(self, message: str):
        if self.telegram:
            await self.telegram.notify_superadmin(message)
        else:
            logger.info(f"[NOTIFY] {message}")

    async def stop(self):
        self._running = False
        self._loop_active = False
        if self.telegram:
            await self.telegram.stop()
        logger.info("JARVIS agent stopped.")
