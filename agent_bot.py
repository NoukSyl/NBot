import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
from huggingface_hub import InferenceClient
import json
import re
import asyncio
import datetime

load_dotenv()

# ---------- Discord Setup ----------
intents = discord.Intents.all()
bot = commands.Bot(command_prefix='!', intents=intents)

# Hugging Face Client — model specified directly to avoid auto-router error
HF_MODEL = "HuggingFaceH4/zephyr-7b-beta"  # Free, instruction-tuned, no provider issues
hf_client = InferenceClient(
    model=HF_MODEL,
    token=os.getenv("HUGGINGFACE_TOKEN")
)

# ---------- Admin Check ----------
def is_admin(ctx_or_member):
    """Check if user has Administrator permission or is server owner"""
    if isinstance(ctx_or_member, commands.Context):
        member = ctx_or_member.author
        guild = ctx_or_member.guild
    elif isinstance(ctx_or_member, discord.Message):
        member = ctx_or_member.author
        guild = ctx_or_member.guild
    else:
        member = ctx_or_member
        guild = getattr(member, "guild", None)

    if not guild:
        return False
    if guild.owner_id == member.id:
        return True
    if isinstance(member, discord.Member) and member.guild_permissions.administrator:
        return True
    return False

def admin_only():
    async def predicate(ctx):
        if not is_admin(ctx):
            await ctx.send("🔒 **Access Denied** — Admin only.")
            return False
        return True
    return commands.check(predicate)

