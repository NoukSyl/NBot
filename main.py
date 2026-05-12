import discord
from discord.ext import commands, tasks
from discord import app_commands
import datetime
import asyncio
import os
from dotenv import load_dotenv
from collections import defaultdict

# ──────────────────────────────────────────────
# โหลด Environment Variables
# ──────────────────────────────────────────────
load_dotenv()

TOKEN            = os.getenv("DISCORD_TOKEN")
PREFIX           = os.getenv("PREFIX", "!")
LOG_CHANNEL_ID   = int(os.getenv("LOG_CHANNEL_ID", 0))
WELCOME_CHANNEL_ID = int(os.getenv("WELCOME_CHANNEL_ID", 0))
MUTED_ROLE_ID    = int(os.getenv("MUTED_ROLE_ID", 0))
AUTO_ROLE_ID     = int(os.getenv("AUTO_ROLE_ID", 0))

# ──────────────────────────────────────────────
# ตั้งค่า Bot
# ──────────────────────────────────────────────
intents = discord.Intents.all()
bot = commands.Bot(command_prefix=PREFIX, intents=intents, help_command=None)
tree = bot.tree

# เก็บข้อมูล warn และ spam
warn_data: dict[int, list] = defaultdict(list)       # {user_id: [reason, ...]}
spam_tracker: dict[int, list] = defaultdict(list)    # {user_id: [timestamps]}
SPAM_LIMIT = 5      # จำนวนข้อความสูงสุดใน
SPAM_INTERVAL = 5   # วินาที


# ──────────────────────────────────────────────
# Helper: Log
# ──────────────────────────────────────────────
async def send_log(guild: discord.Guild, embed: discord.Embed):
    if LOG_CHANNEL_ID:
        ch = guild.get_channel(LOG_CHANNEL_ID)
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
    await tree.sync()
    await bot.change_presence(
        activity=discord.Activity(type=discord.ActivityType.watching, name=f"{PREFIX}help | Manager Bot")
    )
    print(f"✅ บอทออนไลน์แล้ว: {bot.user} ({bot.user.id})")


@bot.event
async def on_member_join(member: discord.Member):
    # Welcome Message
    if WELCOME_CHANNEL_ID:
        ch = member.guild.get_channel(WELCOME_CHANNEL_ID)
        if ch:
            e = discord.Embed(
                title="👋 ยินดีต้อนรับ!",
                description=f"สวัสดี {member.mention}! ยินดีต้อนรับสู่ **{member.guild.name}** 🎉",
                color=discord.Color.green()
            )
            e.set_thumbnail(url=member.display_avatar.url)
            e.set_footer(text=f"สมาชิกคนที่ {member.guild.member_count}")
            await ch.send(embed=e)

    # Auto-Role
    if AUTO_ROLE_ID:
        role = member.guild.get_role(AUTO_ROLE_ID)
        if role:
            await member.add_roles(role, reason="Auto-Role")

    # Log
    await send_log(member.guild, log_embed(
        "📥 สมาชิกเข้าร่วม", discord.Color.green(),
        สมาชิก=f"{member} ({member.id})",
        บัญชีสร้างเมื่อ=member.created_at.strftime("%d/%m/%Y %H:%M")
    ))


@bot.event
async def on_member_remove(member: discord.Member):
    if WELCOME_CHANNEL_ID:
        ch = member.guild.get_channel(WELCOME_CHANNEL_ID)
        if ch:
            e = discord.Embed(
                title="👋 สมาชิกออกจากเซิร์ฟเวอร์",
                description=f"**{member}** ได้ออกจากเซิร์ฟเวอร์แล้ว",
                color=discord.Color.red()
            )
            await ch.send(embed=e)

    await send_log(member.guild, log_embed(
        "📤 สมาชิกออก", discord.Color.red(),
        สมาชิก=f"{member} ({member.id})"
    ))


@bot.event
async def on_message_delete(message: discord.Message):
    if message.author.bot:
        return
    await send_log(message.guild, log_embed(
        "🗑️ ข้อความถูกลบ", discord.Color.orange(),
        ผู้ส่ง=str(message.author),
        ห้อง=message.channel.mention,
        ข้อความ=message.content or "*(ไม่มีข้อความ)*"
    ))


@bot.event
async def on_message_edit(before: discord.Message, after: discord.Message):
    if before.author.bot or before.content == after.content:
        return
    await send_log(before.guild, log_embed(
        "✏️ ข้อความถูกแก้ไข", discord.Color.blue(),
        ผู้ส่ง=str(before.author),
        ห้อง=before.channel.mention,
        ก่อนหน้า=before.content or "*(ว่าง)*",
        หลังแก้ไข=after.content or "*(ว่าง)*"
    ))


