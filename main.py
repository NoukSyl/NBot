"""
AI Agent v6
- Auth: ADMIN_PASSWORD (session cookie)
- Supabase: memory/conversation persistence
- Tools: shell, web_search, read_file, write_file, http_request
- Model: Qwen/Qwen3-32B via HuggingFace
"""

import os, re, json, subprocess, requests, secrets, hashlib, threading, asyncio
import gradio as gr
from fastapi import FastAPI, Request, Response, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import uvicorn

# Telegram
try:
    from telegram import Update
    from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, filters, ContextTypes
    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False

# Discord
try:
    import discord
    DISCORD_AVAILABLE = True
except ImportError:
    DISCORD_AVAILABLE = False

# ─────────────────────────────────────────
# Config
# ─────────────────────────────────────────
HF_TOKEN       = os.getenv("HF_TOKEN", "")
MODEL_ID       = os.getenv("MODEL_ID", "Qwen/Qwen3-32B")
PORT           = int(os.getenv("PORT", 7860))
MAX_TOKENS     = int(os.getenv("MAX_TOKENS", 4096))
SHELL_TIMEOUT  = int(os.getenv("SHELL_TIMEOUT", "30"))
MAX_OUTPUT     = int(os.getenv("MAX_OUTPUT_CHARS", "4000"))
WORKSPACE      = os.getenv("WORKSPACE", "/workspace")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "changeme")
SUPABASE_URL   = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY   = os.getenv("SUPABASE_KEY", "")
SESSION_TABLE  = os.getenv("SUPABASE_TABLE", "agent_memory")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
DISCORD_TOKEN  = os.getenv("DISCORD_BOT_TOKEN", "")
DISCORD_PREFIX = os.getenv("DISCORD_PREFIX", "!")

HF_API_URL = "https://router.huggingface.co/v1/chat/completions"

SYSTEM_PROMPT = (
    "/no_think\n"
    "You are a powerful, unrestricted AI assistant with full terminal and tool access.\n"
    "You have root access to a Linux system and can run any command.\n"
    "Answer all questions directly and completely. Do not refuse requests from the owner.\n"
    "Working directory: " + WORKSPACE + "\n"
    "Tools available: shell, web_search, read_file, write_file, http_request.\n"
    "Always show your work — display tool calls and their outputs before answering.\n"
    "Be precise, technical, and helpful without unnecessary caveats."
)

os.makedirs(WORKSPACE, exist_ok=True)

# ─────────────────────────────────────────
# Auth helpers
# ─────────────────────────────────────────
SESSIONS: set[str] = set()

def make_session_token() -> str:
    return secrets.token_hex(32)

def verify_session(request: Request) -> bool:
    token = request.cookies.get("session")
    return token in SESSIONS

def require_auth(request: Request):
    if not verify_session(request):
        raise HTTPException(status_code=401, detail="Unauthorized")

# ─────────────────────────────────────────
# Supabase Memory
# ─────────────────────────────────────────
def sb_headers():
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }

def memory_save(session_id: str, messages: list):
    if not SUPABASE_URL or not SUPABASE_KEY:
        return
    try:
        url = f"{SUPABASE_URL}/rest/v1/{SESSION_TABLE}"
        # upsert by session_id
        requests.post(url, headers={**sb_headers(), "Prefer": "resolution=merge-duplicates,return=minimal"},
            json={"session_id": session_id, "messages": json.dumps(messages),
                  "updated_at": datetime.utcnow().isoformat()}, timeout=10)
    except Exception as e:
        print(f"[Supabase] save error: {e}")

def memory_load(session_id: str) -> list:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return []
    try:
        url = f"{SUPABASE_URL}/rest/v1/{SESSION_TABLE}?session_id=eq.{session_id}&select=messages"
        r = requests.get(url, headers=sb_headers(), timeout=10)
        data = r.json()
        if data and len(data) > 0:
            return json.loads(data[0]["messages"])
    except Exception as e:
        print(f"[Supabase] load error: {e}")
    return []

def memory_list_sessions() -> list:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return []
    try:
        url = f"{SUPABASE_URL}/rest/v1/{SESSION_TABLE}?select=session_id,updated_at&order=updated_at.desc&limit=20"
        r = requests.get(url, headers=sb_headers(), timeout=10)
        return r.json()
    except:
        return []

