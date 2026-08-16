import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional
import datetime
import asyncio
import os
import json
from dotenv import load_dotenv
from collections import defaultdict

from templates import TEMPLATES

# ──────────────────────────────────────────────
# Load environment variables
# Only the bot token lives in .env.
# Everything else (log channel, welcome channel, muted role, auto role)
# is configured live from inside the Discord server using the
# `/config` slash commands below — no more editing .env and restarting the bot.
# ──────────────────────────────────────────────
load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")

# ──────────────────────────────────────────────
# Per-guild configuration storage
# Settings are stored per-server in a local JSON file so each server
# can have its own log channel, welcome channel, muted role, and auto role.
# ──────────────────────────────────────────────
CONFIG_FILE = "guild_config.json"

DEFAULT_CONFIG = {
    "log_channel_id": 0,
    "welcome_channel_id": 0,
    "muted_role_id": 0,
    "auto_role_id": 0,
    "verify_role_id": 0,
    "verify_channel_id": 0,
}


def _load_all_config() -> dict:
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {}
    return {}


def _save_all_config(data: dict) -> None:
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def get_guild_config(guild_id: int) -> dict:
    """Return the config dict for a guild, filled in with defaults."""
    all_config = _load_all_config()
    guild_config = all_config.get(str(guild_id), {})
    return {**DEFAULT_CONFIG, **guild_config}


def set_guild_config(guild_id: int, key: str, value: int) -> None:
    """Update a single config value for a guild and persist it."""
    all_config = _load_all_config()
    guild_key = str(guild_id)
    guild_config = {**DEFAULT_CONFIG, **all_config.get(guild_key, {})}
    guild_config[key] = value
    all_config[guild_key] = guild_config
    _save_all_config(all_config)


# ──────────────────────────────────────────────
# Bot setup
# All commands are slash ("/") commands, registered on the bot's
# app_commands tree so Discord's built-in command helper (autocomplete,
# inline argument hints, etc.) works out of the box.
# ──────────────────────────────────────────────
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)
tree = bot.tree

# In-memory warn and spam tracking
warn_data: dict[int, list] = defaultdict(list)       # {user_id: [reason, ...]}
spam_tracker: dict[int, list] = defaultdict(list)    # {user_id: [timestamps]}
SPAM_LIMIT = 5      # max messages allowed within the interval
SPAM_INTERVAL = 5   # seconds


# ──────────────────────────────────────────────
# Helper: Log
# ──────────────────────────────────────────────
async def send_log(guild: discord.Guild, embed: discord.Embed):
    log_channel_id = get_guild_config(guild.id)["log_channel_id"]
    if log_channel_id:
        ch = guild.get_channel(log_channel_id)
        if ch:
            await ch.send(embed=embed)


def log_embed(title: str, color: discord.Color, **fields) -> discord.Embed:
    e = discord.Embed(title=title, color=color, timestamp=datetime.datetime.utcnow())
    for name, value in fields.items():
        e.add_field(name=name, value=value, inline=False)
    return e


# ──────────────────────────────────────────────
# Events
# ──────────────────────────────────────────────
@bot.event
async def on_ready():
    bot.add_view(VerifyView())
    await tree.sync()
    await bot.change_presence(
        activity=discord.Activity(type=discord.ActivityType.watching, name="/help | Manager Bot")
    )
    print(f"✅ Bot is online: {bot.user} ({bot.user.id})")


@bot.event
async def on_member_join(member: discord.Member):
    config = get_guild_config(member.guild.id)

    # Welcome message
    if config["welcome_channel_id"]:
        ch = member.guild.get_channel(config["welcome_channel_id"])
        if ch:
            e = discord.Embed(
                title="👋 Welcome!",
                description=f"Hey {member.mention}! Welcome to **{member.guild.name}** 🎉",
                color=discord.Color.green()
            )
            e.set_thumbnail(url=member.display_avatar.url)
            e.set_footer(text=f"Member #{member.guild.member_count}")
            await ch.send(embed=e)

    # Auto-role
    if config["auto_role_id"]:
        role = member.guild.get_role(config["auto_role_id"])
        if role:
            await member.add_roles(role, reason="Auto-Role")

    # Log
    await send_log(member.guild, log_embed(
        "📥 Member Joined", discord.Color.green(),
        Member=f"{member} ({member.id})",
        AccountCreated=member.created_at.strftime("%d/%m/%Y %H:%M")
    ))


@bot.event
async def on_member_remove(member: discord.Member):
    config = get_guild_config(member.guild.id)

    if config["welcome_channel_id"]:
        ch = member.guild.get_channel(config["welcome_channel_id"])
        if ch:
            e = discord.Embed(
                title="👋 Member Left",
                description=f"**{member}** has left the server",
                color=discord.Color.red()
            )
            await ch.send(embed=e)

    await send_log(member.guild, log_embed(
        "📤 Member Left", discord.Color.red(),
        Member=f"{member} ({member.id})"
    ))


@bot.event
async def on_message_delete(message: discord.Message):
    if message.author.bot:
        return
    await send_log(message.guild, log_embed(
        "🗑️ Message Deleted", discord.Color.orange(),
        Author=str(message.author),
        Channel=message.channel.mention,
        Content=message.content or "*(no content)*"
    ))


@bot.event
async def on_message_edit(before: discord.Message, after: discord.Message):
    if before.author.bot or before.content == after.content:
        return
    await send_log(before.guild, log_embed(
        "✏️ Message Edited", discord.Color.blue(),
        Author=str(before.author),
        Channel=before.channel.mention,
        Before=before.content or "*(empty)*",
        After=after.content or "*(empty)*"
    ))