# ---------- Tools ----------
class Tools:
    def __init__(self, bot):
        self.bot = bot

    # --- Discord Tools ---
    async def send_message(self, channel_id: int, message: str) -> str:
        """Send a message to a channel"""
        channel = self.bot.get_channel(int(channel_id))
        if channel:
            await channel.send(message)
            return f"✅ Sent message to #{channel.name}"
        return "❌ Channel not found"

    async def delete_messages(self, channel_id: int, amount: int = 10) -> str:
        """Delete messages from a channel"""
        channel = self.bot.get_channel(int(channel_id))
        if channel:
            deleted = await channel.purge(limit=int(amount))
            return f"✅ Deleted {len(deleted)} messages from #{channel.name}"
        return "❌ Channel not found"

    async def kick_member(self, guild_id: int, member_name: str, reason: str = "No reason") -> str:
        """Kick a member from the server"""
        guild = self.bot.get_guild(int(guild_id))
        if guild:
            for member in guild.members:
                if member_name.lower() in member.name.lower():
                    await member.kick(reason=reason)
                    return f"✅ Kicked {member.name} (Reason: {reason})"
        return f"❌ Member '{member_name}' not found"

    async def ban_member(self, guild_id: int, member_name: str, reason: str = "No reason") -> str:
        """Ban a member from the server"""
        guild = self.bot.get_guild(int(guild_id))
        if guild:
            for member in guild.members:
                if member_name.lower() in member.name.lower():
                    await member.ban(reason=reason)
                    return f"✅ Banned {member.name} (Reason: {reason})"
        return f"❌ Member '{member_name}' not found"

    async def timeout_member(self, guild_id: int, member_name: str, minutes: int) -> str:
        """Timeout a member"""
        guild = self.bot.get_guild(int(guild_id))
        if guild:
            for member in guild.members:
                if member_name.lower() in member.name.lower():
                    until = discord.utils.utcnow() + datetime.timedelta(minutes=int(minutes))
                    await member.timeout(until)
                    return f"✅ Timed out {member.name} for {minutes} minutes"
        return f"❌ Member '{member_name}' not found"

    async def create_channel(self, guild_id: int, name: str, channel_type: str = "text") -> str:
        """Create a new channel"""
        guild = self.bot.get_guild(int(guild_id))
        if guild:
            if channel_type == "voice":
                channel = await guild.create_voice_channel(name)
            else:
                channel = await guild.create_text_channel(name)
            return f"✅ Created {channel_type} channel #{channel.name}"
        return "❌ Guild not found"

    async def delete_channel(self, channel_id: int) -> str:
        """Delete a channel"""
        channel = self.bot.get_channel(int(channel_id))
        if channel:
            name = channel.name
            await channel.delete()
            return f"✅ Deleted channel #{name}"
        return "❌ Channel not found"

    async def send_dm(self, user_id: int, message: str) -> str:
        """Send a DM to a user"""
        try:
            user = await self.bot.fetch_user(int(user_id))
            await user.send(message)
            return f"✅ Sent DM to {user.name}"
        except Exception as e:
            return f"❌ Failed: {str(e)}"

    async def get_members(self, guild_id: int) -> str:
        """List members in the server"""
        guild = self.bot.get_guild(int(guild_id))
        if guild:
            members = guild.members
            lines = [f"• {m.name}{'  [BOT]' if m.bot else ''}" for m in members[:30]]
            return f"👥 Members ({len(members)} total):\n" + "\n".join(lines)
        return "❌ Guild not found"

    async def get_channels(self, guild_id: int) -> str:
        """List all channels in the server"""
        guild = self.bot.get_guild(int(guild_id))
        if guild:
            lines = [f"• #{c.name} (id:{c.id})" for c in guild.channels[:30]]
            return f"📋 Channels ({len(guild.channels)} total):\n" + "\n".join(lines)
        return "❌ Guild not found"

    async def search_messages(self, channel_id: int, keyword: str, limit: int = 100) -> str:
        """Search messages in a channel"""
        channel = self.bot.get_channel(int(channel_id))
        if channel:
            results = []
            async for msg in channel.history(limit=int(limit)):
                if keyword.lower() in msg.content.lower():
                    results.append(f"{msg.author.name}: {msg.content[:80]}")
            if results:
                return f"🔍 Found {len(results)} results:\n" + "\n".join(results[:15])
            return f"No messages found for '{keyword}'"
        return "❌ Channel not found"

    async def add_role(self, guild_id: int, member_name: str, role_name: str) -> str:
        """Add a role to a member"""
        guild = self.bot.get_guild(int(guild_id))
        if guild:
            role = discord.utils.get(guild.roles, name=role_name)
            if not role:
                return f"❌ Role '{role_name}' not found"
            for member in guild.members:
                if member_name.lower() in member.name.lower():
                    await member.add_roles(role)
                    return f"✅ Added role '{role_name}' to {member.name}"
        return f"❌ Member '{member_name}' not found"

    async def remove_role(self, guild_id: int, member_name: str, role_name: str) -> str:
        """Remove a role from a member"""
        guild = self.bot.get_guild(int(guild_id))
        if guild:
            role = discord.utils.get(guild.roles, name=role_name)
            if not role:
                return f"❌ Role '{role_name}' not found"
            for member in guild.members:
                if member_name.lower() in member.name.lower():
                    await member.remove_roles(role)
                    return f"✅ Removed role '{role_name}' from {member.name}"
        return f"❌ Member '{member_name}' not found"

    async def server_info(self, guild_id: int) -> str:
        """Get server information"""
        guild = self.bot.get_guild(int(guild_id))
        if guild:
            return (
                f"🏰 **{guild.name}**\n"
                f"• ID: {guild.id}\n"
                f"• Owner: {guild.owner}\n"
                f"• Members: {guild.member_count}\n"
                f"• Channels: {len(guild.channels)}\n"
                f"• Roles: {len(guild.roles)}\n"
                f"• Created: {guild.created_at.strftime('%Y-%m-%d')}\n"
                f"• Boost Level: {guild.premium_tier}"
            )
        return "❌ Guild not found"

    async def run_command(self, command: str) -> str:
        """Run a shell command on the server"""
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
                result += f"📤 Output:\n{output[:1500]}"
            if error:
                result += f"\n⚠️ Error:\n{error[:400]}"
            return result[:1900] if result else "✅ Command executed (no output)"
        except asyncio.TimeoutError:
            return "⏰ Command timed out (30s)"
        except Exception as e:
            return f"❌ {str(e)}"

    async def read_file(self, path: str) -> str:
        """Read a file"""
        try:
            with open(path, 'r') as f:
                content = f.read()
            return f"📄 `{path}`:\n```\n{content[:1500]}\n```"
        except Exception as e:
            return f"❌ {str(e)}"

    async def write_file(self, path: str, content: str) -> str:
        """Write content to a file"""
        try:
            with open(path, 'w') as f:
                f.write(content)
            return f"✅ Written to `{path}`"
        except Exception as e:
            return f"❌ {str(e)}"

    async def list_files(self, path: str = "/app") -> str:
        """List files in a directory"""
        try:
            files = os.listdir(path)
            lines = [f"📄 {f}" for f in files[:30]]
            return f"📁 `{path}`:\n" + "\n".join(lines)
        except Exception as e:
            return f"❌ {str(e)}"

    def get_tool_descriptions(self) -> str:
        tools = []
        for name in dir(self):
            if not name.startswith("_") and name != "get_tool_descriptions" and callable(getattr(self, name)):
                func = getattr(self, name)
                doc = func.__doc__ or "No description"
                tools.append(f"- {name}: {doc}")
        return "\n".join(tools)