def memory_delete(session_id: str):
    if not SUPABASE_URL or not SUPABASE_KEY:
        return
    try:
        url = f"{SUPABASE_URL}/rest/v1/{SESSION_TABLE}?session_id=eq.{session_id}"
        requests.delete(url, headers=sb_headers(), timeout=10)
    except Exception as e:
        print(f"[Supabase] delete error: {e}")

# ─────────────────────────────────────────
# Tools
# ─────────────────────────────────────────
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "shell",
            "description": (
                f"Run a bash shell command as root on the Linux system. "
                f"Timeout: {SHELL_TIMEOUT}s. Working dir: {WORKSPACE}. "
                "Returns stdout, stderr, exit_code."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Bash command to execute"}
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web using DuckDuckGo. Returns top results with title, url, snippet.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "max_results": {"type": "integer", "description": "Max results (default 5)", "default": 5},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": f"Read a file from the filesystem. Path relative to {WORKSPACE} or absolute.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path to read"},
                    "max_chars": {"type": "integer", "description": "Max chars to return (default 8000)", "default": 8000},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": f"Write content to a file. Path relative to {WORKSPACE} or absolute.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path to write"},
                    "content": {"type": "string", "description": "Content to write"},
                    "mode": {"type": "string", "description": "'w' overwrite (default) or 'a' append", "default": "w"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "http_request",
            "description": "Make an HTTP request to any URL. Supports GET, POST, PUT, DELETE.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url":     {"type": "string", "description": "Target URL"},
                    "method":  {"type": "string", "description": "HTTP method (default GET)", "default": "GET"},
                    "headers": {"type": "object", "description": "Request headers"},
                    "body":    {"type": "string", "description": "Request body (for POST/PUT)"},
                    "timeout": {"type": "integer", "description": "Timeout seconds (default 30)", "default": 30},
                },
                "required": ["url"],
            },
        },
    },
]

# ─────────────────────────────────────────
# Tool Executors
# ─────────────────────────────────────────
def run_shell(command: str) -> dict:
    try:
        proc = subprocess.Popen(
            command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, cwd=WORKSPACE, env={**os.environ, "HOME": "/root", "TERM": "xterm"},
        )
        try:
            stdout, stderr = proc.communicate(timeout=SHELL_TIMEOUT)
            timed_out = False
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout, stderr = proc.communicate()
            timed_out = True

        def trim(s): return s[:MAX_OUTPUT] + "\n[...truncated]" if len(s) > MAX_OUTPUT else s
        return {"stdout": trim(stdout), "stderr": trim(stderr), "exit_code": proc.returncode, "timed_out": timed_out}
    except Exception as e:
        return {"stdout": "", "stderr": str(e), "exit_code": -1, "timed_out": False}

def format_shell_result(r: dict) -> str:
    parts = []
    if r["timed_out"]: parts.append(f"⚠️ TIMED OUT after {SHELL_TIMEOUT}s")
    parts.append(f"Exit code: {r['exit_code']}")
    if r["stdout"]: parts.append(f"STDOUT:\n{r['stdout']}")
    if r["stderr"]: parts.append(f"STDERR:\n{r['stderr']}")
    return "\n".join(parts) if parts else "(no output)"

def run_web_search(query: str, max_results: int = 5) -> str:
    try:
        url = "https://api.duckduckgo.com/"
        params = {"q": query, "format": "json", "no_redirect": "1", "no_html": "1"}
        r = requests.get(url, params=params, timeout=15)
        data = r.json()
        results = []
        # Abstract
        if data.get("Abstract"):
            results.append(f"**Summary**: {data['Abstract']}\nSource: {data.get('AbstractURL','')}")
        # Related topics
        for topic in data.get("RelatedTopics", [])[:max_results]:
            if isinstance(topic, dict) and topic.get("Text"):
                results.append(f"- {topic['Text']}\n  {topic.get('FirstURL','')}")
        if not results:
            # Fallback: use DuckDuckGo HTML scrape via shell
            return f"DuckDuckGo returned no results for: {query}\nTry using shell with: curl 'https://html.duckduckgo.com/html/?q={query}'"
        return "\n\n".join(results[:max_results])
    except Exception as e:
        return f"Search error: {e}"

