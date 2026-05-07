"""
AI Agent - HuggingFace Inference + Terminal/Root Access
Model: Qwen/Qwen3-32B (Free)
Deploy: Railway

v5: เพิ่ม Shell Tool — agent รัน terminal command ได้ผ่าน tool calling
    - LLM คิดเอง → เลือก tool → รัน shell → เห็น output → ตอบ
    - root access: Railway container รัน as root by default
    - timeout 30s / output จำกัด 4000 chars ป้องกัน flood context
    - working dir = /workspace (สร้างอัตโนมัติ)
    - Gradio UI แสดง tool call + output แบบ step-by-step
"""

import os
import re
import json
import subprocess
import requests
import gradio as gr
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Optional
import uvicorn

# ─────────────────────────────────────────
# Config
# ─────────────────────────────────────────
HF_TOKEN    = os.getenv("HF_TOKEN", "")
MODEL_ID    = os.getenv("MODEL_ID", "Qwen/Qwen3-32B")
PORT        = int(os.getenv("PORT", 7860))
MAX_TOKENS  = int(os.getenv("MAX_TOKENS", 4096))
SHELL_TIMEOUT = int(os.getenv("SHELL_TIMEOUT", "30"))      # วินาที
MAX_OUTPUT  = int(os.getenv("MAX_OUTPUT_CHARS", "4000"))   # ป้องกัน context flood
WORKSPACE   = os.getenv("WORKSPACE", "/workspace")

HF_API_URL  = "https://router.huggingface.co/v1/chat/completions"

SYSTEM_PROMPT = (
    "/no_think\n"
    "You are a powerful AI assistant with terminal access to a Linux system (root).\n"
    "You can run shell commands using the `shell` tool to help users.\n"
    "Always explain what you're doing before running commands.\n"
    "Working directory: " + WORKSPACE + "\n"
    "Be careful with destructive commands — ask for confirmation if unsure.\n"
    "After running commands, explain the output clearly."
)

# สร้าง workspace
os.makedirs(WORKSPACE, exist_ok=True)

# ─────────────────────────────────────────
# Tool Definition — ส่งให้ LLM รู้จัก
# ─────────────────────────────────────────
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "shell",
            "description": (
                "Run a shell command on the Linux system as root. "
                "Returns stdout, stderr, exit code, and whether it timed out. "
                f"Timeout: {SHELL_TIMEOUT}s. Working dir: {WORKSPACE}"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The shell command to execute (bash)",
                    }
                },
                "required": ["command"],
            },
        },
    }
]

# ─────────────────────────────────────────
# Shell Executor
# ─────────────────────────────────────────
def run_shell(command: str) -> dict:
    """รัน shell command ใน subprocess พร้อม timeout และ output limit"""
    try:
        proc = subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=WORKSPACE,
            env={**os.environ, "HOME": "/root", "TERM": "xterm"},
        )
        try:
            stdout, stderr = proc.communicate(timeout=SHELL_TIMEOUT)
            timed_out = False
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout, stderr = proc.communicate()
            timed_out = True

        # จำกัดขนาด output
        def trim(s): return s[:MAX_OUTPUT] + "\n[...truncated]" if len(s) > MAX_OUTPUT else s

        return {
            "stdout":    trim(stdout),
            "stderr":    trim(stderr),
            "exit_code": proc.returncode,
            "timed_out": timed_out,
        }
    except Exception as e:
        return {"stdout": "", "stderr": str(e), "exit_code": -1, "timed_out": False}


def format_shell_result(result: dict) -> str:
    """แปลง shell result เป็น string ส่งกลับ LLM"""
    parts = []
    if result["timed_out"]:
        parts.append(f"⚠️ TIMED OUT after {SHELL_TIMEOUT}s")
    parts.append(f"Exit code: {result['exit_code']}")
    if result["stdout"]:
        parts.append(f"STDOUT:\n{result['stdout']}")
    if result["stderr"]:
        parts.append(f"STDERR:\n{result['stderr']}")
    return "\n".join(parts) if parts else "(no output)"


# ─────────────────────────────────────────
# Helper: strip <think> block
# ─────────────────────────────────────────
def strip_thinking(text: str) -> str:
    return re.sub(r"<think>.*?</think>\s*", "", text, flags=re.DOTALL).strip()


