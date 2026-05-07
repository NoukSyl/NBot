"""
AI Agent - Hugging Face Serverless Inference
Model: Qwen/Qwen3-32B (Free, best quality on HF)
Deploy: Railway
"""

import os
import json
import requests
import gradio as gr
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Optional
import uvicorn

# ─────────────────────────────────────────
# Config
# ─────────────────────────────────────────
HF_TOKEN = os.getenv("HF_TOKEN", "")
MODEL_ID = os.getenv("MODEL_ID", "Qwen/Qwen3-32B")
PORT = int(os.getenv("PORT", 7860))
MAX_TOKENS = int(os.getenv("MAX_TOKENS", 1024))

HF_API_URL = f"https://api-inference.huggingface.co/models/{MODEL_ID}/v1/chat/completions"

SYSTEM_PROMPT = os.getenv(
    "SYSTEM_PROMPT",
    "You are a helpful, smart, and concise AI assistant. "
    "Think step by step and answer accurately."
)

# ─────────────────────────────────────────
# Core: Call HuggingFace API
# ─────────────────────────────────────────
def call_hf(messages: list, temperature: float = 0.7, max_tokens: int = MAX_TOKENS) -> str:
    if not HF_TOKEN:
        return "❌ HF_TOKEN not set. Please add it in Railway environment variables."

    headers = {
        "Authorization": f"Bearer {HF_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": MODEL_ID,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": False,
    }

    try:
        resp = requests.post(HF_API_URL, headers=headers, json=payload, timeout=120)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()
    except requests.exceptions.Timeout:
        return "⏱️ Request timed out. The model may be loading, please try again."
    except requests.exceptions.HTTPError as e:
        if resp.status_code == 503:
            return "🔄 Model is loading (cold start). Please wait ~30s and try again."
        elif resp.status_code == 429:
            return "⚠️ Rate limit reached. Free tier allows ~few hundred req/hr. Try again later."
        elif resp.status_code == 401:
            return "🔑 Invalid HF_TOKEN. Please check your Hugging Face access token."
        return f"❌ API error {resp.status_code}: {e}"
    except Exception as e:
        return f"❌ Error: {str(e)}"


# ─────────────────────────────────────────
# Agent Logic: Multi-turn with history
# ─────────────────────────────────────────
def build_messages(history: list, user_input: str) -> list:
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for user_msg, bot_msg in history:
        messages.append({"role": "user", "content": user_msg})
        if bot_msg:
            messages.append({"role": "assistant", "content": bot_msg})
    messages.append({"role": "user", "content": user_input})
    return messages


def chat(user_input: str, history: list, temperature: float, max_tokens: int):
    if not user_input.strip():
        return history, history

    messages = build_messages(history, user_input)
    response = call_hf(messages, temperature=temperature, max_tokens=int(max_tokens))

    history = history + [(user_input, response)]
    return history, history


# ─────────────────────────────────────────
# FastAPI App
# ─────────────────────────────────────────
app = FastAPI(title="HF AI Agent", version="1.0")


class ChatRequest(BaseModel):
    message: str
    history: Optional[list] = []
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = 1024


class ChatResponse(BaseModel):
    response: str
    model: str


@app.get("/", response_class=HTMLResponse)
def root():
    return """
    <html><body style="font-family:sans-serif;max-width:600px;margin:40px auto">
    <h2>🤖 HF AI Agent</h2>
    <p>Model: <strong>{model}</strong></p>
    <ul>
      <li><a href="/ui">💬 Chat UI</a></li>
      <li><a href="/docs">📖 API Docs</a></li>
      <li><a href="/health">❤️ Health Check</a></li>
    </ul>
    </body></html>
    """.format(model=MODEL_ID)


@app.get("/health")
def health():
    return {"status": "ok", "model": MODEL_ID, "hf_token_set": bool(HF_TOKEN)}


@app.post("/chat", response_model=ChatResponse)
def api_chat(req: ChatRequest):
    messages = build_messages(req.history or [], req.message)
    response = call_hf(messages, temperature=req.temperature, max_tokens=req.max_tokens)
    return ChatResponse(response=response, model=MODEL_ID)


# ─────────────────────────────────────────
# Gradio UI
# ─────────────────────────────────────────
def build_gradio():
    with gr.Blocks(
        title="🤖 AI Agent",
        theme=gr.themes.Soft(primary_hue="violet"),
        css="""
        .gradio-container { max-width: 860px !important; margin: auto; }
        .model-badge { background: #7c3aed; color: white; padding: 4px 12px;
                       border-radius: 20px; font-size: 0.8em; font-weight: bold; }
        """
    ) as demo:
        gr.HTML(f"""
        <div style="text-align:center;padding:20px 0 10px">
          <h1>🤖 AI Agent</h1>
          <span class="model-badge">⚡ {MODEL_ID}</span>
          <p style="color:#666;margin-top:8px">Powered by Hugging Face Serverless Inference · 100% Free</p>
        </div>
        """)

        chatbot = gr.Chatbot(
            label="Conversation",
            height=480,
            bubble_full_width=False,
            avatar_images=("👤", "🤖"),
        )

        with gr.Row():
            msg_box = gr.Textbox(
                placeholder="Ask me anything...",
                show_label=False,
                scale=9,
                container=False,
            )
            send_btn = gr.Button("Send", variant="primary", scale=1)

        with gr.Accordion("⚙️ Settings", open=False):
            with gr.Row():
                temperature = gr.Slider(0.0, 1.5, value=0.7, step=0.05, label="Temperature")
                max_tokens = gr.Slider(128, 2048, value=1024, step=64, label="Max Tokens")

        clear_btn = gr.Button("🗑️ Clear Chat", variant="secondary")

        state = gr.State([])

        def respond(user_input, history, temp, max_tok):
            new_history, new_state = chat(user_input, history, temp, max_tok)
            return new_history, new_state, ""

        send_btn.click(
            respond,
            inputs=[msg_box, state, temperature, max_tokens],
            outputs=[chatbot, state, msg_box],
        )
        msg_box.submit(
            respond,
            inputs=[msg_box, state, temperature, max_tokens],
            outputs=[chatbot, state, msg_box],
        )
        clear_btn.click(lambda: ([], [], ""), outputs=[chatbot, state, msg_box])

        gr.Examples(
            examples=[
                "Explain quantum computing in simple terms",
                "Write a Python function to find prime numbers",
                "What are the pros and cons of microservices architecture?",
                "Help me debug: Why does my list comprehension return None?",
            ],
            inputs=msg_box,
        )

    return demo


# ─────────────────────────────────────────
# Mount Gradio on FastAPI
# ─────────────────────────────────────────
gradio_app = build_gradio()
app = gr.mount_gradio_app(app, gradio_app, path="/ui")


# ─────────────────────────────────────────
# Entrypoint
# ─────────────────────────────────────────
if __name__ == "__main__":
    print(f"🚀 Starting AI Agent")
    print(f"   Model : {MODEL_ID}")
    print(f"   Port  : {PORT}")
    print(f"   Token : {'✅ Set' if HF_TOKEN else '❌ Missing!'}")
    uvicorn.run("main:app", host="0.0.0.0", port=PORT, reload=False)