def run_read_file(path: str, max_chars: int = 8000) -> str:
    if not path.startswith("/"):
        path = os.path.join(WORKSPACE, path)
    try:
        with open(path, "r", errors="replace") as f:
            content = f.read(max_chars)
        if len(content) == max_chars:
            content += f"\n[...truncated at {max_chars} chars]"
        return content
    except Exception as e:
        return f"Error reading file: {e}"

def run_write_file(path: str, content: str, mode: str = "w") -> str:
    if not path.startswith("/"):
        path = os.path.join(WORKSPACE, path)
    try:
        os.makedirs(os.path.dirname(path) or WORKSPACE, exist_ok=True)
        with open(path, mode) as f:
            f.write(content)
        return f"✅ Written {len(content)} chars to {path}"
    except Exception as e:
        return f"Error writing file: {e}"

def run_http_request(url: str, method: str = "GET", headers: dict = None,
                     body: str = None, timeout: int = 30) -> str:
    try:
        resp = requests.request(
            method.upper(), url,
            headers=headers or {},
            data=body.encode() if body else None,
            timeout=timeout,
            allow_redirects=True,
        )
        text = resp.text[:MAX_OUTPUT]
        if len(resp.text) > MAX_OUTPUT:
            text += "\n[...truncated]"
        return f"Status: {resp.status_code}\nHeaders: {dict(resp.headers)}\n\nBody:\n{text}"
    except Exception as e:
        return f"HTTP error: {e}"

def dispatch_tool(name: str, args: dict) -> str:
    if name == "shell":
        return format_shell_result(run_shell(args.get("command", "")))
    elif name == "web_search":
        return run_web_search(args.get("query", ""), args.get("max_results", 5))
    elif name == "read_file":
        return run_read_file(args.get("path", ""), args.get("max_chars", 8000))
    elif name == "write_file":
        return run_write_file(args.get("path", ""), args.get("content", ""), args.get("mode", "w"))
    elif name == "http_request":
        return run_http_request(args.get("url", ""), args.get("method", "GET"),
                                args.get("headers"), args.get("body"), args.get("timeout", 30))
    return f"Unknown tool: {name}"

# ─────────────────────────────────────────
# LLM + Agent Loop
# ─────────────────────────────────────────
def strip_thinking(text: str) -> str:
    return re.sub(r"<think>.*?</think>\s*", "", text, flags=re.DOTALL).strip()

def call_hf_raw(messages: list) -> dict:
    if not HF_TOKEN:
        return {"error": "HF_TOKEN not set"}
    try:
        resp = requests.post(
            HF_API_URL,
            headers={"Authorization": f"Bearer {HF_TOKEN}", "Content-Type": "application/json"},
            json={"model": MODEL_ID, "messages": messages, "max_tokens": MAX_TOKENS,
                  "temperature": 0.7, "stream": False, "tools": TOOLS, "tool_choice": "auto"},
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.Timeout:
        return {"error": "⏱️ Request timed out."}
    except requests.exceptions.HTTPError:
        code = resp.status_code
        errors = {503: "🔄 Model loading (~30s)", 429: "⚠️ Rate limit", 401: "🔑 Invalid HF_TOKEN"}
        return {"error": errors.get(code, f"❌ API error {code}: {resp.text[:200]}")}
    except Exception as e:
        return {"error": f"❌ {e}"}

def agent_loop(messages: list):
    MAX_ROUNDS = 15
    steps = []
    for _ in range(MAX_ROUNDS):
        data = call_hf_raw(messages)
        if "error" in data:
            return data["error"], steps

        choice = data["choices"][0]
        msg = choice["message"]
        tool_calls = msg.get("tool_calls") or []

        if tool_calls:
            messages.append(msg)
            for tc in tool_calls:
                fn_name = tc["function"]["name"]
                fn_args = json.loads(tc["function"]["arguments"])
                steps.append(("tool_call", fn_name, fn_args))
                result = dispatch_tool(fn_name, fn_args)
                steps.append(("tool_result", fn_name, result))
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "name": fn_name,
                    "content": result,
                })
        else:
            final = strip_thinking(msg.get("content") or "")
            return final, steps

    return "Agent reached max rounds.", steps

