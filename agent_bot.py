import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
from langchain.llms import HuggingFaceEndpoint
from langchain.agents import Tool, initialize_agent, AgentType
from langchain.memory import ConversationBufferMemory
from langchain.prompts import MessagesPlaceholder
import asyncio
import datetime

load_dotenv()

# ---------- ตั้งค่า Discord Intents ----------
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# ---------- สร้าง Tools สำหรับ AI Agent ----------
# Tool 1: ลบข้อความในแชท
async def delete_messages(channel_id, amount=10):
    """ใช้สำหรับลบข้อความในแชท"""
    channel = bot.get_channel(int(channel_id))
    if channel:
        deleted = await channel.purge(limit=amount)
        return f"✅ ลบข้อความ {len(deleted)} ข้อความเรียบร้อย"
    return "❌ ไม่พบแชทที่ระบุ"

# Tool 2: เตะสมาชิก
async def kick_member(guild_id, member_name, reason="ไม่ระบุ"):
    """ใช้สำหรับเตะสมาชิกออกจากเซิร์ฟเวอร์"""
    guild = bot.get_guild(int(guild_id))
    if guild:
        for member in guild.members:
            if member_name.lower() in member.name.lower():
                await member.kick(reason=reason)
                return f"✅ เตะ {member.name} ออกจากเซิร์ฟเวอร์แล้ว (เหตุผล: {reason})"
    return f"❌ ไม่พบสมาชิกชื่อ {member_name}"

# Tool 3: ดูข้อมูลเซิร์ฟเวอร์
async def get_server_info(guild_id):
    """ดูข้อมูลพื้นฐานของเซิร์ฟเวอร์"""
    guild = bot.get_guild(int(guild_id))
    if guild:
        return f"""📊 **{guild.name}**
👑 เจ้าของ: {guild.owner}
👥 สมาชิก: {guild.member_count}
💬 แชท: {len(guild.text_channels)}
🎤 เสียง: {len(guild.voice_channels)}
🎭 บทบาท: {len(guild.roles)}"""
    return "❌ ไม่พบเซิร์ฟเวอร์"

# Tool 4: ค้นหาข้อความในแชท
async def search_messages(channel_id, keyword, limit=50):
    """ค้นหาข้อความที่มีคำสำคัญ"""
    channel = bot.get_channel(int(channel_id))
    if channel:
        results = []
        async for msg in channel.history(limit=limit):
            if keyword.lower() in msg.content.lower():
                results.append(f"{msg.author.name}: {msg.content[:100]}...")
        
        if results:
            return f"🔍 พบ {len(results)} ข้อความ:\n" + "\n".join(results[:10])
        return f"🔍 ไม่พบคำว่า '{keyword}' ใน {limit} ข้อความล่าสุด"
    return "❌ ไม่พบแชท"

# Tool 5: เวลาปัจจุบัน
def get_current_time():
    """ดูเวลาปัจจุบัน"""
    now = datetime.datetime.now()
    return f"🕐 ปัจจุบัน: {now.strftime('%d/%m/%Y %H:%M:%S')}"

# ---------- สร้าง LangChain Agent ----------
# เปลี่ยน async function ให้เป็น sync สำหรับ LangChain
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
        description="ลบข้อความในแชท ใช้เมื่อมีคนขอให้ลบข้อความ รูปแบบ: channel_id|จำนวน (เช่น 123456789|20)"
    ),
    Tool(
        name="KickMember", 
        func=lambda x: kick_member_sync(*x.split('|')) if '|' in x else kick_member_sync(x, "", ""),
        description="เตะสมาชิกออกจากเซิร์ฟเวอร์ ใช้เมื่อมีคนขอให้เตะใคร รูปแบบ: guild_id|ชื่อสมาชิก|เหตุผล"
    ),
    Tool(
        name="GetServerInfo",
        func=get_server_info_sync,
        description="ดูข้อมูลเซิร์ฟเวอร์ ใช้เมื่อมีคนถามเกี่ยวกับข้อมูลเซิร์ฟเวอร์"
    ),
    Tool(
        name="SearchMessages",
        func=lambda x: search_messages_sync(*x.split('|')) if '|' in x else search_messages_sync(x, "", 50),
        description="ค้นหาข้อความในแชท ใช้เมื่อมีคนขอให้ค้นหาข้อความ รูปแบบ: channel_id|คำค้นหา|จำนวนข้อความ"
    ),
    Tool(
        name="GetCurrentTime",
        func=lambda _: get_current_time(),
        description="ดูเวลาปัจจุบัน ใช้เมื่อมีคนถามเกี่ยวกับเวลา"
    )
]

