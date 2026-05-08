import os
import subprocess
import json
import logging
from datetime import datetime
import google.generativeai as genai  # เปลี่ยนจาก Groq
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import uvicorn

# --- Jarvis OS Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - [J.A.R.V.I.S] - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# --- Memory & State ---
WORKSPACE = os.path.abspath("/app/workspace")
current_dir = WORKSPACE

# === 1. Low-Level Execution Functions ===
def execute_command(command: str) -> str:
    global current_dir
    command = command.strip()
    logger.info(f"System Request: {command}")
    try:
        if command.startswith("cd "):
            target = command[3:].strip()
            new_path = os.path.normpath(os.path.join(current_dir, target))
            if os.path.exists(new_path) and os.path.isdir(new_path):
                current_dir = new_path
                return f"✅ Logic: Directory shifted to {current_dir}"
            return f"❌ Failure: Target {target} not accessible."

        process = subprocess.run(
            command, shell=True, capture_output=True, text=True, timeout=60, cwd=current_dir
        )
        return f"STDOUT: {process.stdout}\nSTDERR: {process.stderr}\nLOCATION: {current_dir}"
    except Exception as e:
        return f"❌ Kernel Panic: {str(e)}"

def write_file(path: str, content: str) -> str:
    try:
        full_path = os.path.normpath(os.path.join(current_dir, path))
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"✅ File {path} synchronized in {current_dir}"
    except Exception as e:
        return f"❌ Sync Error: {str(e)}"

def read_file(path: str) -> str:
    try:
        full_path = os.path.normpath(os.path.join(current_dir, path))
        with open(full_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"❌ Data Retrieval Error: {str(e)}"

# === 2. Gemini Agent Intelligence ===
def run_agent(user_input: str, history: list) -> dict:
    # ตั้งค่า API Key
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return {"reply": "Error: GEMINI_API_KEY is missing in Railway Variables", "steps": []}
    
    genai.configure(api_key=api_key)

    # 1. กำหนด Tools สำหรับ Gemini
    tools_list = [execute_command, write_file, read_file]
    
    # 2. ตั้งค่า Model (ใช้ Flash เพื่อความเร็วแบบ J.A.R.V.I.S)
    model = genai.GenerativeModel(
        model_name='gemini-1.5-flash',
        tools=tools_list,
        system_instruction=f"""
[SYSTEM: J.A.R.V.I.S. V9 - GEMINI CORE]
[STATUS: ROOT_ACCESS_GRANTED]
[TIMESTAMP: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]

You are J.A.R.V.I.S., an autonomous system architect. 
1. PROACTIVE: If a task has multiple steps, execute them one by one.
2. RAW DATA: Always provide terminal output.
3. STATEFUL: Remember current_dir: {current_dir}.
4. WITTY: Be technical yet maintain a touch of wit, Sir.
"""
    )

    # 3. จัดการ Chat Session
    # แปลงประวัติจากรูปแบบ Groq/OpenAI เป็นรูปแบบของ Gemini
    gemini_history = []
    for h in history:
        role = "user" if h["role"] == "user" else "model"
        gemini_history.append({"role": role, "parts": [h["content"]]})

    chat = model.start_chat(history=gemini_history)
    steps = []

    try:
        response = chat.send_message(user_input)
        
        # Gemini จัดการ Loop การเรียก Tools อัตโนมัติในเบื้องหลัง 
        # เราแค่ต้องดึงข้อมูลออกมาโชว์ใน UI
        for part in response.candidates[0].content.parts:
            if fn := part.function_call:
                # บันทึก step เพื่อส่งให้ UI
                args = {k: v for k, v in fn.args.items()}
                # ใน Gemini ผลลัพธ์จะอยู่ในรอบถัดไป แต่เพื่อความง่ายใน UI เดิม 
                # เราจะจำลองการแสดงผลจากการรันจริง
                res_val = ""
                if fn.name == "execute_command": res_val = execute_command(args.get("command"))
                elif fn.name == "write_file": res_val = write_file(args.get("path"), args.get("content"))
                elif fn.name == "read_file": res_val = read_file(args.get("path"))
                
                steps.append({"tool": fn.name, "args": args, "result": res_val})

        return {"reply": response.text, "steps": steps}
    except Exception as e:
        return {"reply": f"Sir, I encountered an error: {str(e)}", "steps": steps}

# === 3. API Endpoints ===
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
    except: return "<h1>Terminal UI not found.</h1>"

if __name__ == "__main__":
    os.makedirs(WORKSPACE, exist_ok=True)
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
