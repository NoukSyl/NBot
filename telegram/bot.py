"""
Telegram Bot Handler
- Receives commands from superadmin
- Sends autonomous notifications
- Approval/denial interface
"""

import os
import logging
import asyncio
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes
)

logger = logging.getLogger(__name__)


class TelegramBot:
    def __init__(self, admin_system, brain, memory, agent):
        self.admin = admin_system
        self.brain = brain
        self.memory = memory
        self.agent = agent
        self.token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.app: Application = None

    async def start(self):
        if not self.token:
            logger.error("TELEGRAM_BOT_TOKEN not set!")
            return

        self.app = Application.builder().token(self.token).build()

        # Register handlers
        self.app.add_handler(CommandHandler("start", self.cmd_start))
        self.app.add_handler(CommandHandler("status", self.cmd_status))
        self.app.add_handler(CommandHandler("think", self.cmd_think))
        self.app.add_handler(CommandHandler("plan", self.cmd_plan))
        self.app.add_handler(CommandHandler("memory", self.cmd_memory))
        self.app.add_handler(CommandHandler("link", self.cmd_link))
        self.app.add_handler(CommandHandler("pending", self.cmd_pending))
        self.app.add_handler(CommandHandler("help", self.cmd_help))
        self.app.add_handler(CallbackQueryHandler(self.handle_callback))
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))

        logger.info("Telegram bot starting...")
        await self.app.initialize()
        await self.app.start()
        await self.app.updater.start_polling(drop_pending_updates=True)
        logger.info("Telegram bot is live.")

    async def stop(self):
        if self.app:
            await self.app.updater.stop()
            await self.app.stop()
            await self.app.shutdown()

    # ─────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────

    def _get_platform_id(self, update: Update) -> tuple[str, str]:
        return "telegram", str(update.effective_user.id)

    def _is_admin(self, update: Update) -> bool:
        platform, uid = self._get_platform_id(update)
        return self.admin.is_superadmin(platform, uid)

    async def _admin_only(self, update: Update) -> bool:
        if not self._is_admin(update):
            await update.message.reply_text(
                "⛔ Access Denied.\nOnly the Creator may command me."
            )
            return False
        return True

    async def notify_superadmin(self, message: str, reply_markup=None):
        """Send a message to the superadmin proactively."""
        if not self.app:
            return
        sa_id = self.admin.get_superadmin_telegram_id()
        if not sa_id:
            logger.warning("No superadmin Telegram ID configured.")
            return
        try:
            await self.app.bot.send_message(
                chat_id=sa_id,
                text=message,
                reply_markup=reply_markup,
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Failed to notify superadmin: {e}")

    async def send_approval_request(self, action_id: str, description: str):
        """Send approval request with inline buttons."""
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Approve", callback_data=f"approve:{action_id}"),
                InlineKeyboardButton("❌ Deny", callback_data=f"deny:{action_id}")
            ]
        ])
        msg = (
            f"🤖 <b>JARVIS requests approval</b>\n\n"
            f"<b>Action ID:</b> <code>{action_id}</code>\n"
            f"<b>Description:</b>\n{description}\n\n"
            f"Do you authorize this action?"
        )
        await self.notify_superadmin(msg, reply_markup=keyboard)

    # ─────────────────────────────────────────
    # Commands
    # ─────────────────────────────────────────

    async def cmd_start(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        platform, uid = self._get_platform_id(update)
        is_admin = self.admin.is_superadmin(platform, uid)

        if is_admin:
            name = self.admin.get_superadmin_info()["name"]
            await update.message.reply_text(
                f"🌟 <b>Welcome back, {name}.</b>\n\n"
                f"I am JARVIS — your autonomous agent.\n"
                f"I think, monitor, and act — but always with your permission.\n\n"
                f"Type /help to see what I can do.",
                parse_mode="HTML"
            )
        else:
            await update.message.reply_text(
                "I am JARVIS. I serve only my Creator.\n"
                f"Your ID: <code>{uid}</code>",
                parse_mode="HTML"
            )

    async def cmd_help(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not await self._admin_only(update):
            return
        await update.message.reply_text(
            "🤖 <b>JARVIS Commands</b>\n\n"
            "/status — Agent status\n"
            "/think [question] — Ask me to think\n"
            "/plan [goal] — Generate a plan\n"
            "/memory — Show recent memory\n"
            "/pending — Show pending approvals\n"
            "/link [platform] [user_id] — Link your identity\n"
            "/help — This menu",
            parse_mode="HTML"
        )

    async def cmd_status(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not await self._admin_only(update):
            return
        s = self.admin.status()
        agent_status = self.agent.get_status()
        await update.message.reply_text(
            f"⚡ <b>JARVIS Status</b>\n\n"
            f"🧠 Agent: {'Running' if agent_status['running'] else 'Stopped'}\n"
            f"🔄 Autonomous loop: {'Active' if agent_status['loop_active'] else 'Inactive'}\n"
            f"👑 Superadmin: {s['superadmin_name']} ({s['superadmin_telegram']})\n"
            f"🔗 Linked identities: {s['total_identities']}\n"
            f"⏳ Pending approvals: {s['pending_approvals']}\n"
            f"🕐 Time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
            parse_mode="HTML"
        )

    async def cmd_think(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not await self._admin_only(update):
            return
        question = " ".join(ctx.args)
        if not question:
            await update.message.reply_text("Usage: /think [your question]")
            return
        msg = await update.message.reply_text("🧠 Thinking...")
        context = self.memory.get_context_summary()
        answer = await self.brain.think(question, system=f"Context:\n{context}")
        self.memory.log_event("think", f"Q: {question[:80]} | A: {answer[:80]}")
        await msg.edit_text(f"🧠 <b>JARVIS:</b>\n\n{answer}", parse_mode="HTML")

    async def cmd_plan(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not await self._admin_only(update):
            return
        goal = " ".join(ctx.args)
        if not goal:
            await update.message.reply_text("Usage: /plan [your goal]")
            return
        msg = await update.message.reply_text("📋 Planning...")
        context = self.memory.get_context_summary()
        plan = await self.brain.plan(goal, context)
        self.memory.log_event("plan", f"Goal: {goal[:80]}")
        await msg.edit_text(
            f"📋 <b>Plan for:</b> {goal}\n\n{plan}",
            parse_mode="HTML"
        )

    async def cmd_memory(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not await self._admin_only(update):
            return
        events = self.memory.get_recent_events(10)
        if not events:
            await update.message.reply_text("📭 No memory yet.")
            return
        lines = []
        for e in reversed(events):
            ts = e["timestamp"][:16].replace("T", " ")
            lines.append(f"[{ts}] <b>{e['type']}</b>: {e['content'][:80]}")
        await update.message.reply_text(
            "🧠 <b>Recent Memory</b>\n\n" + "\n".join(lines),
            parse_mode="HTML"
        )

    async def cmd_link(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not await self._admin_only(update):
            return
        if len(ctx.args) < 2:
            await update.message.reply_text(
                "Usage: /link [platform] [user_id]\n"
                "Example: /link discord 123456789\n\n"
                "This links that account as YOUR identity (superadmin)."
            )
            return
        platform = ctx.args[0].lower()
        user_id = ctx.args[1]
        p, uid = self._get_platform_id(update)
        result = self.admin.link_own_identity(platform, user_id, p, uid)
        if result["ok"]:
            await update.message.reply_text(f"✅ {result['message']}")
        else:
            await update.message.reply_text(f"❌ {result['reason']}")

    async def cmd_pending(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not await self._admin_only(update):
            return
        pending = self.admin.get_pending_approvals()
        if not pending:
            await update.message.reply_text("✅ No pending approvals.")
            return
        for req in pending:
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✅ Approve", callback_data=f"approve:{req['id']}"),
                    InlineKeyboardButton("❌ Deny", callback_data=f"deny:{req['id']}")
                ]
            ])
            await update.message.reply_text(
                f"⏳ <b>Pending:</b> <code>{req['id']}</code>\n{req['description']}",
                parse_mode="HTML",
                reply_markup=keyboard
            )

    async def handle_callback(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        platform, uid = "telegram", str(query.from_user.id)

        data = query.data
        if data.startswith("approve:"):
            action_id = data[8:]
            result = self.admin.approve(action_id, platform, uid)
            if result["ok"]:
                await query.edit_message_text(f"✅ Approved: <code>{action_id}</code>", parse_mode="HTML")
                # Signal agent
                await self.agent.on_approved(action_id)
            else:
                await query.edit_message_text(f"❌ {result['reason']}")

        elif data.startswith("deny:"):
            action_id = data[5:]
            result = self.admin.deny(action_id, platform, uid)
            if result["ok"]:
                await query.edit_message_text(f"🚫 Denied: <code>{action_id}</code>", parse_mode="HTML")
                await self.agent.on_denied(action_id)
            else:
                await query.edit_message_text(f"❌ {result['reason']}")

    async def handle_message(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self._is_admin(update):
            return
        text = update.message.text
        msg = await update.message.reply_text("🧠 Thinking...")
        context = self.memory.get_context_summary()
        answer = await self.brain.think(
            text,
            system=f"You are JARVIS, an autonomous AI agent. Answer the superadmin's question or request.\n\nRecent context:\n{context}"
        )
        self.memory.log_event("chat", f"User: {text[:60]} | JARVIS: {answer[:60]}")
        await msg.edit_text(f"🤖 {answer}", parse_mode="HTML")