# ──────────────────────────────────────────────
# Anti-Spam
# ──────────────────────────────────────────────
@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or not message.guild:
        return

    config = get_guild_config(message.guild.id)
    uid = message.author.id
    now = datetime.datetime.utcnow().timestamp()
    spam_tracker[uid] = [t for t in spam_tracker[uid] if now - t < SPAM_INTERVAL]
    spam_tracker[uid].append(now)

    if len(spam_tracker[uid]) >= SPAM_LIMIT:
        await message.delete()
        muted_role = message.guild.get_role(config["muted_role_id"])
        if muted_role:
            await message.author.add_roles(muted_role, reason="Anti-Spam Auto-Mute")
        try:
            await message.author.send(
                f"⚠️ You were automatically muted for sending messages too fast in **{message.guild.name}**"
            )
        except discord.Forbidden:
            pass
        spam_tracker[uid] = []
        await send_log(message.guild, log_embed(
            "🤖 Anti-Spam: Auto-Mute", discord.Color.dark_red(),
            User=f"{message.author} ({uid})",
            Channel=message.channel.mention
        ))
        return

    await bot.process_commands(message)


# ──────────────────────────────────────────────
# ─── SERVER CONFIGURATION COMMANDS ───
# Set everything directly in the server via /config — no .env editing required.
# ──────────────────────────────────────────────

def fmt_channel(guild: discord.Guild, channel_id: int) -> str:
    if not channel_id:
        return "*not set*"
    ch = guild.get_channel(channel_id)
    return ch.mention if ch else f"*invalid ({channel_id})*"


def fmt_role(guild: discord.Guild, role_id: int) -> str:
    if not role_id:
        return "*not set*"
    role = guild.get_role(role_id)
    return role.mention if role else f"*invalid ({role_id})*"


def build_config_embed(guild: discord.Guild) -> discord.Embed:
    config = get_guild_config(guild.id)
    e = discord.Embed(title="⚙️ Server Configuration", color=discord.Color.blurple())
    e.add_field(name="Log Channel", value=fmt_channel(guild, config["log_channel_id"]), inline=False)
    e.add_field(name="Welcome Channel", value=fmt_channel(guild, config["welcome_channel_id"]), inline=False)
    e.add_field(name="Muted Role", value=fmt_role(guild, config["muted_role_id"]), inline=False)
    e.add_field(name="Auto Role", value=fmt_role(guild, config["auto_role_id"]), inline=False)
    e.set_footer(text="Use /config <logchannel|welcomechannel|mutedrole|autorole> to change these")
    return e


class ConfigGroup(app_commands.Group):
    def __init__(self):
        super().__init__(name="config", description="Configure this server's settings")

    @app_commands.command(name="logchannel", description="Set the channel used for moderation/event logs")
    @app_commands.describe(channel="The text channel logs should be sent to")
    @app_commands.checks.has_permissions(administrator=True)
    async def logchannel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        set_guild_config(interaction.guild.id, "log_channel_id", channel.id)
        await interaction.response.send_message(f"✅ Log channel set to {channel.mention}", ephemeral=True)

    @app_commands.command(name="welcomechannel", description="Set the channel used for welcome/leave messages")
    @app_commands.describe(channel="The text channel welcome messages should be sent to")
    @app_commands.checks.has_permissions(administrator=True)
    async def welcomechannel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        set_guild_config(interaction.guild.id, "welcome_channel_id", channel.id)
        await interaction.response.send_message(f"✅ Welcome channel set to {channel.mention}", ephemeral=True)

    @app_commands.command(name="mutedrole", description="Set the role applied to muted members")
    @app_commands.describe(role="The role used to mute members")
    @app_commands.checks.has_permissions(administrator=True)
    async def mutedrole(self, interaction: discord.Interaction, role: discord.Role):
        set_guild_config(interaction.guild.id, "muted_role_id", role.id)
        await interaction.response.send_message(f"✅ Muted role set to {role.mention}", ephemeral=True)

    @app_commands.command(name="autorole", description="Set the role automatically given to new members")
    @app_commands.describe(role="The role given to members when they join")
    @app_commands.checks.has_permissions(administrator=True)
    async def autorole(self, interaction: discord.Interaction, role: discord.Role):
        set_guild_config(interaction.guild.id, "auto_role_id", role.id)
        await interaction.response.send_message(f"✅ Auto-role set to {role.mention}", ephemeral=True)

    @app_commands.command(name="show", description="Show this server's current configuration")
    @app_commands.checks.has_permissions(administrator=True)
    async def show(self, interaction: discord.Interaction):
        await interaction.response.send_message(embed=build_config_embed(interaction.guild), ephemeral=True)


bot.tree.add_command(ConfigGroup())


# ──────────────────────────────────────────────
# ─── MODERATION COMMANDS ───
# ──────────────────────────────────────────────

