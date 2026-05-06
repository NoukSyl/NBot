import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
from huggingface_hub import InferenceClient
import json
import re
import asyncio
import datetime
import subprocess
import requests
from bs4 import BeautifulSoup

load_dotenv()

intents = discord.Intents.all()
bot = commands.Bot(command_prefix='!', intents=intents)

hf_client = InferenceClient(
    "mistralai/Mistral-7B-Instruct-v0.3",
    token=os.getenv("HUGGINGFACE_TOKEN")
)

class Terminal:
    @staticmethod
    async def run_command(command: str, timeout: int = 30) -> str:
        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd="/app"
            )
            try:
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
            except asyncio.TimeoutError:
                process.kill()
                return f"⏰ คำสั่งใช้เวลานานเกิน {timeout} วินาที"
            
            output = stdout.decode('utf-8', errors='replace')
            error = stderr.decode('utf-8', errors='replace')
            
            result = ""
            if output:
                result += f"📤 OUTPUT:\n{output[:1800]}"
            if error:
                result += f"\n⚠️ ERROR:\n{error[:500]}"
            if process.returncode != 0:
                result += f"\n🔴 Exit code: {process.returncode}"
            
            return result[:1900] if result else f"✅ '{command}' รันสำเร็จ"
        except Exception as e:
            return f"❌ {str(e)}"
    
    @staticmethod
    async def read_file(filepath: str) -> str:
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return f"📄 {filepath}:\n```\n{f.read()[:1500]}\n```"
        except Exception as e:
            return f"❌ {str(e)}"
    
    @staticmethod
    async def write_file(filepath: str, content: str) -> str:
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            return f"✅ เขียน {filepath} เรียบร้อย"
        except Exception as e:
            return f"❌ {str(e)}"
    
    @staticmethod
    async def list_files(path: str = ".") -> str:
        try:
            files = os.listdir(path)
            formatted = "\n".join([f"📁 {f}/" if os.path.isdir(os.path.join(path, f)) else f"📄 {f}" for f in files[:50]])
            return f"📂 {path}:\n{formatted}"
        except Exception as e:
            return f"❌ {str(e)}"

class WebTools:
    @staticmethod
    async def fetch_url(url: str) -> str:
        """ดึงเนื้อหาจาก URL"""
        try:
            response = requests.get(url, timeout=15, headers={'User-Agent': 'Mozilla/5.0'})
            soup = BeautifulSoup(response.text, 'html.parser')
            # เอาเฉพาะ text
            text = soup.get_text()
            # ตัดเหลื่อม
            text = re.sub(r'\n+', '\n', text)
            return f"🌐 {url}:\n{text[:1500]}"
        except Exception as e:
            return f"❌ ดึงข้อมูลไม่ได้: {str(e)}"
    
    @staticmethod
    async def search_web(query: str) -> str:
        """ค้นหา Google (ใช้ DuckDuckGo แทน)"""
        try:
            url = f"https://html.duckduckgo.com/html/?q={query.replace(' ', '+')}"
            response = requests.get(url, timeout=15)
            soup = BeautifulSoup(response.text, 'html.parser')
            results = soup.find_all('a', class_='result__a')[:5]
            if results:
                links = []
                for r in results:
                    links.append(f"- {r.get_text()}")
                return f"🔍 ผลการค้นหา '{query}':\n" + "\n".join(links)
            return "🔍 ไม่พบผลการค้นหา"
        except Exception as e:
            return f"❌ {str(e)}"

