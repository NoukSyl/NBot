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

# --- Setup Logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - [AGENT_V10] - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# --- Environment Configuration ---
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
        logger.info("Database connected.")
    except: logger.error("Database connection failed.")

# === 1. Tool Definitions ===

def execute_command(command: str) -> str:
    global current_dir
    try:
        command = command.strip()
        if command.startswith("cd "):
            target = command[3:].strip()
            new_path = os.path.normpath(os.path.join(current_dir, target))
            if os.path.exists(new_path) and os.path.isdir(new_path):
                current_dir = new_path
                return f"✅ Switched to {current_dir}"
            return f"❌ Directory not found: {target}"
        
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True, timeout=60, cwd=current_dir
        )
        return f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}\nEXIT_CODE: {result.returncode}"
    except Exception as e:
        return f"❌ Execution Error: {str(e)}"

def write_file(path: str, content: str) -> str:
    try:
        full_path = os.path.normpath(os.path.join(current_dir, path))
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"✅ File saved: {path}"
    except Exception as e:
        return f"❌ Write Error: {str(e)}"

def read_file(path: str) -> str:
    try:
        full_path = os.path.normpath(os.path.join(current_dir, path))
        with open(full_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"❌ Read Error: {str(e)}"

# === 2. AI Core (Gemini 3.1 Flash Loop) ===

def run_agent(user_input: str, history: list) -> dict:
    if not GEMINI_API_KEY:
        return {"reply": "Missing API Key", "steps": []}

    genai.configure(api_key=GEMINI_API_KEY)
    
    # ใช้ชื่อรุ่น gemini-flash-latest ตามที่คุณเลือก
    model = genai.GenerativeModel(
        model_name='gemini-flash-latest', 
        tools=[execute_command, write_file, read_file]
    )

    chat_history = []
    for h in history[-10:]:
        role = "user" if h["role"] == "user" else "model"
        chat_history.append({"role": role, "parts": [h["content"]]})

    sys_instr = f"""
[AGENT_SYSTEM_V10.6]
Environment: Linux (Railway)
Current Dir: {current_dir}
Status: Technical Assistant Mode (No Roleplay)
Rule: Use tools for all technical tasks. Execute sequential steps if needed.
"""

    chat = model.start_chat(history=chat_history)
    steps = []

    try:
        # ส่งคำสั่งเริ่มต้น
        response = chat.send_message(f"{sys_instr}\n\nUser: {user_input}")

        # วนลูปจัดการ Tool Calls จนกว่า AI จะทำงานเสร็จ
        # นี่คือส่วนที่แก้ปัญหา "Could not convert part.function_call to text"
        max_turns = 5  # ป้องกัน Loop นรก
        turn = 0
        
        while turn < max_turns:
            # เช็คว่ารอบนี้มีการเรียกใช้ Function หรือไม่
            parts = response.candidates[0].content.parts
            function_calls = [p.function_call for p in parts if p.function_call]
            
            if not function_calls:
                break  # ไม่มี Function Call แล้ว จบการทำงาน
            
            turn += 1
            tool_responses = []
            
            for fn in function_calls:
                args = dict(fn.args)
                res_val = ""
                
                # เรียกใช้งาน Tool ตามที่ AI สั่ง
                if fn.name == "execute_command": res_val = execute_command(args.get("command"))
                elif fn.name == "write_file": res_val = write_file(args.get("path"), args.get("content"))
                elif fn.name == "read_file": res_val = read_file(args.get("path"))
                
                steps.append({"tool": fn.name, "args": args, "result": res_val})
                
                # เตรียมคำตอบส่งกลับไปให้ AI
                tool_responses.append(
                    genai.protos.Part(
                        function_response=genai.protos.FunctionResponse(
                            name=fn.name, 
                            response={'result': res_val}
                        )
                    )
                )
            
            # ส่งผลลัพธ์กลับไปให้ AI เพื่อประมวลผลต่อ
            response = chat.send_message(genai.protos.Content(parts=tool_responses))

        # เมื่อ Loop จบ response.text จะพร้อมใช้งาน
        final_reply = response.text
        
        if supabase:
            try:
                supabase.table("memories").insert({
                    "user_query": user_input,
                    "content": final_reply,
                    "project_context": "TECHNICAL_AGENT_STABLE"
                }).execute()
            except: pass

        return {"reply": final_reply, "steps": steps}

    except Exception as e:
        logger.error(f"Error in Agent: {str(e)}")
        return {"reply": f"System Error: {str(e)}", "steps": steps}

# === 3. FastAPI Entry Points ===

class ChatRequest(BaseModel):
    message: str
    history: list = []

@app.post("/chat")
async def chat_endpoint(req: ChatRequest):
    return run_agent(req.message, req.history)

@app.get("/", response_class=HTMLResponse)
def index():
    try:
        with open("static/index.html", "r", encoding="utf-8") as f: return f.read()
    except: return "Frontend missing."

if __name__ == "__main__":
    os.makedirs(WORKSPACE, exist_ok=True)
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