@bot.tree.command(name="ban", description="Ban a member from the server")
@app_commands.describe(member="The member to ban", reason="Why they're being banned")
@app_commands.checks.has_permissions(ban_members=True)
async def ban(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason given"):
    await member.ban(reason=reason)
    e = discord.Embed(title="🔨 Member Banned", color=discord.Color.red())
    e.add_field(name="Member", value=str(member))
    e.add_field(name="Reason", value=reason)
    e.add_field(name="By", value=str(interaction.user))
    await interaction.response.send_message(embed=e)
    await send_log(interaction.guild, e)


@bot.tree.command(name="unban", description="Unban a user by their user ID")
@app_commands.describe(user_id="The ID of the user to unban")
@app_commands.checks.has_permissions(ban_members=True)
async def unban(interaction: discord.Interaction, user_id: str):
    user = await bot.fetch_user(int(user_id))
    await interaction.guild.unban(user)
    await interaction.response.send_message(embed=discord.Embed(
        title="✅ Unbanned",
        description=f"**{user}** has been unbanned",
        color=discord.Color.green()
    ))


@bot.tree.command(name="kick", description="Kick a member from the server")
@app_commands.describe(member="The member to kick", reason="Why they're being kicked")
@app_commands.checks.has_permissions(kick_members=True)
async def kick(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason given"):
    await member.kick(reason=reason)
    e = discord.Embed(title="👢 Member Kicked", color=discord.Color.orange())
    e.add_field(name="Member", value=str(member))
    e.add_field(name="Reason", value=reason)
    e.add_field(name="By", value=str(interaction.user))
    await interaction.response.send_message(embed=e)
    await send_log(interaction.guild, e)


@bot.tree.command(name="mute", description="Mute a member using this server's configured muted role")
@app_commands.describe(member="The member to mute", duration="Minutes to mute for (0 = permanent)", reason="Why they're being muted")
@app_commands.checks.has_permissions(manage_roles=True)
async def mute(interaction: discord.Interaction, member: discord.Member, duration: int = 0, reason: str = "No reason given"):
    muted_role = interaction.guild.get_role(get_guild_config(interaction.guild.id)["muted_role_id"])
    if not muted_role:
        return await interaction.response.send_message(
            "❌ Muted role not found. Set one with `/config mutedrole`", ephemeral=True
        )
    await member.add_roles(muted_role, reason=reason)
    e = discord.Embed(title="🔇 Member Muted", color=discord.Color.dark_grey())
    e.add_field(name="Member", value=str(member))
    e.add_field(name="Duration", value=f"{duration} minutes" if duration else "Permanent")
    e.add_field(name="Reason", value=reason)
    await interaction.response.send_message(embed=e)
    await send_log(interaction.guild, e)
    if duration > 0:
        await asyncio.sleep(duration * 60)
        if muted_role in member.roles:
            await member.remove_roles(muted_role, reason="Mute duration expired")


@bot.tree.command(name="unmute", description="Remove the muted role from a member")
@app_commands.describe(member="The member to unmute")
@app_commands.checks.has_permissions(manage_roles=True)
async def unmute(interaction: discord.Interaction, member: discord.Member):
    muted_role = interaction.guild.get_role(get_guild_config(interaction.guild.id)["muted_role_id"])
    if muted_role and muted_role in member.roles:
        await member.remove_roles(muted_role)
        await interaction.response.send_message(embed=discord.Embed(
            title="🔊 Unmuted",
            description=f"**{member}** has been unmuted",
            color=discord.Color.green()
        ))
    else:
        await interaction.response.send_message("❌ This member is not muted", ephemeral=True)


@bot.tree.command(name="warn", description="Give a member a warning")
@app_commands.describe(member="The member to warn", reason="Why they're being warned")
@app_commands.checks.has_permissions(manage_messages=True)
async def warn(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason given"):
    warn_data[member.id].append(reason)
    count = len(warn_data[member.id])
    e = discord.Embed(title="⚠️ Warning", color=discord.Color.yellow())
    e.add_field(name="Member", value=str(member))
    e.add_field(name="Reason", value=reason)
    e.add_field(name="Warn Count", value=f"{count}")
    await interaction.response.send_message(embed=e)
    await send_log(interaction.guild, e)
    try:
        await member.send(f"⚠️ You received a warning in **{interaction.guild.name}**: {reason} (warning #{count})")
    except discord.Forbidden:
        pass


@bot.tree.command(name="warnings", description="View a member's warnings")
@app_commands.describe(member="The member to check")
async def warnings(interaction: discord.Interaction, member: discord.Member):
    warns = warn_data.get(member.id, [])
    e = discord.Embed(title=f"⚠️ Warnings for {member}", color=discord.Color.yellow())
    if warns:
        for i, w in enumerate(warns, 1):
            e.add_field(name=f"#{i}", value=w, inline=False)
    else:
        e.description = "No warnings"
    await interaction.response.send_message(embed=e)


@bot.tree.command(name="clearwarn", description="Clear all warnings for a member")
@app_commands.describe(member="The member whose warnings should be cleared")
@app_commands.checks.has_permissions(manage_messages=True)
async def clearwarn(interaction: discord.Interaction, member: discord.Member):
    warn_data[member.id] = []
    await interaction.response.send_message(f"✅ Cleared warnings for **{member}**")


@bot.tree.command(name="clear", description="Bulk delete recent messages in this channel")
@app_commands.describe(amount="How many messages to delete (default 10)")
@app_commands.checks.has_permissions(manage_messages=True)
async def clear(interaction: discord.Interaction, amount: int = 10):
    await interaction.response.defer(ephemeral=True)
    deleted = await interaction.channel.purge(limit=amount)
    await interaction.followup.send(f"🧹 Deleted {len(deleted)} messages", ephemeral=True)


@bot.tree.command(name="slowmode", description="Set this channel's slowmode delay")
@app_commands.describe(seconds="Slowmode delay in seconds (0 disables it)")
@app_commands.checks.has_permissions(manage_channels=True)
async def slowmode(interaction: discord.Interaction, seconds: int = 0):
    await interaction.channel.edit(slowmode_delay=seconds)
    await interaction.response.send_message(
        f"⏱️ Slowmode set to **{seconds} seconds**" if seconds else "⏱️ Slowmode disabled"
    )


@bot.tree.command(name="lock", description="Prevent @everyone from sending messages in this channel")
@app_commands.checks.has_permissions(manage_channels=True)
async def lock(interaction: discord.Interaction):
    overwrite = interaction.channel.overwrites_for(interaction.guild.default_role)
    overwrite.send_messages = False
    await interaction.channel.set_permissions(interaction.guild.default_role, overwrite=overwrite)
    await interaction.response.send_message("🔒 Channel locked")


@bot.tree.command(name="unlock", description="Allow @everyone to send messages in this channel again")
@app_commands.checks.has_permissions(manage_channels=True)
async def unlock(interaction: discord.Interaction):
    overwrite = interaction.channel.overwrites_for(interaction.guild.default_role)
    overwrite.send_messages = True
    await interaction.channel.set_permissions(interaction.guild.default_role, overwrite=overwrite)
    await interaction.response.send_message("🔓 Channel unlocked")


# ──────────────────────────────────────────────
# ─── CHANNEL & CATEGORY MANAGEMENT ───
# ──────────────────────────────────────────────

CHANNEL_TYPE_CHOICES = [
    app_commands.Choice(name="Text", value="text"),
    app_commands.Choice(name="Voice", value="voice"),
    app_commands.Choice(name="Announcement", value="announcement"),
    app_commands.Choice(name="Stage", value="stage"),
    app_commands.Choice(name="Forum", value="forum"),
]


async def create_channel_of_type(guild: discord.Guild, name: str, kind: str,
                                  category: Optional[discord.CategoryChannel], topic: Optional[str]):
    """Create a channel of the requested kind. Raises on failure so the caller can report it."""
    if kind == "text":
        return await guild.create_text_channel(name, category=category, topic=topic)
    if kind == "voice":
        return await guild.create_voice_channel(name, category=category)
    if kind == "stage":
        return await guild.create_stage_channel(name, category=category)
    if kind == "forum":
        return await guild.create_forum(name, category=category, topic=topic)
    if kind == "announcement":
        # Announcement (news) channels require the server to have Community enabled.
        ch = await guild.create_text_channel(name, category=category, topic=topic)
        await ch.edit(type=discord.ChannelType.news)
        return ch
    raise ValueError(f"Unknown channel type: {kind}")


class ChannelGroup(app_commands.Group):
    def __init__(self):
        super().__init__(name="channel", description="Create, delete, rename, or move channels")

    @app_commands.command(name="create", description="Create a new channel")
    @app_commands.describe(
        name="Name of the new channel",
        type="What kind of channel to create",
        category="Category to put it in (optional)",
        topic="Topic/description for the channel (text-based channels only)",
    )
    @app_commands.choices(type=CHANNEL_TYPE_CHOICES)
    @app_commands.checks.has_permissions(manage_channels=True)
    async def create(self, interaction: discord.Interaction, name: str, type: app_commands.Choice[str],
                      category: Optional[discord.CategoryChannel] = None, topic: Optional[str] = None):
        try:
            channel = await create_channel_of_type(interaction.guild, name, type.value, category, topic)
        except discord.Forbidden:
            return await interaction.response.send_message(
                "❌ I don't have permission to create that channel type here.", ephemeral=True
            )
        except discord.HTTPException as exc:
            return await interaction.response.send_message(f"❌ Couldn't create the channel: {exc}", ephemeral=True)
        await interaction.response.send_message(f"✅ Created {channel.mention}")

    @app_commands.command(name="delete", description="Delete a channel")
    @app_commands.describe(channel="The channel to delete", reason="Why it's being deleted")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def delete(self, interaction: discord.Interaction, channel: discord.abc.GuildChannel,
                      reason: str = "No reason given"):
        name = channel.name
        await channel.delete(reason=reason)
        await interaction.response.send_message(f"🗑️ Deleted channel **#{name}**")

    @app_commands.command(name="rename", description="Rename a channel")
    @app_commands.describe(channel="The channel to rename", new_name="The new name")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def rename(self, interaction: discord.Interaction, channel: discord.abc.GuildChannel, new_name: str):
        old_name = channel.name
        await channel.edit(name=new_name)
        await interaction.response.send_message(f"✏️ Renamed **#{old_name}** to **#{new_name}**")

    @app_commands.command(name="move", description="Move a channel into a different category")
    @app_commands.describe(channel="The channel to move", category="The category to move it into")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def move(self, interaction: discord.Interaction, channel: discord.abc.GuildChannel,
                    category: discord.CategoryChannel):
        await channel.edit(category=category)
        await interaction.response.send_message(f"📁 Moved {channel.mention} to **{category.name}**")


class CategoryGroup(app_commands.Group):
    def __init__(self):
        super().__init__(name="category", description="Create or delete categories")

    @app_commands.command(name="create", description="Create a new category")
    @app_commands.describe(name="Name of the new category")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def create(self, interaction: discord.Interaction, name: str):
        category = await interaction.guild.create_category(name)
        await interaction.response.send_message(f"✅ Created category **{category.name}**")

    @app_commands.command(name="delete", description="Delete a category")
    @app_commands.describe(
        category="The category to delete",
        delete_channels="Also delete every channel inside it (default: off)",
    )
    @app_commands.checks.has_permissions(manage_channels=True)
    async def delete(self, interaction: discord.Interaction, category: discord.CategoryChannel,
                      delete_channels: bool = False):
        await interaction.response.defer(ephemeral=True)
        name = category.name
        count = 0
        if delete_channels:
            for ch in list(category.channels):
                await ch.delete(reason="Category deleted")
                count += 1
                await asyncio.sleep(0.3)
        await category.delete()
        extra = f" and its {count} channel(s)" if delete_channels else ""
        await interaction.followup.send(f"🗑️ Deleted category **{name}**{extra}", ephemeral=True)


bot.tree.add_command(ChannelGroup())
bot.tree.add_command(CategoryGroup())


# ──────────────────────────────────────────────
# ─── SERVER AUTO-SETUP (TEMPLATES) ───
# ──────────────────────────────────────────────

VERIFY_ROLE_KEY = "verify_role_id"
VERIFY_CHANNEL_KEY = "verify_channel_id"


def template_summary(key: str) -> str:
    tpl = TEMPLATES[key]
    num_roles = len(tpl["roles"])
    num_categories = len(tpl["categories"])
    num_channels = sum(len(cat["channels"]) for cat in tpl["categories"])
    return f"**{num_roles}** roles · **{num_categories}** categories · **{num_channels}** channels"


async def delete_channels_except(guild: discord.Guild, keep_channel: Optional[discord.abc.GuildChannel] = None) -> int:
    count = 0
    for channel in list(guild.channels):
        if keep_channel and channel.id == keep_channel.id:
            continue
        try:
            await channel.delete(reason="Server template setup cleanup")
            count += 1
            await asyncio.sleep(0.3)
        except (discord.Forbidden, discord.HTTPException):
            pass
    return count


async def build_server_from_template(guild: discord.Guild, key: str) -> dict:
    """Create every role/category/channel described by the template. Returns counts."""
    tpl = TEMPLATES[key]
    created = {"roles": 0, "categories": 0, "channels": 0}

    for role_spec in tpl["roles"]:
        await guild.create_role(
            name=role_spec["name"],
            color=role_spec["color"],
            hoist=role_spec["hoist"],
            mentionable=role_spec["mentionable"],
            reason="Server template setup",
        )
        created["roles"] += 1
        await asyncio.sleep(0.3)

    for cat_spec in tpl["categories"]:
        category = await guild.create_category(cat_spec["name"], reason="Server template setup")
        created["categories"] += 1
        await asyncio.sleep(0.3)
        for ch_spec in cat_spec["channels"]:
            await create_channel_of_type(
                guild, ch_spec["name"], ch_spec["type"], category, ch_spec.get("topic")
            )
            created["channels"] += 1
            await asyncio.sleep(0.3)

    return created


async def setup_verification_system(guild: discord.Guild) -> dict:
    """Create a complete button-based verification system automatically."""
    existing_role = discord.utils.get(guild.roles, name="Verified")
    verified_role = existing_role or await guild.create_role(
        name="Verified",
        color=discord.Color.green(),
        hoist=False,
        mentionable=False,
        reason="Automatic verification setup",
    )

    verify_channel = guild.get_channel(get_guild_config(guild.id).get(VERIFY_CHANNEL_KEY, 0))
    if not isinstance(verify_channel, discord.TextChannel):
        info_category = discord.utils.find(
            lambda c: isinstance(c, discord.CategoryChannel) and c.name == "📋 INFORMATION",
            guild.categories,
        )
        verify_channel = discord.utils.get(guild.text_channels, name="verify")
        if not verify_channel:
            verify_channel = await guild.create_text_channel(
                "verify",
                category=info_category,
                topic="Verify here to unlock the server.",
                reason="Automatic verification setup",
            )

    # Make the verification channel accessible to everyone.
    await verify_channel.set_permissions(
        guild.default_role,
        view_channel=True,
        send_messages=False,
        read_message_history=True,
        reason="Automatic verification setup",
    )
    await verify_channel.set_permissions(
        verified_role,
        view_channel=True,
        send_messages=False,
        read_message_history=True,
        reason="Automatic verification setup",
    )

    # Lock normal server channels for unverified members.
    for channel in guild.channels:
        if channel.id == verify_channel.id:
            continue
        try:
            if isinstance(channel, discord.TextChannel):
                await channel.set_permissions(
                    guild.default_role,
                    view_channel=False,
                    reason="Automatic verification setup",
                )
                await channel.set_permissions(
                    verified_role,
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                    reason="Automatic verification setup",
                )
            elif isinstance(channel, discord.VoiceChannel):
                await channel.set_permissions(
                    guild.default_role,
                    view_channel=False,
                    reason="Automatic verification setup",
                )
                await channel.set_permissions(
                    verified_role,
                    view_channel=True,
                    connect=True,
                    speak=True,
                    reason="Automatic verification setup",
                )
        except (discord.Forbidden, discord.HTTPException):
            pass

    set_guild_config(guild.id, VERIFY_ROLE_KEY, verified_role.id)
    set_guild_config(guild.id, VERIFY_CHANNEL_KEY, verify_channel.id)

    # Avoid duplicate panels when setup is run again.
    try:
        async for message in verify_channel.history(limit=50):
            if message.author.id == bot.user.id and message.components:
                await message.edit(view=VerifyView())
                return {"role": verified_role, "channel": verify_channel, "created_panel": False}
    except (discord.Forbidden, discord.HTTPException):
        pass

    embed = discord.Embed(
        title="🛡️ Server Verification",
        description=(
            "Welcome! Click the button below to verify your account and unlock the server.\n\n"
            "After verification, your **Verified** role will be added automatically."
        ),
        color=discord.Color.green(),
    )
    embed.set_footer(text="Automatic verification system")
    await verify_channel.send(embed=embed, view=VerifyView())
    return {"role": verified_role, "channel": verify_channel, "created_panel": True}


class VerifyView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Verify",
        style=discord.ButtonStyle.green,
        emoji="✅",
        custom_id="server_verify_button",
    )
    async def verify(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("This button can only be used inside a server.", ephemeral=True)

        role_id = get_guild_config(interaction.guild.id).get(VERIFY_ROLE_KEY, 0)
        role = interaction.guild.get_role(role_id)
        if not role:
            return await interaction.response.send_message(
                "The verification system is not configured correctly. Please contact an administrator.",
                ephemeral=True,
            )

        if role in interaction.user.roles:
            return await interaction.response.send_message("You are already verified.", ephemeral=True)

        try:
            await interaction.user.add_roles(role, reason="Server verification")
        except discord.Forbidden:
            return await interaction.response.send_message(
                "I cannot assign the Verified role. Please check my role position and permissions.",
                ephemeral=True,
            )

        await interaction.response.send_message(
            "✅ You are now verified. Welcome to the server!",
            ephemeral=True,
        )


class TemplateModeSelect(discord.ui.Select):
    def __init__(self, author_id: int, template_key: str, keep_channel_id: int):
        self.author_id = author_id
        self.template_key = template_key
        self.keep_channel_id = keep_channel_id
        options = [
            discord.SelectOption(
                label="Delete all channels",
                value="delete_all",
                description="Delete every channel and category before setup.",
                emoji="🗑️",
            ),
            discord.SelectOption(
                label="Delete all except this channel",
                value="keep_command_channel",
                description="Keep the channel where /setup was used and delete everything else.",
                emoji="📌",
            ),
            discord.SelectOption(
                label="Do not delete anything",
                value="keep_all",
                description="Keep all existing channels and categories.",
                emoji="🛡️",
            ),
        ]
        super().__init__(
            placeholder="Choose what to do with existing channels...",
            options=options,
            min_values=1,
            max_values=1,
        )

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.author_id:
            return await interaction.response.send_message(
                "Only the person who ran /setup can choose this option.", ephemeral=True
            )
        await interaction.response.edit_message(
            embed=discord.Embed(
                title="⚙️ Setup Options Selected",
                description=(
                    f"Template: **{TEMPLATES[self.template_key]['label']}**\n"
                    f"Channel cleanup mode: **{self.values[0]}**\n\n"
                    "The server will now be prepared, built, and verified automatically."
                ),
                color=TEMPLATES[self.template_key]["color"],
            ),
            view=ConfirmBuildView(
                self.author_id,
                self.template_key,
                self.values[0],
                self.keep_channel_id,
            ),
        )


class ConfirmBuildView(discord.ui.View):
    def __init__(self, author_id: int, template_key: str, cleanup_mode: str, keep_channel_id: int):
        super().__init__(timeout=120)
        self.author_id = author_id
        self.template_key = template_key
        self.cleanup_mode = cleanup_mode
        self.keep_channel_id = keep_channel_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "Only the person who ran /setup can confirm this.", ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="Start Setup", style=discord.ButtonStyle.green, emoji="🚀")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        for child in self.children:
            child.disabled = True

        tpl = TEMPLATES[self.template_key]
        await interaction.response.edit_message(
            embed=discord.Embed(
                title=f"{tpl['emoji']} Setting up {tpl['label']}...",
                description="Please wait. The server structure and verification system are being configured automatically.",
                color=tpl["color"],
            ),
            view=self,
        )

        try:
            deleted = 0
            if self.cleanup_mode == "delete_all":
                deleted = await delete_channels_except(interaction.guild)
            elif self.cleanup_mode == "keep_command_channel":
                keep = interaction.guild.get_channel(self.keep_channel_id)
                deleted = await delete_channels_except(interaction.guild, keep)

            created = await build_server_from_template(interaction.guild, self.template_key)
            verification = await setup_verification_system(interaction.guild)

        except discord.Forbidden:
            fail_embed = discord.Embed(
                title="❌ Missing Permissions",
                description=(
                    "I need **Manage Channels**, **Manage Roles**, and permission to manage the Verified role "
                    "to complete automatic setup."
                ),
                color=discord.Color.red(),
            )
            if self.cleanup_mode == "delete_all":
                return await interaction.followup.send(embed=fail_embed, ephemeral=True)
            return await interaction.edit_original_response(embed=fail_embed, view=None)
        except discord.HTTPException as exc:
            fail_embed = discord.Embed(
                title="❌ Setup Failed",
                description=f"Setup stopped because Discord returned an error: `{exc}`",
                color=discord.Color.red(),
            )
            if self.cleanup_mode == "delete_all":
                return await interaction.followup.send(embed=fail_embed, ephemeral=True)
            return await interaction.edit_original_response(embed=fail_embed, view=None)

        done_embed = discord.Embed(
            title=f"{tpl['emoji']} {tpl['label']} Setup Complete",
            description=(
                f"Created **{created['roles']}** roles, **{created['categories']}** categories, and **{created['channels']}** channels.\n\n"
                f"Deleted **{deleted}** existing channels/categories.\n"
                f"Verification is ready in {verification['channel'].mention}.\n\n"
                "No separate verification setup command is required."
            ),
            color=tpl["color"],
        )
        if self.cleanup_mode == "delete_all":
            await interaction.followup.send(embed=done_embed)
        else:
            await interaction.edit_original_response(embed=done_embed, view=None)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.grey, emoji="✖️")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            embed=discord.Embed(description="Setup cancelled. No changes were made.", color=discord.Color.greyple()),
            view=None,
        )