class DiscordTools:
    def __init__(self, bot):
        self.bot = bot
        self.terminal = Terminal()
        self.web = WebTools()
    
    # Terminal
    async def run_terminal(self, command): return await self.terminal.run_command(command)
    async def read_file(self, filepath): return await self.terminal.read_file(filepath)
    async def write_file(self, filepath, content): return await self.terminal.write_file(filepath, content)
    async def list_files(self, path="."): return await self.terminal.list_files(path)
    
    # Web
    async def fetch_url(self, url): return await self.web.fetch_url(url)
    async def search_web(self, query): return await self.web.search_web(query)
    
    # Discord Moderation
    async def delete_messages(self, channel_id, amount=10):
        channel = self.bot.get_channel(int(channel_id))
        if channel:
            deleted = await channel.purge(limit=amount)
            return f"✅ ลบ {len(deleted)} ข้อความ"
        return "❌ ไม่พบแชท"
    
    async def kick_member(self, guild_id, member_name, reason=""):
        guild = self.bot.get_guild(int(guild_id))
        if guild:
            for member in guild.members:
                if member_name.lower() in member.name.lower():
                    await member.kick(reason=reason)
                    return f"✅ เตะ {member.name}"
        return f"❌ ไม่พบ {member_name}"
    
    async def ban_member(self, guild_id, member_name, reason=""):
        guild = self.bot.get_guild(int(guild_id))
        if guild:
            for member in guild.members:
                if member_name.lower() in member.name.lower():
                    await member.ban(reason=reason)
                    return f"✅ แบน {member.name}"
        return f"❌ ไม่พบ {member_name}"
    
    async def create_channel(self, guild_id, name, channel_type="text"):
        guild = self.bot.get_guild(int(guild_id))
        if guild:
            if channel_type == "text":
                channel = await guild.create_text_channel(name)
            else:
                channel = await guild.create_voice_channel(name)
            return f"✅ สร้าง #{channel.name}"
        return "❌ ไม่พบเซิร์ฟเวอร์"
    
    async def delete_channel(self, channel_id):
        channel = self.bot.get_channel(int(channel_id))
        if channel:
            await channel.delete()
            return f"✅ ลบ {channel.name}"
        return "❌ ไม่พบห้อง"
    
    async def send_dm(self, user_id, message):
        user = await self.bot.fetch_user(int(user_id))
        if user:
            await user.send(message)
            return f"✅ ส่งถึง {user.name}"
        return "❌ ไม่พบผู้ใช้"
    
    async def get_members(self, guild_id):
        guild = self.bot.get_guild(int(guild_id))
        if guild:
            members = "\n".join([f"- {m.name}" for m in guild.members[:20]])
            return f"👥 {len(guild.members)} คน:\n{members}"
        return "❌ ไม่พบ"
    
    async def get_channels(self, guild_id):
        guild = self.bot.get_guild(int(guild_id))
        if guild:
            channels = "\n".join([f"#{c.name}" for c in guild.text_channels[:20]])
            return f"💬 {len(guild.text_channels)} ห้อง:\n{channels}"
        return "❌ ไม่พบ"
    
    async def timeout_member(self, guild_id, member_name, minutes):
        guild = self.bot.get_guild(int(guild_id))
        if guild:
            for member in guild.members:
                if member_name.lower() in member.name.lower():
                    duration = discord.utils.utcnow() + datetime.timedelta(minutes=minutes)
                    await member.timeout(duration)
                    return f"✅ จำกัด {member.name} {minutes} นาที"
        return f"❌ ไม่พบ {member_name}"
    
    async def search_chat(self, channel_id, keyword, limit=100):
        channel = self.bot.get_channel(int(channel_id))
        if channel:
            results = []
            async for msg in channel.history(limit=limit):
                if keyword.lower() in msg.content.lower():
                    results.append(f"{msg.author.name}: {msg.content[:100]}")
            if results:
                return f"🔍 พบ {len(results)}:\n" + "\n".join(results[:10])
            return f"🔍 ไม่พบ '{keyword}'"
        return "❌ ไม่พบห้อง"
    
    async def get_system_info(self):
        return await self.terminal.run_command("echo '🐍 Python:' && python --version 2>&1 && echo '📁 PWD:' && pwd && echo '📂 Files:' && ls -la | head -10")
    
    async def restart_self(self):
        asyncio.create_task(self._restart_task())
        return "🔄 กำลังรีสตาร์ท..."
    
    async def _restart_task(self):
        await asyncio.sleep(2)
        os._exit(0)

class GodAgent:
    def __init__(self, bot, tools):
        self.bot = bot
        self.tools = tools
        self.memory = []
    
    async def think_and_act(self, prompt, channel_id, guild_id, author_id):
        tool_list = [f"- {m}" for m in dir(self.tools) if not m.startswith("_") and callable(getattr(self.tools, m)) and m not in ['bot', 'terminal', 'web']]
        
        system_prompt = f"""คุณคือ GOD MODE AI Agent มีอำนาจเต็ม

Tools: {tool_list}

Context: guild={guild_id}, channel={channel_id}

Memory: {chr(10).join(self.memory[-10:])}

User: {prompt}

ตอบเป็น JSON: {{"action": "tool_name", "args": [arg1, arg2]}} หรือตอบข้อความปกติ"""

        response = hf_client.text_generation(system_prompt, max_new_tokens=400, temperature=0.5)
        
        try:
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                cmd = json.loads(json_match.group())
                action = cmd.get("action")
                args = cmd.get("args", [])
                if hasattr(self.tools, action):
                    func = getattr(self.tools, action)
                    result = await func(*args) if asyncio.iscoroutinefunction(func) else func(*args)
                    self.memory.append(f"User: {prompt}\nResult: {result}")
                    return result
        except:
            pass
        
        self.memory.append(f"User: {prompt}\nAssistant: {response[:200]}")
        return response

tools = DiscordTools(bot)
agent = GodAgent(bot, tools)

@bot.event
async def on_ready():
    print(f'✅ {bot.user} ONLINE!')
    await bot.change_presence(activity=discord.Game(name="💀 GOD MODE | @me"))

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    if bot.user in message.mentions:
        prompt = message.content.replace(f'<@{bot.user.id}>', '').strip()
        if prompt:
            async with message.channel.typing():
                result = await agent.think_and_act(prompt, message.channel.id, message.guild.id, message.author.id)
                await message.reply(str(result)[:1900])
    await bot.process_commands(message)

@bot.command(name='ping')
async def ping(ctx):
    await ctx.send(f'🏓 {round(bot.latency * 1000)}ms')

bot.run(os.getenv("DISCORD_TOKEN"))