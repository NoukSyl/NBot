import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
from langchain_huggingface import HuggingFaceEndpoint
from langchain.tools import Tool  # เปลี่ยนตรงนี้
from langchain.agents import initialize_agent, AgentType
from langchain.memory import ConversationBufferMemory
import asyncio
import datetime

load_dotenv()

# ---------- ตั้งค่า Discord Intents ----------
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix='!', intents=intents)

# ---------- สร้าง Tools สำหรับ AI Agent ----------
async def delete_messages(channel_id, amount=10):
    channel = bot.get_channel(int(channel_id))
    if channel:
        deleted = await channel.purge(limit=amount)
        return f"✅ ลบข้อความ {len(deleted)} ข้อความเรียบร้อย"
    return "❌ ไม่พบแชทที่ระบุ"

async def kick_member(guild_id, member_name, reason="ไม่ระบุ"):
    guild = bot.get_guild(int(guild_id))
    if guild:
        for member in guild.members:
            if member_name.lower() in member.name.lower():
                await member.kick(reason=reason)
                return f"✅ เตะ {member.name} ออกจากเซิร์ฟเวอร์แล้ว"
    return f"❌ ไม่พบสมาชิกชื่อ {member_name}"

async def get_server_info(guild_id):
    guild = bot.get_guild(int(guild_id))
    if guild:
        return f"""📊 **{guild.name}**
👑 เจ้าของ: {guild.owner}
👥 สมาชิก: {guild.member_count}
💬 แชท: {len(guild.text_channels)}
🎤 เสียง: {len(guild.voice_channels)}"""
    return "❌ ไม่พบเซิร์ฟเวอร์"

async def search_messages(channel_id, keyword, limit=50):
    channel = bot.get_channel(int(channel_id))
    if channel:
        results = []
        async for msg in channel.history(limit=limit):
            if keyword.lower() in msg.content.lower():
                results.append(f"{msg.author.name}: {msg.content[:100]}...")
        if results:
            return f"🔍 พบ {len(results)} ข้อความ:\n" + "\n".join(results[:10])
        return f"🔍 ไม่พบคำว่า '{keyword}'"
    return "❌ ไม่พบแชท"

def get_current_time():
    now = datetime.datetime.now()
    return f"🕐 {now.strftime('%d/%m/%Y %H:%M:%S')}"

# sync wrappers
def delete_messages_sync(channel_id, amount=10):
    return asyncio.run(delete_messages(channel_id, amount))

def kick_member_sync(guild_id, member_name, reason=""):
    return asyncio.run(kick_member(guild_id, member_name, reason))

def get_server_info_sync(guild_id):
    return asyncio.run(get_server_info(guild_id))

def search_messages_sync(channel_id, keyword, limit=50):
    return asyncio.run(search_messages(channel_id, keyword, limit))

# สร้าง Tools
tools = [
    Tool(
        name="DeleteMessages",
        func=lambda x: delete_messages_sync(*x.split('|')) if '|' in x else delete_messages_sync(x, 10),
        description="ลบข้อความ ใช้เมื่อมีคนขอให้ลบข้อความ รูปแบบ: channel_id|จำนวน"
    ),
    Tool(
        name="KickMember", 
        func=lambda x: kick_member_sync(*x.split('|')) if '|' in x else kick_member_sync(x, "", ""),
        description="เตะสมาชิก ใช้เมื่อมีคนขอให้เตะใคร รูปแบบ: guild_id|ชื่อสมาชิก|เหตุผล"
    ),
    Tool(
        name="GetServerInfo",
        func=get_server_info_sync,
        description="ดูข้อมูลเซิร์ฟเวอร์"
    ),
    Tool(
        name="SearchMessages",
        func=lambda x: search_messages_sync(*x.split('|')) if '|' in x else search_messages_sync(x, "", 50),
        description="ค้นหาข้อความ รูปแบบ: channel_id|คำค้นหา"
    ),
    Tool(
        name="GetCurrentTime",
        func=lambda _: get_current_time(),
        description="ดูเวลาปัจจุบัน"
    )
]

# ตั้งค่า Hugging Face LLM
llm = HuggingFaceEndpoint(
    repo_id="microsoft/DialoGPT-medium",
    huggingfacehub_api_token=os.getenv("HUGGINGFACE_TOKEN"),
    max_new_tokens=512,
    temperature=0.7
)

# เพิ่ม Memory
memory = ConversationBufferMemory(memory_key="chat_history", return_messages=True)

# สร้าง Agent
agent = initialize_agent(
    tools,
    llm,
    agent=AgentType.CONVERSATIONAL_REACT_DESCRIPTION,
    memory=memory,
    verbose=True,
    handle_parsing_errors=True,
    max_iterations=3
)

# ---------- Discord Bot Commands ----------
@bot.event
async def on_ready():
    print(f'✅ AI Agent {bot.user} is online!')
    print(f'📡 Connected to {len(bot.guilds)} servers')
    await bot.change_presence(activity=discord.Game(name="🤖 AI Agent | @me"))

@bot.command(name='agent')
async def agent_command(ctx, *, prompt: str):
    async with ctx.typing():
        try:
            response = agent.run(prompt)
            await ctx.send(str(response)[:1900])
        except Exception as e:
            await ctx.send(f"❌ Error: {str(e)[:100]}")

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    
    if bot.user in message.mentions:
        prompt = message.content.replace(f'<@{bot.user.id}>', '').strip()
        if prompt:
            async with message.channel.typing():
                try:
                    response = agent.run(prompt)
                    await message.reply(str(response)[:1900])
                except Exception as e:
                    await message.reply(f"❌ {str(e)[:100]}")
        else:
            await message.reply("👋 พิมพ์ `!agent` หรือ @ฉัน แล้วบอกสิ่งที่ต้องการได้เลย")
    
    await bot.process_commands(message)

@bot.command(name='ping')
async def ping(ctx):
    await ctx.send(f'🏓 Pong! `{round(bot.latency * 1000)}ms`')

@bot.command(name='clear_memory')
async def clear_memory(ctx):
    memory.clear()
    await ctx.send("🧹 ล้างความจำ Agent เรียบร้อย!")

if __name__ == "__main__":
    bot.run(os.getenv("DISCORD_TOKEN"))