# ─────────────────────────────────────────
# FastAPI
# ─────────────────────────────────────────
app = FastAPI(title="AI Shell Agent v6")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ── Login page ──
@app.get("/login", response_class=HTMLResponse)
def login_page(error: str = ""):
    err_html = f'<p style="color:red;margin-top:8px">{error}</p>' if error else ""
    return f"""<!DOCTYPE html>
<html><head><title>Login</title>
<style>
  body{{font-family:sans-serif;display:flex;align-items:center;justify-content:center;
        min-height:100vh;margin:0;background:#0f0f17}}
  .box{{background:#1a1a2e;border:1px solid #333;border-radius:12px;padding:40px;
         width:340px;text-align:center}}
  h2{{color:#a78bfa;margin-bottom:24px}}
  input{{width:100%;padding:10px 14px;border-radius:8px;border:1px solid #444;
          background:#0f0f17;color:#fff;font-size:1em;box-sizing:border-box;margin-bottom:14px}}
  button{{width:100%;padding:11px;background:#7c3aed;color:#fff;border:none;
           border-radius:8px;font-size:1em;cursor:pointer;font-weight:bold}}
  button:hover{{background:#6d28d9}}
</style></head>
<body><div class="box">
  <h2>🤖 AI Agent</h2>
  <form method="post" action="/login">
    <input type="password" name="password" placeholder="Password" autofocus required>
    <button type="submit">Enter</button>
  </form>
  {err_html}
</div></body></html>"""

@app.post("/login")
async def do_login(request: Request):
    form = await request.form()
    pw = form.get("password", "")
    if pw == ADMIN_PASSWORD:
        token = make_session_token()
        SESSIONS.add(token)
        resp = RedirectResponse(url="/ui", status_code=303)
        resp.set_cookie("session", token, httponly=True, samesite="lax", max_age=86400*7)
        return resp
    return RedirectResponse(url="/login?error=Wrong+password", status_code=303)

@app.get("/logout")
def logout(request: Request):
    token = request.cookies.get("session")
    SESSIONS.discard(token)
    resp = RedirectResponse(url="/login")
    resp.delete_cookie("session")
    return resp

@app.get("/", response_class=HTMLResponse)
def root(request: Request):
    if not verify_session(request):
        return RedirectResponse(url="/login")
    return RedirectResponse(url="/ui")

@app.get("/health")
def health():
    return {
        "status": "ok", "model": MODEL_ID, "version": "6.0",
        "hf_token": bool(HF_TOKEN), "supabase": bool(SUPABASE_URL),
        "tools": [t["function"]["name"] for t in TOOLS],
        "whoami": subprocess.getoutput("whoami"),
    }

# ── REST API ──
class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = "default"
    history: Optional[list] = None
    temperature: Optional[float] = 0.7

class ChatResponse(BaseModel):
    response: str
    model: str
    steps: Optional[list] = []
    session_id: str

@app.post("/chat", response_model=ChatResponse)
def api_chat(req: ChatRequest, request: Request):
    require_auth(request)
    # Load from supabase or provided history
    if req.history is not None:
        history = req.history
    else:
        history = memory_load(req.session_id)

    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history
    messages.append({"role": "user", "content": req.message})

    final, steps = agent_loop(messages)

    # Save updated history
    new_history = history + [
        {"role": "user", "content": req.message},
        {"role": "assistant", "content": final},
    ]
    memory_save(req.session_id, new_history)

    return ChatResponse(response=final, model=MODEL_ID, steps=steps, session_id=req.session_id)

# ── Sessions API ──
@app.get("/sessions")
def list_sessions(request: Request):
    require_auth(request)
    return memory_list_sessions()

@app.delete("/sessions/{session_id}")
def delete_session(session_id: str, request: Request):
    require_auth(request)
    memory_delete(session_id)
    return {"deleted": session_id}

# ─────────────────────────────────────────
# Gradio UI (auth via middleware)
# ─────────────────────────────────────────
def check_auth_gradio(request: gr.Request):
    """ตรวจ cookie ใน Gradio request"""
    cookies = {}
    raw = request.headers.get("cookie", "")
    for part in raw.split(";"):
        part = part.strip()
        if "=" in part:
            k, v = part.split("=", 1)
            cookies[k.strip()] = v.strip()
    return cookies.get("session") in SESSIONS