class TemplateSelect(discord.ui.Select):
    def __init__(self, author_id: int, command_channel_id: int):
        self.author_id = author_id
        self.command_channel_id = command_channel_id
        options = [
            discord.SelectOption(
                label=tpl["label"],
                value=key,
                description=tpl["description"][:100],
                emoji=tpl["emoji"],
            )
            for key, tpl in TEMPLATES.items()
        ]
        super().__init__(placeholder="Choose a server template...", options=options, min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.author_id:
            return await interaction.response.send_message(
                "Only the person who ran /setup can pick a template.", ephemeral=True
            )

        key = self.values[0]
        tpl = TEMPLATES[key]
        embed = discord.Embed(
            title=f"{tpl['emoji']} {tpl['label']}",
            description=f"{tpl['description']}\n\n{template_summary(key)}\n\nChoose how existing channels should be handled before setup.",
            color=tpl["color"],
        )
        await interaction.response.edit_message(
            embed=embed,
            view=TemplateModeView(self.author_id, key, self.command_channel_id),
        )


class TemplateSelectView(discord.ui.View):
    def __init__(self, author_id: int, command_channel_id: int):
        super().__init__(timeout=120)
        self.add_item(TemplateSelect(author_id, command_channel_id))


class TemplateModeView(discord.ui.View):
    def __init__(self, author_id: int, template_key: str, command_channel_id: int):
        super().__init__(timeout=120)
        self.add_item(TemplateModeSelect(author_id, template_key, command_channel_id))


class SetupGroup(app_commands.Group):
    def __init__(self):
        super().__init__(name="setup", description="Automatically configure this server")

    @app_commands.command(name="templates", description="Build this server from a ready-made template")
    @app_commands.checks.has_permissions(administrator=True)
    async def templates(self, interaction: discord.Interaction):
        e = discord.Embed(
            title="🏗️ Server Auto-Setup",
            description=(
                "Choose a template and the bot will automatically create the roles, categories, channels, "
                "and verification system.\n\n"
                "You can also choose whether existing channels should be deleted before setup."
            ),
            color=discord.Color.blurple(),
        )
        for key, tpl in TEMPLATES.items():
            e.add_field(name=f"{tpl['emoji']} {tpl['label']}", value=tpl["description"], inline=False)
        await interaction.response.send_message(
            embed=e,
            view=TemplateSelectView(interaction.user.id, interaction.channel.id),
        )

    @app_commands.command(name="wipe", description="Delete all channels and categories in this server")
    @app_commands.checks.has_permissions(administrator=True)
    async def wipe(self, interaction: discord.Interaction):
        warn_embed = discord.Embed(
            title="⚠️ Wipe all channels?",
            description=(
                f"This permanently deletes **every channel and category** in **{interaction.guild.name}**.\n"
                "Roles are not affected. This cannot be undone."
            ),
            color=discord.Color.red(),
        )
        await interaction.response.send_message(embed=warn_embed, view=WipeConfirmView(interaction.user.id))


class WipeConfirmView(discord.ui.View):
    def __init__(self, author_id: int):
        super().__init__(timeout=60)
        self.author_id = author_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "Only the person who ran this command can confirm it.", ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="Yes, delete everything", style=discord.ButtonStyle.red, emoji="🗑️")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(
            embed=discord.Embed(description="🗑️ Deleting channels...", color=discord.Color.red()), view=self
        )
        count = await delete_channels_except(interaction.guild)
        await interaction.edit_original_response(
            embed=discord.Embed(
                description=f"✅ Deleted {count} channels/categories.",
                color=discord.Color.green(),
            ),
            view=None,
        )

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.grey, emoji="✖️")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            embed=discord.Embed(description="Cancelled. Nothing was deleted.", color=discord.Color.greyple()),
            view=None,
        )