# ──────────────────────────────────────────────
# Anti-Spam
# ──────────────────────────────────────────────
@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or not message.guild:
        return

    uid = message.author.id
    now = datetime.datetime.utcnow().timestamp()
    spam_tracker[uid] = [t for t in spam_tracker[uid] if now - t < SPAM_INTERVAL]
    spam_tracker[uid].append(now)

    if len(spam_tracker[uid]) >= SPAM_LIMIT:
        await message.delete()
        muted_role = message.guild.get_role(MUTED_ROLE_ID)
        if muted_role:
            await message.author.add_roles(muted_role, reason="Anti-Spam Auto-Mute")
        try:
            await message.author.send(
                f"⚠️ คุณถูก Mute อัตโนมัติเพราะส่งข้อความเร็วเกินไปใน **{message.guild.name}**"
            )
        except discord.Forbidden:
            pass
        spam_tracker[uid] = []
        await send_log(message.guild, log_embed(
            "🤖 Anti-Spam: Auto-Mute", discord.Color.dark_red(),
            ผู้ใช้=f"{message.author} ({uid})",
            ห้อง=message.channel.mention
        ))
        return

    await bot.process_commands(message)


# ──────────────────────────────────────────────
# ─── MODERATION COMMANDS ───
# ──────────────────────────────────────────────

@bot.command(name="ban")
@commands.has_permissions(ban_members=True)
async def ban(ctx, member: discord.Member, *, reason="ไม่ระบุเหตุผล"):
    await member.ban(reason=reason)
    e = discord.Embed(title="🔨 แบนสมาชิก", color=discord.Color.red())
    e.add_field(name="สมาชิก", value=str(member))
    e.add_field(name="เหตุผล", value=reason)
    e.add_field(name="โดย", value=str(ctx.author))
    await ctx.send(embed=e)
    await send_log(ctx.guild, e)


@bot.command(name="unban")
@commands.has_permissions(ban_members=True)
async def unban(ctx, user_id: int):
    user = await bot.fetch_user(user_id)
    await ctx.guild.unban(user)
    await ctx.send(embed=discord.Embed(
        title="✅ Unban แล้ว",
        description=f"**{user}** ถูก Unban แล้ว",
        color=discord.Color.green()
    ))


@bot.command(name="kick")
@commands.has_permissions(kick_members=True)
async def kick(ctx, member: discord.Member, *, reason="ไม่ระบุเหตุผล"):
    await member.kick(reason=reason)
    e = discord.Embed(title="👢 Kick สมาชิก", color=discord.Color.orange())
    e.add_field(name="สมาชิก", value=str(member))
    e.add_field(name="เหตุผล", value=reason)
    e.add_field(name="โดย", value=str(ctx.author))
    await ctx.send(embed=e)
    await send_log(ctx.guild, e)


@bot.command(name="mute")
@commands.has_permissions(manage_roles=True)
async def mute(ctx, member: discord.Member, duration: int = 0, *, reason="ไม่ระบุเหตุผล"):
    """mute @user [นาที] [เหตุผล]"""
    muted_role = ctx.guild.get_role(MUTED_ROLE_ID)
    if not muted_role:
        return await ctx.send("❌ ไม่พบ Muted Role กรุณาตั้งค่า MUTED_ROLE_ID ใน .env")
    await member.add_roles(muted_role, reason=reason)
    e = discord.Embed(title="🔇 Mute สมาชิก", color=discord.Color.dark_grey())
    e.add_field(name="สมาชิก", value=str(member))
    e.add_field(name="ระยะเวลา", value=f"{duration} นาที" if duration else "ถาวร")
    e.add_field(name="เหตุผล", value=reason)
    await ctx.send(embed=e)
    await send_log(ctx.guild, e)
    if duration > 0:
        await asyncio.sleep(duration * 60)
        if muted_role in member.roles:
            await member.remove_roles(muted_role, reason="หมดเวลา Mute")


@bot.command(name="unmute")
@commands.has_permissions(manage_roles=True)
async def unmute(ctx, member: discord.Member):
    muted_role = ctx.guild.get_role(MUTED_ROLE_ID)
    if muted_role and muted_role in member.roles:
        await member.remove_roles(muted_role)
        await ctx.send(embed=discord.Embed(
            title="🔊 Unmute แล้ว",
            description=f"**{member}** ถูก Unmute แล้ว",
            color=discord.Color.green()
        ))
    else:
        await ctx.send("❌ สมาชิกนี้ไม่ได้ถูก Mute อยู่")


