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

# --- Setup Logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - [AGENT_CORE] - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# --- State & Config ---
WORKSPACE = os.path.abspath("/app/workspace")
current_dir = WORKSPACE

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# Initialize Supabase
supabase = None
if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        logger.info("Database: Connected")
    except:
        logger.error("Database: Connection Failed")

# === 1. Core Execution Tools ===

def execute_command(command: str) -> str:
    global current_dir
    try:
        command = command.strip()
        if command.startswith("cd "):
            target = command[3:].strip()
            new_path = os.path.normpath(os.path.join(current_dir, target))
            if os.path.exists(new_path) and os.path.isdir(new_path):
                current_dir = new_path
                return f"✅ Changed directory to: {current_dir}"
            return f"❌ Error: Path '{target}' not found."

        result = subprocess.run(
            command, shell=True, capture_output=True, text=True, timeout=60, cwd=current_dir
        )
        return f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}\nCODE: {result.returncode}"
    except Exception as e:
        return f"❌ System Error: {str(e)}"

def write_file(path: str, content: str) -> str:
    try:
        full_path = os.path.normpath(os.path.join(current_dir, path))
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"✅ File created: {path}"
    except Exception as e:
        return f"❌ Write Error: {str(e)}"

def read_file(path: str) -> str:
    try:
        full_path = os.path.normpath(os.path.join(current_dir, path))
        with open(full_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"❌ Read Error: {str(e)}"

# === 2. Memory & Intelligence ===

def get_db_context():
    if not supabase: return ""
    try:
        res = supabase.table("memories").select("*").order("created_at", desc=True).limit(5).execute()
        if res.data:
            return "\n".join([f"Previous Task: {m['user_query']}\nResult: {m['content']}" for m in reversed(res.data)])
    except: pass
    return ""

def run_agent(user_input: str, history: list) -> dict:
    if not GEMINI_API_KEY:
        return {"reply": "Error: GEMINI_API_KEY is missing.", "steps": []}
    
    genai.configure(api_key=GEMINI_API_KEY)
    
    # --- ปรับแก้ชื่อโมเดลเป็นมาตรฐานสูงสุด ---
    # ใช้ชื่อ 'gemini-1.5-flash' (ตัวหลัก) หรือ 'gemini-1.5-flash-001'
    try:
        model = genai.GenerativeModel(
            model_name='gemini-1.5-flash', # ตัดคำว่า -latest ออกเพื่อความเสถียร
            tools=[execute_command, write_file, read_file]
        )
    except:
        # Fallback กรณี API บางตัวต้องการเจาะจงเวอร์ชัน
        model = genai.GenerativeModel(model_name='models/gemini-1.5-flash')

    # Prepare Context
    db_ctx = get_db_context()
    sys_instruction = f"""
[SYSTEM_CONTEXT]
Current Working Directory: {current_dir}
DB Memory: {db_ctx}

[INSTRUCTIONS]
1. You are a technical assistant. Execute commands directly.
2. Provide raw output from the terminal.
3. If a command fails, fix it.
"""

    # Format history for Gemini
    gemini_history = []
    for h in history[-8:]:
        role = "user" if h["role"] == "user" else "model"
        gemini_history.append({"role": role, "parts": [h["content"]]})

    chat = model.start_chat(history=gemini_history)
    steps = []

    try:
        # ส่ง Prompt พร้อมบริบทแบบ Inline
        response = chat.send_message(f"{sys_instruction}\n\nUser Question: {user_input}")
        
        # วนลูปจัดการ Tool Calls
        # Note: SDK เวอร์ชันใหม่มักจะจัดการ loop ให้ แต่ถ้าคุณต้องการเก็บ steps ไปโชว์ใน UI
        # ต้องดึงออกมาแบบนี้:
        for part in response.candidates[0].content.parts:
            if fn := part.function_call:
                args = dict(fn.args)
                res = ""
                if fn.name == "execute_command": res = execute_command(args.get("command"))
                elif fn.name == "write_file": res = write_file(args.get("path"), args.get("content"))
                elif fn.name == "read_file": res = read_file(args.get("path"))
                steps.append({"tool": fn.name, "args": args, "result": res})

        # Save to Supabase
        if supabase:
            try:
                supabase.table("memories").insert({
                    "user_query": user_input,
                    "content": response.text,
                    "project_context": "TECHNICAL_AGENT"
                }).execute()
            except: pass

        return {"reply": response.text, "steps": steps}
    except Exception as e:
        # หากเกิด 404 หรือปัญหาเรื่องโมเดล จะแจ้งเตือนที่นี่
        return {"reply": f"Engine Connectivity Error: {str(e)}", "steps": steps}

# === 3. API Entry Points ===

class ChatRequest(BaseModel):
    message: str
    history: list = []

@app.post("/chat")
async def chat(req: ChatRequest):
    return run_agent(req.message, req.history)

@app.get("/", response_class=HTMLResponse)
def home():
    try:
        with open("static/index.html", "r", encoding="utf-8") as f: return f.read()
    except: return "Frontend UI Not Found"

if __name__ == "__main__":
    os.makedirs(WORKSPACE, exist_ok=True)
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