bot.tree.add_command(SetupGroup())



# ──────────────────────────────────────────────
# ─── INFO COMMANDS ───
# ──────────────────────────────────────────────

@bot.tree.command(name="serverinfo", description="Show information about this server")
async def serverinfo(interaction: discord.Interaction):
    g = interaction.guild
    e = discord.Embed(title=f"🏠 {g.name}", color=discord.Color.blurple())
    if g.icon:
        e.set_thumbnail(url=g.icon.url)
    e.add_field(name="Owner", value=str(g.owner))
    e.add_field(name="Members", value=g.member_count)
    e.add_field(name="Channels", value=len(g.channels))
    e.add_field(name="Roles", value=len(g.roles))
    e.add_field(name="Created On", value=g.created_at.strftime("%d/%m/%Y"))
    e.add_field(name="Boost Level", value=g.premium_tier)
    await interaction.response.send_message(embed=e)


@bot.tree.command(name="userinfo", description="Show information about a member")
@app_commands.describe(member="The member to look up (defaults to you)")
async def userinfo(interaction: discord.Interaction, member: Optional[discord.Member] = None):
    member = member or interaction.user
    roles = [r.mention for r in member.roles[1:]] or ["None"]
    e = discord.Embed(title=f"👤 {member}", color=member.color)
    e.set_thumbnail(url=member.display_avatar.url)
    e.add_field(name="ID", value=member.id)
    e.add_field(name="Account Created", value=member.created_at.strftime("%d/%m/%Y"))
    e.add_field(name="Joined Server", value=member.joined_at.strftime("%d/%m/%Y") if member.joined_at else "N/A")
    e.add_field(name="Roles", value=" ".join(roles)[:1024], inline=False)
    await interaction.response.send_message(embed=e)


