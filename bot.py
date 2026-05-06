import os
import discord
from discord.ext import commands
from huggingface_hub import InferenceClient
import asyncio

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# Hugging Face Client
hf_client = InferenceClient(
    "mistralai/Mistral-7B-Instruct-v0.3",
    token=os.getenv("HF_TOKEN")
)

@bot.event
async def on_ready():
    print(f'✅ {bot.user} is online on Railway!')

@bot.command(name='chat')
async def chat(ctx, *, prompt: str):
    """คุยกับ AI Agent"""
    async with ctx.typing():
        response = hf_client.chat_completion(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=500,
            temperature=0.7
        )
        reply = response.choices[0].message.content
        await ctx.reply(reply[:1900])

# Agent-auto mode: เมื่อถูก @
@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    
    # ถ้า tag bot แล้วพิมพ์อะไร
    if bot.user in message.mentions:
        prompt = message.content.replace(f'<@{bot.user.id}>', '').strip()
        if prompt:
            async with message.channel.typing():
                response = hf_client.chat_completion(
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=500
                )
                await message.reply(response.choices[0].message.content[:1900])
    
    await bot.process_commands(message)

bot.run(os.getenv("DISCORD_TOKEN"))