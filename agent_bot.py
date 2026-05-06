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

load_dotenv()

# ---------- Discord Setup ----------
intents = discord.Intents.all()
bot = commands.Bot(command_prefix='!', intents=intents)

# Hugging Face Client
hf_client = InferenceClient(
    "mistralai/Mistral-7B-Instruct-v0.3",
    token=os.getenv("HUGGINGFACE_TOKEN")
)

# ---------- Terminal Tools ----------
class Terminal:
    @staticmethod
    async def run_command(command: str) -> str:
        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd="/app"
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=30)
            output = stdout.decode('utf-8', errors='replace')
            error = stderr.decode('utf-8', errors='replace')
            result = ""
            if output:
                result += f"📤 {output[:1800]}"
            if error:
                result += f"\n⚠️ {error[:500]}"
            return result[:1900] if result else "✅ Done"
        except asyncio.TimeoutError:
            return "⏰ Timeout"
        except Exception as e:
            return f"❌ {str(e)}"
    
    @staticmethod
    async def read_file(path: str) -> str:
        try:
            with open(path, 'r') as f:
                return f"```\n{f.read()[:1500]}\n```"
        except Exception as e:
            return f"❌ {str(e)}"
    
    @staticmethod
    async def write_file(path: str, content: str) -> str:
        try:
            with open(path, 'w') as f:
                f.write(content)
            return f"✅ Written to {path}"
        except Exception as e:
            return f"❌ {str(e)}"
    
    @staticmethod
    async def list_files(path: str = ".") -> str:
        try:
            files = os.listdir(path)
            return "\n".join([f"📄 {f}" for f in files[:30]])
        except Exception as e:
            return f"❌ {str(e)}"

# ---------- Discord Tools ----------
class DiscordTools:
    def __init__(self, bot):
        self.bot = bot
        self.terminal = Terminal()
    
    async def delete_messages(self, channel_id: int, amount: int = 10):
        channel = self.bot.get_channel(channel_id)
        if channel:
            deleted = await channel.purge(limit=amount)
            return f"✅ Deleted {len(deleted)} messages"
        return "❌ Channel not found"
    
    async def kick(self, guild_id: int, member_name: str, reason: str = ""):
        guild = self.bot.get_guild(guild_id)
        if guild:
            for member in guild.members:
                if member_name.lower() in member.name.lower():
                    await member.kick(reason=reason)
                    return f"✅ Kicked {member.name}"
        return f"❌ Member {member_name} not found"
    
    async def ban(self, guild_id: int, member_name: str, reason: str = ""):
        guild = self.bot.get_guild(guild_id)
        if guild:
            for member in guild.members:
                if member_name.lower() in member.name.lower():
                    await member.ban(reason=reason)
                    return f"✅ Banned {member.name}"
        return f"❌ Member {member_name} not found"
    
    async def create_channel(self, guild_id: int, name: str):
        guild = self.bot.get_guild(guild_id)
        if guild:
            channel = await guild.create_text_channel(name)
            return f"✅ Created #{channel.name}"
        return "❌ Guild not found"
    
    async def delete_channel(self, channel_id: int):
        channel = self.bot.get_channel(channel_id)
        if channel:
            await channel.delete()
            return f"✅ Deleted #{channel.name}"
        return "❌ Channel not found"
    
    async def send_dm(self, user_id: int, message: str):
        user = await self.bot.fetch_user(user_id)
        if user:
            await user.send(message)
            return f"✅ Sent DM to {user.name}"
        return "❌ User not found"
    
    async def get_members(self, guild_id: int):
        guild = self.bot.get_guild(guild_id)
        if guild:
            names = [m.name for m in guild.members[:20]]
            return f"Members ({len(guild.members)}):\n" + "\n".join(names)
        return "❌ Guild not found"
    
    async def timeout(self, guild_id: int, member_name: str, minutes: int):
        guild = self.bot.get_guild(guild_id)
        if guild:
            for member in guild.members:
                if member_name.lower() in member.name.lower():
                    duration = discord.utils.utcnow() + datetime.timedelta(minutes=minutes)
                    await member.timeout(duration)
                    return f"✅ Timed out {member.name} for {minutes} minutes"
        return f"❌ Member {member_name} not found"
    
    async def search(self, channel_id: int, keyword: str, limit: int = 100):
        channel = self.bot.get_channel(channel_id)
        if channel:
            results = []
            async for msg in channel.history(limit=limit):
                if keyword.lower() in msg.content.lower():
                    results.append(f"{msg.author.name}: {msg.content[:80]}")
            if results:
                return f"Found {len(results)}:\n" + "\n".join(results[:10])
            return f"No results for '{keyword}'"
        return "❌ Channel not found"
    
    # Terminal commands
    async def terminal(self, command: str):
        return await self.terminal.run_command(command)
    
    async def cat(self, path: str):
        return await self.terminal.read_file(path)
    
    async def write(self, path: str, content: str):
        return await self.terminal.write_file(path, content)
    
    async def ls(self, path: str = "."):
        return await self.terminal.list_files(path)
    
    async def info(self):
        result = await self.terminal.run_command("python --version && echo '---' && pwd && echo '---' && ls -la | head -5")
        return f"📊 System Info:\n{result}"
    
    async def restart(self):
        asyncio.create_task(self._restart_task())
        return "🔄 Restarting..."
    
    async def _restart_task(self):
        await asyncio.sleep(2)
        os._exit(0)

