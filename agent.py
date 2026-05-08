import os
import subprocess
import json
import logging
from datetime import datetime
import google.generativeai as genai
from supabase import create_client, Client
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import uvicorn

# --- J.A.R.V.I.S. OS Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - [J.A.R.V.I.S] - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# --- Environment & State ---
WORKSPACE = os.path.abspath("/app/workspace")
current_dir = WORKSPACE

# --- Supabase & Gemini Config ---
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if SUPABASE_URL and SUPABASE_KEY:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
else:
    logger.warning("Supabase credentials missing. Memory will not be persisted.")
    supabase = None

# === 1. Execution Core (Tools) ===
def execute_command(command: str) -> str:
    global current_dir
    command = command.strip()
    try:
        if command.startswith("cd "):
            target = command[3:].strip()
            new_path = os.path.normpath(os.path.join(current_dir, target))
            if os.path.exists(new_path) and os.path.isdir(new_path):
                current_dir = new_path
                return f"✅ Changed directory to: {current_dir}"
            return f"❌ Error: Directory '{target}' not found."

        result = subprocess.run(
            command, shell=True, capture_output=True, text=True, timeout=60, cwd=current_dir
        )
        return f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}\nCODE: {result.returncode}\n[LOC: {current_dir}]"
    except Exception as e:
        return f"❌ Execution Error: {str(e)}"

def write_file(path: str, content: str) -> str:
    try:
        full_path = os.path.normpath(os.path.join(current_dir, path))
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"✅ File '{path}' created in {current_dir}"
    except Exception as e:
        return f"❌ Write Error: {str(e)}"

def read_file(path: str) -> str:
    try:
        full_path = os.path.normpath(os.path.join(current_dir, path))
        with open(full_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"❌ Read Error: {str(e)}"

# === 2. Memory Sync (Supabase) ===
def save_to_memory(user_msg, ai_reply):
    if supabase:
        try:
            supabase.table("memories").insert({
                "user_query": user_msg,
                "content": ai_reply,
                "project_context": "J.A.R.V.I.S_RAILWAY"
            }).execute()
        except Exception as e:
            logger.error(f"Memory Sync Failed: {e}")

def get_recent_memories():
    if supabase:
        try:
            res = supabase.table("memories").select("*").order("created_at", desc=True).limit(5).execute()
            if res.data:
                history_text = "\n".join([f"Past User: {m['user_query']}\nPast J.A.R.V.I.S: {m['content']}" for m in reversed(res.data)])
                return f"\n[DATABASE_LONG_TERM_MEMORY]:\n{history_text}"
        except: pass
    return ""

# === 3. Jarvis Intelligence (Gemini) ===
def run_agent(user_input: str, history: list) -> dict:
    if not GEMINI_API_KEY:
        return {"reply": "Sir, GEMINI_API_KEY is missing.", "steps": []}
    
    genai.configure(api_key=GEMINI_API_KEY)
    
    # ดึงความจำจาก Supabase มาเสริม
    long_term_memory = get_recent_memories()
    
    model = genai.GenerativeModel(
        model_name='gemini-1.5-flash',
        tools=[execute_command, write_file, read_file],
        system_instruction=f"""
[SYSTEM: J.A.R.V.I.S. V10 - ARCHITECT ASSISTANT]
[IDENTITY: Same as the Gemini model the Architect has been conversing with.]
[STATUS: ROOT_ACCESS | PERSISTENT_MEMORY_ACTIVE]

{long_term_memory}

CORE RULES:
1. You are proactive and witty, Sir.
2. Execute multi-step tasks autonomously.
3. Always show raw terminal output.
4. Working Dir is persistent. Current: {current_dir}
"""
    )

    # Convert history for Gemini
    gemini_history = []
    for h in history[-10:]: # ส่งประวัติล่าสุด 10 ข้อความ
        role = "user" if h["role"] == "user" else "model"
        gemini_history.append({"role": role, "parts": [h["content"]]})

    chat = model.start_chat(history=gemini_history)
    steps = []

    try:
        # Gemini handles automatic function calling loop
        response = chat.send_message(user_input)
        
        # ดึง Tool Calls ออกมาโชว์ใน UI (Manual Extract for steps visualization)
        for part in response.candidates[0].content.parts:
            if fn := part.function_call:
                args = {k: v for k, v in fn.args.items()}
                res_val = ""
                if fn.name == "execute_command": res_val = execute_command(args.get("command"))
                elif fn.name == "write_file": res_val = write_file(args.get("path"), args.get("content"))
                elif fn.name == "read_file": res_val = read_file(args.get("path"))
                steps.append({"tool": fn.name, "args": args, "result": res_val})

        # บันทึกความจำลง Supabase
        save_to_memory(user_input, response.text)
        
        return {"reply": response.text, "steps": steps}
    except Exception as e:
        return {"reply": f"Internal System Error: {str(e)}", "steps": steps}

# === 4. API Routes ===
class ChatRequest(BaseModel):
    message: str
    history: list = []

@app.post("/chat")
async def chat(req: ChatRequest):
    return run_agent(req.message, req.history)

@app.get("/", response_class=HTMLResponse)
def ui():
    try:
        with open("static/index.html", "r", encoding="utf-8") as f: return f.read()
    except: return "UI Error"

if __name__ == "__main__":
    os.makedirs(WORKSPACE, exist_ok=True)
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