# ตั้งค่า Hugging Face LLM
llm = HuggingFaceEndpoint(
    repo_id="mistralai/Mistral-7B-Instruct-v0.3",
    huggingfacehub_api_token=os.getenv("HUGGINGFACE_TOKEN"),
    max_new_tokens=512,
    temperature=0.7,
    task="text-generation"
)

# เพิ่ม Memory ให้แอ๊กจำบทสนทนาได้
memory = ConversationBufferMemory(
    memory_key="chat_history",
    return_messages=True,
    output_key="output"
)

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
    await bot.change_presence(activity=discord.Game(name="🤖 AI Agent | @me to chat"))

@bot.command(name='agent')
async def agent_command(ctx, *, prompt: str):
    """คุยกับ AI Agent (เขาจะตัดสินใจเองว่าต้องทำอะไร)"""
    async with ctx.typing():
        try:
            # Agent จะวิเคราะห์และเลือกใช้ Tool อัตโนมัติ
            response = agent.run(prompt)
            
            # ถ้า Agent ตอบเป็น list หรือ dict ให้แปลง
            if isinstance(response, dict):
                response = str(response)
            
            # ส่งตอบกลับ (Discord จำกัด 2000 ตัวอักษร)
            for i in range(0, len(response), 1900):
                await ctx.send(response[i:i+1900])
                
        except Exception as e:
            await ctx.send(f"❌ Agent error: {str(e)[:100]}")

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    
    # เมื่อมีคน @ บอท
    if bot.user in message.mentions:
        prompt = message.content.replace(f'<@{bot.user.id}>', '').strip()
        if prompt:
            async with message.channel.typing():
                try:
                    response = agent.run(prompt)
                    # ตอบกลับในเธรด
                    await message.reply(str(response)[:1900])
                except Exception as e:
                    await message.reply(f"❌ {str(e)[:100]}")
        else:
            await message.reply("👋 สวัสดีครับ! พิมพ์ `!agent` ตามด้วยคำสั่ง หรือ @ผม แล้วบอกสิ่งที่ต้องการได้เลย เช่น:\n- ช่วยลบข้อความ 20 ข้อความล่าสุด\n- ข้อมูลเซิร์ฟเวอร์นี้หน่อย\n- ตอนนี้กี่โมง")
    
    await bot.process_commands(message)

@bot.command(name='clear_agent')
async def clear_agent_memory(ctx):
    """ล้างความจำของ Agent"""
    memory.clear()
    await ctx.send("🧹 ล้างความจำ Agent เรียบร้อย! ตอนนี้ Agent จะเริ่มบทสนทนาใหม่")

@bot.command(name='ping')
async def ping(ctx):
    """เช็คสถานะบอท"""
    await ctx.send(f'🏓 Pong! `{round(bot.latency * 1000)}ms`')

# ---------- ระบบ Auto-Mod (Agent คอยดูลบข้อความไม่เหมาะสมอัตโนมัติ) ----------
BAD_WORDS = ["คำหยาบ1", "คำหยาบ2"]  # ใส่คำที่ต้องการบล็อค

@bot.event
async def on_message_edit(before, after):
    """เมื่อมีการแก้ไขข้อความ ให้ Agent ตรวจสอบ"""
    await auto_mod_check(after)

async def auto_mod_check(message):
    """Agent ตรวจสอบข้อความอัตโนมัติ (สามารถปรับให้ AI ตัดสินใจเองได้)"""
    if message.author == bot.user:
        return
    
    # ตรวจสอบคำต้องห้าม
    content_lower = message.content.lower()
    for bad_word in BAD_WORDS:
        if bad_word in content_lower:
            await message.delete()
            await message.channel.send(f"⚠️ {message.author.mention} โปรดใช้ภาษาให้สุภาพ (Agent ลบข้อความอัตโนมัติ)", delete_after=5)
            break

# ---------- รันบอท ----------
if __name__ == "__main__":
    bot.run(os.getenv("DISCORD_TOKEN"))