@bot.tree.command(name="avatar", description="Show a member's avatar")
@app_commands.describe(member="The member to look up (defaults to you)")
async def avatar(interaction: discord.Interaction, member: Optional[discord.Member] = None):
    member = member or interaction.user
    e = discord.Embed(title=f"🖼️ {member}'s Avatar", color=discord.Color.blurple())
    e.set_image(url=member.display_avatar.url)
    await interaction.response.send_message(embed=e)


# ──────────────────────────────────────────────
# ─── POLL ───
# ──────────────────────────────────────────────

@bot.tree.command(name="poll", description="Create a simple 👍 / 👎 poll")
@app_commands.describe(question="The question to poll")
async def poll(interaction: discord.Interaction, question: str):
    e = discord.Embed(
        title="📊 Vote!",
        description=question,
        color=discord.Color.blurple()
    )
    e.set_footer(text=f"By {interaction.user}", icon_url=interaction.user.display_avatar.url)
    await interaction.response.send_message(embed=e)
    msg = await interaction.original_response()
    await msg.add_reaction("👍")
    await msg.add_reaction("👎")


# ──────────────────────────────────────────────
# ─── TICKET SYSTEM ───
# ──────────────────────────────────────────────

class TicketCloseView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔒 Close Ticket", style=discord.ButtonStyle.red, custom_id="close_ticket")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("🔒 Closing ticket...", ephemeral=True)
        await asyncio.sleep(3)
        await interaction.channel.delete(reason="Ticket closed")