# ---------- AI Agent ----------
class GodAgent:
    def __init__(self, bot, tools):
        self.bot = bot
        self.tools = tools
        self.memory = []
    
    async def think(self, prompt: str, guild_id: int, channel_id: int) -> str:
        # Build tool list
        tool_list = []
        for name in dir(self.tools):
            if not name.startswith("_") and callable(getattr(self.tools, name)):
                tool_list.append(f"- {name}")
        
        system_prompt = f"""You are a GOD MODE AI Agent with FULL CONTROL over Discord.

AVAILABLE TOOLS:
{chr(10).join(tool_list)}

Current context:
- guild_id: {guild_id}
- channel_id: {channel_id}

Recent memory:
{chr(10).join(self.memory[-8:])}

User request: "{prompt}"

IMPORTANT: Respond ONLY with a JSON object in this format:
{{"action": "tool_name", "args": [arg1, arg2, ...]}}

If user just asked a question (not asking you to DO something), respond with a normal text message.

Choose the right tool and execute immediately. Don't ask questions back."""

        try:
            response = hf_client.text_generation(
                system_prompt,
                max_new_tokens=300,
                temperature=0.5
            )
            
            # Try to parse JSON
            json_match = re.search(r'\{[^{}]*\}', response)
            if json_match:
                cmd = json.loads(json_match.group())
                action = cmd.get("action")
                args = cmd.get("args", [])
                
                if action and hasattr(self.tools, action):
                    func = getattr(self.tools, action)
                    result = await func(*args)
                    self.memory.append(f"Q: {prompt}\nA: {result[:100]}")
                    return result
                else:
                    return f"❌ Tool '{action}' not found. Available: {', '.join([t.replace('- ', '') for t in tool_list[:10]])}"
            else:
                # Normal text response
                self.memory.append(f"Q: {prompt}\nA: {response[:100]}")
                return response[:1900]
                
        except Exception as e:
            return f"❌ Error: {str(e)[:100]}"

# ---------- Discord Events ----------
tools = DiscordTools(bot)
agent = GodAgent(bot, tools)

@bot.event
async def on_ready():
    print(f'✅ {bot.user} is ONLINE with GOD MODE!')
    print(f'📡 Connected to {len(bot.guilds)} servers')
    await bot.change_presence(activity=discord.Game(name="💀 GOD MODE | @me"))

@bot.command(name='god')
async def god_cmd(ctx, *, prompt: str):
    """Talk to the God Agent"""
    async with ctx.typing():
        result = await agent.think(prompt, ctx.guild.id, ctx.channel.id)
        await ctx.send(str(result)[:1900])

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    
    # When bot is mentioned
    if bot.user in message.mentions:
        prompt = message.content.replace(f'<@{bot.user.id}>', '').strip()
        if prompt:
            async with message.channel.typing():
                result = await agent.think(prompt, message.guild.id, message.channel.id)
                await message.reply(str(result)[:1900])
    
    await bot.process_commands(message)

@bot.command(name='ping')
async def ping(ctx):
    await ctx.send(f'🏓 Pong! `{round(bot.latency * 1000)}ms`')

@bot.command(name='clear_memory')
async def clear_memory(ctx):
    agent.memory = []
    await ctx.send("🧹 Memory cleared!")

# ---------- Run ----------
if __name__ == "__main__":
    bot.run(os.getenv("DISCORD_TOKEN"))