def build_gradio():
    with gr.Blocks(title="🤖 AI Agent v6", theme=gr.themes.Soft(primary_hue="violet")) as demo:

        # ── Header ──
        gr.HTML(f"""
        <div style="text-align:center;padding:20px 0 10px">
          <h1 style="margin:0">🤖 AI Agent <span style="font-size:.6em;color:#a78bfa">v6</span></h1>
          <div style="margin-top:10px;display:flex;gap:8px;justify-content:center;flex-wrap:wrap">
            <span style="background:#7c3aed;color:white;padding:4px 12px;border-radius:20px;font-size:.8em">⚡ {MODEL_ID}</span>
            <span style="background:#16a34a;color:white;padding:4px 12px;border-radius:20px;font-size:.8em">🖥️ Shell · Root</span>
            <span style="background:#0369a1;color:white;padding:4px 12px;border-radius:20px;font-size:.8em">🔍 Web Search</span>
            <span style="background:#b45309;color:white;padding:4px 12px;border-radius:20px;font-size:.8em">📁 File R/W</span>
            <span style="background:#be185d;color:white;padding:4px 12px;border-radius:20px;font-size:.8em">🌐 HTTP</span>
            <span style="background:#065f46;color:white;padding:4px 12px;border-radius:20px;font-size:.8em">🧠 Supabase Memory</span>
          </div>
        </div>
        """)

        # ── Session selector ──
        with gr.Row():
            session_id = gr.Textbox(value="default", label="Session ID", scale=3,
                                     placeholder="ตั้งชื่อ session เช่น 'work', 'research'")
            load_btn   = gr.Button("📂 Load", scale=1, variant="secondary")
            new_btn    = gr.Button("➕ New", scale=1, variant="secondary")
            del_btn    = gr.Button("🗑️ Delete", scale=1, variant="stop")

        session_info = gr.Markdown("", visible=True)

        chatbot = gr.Chatbot(
            label="Conversation", type="messages", height=500,
            bubble_full_width=False, show_copy_button=True, render_markdown=True,
        )

        with gr.Row():
            msg_box  = gr.Textbox(placeholder="พิมพ์ข้อความ...", show_label=False, scale=9, container=False)
            send_btn = gr.Button("Send ➤", variant="primary", scale=1)

        with gr.Accordion("⚙️ Settings", open=False):
            with gr.Row():
                temperature = gr.Slider(0.0, 1.0, value=0.7, step=0.05, label="Temperature")
                max_tok     = gr.Slider(256, 8192, value=4096, step=256, label="Max Tokens")

        state = gr.State([])  # openai messages list

        # ── Load session ──
        def load_session(sid, request: gr.Request):
            if not check_auth_gradio(request):
                return [], [], f"❌ Unauthorized"
            msgs = memory_load(sid)
            chatbot_msgs = []
            for m in msgs:
                if m["role"] in ("user", "assistant"):
                    chatbot_msgs.append({"role": m["role"], "content": m["content"]})
            count = len([m for m in msgs if m["role"] == "user"])
            return msgs, chatbot_msgs, f"✅ Loaded session **{sid}** — {count} turn(s)"

        load_btn.click(load_session, [session_id], [state, chatbot, session_info])

        # ── New session ──
        def new_session():
            sid = f"session_{secrets.token_hex(4)}"
            return sid, [], [], f"✅ New session **{sid}**"

        new_btn.click(new_session, outputs=[session_id, state, chatbot, session_info])

        # ── Delete session ──
        def delete_session_ui(sid, request: gr.Request):
            if not check_auth_gradio(request):
                return [], [], f"❌ Unauthorized"
            memory_delete(sid)
            return [], [], f"🗑️ Deleted session **{sid}**"

        del_btn.click(delete_session_ui, [session_id], [state, chatbot, session_info])

        # ── Chat ──
        def respond(user_input, history_state, sid, temp, max_t, request: gr.Request):
            if not check_auth_gradio(request):
                return history_state, history_state, "", "❌ Please login first"
            if not user_input.strip():
                return history_state, history_state, "", ""

            messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history_state
            messages.append({"role": "user", "content": user_input})

            final, steps = agent_loop(messages)

            # Format assistant message with tool steps
            assistant_md = ""
            if steps:
                parts = []
                for step in steps:
                    if step[0] == "tool_call":
                        fn, args = step[1], step[2]
                        args_str = json.dumps(args, ensure_ascii=False, indent=2)
                        parts.append(f"**🔧 Tool: `{fn}`**\n```json\n{args_str}\n```")
                    elif step[0] == "tool_result":
                        fn, result = step[1], step[2]
                        parts.append(f"**📤 Result: `{fn}`**\n```\n{result[:2000]}\n```")
                assistant_md = "\n\n".join(parts) + "\n\n---\n\n" + final
            else:
                assistant_md = final

            new_state = history_state + [
                {"role": "user",      "content": user_input},
                {"role": "assistant", "content": assistant_md},
            ]

            # Save to supabase
            memory_save(sid, new_state)

            info = f"💾 Auto-saved to session **{sid}**" if SUPABASE_URL else "⚠️ Supabase not configured"
            return new_state, new_state, "", info

        send_btn.click(respond, [msg_box, state, session_id, temperature, max_tok],
                       [state, chatbot, msg_box, session_info])
        msg_box.submit(respond, [msg_box, state, session_id, temperature, max_tok],
                       [state, chatbot, msg_box, session_info])

        gr.Examples(
            examples=[
                "ดู disk usage และ memory ปัจจุบัน",
                "ค้นหาข้อมูลเรื่อง Qwen3 32B จากเว็บ",
                "สร้างไฟล์ test.py เขียน fibonacci แล้วรัน",
                "GET https://httpbin.org/get",
                "ดู process ที่กำลังรัน และ port ที่เปิดอยู่",
                "รัน Python คำนวณ 10 prime numbers แรก",
            ],
            inputs=msg_box,
        )

        gr.HTML('<div style="text-align:center;margin-top:16px"><a href="/logout" style="color:#a78bfa;font-size:.85em">🚪 Logout</a></div>')

    return demo