class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🎫 Open Ticket", style=discord.ButtonStyle.green, custom_id="open_ticket")
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        existing = discord.utils.get(guild.channels, name=f"ticket-{interaction.user.name.lower()}")
        if existing:
            return await interaction.response.send_message(
                f"❌ You already have a ticket open: {existing.mention}", ephemeral=True
            )
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True),
        }
        ch = await guild.create_text_channel(
            f"ticket-{interaction.user.name}",
            overwrites=overwrites,
            reason="Ticket opened"
        )
        e = discord.Embed(
            title="🎫 Your Ticket",
            description=f"Hi {interaction.user.mention}!\nPlease describe your issue and staff will assist you.\nClick the button below to close this ticket.",
            color=discord.Color.green()
        )
        await ch.send(embed=e, view=TicketCloseView())
        await interaction.response.send_message(f"✅ Ticket created: {ch.mention}", ephemeral=True)


@bot.tree.command(name="ticket", description="Post the ticket system panel in this channel")
@app_commands.checks.has_permissions(manage_channels=True)
async def ticket_setup(interaction: discord.Interaction):
    e = discord.Embed(
        title="🎫 Support Ticket System",
        description="Click the button below to open a ticket and get help from staff",
        color=discord.Color.blurple()
    )
    await interaction.response.send_message(embed=e, view=TicketView())