# ---------- ReAct Agent ----------
class ReActAgent:
    def __init__(self, bot, tools: Tools):
        self.bot = bot
        self.tools = tools
        self.memory = []  # long-term memory across conversations
        self.MAX_STEPS = 6

    async def run(self, user_request: str, guild_id: int, channel_id: int, status_callback=None) -> str:
        """
        True ReAct loop:
        Thought → Action → Observation → Thought → Action → ... → Final Answer
        """
        steps = []
        step_num = 0

        # Build context
        tool_descriptions = self.tools.get_tool_descriptions()
        memory_str = "\n".join(self.memory[-6:]) if self.memory else "None"

        system_prompt = f"""You are a GOD MODE AI Agent with FULL CONTROL over a Discord server.
You operate in a strict ReAct (Reason + Act) loop. Each step you MUST output EXACTLY one of these formats:

FORMAT A — When you need to use a tool:
Thought: <your reasoning about what to do next>
Action: <tool_name>
Args: <JSON array of arguments>

FORMAT B — When you have the final answer:
Thought: <final reasoning>
Final Answer: <your response to the user>

AVAILABLE TOOLS:
{tool_descriptions}

CONTEXT:
- guild_id: {guild_id}
- channel_id: {channel_id}
- memory: {memory_str}

RULES:
- Always start with a Thought
- Use tools step by step, one at a time
- After each Observation, decide next step
- When task is complete, give Final Answer
- Never hallucinate tool results
- If a tool fails, try another approach

USER REQUEST: {user_request}"""

        # conversation history as plain text for text_generation
        conversation = ""

        while step_num < self.MAX_STEPS:
            step_num += 1

            # Build prompt: system + conversation so far
            prompt = system_prompt + "\n" + conversation

            # Call AI via text_generation (no router, works with free HF token)
            try:
                response = hf_client.text_generation(
                    prompt,
                    max_new_tokens=400,
                    temperature=0.3,
                    stop_sequences=["Observation:"],
                    do_sample=True,
                )
            except Exception as e:
                return f"❌ AI Error: {str(e)[:150]}"

            steps.append(response)

            # Parse response
            thought_match = re.search(r'Thought:\s*(.+?)(?=Action:|Final Answer:|$)', response, re.DOTALL)
            action_match = re.search(r'Action:\s*(\w+)', response)
            args_match = re.search(r'Args:\s*(\[.*?\])', response, re.DOTALL)
            final_match = re.search(r'Final Answer:\s*(.+)', response, re.DOTALL)

            thought = thought_match.group(1).strip() if thought_match else ""

            # Final Answer reached
            if final_match:
                final = final_match.group(1).strip()
                self.memory.append(f"[{datetime.datetime.now().strftime('%H:%M')}] Q: {user_request[:80]} → {final[:80]}")
                if len(self.memory) > 20:
                    self.memory = self.memory[-20:]

                # Build step summary
                step_log = f"🧠 **Steps taken: {step_num-1}**\n" if step_num > 2 else ""
                return step_log + final

            # Execute Action
            if action_match:
                tool_name = action_match.group(1).strip()
                args = []
                if args_match:
                    try:
                        args = json.loads(args_match.group(1))
                    except:
                        args = []

                # Status update
                if status_callback:
                    await status_callback(f"⚙️ Step {step_num}: `{tool_name}({', '.join(str(a) for a in args[:2])}...)`")

                # Run tool
                if hasattr(self.tools, tool_name):
                    try:
                        func = getattr(self.tools, tool_name)
                        observation = await func(*args)
                    except Exception as e:
                        observation = f"❌ Tool error: {str(e)}"
                else:
                    observation = f"❌ Tool '{tool_name}' not found"

                # Add observation back to messages for next iteration
                messages.append({
                    "role": "assistant",
                    "content": response
                })
                messages.append({
                    "role": "user",
                    "content": f"Observation: {observation}\n\nContinue the ReAct loop."
                })

            else:
                # AI didn't follow format — try to recover
                messages.append({
                    "role": "assistant",
                    "content": response
                })
                messages.append({
                    "role": "user",
                    "content": "You must follow the ReAct format. Either output 'Action:' with a tool, or 'Final Answer:' when done."
                })

        return "⚠️ Max steps reached without completing the task."


