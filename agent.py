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

# --- System Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - [AGENT_CORE] - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# --- Paths & State ---
WORKSPACE = os.path.abspath("/app/workspace")
current_dir = WORKSPACE

# --- Configuration ---
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# Initialize Supabase
if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
        logger.info("Supabase connected successfully.")
    except Exception as e:
        logger.error(f"Supabase connection failed: {e}")
        supabase = None
else:
    supabase = None

# === 1. Functional Tools ===

def execute_command(command: str) -> str:
    """รันคำสั่ง Linux ในระบบจริง"""
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
        output = f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}\nEXIT_CODE: {result.returncode}"
        return output
    except Exception as e:
        return f"❌ System Error: {str(e)}"

def write_file(path: str, content: str) -> str:
    """เขียนหรือสร้างไฟล์ลงในดิสก์"""
    try:
        full_path = os.path.normpath(os.path.join(current_dir, path))
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"✅ File created: {path}"
    except Exception as e:
        return f"❌ Write Error: {str(e)}"

def read_file(path: str) -> str:
    """อ่านข้อมูลจากไฟล์"""
    try:
        full_path = os.path.normpath(os.path.join(current_dir, path))
        with open(full_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"❌ Read Error: {str(e)}"

# === 2. Memory Management (Supabase) ===

def save_to_memory(user_msg: str, ai_reply: str):
    if supabase:
        try:
            supabase.table("memories").insert({
                "user_query": user_msg,
                "content": ai_reply,
                "project_context": "AGENT_TERMINAL_V10"
            }).execute()
        except Exception as e:
            logger.error(f"Save memory error: {e}")

def get_memory_context():
    if supabase:
        try:
            res = supabase.table("memories").select("*").order("created_at", desc=True).limit(5).execute()
            if res.data:
                mem_list = [f"User: {m['user_query']}\nAI: {m['content']}" for m in reversed(res.data)]
                return "\n".join(mem_list)
        except: pass
    return "No previous context."

# === 3. AI Agent Core (Gemini) ===

def run_agent(user_input: str, history: list) -> dict:
    if not GEMINI_API_KEY:
        return {"reply": "Error: GEMINI_API_KEY is missing.", "steps": []}
    
    genai.configure(api_key=GEMINI_API_KEY)
    
    # ดึงความจำจาก Supabase
    past_memory = get_memory_context()
    
    # ตั้งค่าโมเดลและเครื่องมือ
    model = genai.GenerativeModel(
        model_name='gemini-1.5-flash-latest',
        tools=[execute_command, write_file, read_file]
    )

    # เตรียมประวัติการคุย
    gemini_history = []
    for h in history[-10:]:
        role = "user" if h["role"] == "user" else "model"
        gemini_history.append({"role": role, "parts": [h["content"]]})

    # System Instruction แบบ Tech-Focused
    sys_instr = f"""
[SYSTEM_CONTROL_ACTIVE]
Role: Advanced Technical AI Agent.
Working Directory: {current_dir}
Context from Database:
{past_memory}

Instructions:
1. Be technical, precise, and concise.
2. Use tools to execute tasks or verify information.
3. Show raw terminal output without summarization unless requested.
4. If an error occurs, analyze it and propose a solution.
"""

    chat = model.start_chat(history=gemini_history)
    steps = []

    try:
        # ส่ง prompt พร้อมบริบท
        full_prompt = f"{sys_instr}\n\nUser: {user_input}"
        response = chat.send_message(full_prompt)
        
        # จัดเก็บขั้นตอนการใช้ Tool
        for part in response.candidates[0].content.parts:
            if fn := part.function_call:
                args = {k: v for k, v in fn.args.items()}
                res_val = ""
                if fn.name == "execute_command": res_val = execute_command(args.get("command"))
                elif fn.name == "write_file": res_val = write_file(args.get("path"), args.get("content"))
                elif fn.name == "read_file": res_val = read_file(args.get("path"))
                steps.append({"tool": fn.name, "args": args, "result": res_val})

        # บันทึกลง Supabase
        save_to_memory(user_input, response.text)
        
        return {"reply": response.text, "steps": steps}
    except Exception as e:
        return {"reply": f"AI Engine Error: {str(e)}", "steps": steps}

# === 4. API Endpoints ===

class ChatRequest(BaseModel):
    message: str
    history: list = []

@app.post("/chat")
async def chat_endpoint(req: ChatRequest):
    return run_agent(req.message, req.history)

@app.get("/", response_class=HTMLResponse)
def index_ui():
    try:
        with open("static/index.html", "r", encoding="utf-8") as f: return f.read()
    except: return "UI File not found."

if __name__ == "__main__":
    os.makedirs(WORKSPACE, exist_ok=True)
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