# ──────────────────────────────────────────────
# ─── HELP ───
# ──────────────────────────────────────────────

@bot.tree.command(name="help", description="Show all available commands")
async def help_command(interaction: discord.Interaction):
    e = discord.Embed(title="📖 All Commands", color=discord.Color.blurple())
    e.add_field(name="⚙️ Configuration (admin only)", value="""
`/config show` `/config logchannel` `/config welcomechannel`
`/config mutedrole` `/config autorole`
""", inline=False)
    e.add_field(name="🔨 Moderation", value="""
`/ban` `/unban` `/kick` `/mute` `/unmute`
`/warn` `/warnings` `/clearwarn` `/clear`
`/slowmode` `/lock` `/unlock`
""", inline=False)
    e.add_field(name="📁 Channels", value="""
`/channel create` `/channel delete` `/channel rename` `/channel move`
`/category create` `/category delete`
""", inline=False)
    e.add_field(name="🏗️ Server Auto-Setup", value="`/setup templates` (automatic template + verification setup) `/setup wipe`", inline=False)
    e.add_field(name="ℹ️ Info", value="`/serverinfo` `/userinfo` `/avatar`", inline=False)
    e.add_field(name="📊 Other", value="`/poll` `/ticket` (sets up the ticket system)", inline=False)
    e.set_footer(text="Made by Manager Bot")
    await interaction.response.send_message(embed=e)


# ──────────────────────────────────────────────
# Error Handler
# Slash commands report errors through the app_commands tree rather
# than the classic on_command_error event.
# ──────────────────────────────────────────────

@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        message = "❌ You don't have permission to use this command"
    elif isinstance(error, app_commands.CommandOnCooldown):
        message = f"❌ This command is on cooldown, try again in {error.retry_after:.1f}s"
    else:
        print(f"Error: {error}")
        message = "❌ Something went wrong while running that command"

    if interaction.response.is_done():
        await interaction.followup.send(message, ephemeral=True)
    else:
        await interaction.response.send_message(message, ephemeral=True)


# ──────────────────────────────────────────────
# Run
# ──────────────────────────────────────────────

if __name__ == "__main__":
    bot.run(TOKEN)
