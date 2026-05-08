import os
import subprocess
import json
import logging
import google.generativeai as genai
from supabase import create_client, Client
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import uvicorn

# --- System Configuration ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - [AGENT_CORE] - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# --- Workspace & Credentials ---
WORKSPACE = os.path.abspath("/app/workspace")
current_dir = WORKSPACE

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# Initialize Database
supabase = None
if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        logger.info("Database: Supabase Connected")
    except Exception as e:
        logger.error(f"Database: Connection Failed -> {e}")

# === 1. Execution Engine (Bash Tools) ===

def execute_command(command: str) -> str:
    """รันคำสั่ง Linux ใน Workspace"""
    global current_dir
    command = command.strip()
    try:
        if command.startswith("cd "):
            target = command[3:].strip()
            new_path = os.path.normpath(os.path.join(current_dir, target))
            if os.path.exists(new_path) and os.path.isdir(new_path):
                current_dir = new_path
                return f"✅ Directory changed: {current_dir}"
            return f"❌ Error: Path '{target}' not found."

        result = subprocess.run(
            command, shell=True, capture_output=True, text=True, timeout=60, cwd=current_dir
        )
        output = f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}\nCODE: {result.returncode}"
        return output
    except Exception as e:
        return f"❌ Runtime Error: {str(e)}"

def write_file(path: str, content: str) -> str:
    """สร้างหรือแก้ไขไฟล์"""
    try:
        full_path = os.path.normpath(os.path.join(current_dir, path))
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"✅ Successfully written: {path}"
    except Exception as e:
        return f"❌ Write Error: {str(e)}"

def read_file(path: str) -> str:
    """อ่านข้อมูลไฟล์"""
    try:
        full_path = os.path.normpath(os.path.join(current_dir, path))
        with open(full_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"❌ Read Error: {str(e)}"

# === 2. AI Logic (Gemini 3.1 Flash) ===

def run_agent(user_input: str, history: list) -> dict:
    if not GEMINI_API_KEY:
        return {"reply": "Error: GEMINI_API_KEY not found in Environment.", "steps": []}
    
    genai.configure(api_key=GEMINI_API_KEY)
    
    # ดึงความจำล่าสุดจาก Supabase (ถ้ามี)
    db_context = ""
    if supabase:
        try:
            res = supabase.table("memories").select("*").order("created_at", desc=True).limit(3).execute()
            db_context = "\n".join([f"PastTask: {m['user_query']}" for m in reversed(res.data)])
        except: pass

    # ตั้งค่าโมเดลเป็น Gemini 3.1 Flash (รุ่นล่าสุด)
    model = genai.GenerativeModel(
        model_name='gemini-flash-latest', 
        tools=[execute_command, write_file, read_file]
    )

    # จัดการประวัติการสนทนา (ส่งไปแค่ 10 ข้อความเพื่อประหยัด Token)
    chat_history = []
    for h in history[-10:]:
        role = "user" if h["role"] == "user" else "model"
        chat_history.append({"role": role, "parts": [h["content"]]})

    # System Instruction
    sys_prompt = f"""
[SYSTEM_OPERATOR_V10.5]
Role: High-Performance Technical Assistant.
CWD: {current_dir}
DB_Context: {db_context}

Rules:
1. Provide raw terminal output. Be concise.
2. If a task requires multiple steps, use tools sequentially.
3. No conversational filler. Just results.
"""

    chat = model.start_chat(history=chat_history)
    steps = []

    try:
        # ส่งคำสั่งให้ AI
        response = chat.send_message(f"{sys_prompt}\n\nUser: {user_input}")
        
        # ประมวลผล Tool Calls
        for part in response.candidates[0].content.parts:
            if fn := part.function_call:
                args = dict(fn.args)
                res_val = ""
                if fn.name == "execute_command": res_val = execute_command(args.get("command"))
                elif fn.name == "write_file": res_val = write_file(args.get("path"), args.get("content"))
                elif fn.name == "read_file": res_val = read_file(args.get("path"))
                steps.append({"tool": fn.name, "args": args, "result": res_val})

        # บันทึกลงฐานข้อมูล
        if supabase:
            try:
                supabase.table("memories").insert({
                    "user_query": user_input,
                    "content": response.text,
                    "project_context": "GEMINI_3.1_FLASH_AGENT"
                }).execute()
            except: pass

        return {"reply": response.text, "steps": steps}
    except Exception as e:
        return {"reply": f"AI Engine Error: {str(e)}", "steps": steps}

# === 3. Web Service (FastAPI) ===

class ChatRequest(BaseModel):
    message: str
    history: list = []

@app.post("/chat")
async def chat_api(req: ChatRequest):
    return run_agent(req.message, req.history)

@app.get("/", response_class=HTMLResponse)
def ui():
    try:
        with open("static/index.html", "r", encoding="utf-8") as f: return f.read()
    except: return "<h1>Terminal UI Ready</h1>"

if __name__ == "__main__":
    os.makedirs(WORKSPACE, exist_ok=True)
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