@bot.command(name="warn")
@commands.has_permissions(manage_messages=True)
async def warn(ctx, member: discord.Member, *, reason="ไม่ระบุเหตุผล"):
    warn_data[member.id].append(reason)
    count = len(warn_data[member.id])
    e = discord.Embed(title="⚠️ เตือน", color=discord.Color.yellow())
    e.add_field(name="สมาชิก", value=str(member))
    e.add_field(name="เหตุผล", value=reason)
    e.add_field(name="จำนวน Warn", value=f"{count}")
    await ctx.send(embed=e)
    await send_log(ctx.guild, e)
    try:
        await member.send(f"⚠️ คุณได้รับการเตือนใน **{ctx.guild.name}**: {reason} (ครั้งที่ {count})")
    except discord.Forbidden:
        pass


@bot.command(name="warnings")
async def warnings(ctx, member: discord.Member):
    warns = warn_data.get(member.id, [])
    e = discord.Embed(title=f"⚠️ Warns ของ {member}", color=discord.Color.yellow())
    if warns:
        for i, w in enumerate(warns, 1):
            e.add_field(name=f"#{i}", value=w, inline=False)
    else:
        e.description = "ไม่มี Warn"
    await ctx.send(embed=e)


@bot.command(name="clearwarn")
@commands.has_permissions(manage_messages=True)
async def clearwarn(ctx, member: discord.Member):
    warn_data[member.id] = []
    await ctx.send(f"✅ ล้าง Warn ของ **{member}** แล้ว")


@bot.command(name="clear")
@commands.has_permissions(manage_messages=True)
async def clear(ctx, amount: int = 10):
    deleted = await ctx.channel.purge(limit=amount + 1)
    msg = await ctx.send(f"🧹 ลบ {len(deleted)-1} ข้อความแล้ว")
    await asyncio.sleep(3)
    await msg.delete()


@bot.command(name="slowmode")
@commands.has_permissions(manage_channels=True)
async def slowmode(ctx, seconds: int = 0):
    await ctx.channel.edit(slowmode_delay=seconds)
    await ctx.send(f"⏱️ Slowmode: **{seconds} วินาที**" if seconds else "⏱️ ปิด Slowmode แล้ว")


@bot.command(name="lock")
@commands.has_permissions(manage_channels=True)
async def lock(ctx):
    overwrite = ctx.channel.overwrites_for(ctx.guild.default_role)
    overwrite.send_messages = False
    await ctx.channel.set_permissions(ctx.guild.default_role, overwrite=overwrite)
    await ctx.send("🔒 ล็อคห้องนี้แล้ว")


@bot.command(name="unlock")
@commands.has_permissions(manage_channels=True)
async def unlock(ctx):
    overwrite = ctx.channel.overwrites_for(ctx.guild.default_role)
    overwrite.send_messages = True
    await ctx.channel.set_permissions(ctx.guild.default_role, overwrite=overwrite)
    await ctx.send("🔓 ปลดล็อคห้องนี้แล้ว")


# ──────────────────────────────────────────────
# ─── INFO COMMANDS ───
# ──────────────────────────────────────────────

@bot.command(name="serverinfo")
async def serverinfo(ctx):
    g = ctx.guild
    e = discord.Embed(title=f"🏠 {g.name}", color=discord.Color.blurple())
    e.set_thumbnail(url=g.icon.url if g.icon else discord.Embed.Empty)
    e.add_field(name="เจ้าของ", value=str(g.owner))
    e.add_field(name="สมาชิก", value=g.member_count)
    e.add_field(name="ห้อง", value=len(g.channels))
    e.add_field(name="Roles", value=len(g.roles))
    e.add_field(name="สร้างเมื่อ", value=g.created_at.strftime("%d/%m/%Y"))
    e.add_field(name="Boost Level", value=g.premium_tier)
    await ctx.send(embed=e)


@bot.command(name="userinfo")
async def userinfo(ctx, member: discord.Member = None):
    member = member or ctx.author
    roles = [r.mention for r in member.roles[1:]] or ["ไม่มี"]
    e = discord.Embed(title=f"👤 {member}", color=member.color)
    e.set_thumbnail(url=member.display_avatar.url)
    e.add_field(name="ID", value=member.id)
    e.add_field(name="สร้างบัญชี", value=member.created_at.strftime("%d/%m/%Y"))
    e.add_field(name="เข้าร่วมเซิร์ฟ", value=member.joined_at.strftime("%d/%m/%Y") if member.joined_at else "N/A")
    e.add_field(name="Roles", value=" ".join(roles)[:1024], inline=False)
    await ctx.send(embed=e)