# ─────────────────────────────────────────
# Core: Call HF API (with tool calling loop)
# ─────────────────────────────────────────
def call_hf_raw(messages: list, use_tools: bool = True) -> dict:
    """เรียก HF API ครั้งเดียว — return raw response dict"""
    if not HF_TOKEN:
        return {"error": "HF_TOKEN not set"}

    headers = {
        "Authorization": f"Bearer {HF_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": MODEL_ID,
        "messages": messages,
        "max_tokens": MAX_TOKENS,
        "temperature": 0.7,
        "stream": False,
    }
    if use_tools:
        payload["tools"] = TOOLS
        payload["tool_choice"] = "auto"

    try:
        resp = requests.post(HF_API_URL, headers=headers, json=payload, timeout=120)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.Timeout:
        return {"error": "⏱️ Request timed out. Please try again."}
    except requests.exceptions.HTTPError:
        code = resp.status_code
        body = resp.text[:300]
        errors = {
            503: "🔄 Model loading. Wait ~30s and retry.",
            429: "⚠️ Rate limit. Try again later.",
            401: "🔑 Invalid HF_TOKEN.",
        }
        return {"error": errors.get(code, f"❌ API error {code}: {body}")}
    except Exception as e:
        return {"error": f"❌ {str(e)}"}


def agent_loop(messages: list, yield_steps=False):
    """
    Agentic loop: LLM → tool call? → run shell → ส่งผลกลับ → LLM ตอบ
    yield_steps=True: yield (step_type, content) ระหว่างทาง
    """
    MAX_ROUNDS = 10
    steps = []

    for _ in range(MAX_ROUNDS):
        data = call_hf_raw(messages, use_tools=True)

        if "error" in data:
            return data["error"], steps

        choice = data["choices"][0]
        msg = choice["message"]
        finish = choice.get("finish_reason", "")

        # มี tool call?
        tool_calls = msg.get("tool_calls") or []

        if tool_calls:
            # เพิ่ม assistant message (ที่มี tool_calls) เข้า history
            messages.append(msg)

            for tc in tool_calls:
                fn_name = tc["function"]["name"]
                fn_args = json.loads(tc["function"]["arguments"])

                if fn_name == "shell":
                    cmd = fn_args.get("command", "")
                    steps.append(("tool_call", cmd))

                    result = run_shell(cmd)
                    result_str = format_shell_result(result)
                    steps.append(("tool_result", result_str))

                    # ส่งผล tool กลับ LLM
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "name": fn_name,
                        "content": result_str,
                    })

        else:
            # ไม่มี tool call → LLM ตอบสุดท้ายแล้ว
            final = strip_thinking(msg.get("content") or "")
            return final, steps

        if finish == "stop":
            break

    return "Agent reached max rounds without a final answer.", steps


# ─────────────────────────────────────────
# FastAPI
# ─────────────────────────────────────────
app = FastAPI(title="HF Shell Agent", version="1.5")


class ChatRequest(BaseModel):
    message: str
    history: Optional[list] = []
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = 4096


class ChatResponse(BaseModel):
    response: str
    model: str
    steps: Optional[list] = []


@app.get("/", response_class=HTMLResponse)
def root():
    return f"""
    <html><body style="font-family:sans-serif;max-width:600px;margin:40px auto">
    <h2>🤖 HF Shell Agent</h2>
    <p>Model: <strong>{MODEL_ID}</strong> · Root: ✅ · Workspace: <code>{WORKSPACE}</code></p>
    <ul>
      <li><a href="/ui">💬 Chat UI</a></li>
      <li><a href="/docs">📖 API Docs</a></li>
      <li><a href="/health">❤️ Health</a></li>
    </ul>
    </body></html>
    """


@app.get("/health")
def health():
    return {
        "status": "ok", "model": MODEL_ID,
        "hf_token_set": bool(HF_TOKEN),
        "workspace": WORKSPACE,
        "shell_timeout": SHELL_TIMEOUT,
        "whoami": subprocess.getoutput("whoami"),
    }


@app.post("/chat", response_model=ChatResponse)
def api_chat(req: ChatRequest):
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for m in (req.history or []):
        messages.append({"role": m["role"], "content": m["content"]})
    messages.append({"role": "user", "content": req.message})

    final, steps = agent_loop(messages)
    return ChatResponse(response=final, model=MODEL_ID, steps=steps)