# ---------- Bot Setup ----------
tools = Tools(bot)
agent = ReActAgent(bot, tools)


@bot.event
async def on_ready():
    print(f'✅ {bot.user} is ONLINE — True ReAct Agent Mode')
    print(f'📡 Connected to {len(bot.guilds)} servers')
    await bot.change_presence(activity=discord.Game(name="🤖 ReAct Agent | !N"))


@bot.command(name='N')
@admin_only()
async def N_cmd(ctx, *, prompt: str):
    """[ADMIN ONLY] Talk to the ReAct Agent"""
    status_msg = await ctx.send("🤔 Thinking...")

    async def update_status(text):
        try:
            await status_msg.edit(content=text)
        except:
            pass

    result = await agent.run(prompt, ctx.guild.id, ctx.channel.id, status_callback=update_status)
    await status_msg.edit(content=result[:1900])


@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    # Mention handler — admin only
    if bot.user in message.mentions:
        if not is_admin(message):
            await message.reply("🔒 Only admins can use this bot.")
            return

        prompt = message.content.replace(f'<@{bot.user.id}>', '').strip()
        if prompt:
            status_msg = await message.reply("🤔 Thinking...")

            async def update_status(text):
                try:
                    await status_msg.edit(content=text)
                except:
                    pass

            result = await agent.run(prompt, message.guild.id, message.channel.id, status_callback=update_status)
            await status_msg.edit(content=result[:1900])
        await bot.process_commands(message)
        return

    # Admin auto-respond: if admin sends any message (not a command), reply without needing !N
    if not message.content.startswith('!') and is_admin(message) and message.guild:
        prompt = message.content.strip()
        if prompt:
            status_msg = await message.reply("🤔 Thinking...")

            async def update_status_admin(text):
                try:
                    await status_msg.edit(content=text)
                except:
                    pass

            result = await agent.run(prompt, message.guild.id, message.channel.id, status_callback=update_status_admin)
            await status_msg.edit(content=result[:1900])
        return

    await bot.process_commands(message)


@bot.command(name='ping')
async def ping(ctx):
    await ctx.send(f'🏓 Pong! `{round(bot.latency * 1000)}ms`')


@bot.command(name='memory')
@admin_only()
async def show_memory(ctx):
    """[ADMIN ONLY] Show agent memory"""
    if agent.memory:
        mem = "\n".join([f"`{i+1}.` {m}" for i, m in enumerate(agent.memory[-10:])])
        await ctx.send(f"🧠 **Agent Memory (last 10):**\n{mem}")
    else:
        await ctx.send("🧠 Memory is empty.")


@bot.command(name='clear_memory')
@admin_only()
async def clear_memory(ctx):
    """[ADMIN ONLY] Clear agent memory"""
    agent.memory = []
    await ctx.send("🧹 Memory cleared!")


@bot.command(name='tools')
@admin_only()
async def list_tools(ctx):
    """[ADMIN ONLY] List available tools"""
    desc = tools.get_tool_descriptions()
    await ctx.send(f"🛠️ **Available Tools:**\n```\n{desc[:1800]}\n```")


# ---------- Run ----------
if __name__ == "__main__":
    bot.run(os.getenv("DISCORD_TOKEN"))