@bot.command(name="avatar")
async def avatar(ctx, member: discord.Member = None):
    member = member or ctx.author
    e = discord.Embed(title=f"🖼️ Avatar ของ {member}", color=discord.Color.blurple())
    e.set_image(url=member.display_avatar.url)
    await ctx.send(embed=e)


# ──────────────────────────────────────────────
# ─── POLL ───
# ──────────────────────────────────────────────

@bot.command(name="poll")
async def poll(ctx, *, question: str):
    """สร้าง Poll ง่าย ๆ ด้วย 👍 / 👎"""
    e = discord.Embed(
        title="📊 โหวต!",
        description=question,
        color=discord.Color.blurple()
    )
    e.set_footer(text=f"โดย {ctx.author}", icon_url=ctx.author.display_avatar.url)
    msg = await ctx.send(embed=e)
    await msg.add_reaction("👍")
    await msg.add_reaction("👎")
    await ctx.message.delete()


# ──────────────────────────────────────────────
# ─── TICKET SYSTEM ───
# ──────────────────────────────────────────────

class TicketCloseView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔒 ปิด Ticket", style=discord.ButtonStyle.red, custom_id="close_ticket")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("🔒 กำลังปิด Ticket...", ephemeral=True)
        await asyncio.sleep(3)
        await interaction.channel.delete(reason="ปิด Ticket")


class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🎫 เปิด Ticket", style=discord.ButtonStyle.green, custom_id="open_ticket")
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        existing = discord.utils.get(guild.channels, name=f"ticket-{interaction.user.name.lower()}")
        if existing:
            return await interaction.response.send_message(
                f"❌ คุณมี Ticket อยู่แล้ว: {existing.mention}", ephemeral=True
            )
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True),
        }
        ch = await guild.create_text_channel(
            f"ticket-{interaction.user.name}",
            overwrites=overwrites,
            reason="เปิด Ticket"
        )
        e = discord.Embed(
            title="🎫 Ticket ของคุณ",
            description=f"สวัสดี {interaction.user.mention}!\nกรุณาอธิบายปัญหา แล้วทีมงานจะมาช่วยเหลือ\nกดปุ่มด้านล่างเพื่อปิด Ticket",
            color=discord.Color.green()
        )
        await ch.send(embed=e, view=TicketCloseView())
        await interaction.response.send_message(f"✅ สร้าง Ticket แล้ว: {ch.mention}", ephemeral=True)


@bot.command(name="ticket")
@commands.has_permissions(manage_channels=True)
async def ticket_setup(ctx):
    """ตั้งค่าระบบ Ticket"""
    e = discord.Embed(
        title="🎫 ระบบ Ticket Support",
        description="กดปุ่มด้านล่างเพื่อเปิด Ticket และขอความช่วยเหลือจากทีมงาน",
        color=discord.Color.blurple()
    )
    await ctx.send(embed=e, view=TicketView())
    await ctx.message.delete()


# ──────────────────────────────────────────────
# ─── HELP ───
# ──────────────────────────────────────────────

@bot.command(name="help")
async def help_command(ctx):
    e = discord.Embed(title="📖 คำสั่งทั้งหมด", color=discord.Color.blurple())
    e.add_field(name="🔨 Moderation", value="""
`ban` `unban` `kick` `mute [นาที]` `unmute`
`warn` `warnings` `clearwarn` `clear [จำนวน]`
`slowmode [วินาที]` `lock` `unlock`
""", inline=False)
    e.add_field(name="ℹ️ ข้อมูล", value="`serverinfo` `userinfo [@user]` `avatar [@user]`", inline=False)
    e.add_field(name="📊 อื่น ๆ", value="`poll [คำถาม]` `ticket` (ตั้งค่าระบบ Ticket)", inline=False)
    e.set_footer(text=f"Prefix: {PREFIX} | ทำโดย Manager Bot")
    await ctx.send(embed=e)


# ──────────────────────────────────────────────
# Error Handler
# ──────────────────────────────────────────────

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ คุณไม่มีสิทธิ์ใช้คำสั่งนี้")
    elif isinstance(error, commands.MemberNotFound):
        await ctx.send("❌ ไม่พบสมาชิกที่ระบุ")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ ใช้งานไม่ถูกต้อง: `{PREFIX}help` เพื่อดูวิธีใช้")
    else:
        print(f"Error: {error}")


# ──────────────────────────────────────────────
# Run
# ──────────────────────────────────────────────

if __name__ == "__main__":
    bot.run(TOKEN)