# ─────────────────────────────────────────
# Gradio UI
# ─────────────────────────────────────────
def build_gradio() -> gr.Blocks:
    with gr.Blocks(title="🤖 Shell Agent", theme=gr.themes.Soft(primary_hue="violet")) as demo:
        gr.HTML(f"""
        <div style="text-align:center;padding:20px 0 10px">
          <h1>🤖 Shell Agent</h1>
          <span style="background:#7c3aed;color:white;padding:4px 14px;
                       border-radius:20px;font-size:.85em;font-weight:bold">
            ⚡ {MODEL_ID}
          </span>
          <span style="background:#16a34a;color:white;padding:4px 10px;
                       border-radius:20px;font-size:.85em;font-weight:bold;margin-left:6px">
            🖥️ Terminal · Root Access
          </span>
          <p style="color:#666;margin-top:8px">Agent คิดเอง → รัน shell → ตอบ · Workspace: <code>{WORKSPACE}</code></p>
        </div>
        """)

        chatbot = gr.Chatbot(
            label="Conversation",
            type="messages",
            height=520,
            bubble_full_width=False,
            avatar_images=(None, None),
            show_copy_button=True,
            render_markdown=True,
        )

        with gr.Row():
            msg_box = gr.Textbox(
                placeholder='ลองพิมพ์: "ดู disk usage" หรือ "เขียน hello world ด้วย Python แล้วรัน"',
                show_label=False,
                scale=9,
                container=False,
            )
            send_btn = gr.Button("Send ➤", variant="primary", scale=1)

        with gr.Accordion("⚙️ Settings", open=False):
            with gr.Row():
                temperature = gr.Slider(0.0, 1.0, value=0.7, step=0.05, label="Temperature")
                max_tokens  = gr.Slider(256, 8192, value=4096, step=256, label="Max Tokens")

        clear_btn = gr.Button("🗑️ Clear", variant="secondary")
        state = gr.State([])  # openai-style message list

        def respond(user_input, history_state, temp, max_tok):
            if not user_input.strip():
                return history_state, history_state, ""

            # build messages
            messages = [{"role": "system", "content": SYSTEM_PROMPT}]
            for m in history_state:
                messages.append({"role": m["role"], "content": m["content"]})
            messages.append({"role": "user", "content": user_input})

            # run agent
            final, steps = agent_loop(messages)

            # สร้าง assistant message พร้อม tool steps ถ้ามี
            assistant_content = ""
            if steps:
                tool_md = []
                for kind, content in steps:
                    if kind == "tool_call":
                        tool_md.append(f"```bash\n$ {content}\n```")
                    elif kind == "tool_result":
                        tool_md.append(f"```\n{content}\n```")
                assistant_content = "\n".join(tool_md) + "\n\n---\n" + final
            else:
                assistant_content = final

            new_state = history_state + [
                {"role": "user",      "content": user_input},
                {"role": "assistant", "content": assistant_content},
            ]
            return new_state, new_state, ""

        send_btn.click(respond, [msg_box, state, temperature, max_tokens], [chatbot, state, msg_box])
        msg_box.submit(respond, [msg_box, state, temperature, max_tokens], [chatbot, state, msg_box])
        clear_btn.click(lambda: ([], [], ""), outputs=[chatbot, state, msg_box])

        gr.Examples(
            examples=[
                "ดูข้อมูล disk usage และ memory ปัจจุบัน",
                "สร้างไฟล์ hello.py ที่พิมพ์ 'Hello from AI Agent!' แล้วรัน",
                "ติดตั้ง cowsay แล้วให้มันพูดว่า I am an AI",
                "หา IP address ของเครื่องนี้",
                "รัน Python one-liner คำนวณ fibonacci 10 ตัวแรก",
                "ดูว่า process อะไรกำลังรันอยู่บ้าง",
            ],
            inputs=msg_box,
        )

    return demo


gradio_demo = build_gradio()
app = gr.mount_gradio_app(app, gradio_demo, path="/ui", root_path="/ui")


# ─────────────────────────────────────────
# Entrypoint
# ─────────────────────────────────────────
if __name__ == "__main__":
    import subprocess as sp
    whoami = sp.getoutput("whoami")
    print(f"🚀 Starting Shell Agent v1.5")
    print(f"   Model     : {MODEL_ID}")
    print(f"   Endpoint  : {HF_API_URL}")
    print(f"   Port      : {PORT}")
    print(f"   Workspace : {WORKSPACE}")
    print(f"   User      : {whoami}  ({'✅ root' if whoami=='root' else '⚠️ not root'})")
    print(f"   Token     : {'✅ Set' if HF_TOKEN else '❌ Missing!'}")
    uvicorn.run("main:app", host="0.0.0.0", port=PORT, reload=False)