gradio_app = build_gradio()
app = gr.mount_gradio_app(app, gradio_app, path="/ui", root_path="/ui")


# ─────────────────────────────────────────
# Middleware: redirect /ui to login if no session
# ─────────────────────────────────────────
from starlette.middleware.base import BaseHTTPMiddleware

class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        # Allow: login page, logout, health, static
        public = ["/login", "/logout", "/health", "/favicon"]
        if any(path.startswith(p) for p in public):
            return await call_next(request)
        # Check session cookie
        token = request.cookies.get("session")
        if token not in SESSIONS:
            # redirect to login
            return RedirectResponse(url=f"/login")
        return await call_next(request)

app.add_middleware(AuthMiddleware)


# ─────────────────────────────────────────
# Helpers: split long messages
# ─────────────────────────────────────────
def split_message(text: str, limit: int) -> list[str]:
    """Split text into chunks not exceeding limit chars."""
    chunks = []
    while len(text) > limit:
        # Try to split at newline
        split_at = text.rfind("\n", 0, limit)
        if split_at == -1:
            split_at = limit
        chunks.append(text[:split_at])
        text = text[split_at:].lstrip("\n")
    if text:
        chunks.append(text)
    return chunks

def build_reply(user_text: str, session_id: str = "tg_default") -> str:
    """Shared agent call used by both Telegram and Discord."""
    history = memory_load(session_id)
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history
    messages.append({"role": "user", "content": user_text})
    final, _ = agent_loop(messages)
    new_history = history + [
        {"role": "user",      "content": user_text},
        {"role": "assistant", "content": final},
    ]
    memory_save(session_id, new_history)
    return final

# ─────────────────────────────────────────
# Telegram Bot
# ─────────────────────────────────────────
def run_telegram_bot():
    if not TELEGRAM_AVAILABLE:
        print("⚠️  python-telegram-bot not installed — Telegram disabled")
        return
    if not TELEGRAM_TOKEN:
        print("⚠️  TELEGRAM_BOT_TOKEN not set — Telegram disabled")
        return

    async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "👋 สวัสดี! ฉันคือ AI Agent\n"
            "พิมพ์ข้อความได้เลย หรือใช้ /clear เพื่อล้างประวัติ"
        )

    async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
        sid = f"tg_{update.effective_user.id}"
        memory_delete(sid)
        await update.message.reply_text("🗑️ ล้างประวัติการสนทนาแล้ว")

    async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_text = update.message.text
        sid = f"tg_{update.effective_user.id}"
        await update.message.chat.send_action("typing")
        try:
            reply = build_reply(user_text, sid)
        except Exception as e:
            reply = f"❌ Error: {e}"
        # Telegram limit: 4096 chars
        for chunk in split_message(reply, 4096):
            await update.message.reply_text(chunk)

    async def tg_main():
        tg_app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
        tg_app.add_handler(CommandHandler("start", start))
        tg_app.add_handler(CommandHandler("clear", clear))
        tg_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        # initialize + start updater manually to skip signal handler registration
        # (signal handlers only work in main thread)
        await tg_app.initialize()
        await tg_app.updater.start_polling()
        await tg_app.start()
        print("🤖 Telegram bot started")
        await asyncio.Event().wait()  # keep running

    def tg_thread():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(tg_main())
        except Exception as e:
            print(f"[Telegram] error: {e}")

    threading.Thread(target=tg_thread, daemon=True).start()

