import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
from huggingface_hub import InferenceClient

load_dotenv()

# ตั้งค่า Intents
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents)

# Hugging Face Client
hf_client = InferenceClient(
    "microsoft/DialoGPT-medium",  # ใช้โมเดลนี้ฟรี ไม่ต้องรอโหลด
    token=os.getenv("HUGGINGFACE_TOKEN")
)

@bot.event
async def on_ready():
    print(f'✅ {bot.user} is online on Railway!')
    print(f'📡 Connected to {len(bot.guilds)} servers')
    await bot.change_presence(activity=discord.Game(name="!chat | !ping"))

@bot.command(name='ping')
async def ping(ctx):
    """เช็คสถานะบอท"""
    await ctx.send(f'🏓 Pong! `{round(bot.latency * 1000)}ms`')

@bot.command(name='chat')
async def chat(ctx, *, prompt: str):
    """คุยกับ AI (Hugging Face)"""
    async with ctx.typing():
        try:
            response = hf_client.text_generation(
                prompt,
                max_new_tokens=200,
                temperature=0.7
            )
            await ctx.reply(response[:1900])
        except Exception as e:
            await ctx.reply(f"❌ Error: {str(e)[:100]}")

@bot.command(name='info')
async def server_info(ctx):
    """ดูข้อมูลเซิร์ฟเวอร์"""
    guild = ctx.guild
    embed = discord.Embed(title=f"📊 {guild.name}", color=0x00ff00)
    embed.add_field(name="👑 เจ้าของ", value=guild.owner.mention)
    embed.add_field(name="👥 สมาชิก", value=guild.member_count)
    embed.add_field(name="💬 แชท", value=len(guild.text_channels))
    embed.add_field(name="🚀 ความหน่วง", value=f"{round(bot.latency * 1000)}ms")
    await ctx.send(embed=embed)

# เมื่อมีคน @ บอท
@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    
    if bot.user in message.mentions:
        prompt = message.content.replace(f'<@{bot.user.id}>', '').strip()
        if prompt:
            async with message.channel.typing():
                try:
                    response = hf_client.text_generation(prompt, max_new_tokens=200)
                    await message.reply(response[:1900])
                except Exception as e:
                    await message.reply(f"❌ {str(e)[:100]}")
    
    await bot.process_commands(message)

bot.run(os.getenv("DISCORD_TOKEN"))