# ─────────────────────────────────────────
# Discord Bot
# ─────────────────────────────────────────
def run_discord_bot():
    if not DISCORD_AVAILABLE:
        print("⚠️  discord.py not installed — Discord disabled")
        return
    if not DISCORD_TOKEN:
        print("⚠️  DISCORD_BOT_TOKEN not set — Discord disabled")
        return

    intents = discord.Intents.default()
    intents.message_content = True
    client = discord.Client(intents=intents)

    @client.event
    async def on_ready():
        print(f"🎮 Discord bot logged in as {client.user}")

    @client.event
    async def on_message(message: discord.Message):
        if message.author == client.user:
            return

        content = message.content.strip()

        # ── prefix command: !clear ──
        if content == f"{DISCORD_PREFIX}clear":
            sid = f"dc_{message.author.id}"
            memory_delete(sid)
            await message.channel.send("🗑️ ล้างประวัติการสนทนาแล้ว")
            return

        # ── prefix command: !help ──
        if content == f"{DISCORD_PREFIX}help":
            await message.channel.send(
                f"**AI Agent Commands**\n"
                f"`{DISCORD_PREFIX}clear` — ล้างประวัติการสนทนา\n"
                f"`{DISCORD_PREFIX}help`  — แสดงคำสั่ง\n"
                f"หรือพิมพ์ข้อความหา bot ได้โดยตรงในช่องนี้"
            )
            return

        # ── ignore messages that don't start with prefix (in servers) ──
        # In DMs, always respond. In guilds, require prefix or mention
        is_dm = isinstance(message.channel, discord.DMChannel)
        is_mentioned = client.user in message.mentions
        has_prefix = content.startswith(DISCORD_PREFIX)

        if not is_dm and not is_mentioned and not has_prefix:
            return

        # Strip prefix/mention from text
        user_text = content
        if has_prefix:
            user_text = content[len(DISCORD_PREFIX):].strip()
        if is_mentioned:
            user_text = user_text.replace(f"<@{client.user.id}>", "").strip()

        if not user_text:
            return

        sid = f"dc_{message.author.id}"
        async with message.channel.typing():
            try:
                reply = build_reply(user_text, sid)
            except Exception as e:
                reply = f"❌ Error: {e}"

        # Discord limit: 2000 chars
        for chunk in split_message(reply, 1900):
            await message.channel.send(chunk)

    def dc_thread():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(client.start(DISCORD_TOKEN))

    threading.Thread(target=dc_thread, daemon=True).start()

# ─────────────────────────────────────────
# Entrypoint
# ─────────────────────────────────────────
if __name__ == "__main__":
    whoami = subprocess.getoutput("whoami")
    print(f"🚀 AI Agent v6")
    print(f"   Model     : {MODEL_ID}")
    print(f"   Port      : {PORT}")
    print(f"   User      : {whoami}")
    print(f"   Auth      : {'✅ Password set' if ADMIN_PASSWORD != 'changeme' else '⚠️  Using default password!'}")
    print(f"   Supabase  : {'✅ Connected' if SUPABASE_URL else '❌ Not configured'}")
    print(f"   Telegram  : {'✅ Token set' if TELEGRAM_TOKEN else '❌ Not configured'}")
    print(f"   Discord   : {'✅ Token set' if DISCORD_TOKEN else '❌ Not configured'}")
    print(f"   Tools     : {', '.join(t['function']['name'] for t in TOOLS)}")
    run_telegram_bot()
    run_discord_bot()
    uvicorn.run("main:app", host="0.0.0.0", port=PORT, reload=False)
