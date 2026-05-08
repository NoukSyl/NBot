import os
import subprocess
import logging
import google.generativeai as genai
import uvicorn
import json
import asyncio
from fastapi import FastAPI
from fastapi.responses import StreamingResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# --- Configuration & Logging ---
logging.basicConfig(level=logging.INFO)
app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
WORKSPACE = os.path.abspath("/app/workspace")
current_dir = WORKSPACE

# --- System Prompt (The Brain) ---
SYSTEM_PROMPT = (
    "You are a High-Speed Terminal AI Agent. "
    "Your current working directory is: {cwd}\n"
    "RULES:\n"
    "1. If the user just greets or chats, reply instantly as a friendly assistant.\n"
    "2. If the user gives a command or task, use the provided tools immediately.\n"
    "3. Do not explain what you are going to do, JUST DO IT.\n"
    "4. When a task is 100% finished, summarize the result briefly."
)

# --- Tool Definitions ---
def execute_command(command: str) -> str:
    global current_dir
    cmd = command.strip()
    try:
        if cmd.startswith("cd "):
            target = cmd[3:].strip()
            new_path = os.path.normpath(os.path.join(current_dir, target))
            if os.path.exists(new_path):
                current_dir = new_path
                return f"Directory changed to: {current_dir}"
            return "Error: Path not found."
        
        process = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=60, cwd=current_dir
        )
        output = f"STDOUT: {process.stdout}\nSTDERR: {process.stderr}".strip()
        return output or "Success (No output)"
    except Exception as e:
        return f"Execution Error: {str(e)}"

def write_file(path: str, content: str) -> str:
    try:
        full_path = os.path.normpath(os.path.join(current_dir, path))
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"File saved successfully: {path}"
    except Exception as e:
        return f"Write Error: {str(e)}"

def read_file(path: str) -> str:
    try:
        full_path = os.path.normpath(os.path.join(current_dir, path))
        with open(full_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"Read Error: {str(e)}"

# --- Core Streaming Logic ---
async def stream_agent_logic(user_input, history):
    if not GEMINI_API_KEY:
        yield f"data: {json.dumps({'reply': 'Error: Missing API Key'})}\n\n"
        return

    genai.configure(api_key=GEMINI_API_KEY)
    
    # บังคับใช้ System Prompt เพื่อคุมพฤติกรรม AI
    model = genai.GenerativeModel(
        model_name='gemini-3.1-flash-lite',
        tools=[execute_command, write_file, read_file],
        system_instruction=SYSTEM_PROMPT.format(cwd=current_dir)
    )
    
    # จัดการประวัติการสนทนา (ส่งแค่ 5 ข้อความล่าสุดเพื่อลดความหน่วง)
    chat_history = [{"role": h["role"], "parts": [h["content"]]} for h in history[-5:]]
    chat = model.start_chat(history=chat_history)
    
    try:
        # เริ่มต้นการสนทนา
        response = chat.send_message(user_input)
        
        # Autonomous Loop (สูงสุด 12 รอบสำหรับงานซับซ้อน)
        for _ in range(12):
            parts = response.candidates[0].content.parts
            function_calls = [p.function_call for p in parts if p.function_call]
            
            # ถ้าไม่มี Tool Call แล้ว ให้ส่งคำตอบสุดท้ายออกไป
            if not function_calls:
                yield f"data: {json.dumps({'reply': response.text})}\n\n"
                break
            
            tool_responses = []
            for fn in function_calls:
                args = dict(fn.args)
                fn_name = fn.name
                
                # รัน Tool ตามคำสั่ง
                if fn_name == "execute_command":
                    result = execute_command(args.get("command", ""))
                elif fn_name == "write_file":
                    result = write_file(args.get("path", ""), args.get("content", ""))
                elif fn_name == "read_file":
                    result = read_file(args.get("path", ""))
                
                # ส่ง Log ของขั้นตอนนี้กลับไปที่มือถือทันที (Real-time)
                yield f"data: {json.dumps({'step': fn_name, 'result': result})}\n\n"
                
                tool_responses.append(genai.protos.Part(
                    function_response=genai.protos.FunctionResponse(name=fn_name, response={'result': result})
                ))
            
            # ส่งผลลัพธ์ของ Tool กลับไปให้ AI ตัดสินใจต่อ
            response = chat.send_message(genai.protos.Content(parts=tool_responses))
            await asyncio.sleep(0.05) # Small gap for stability

    except Exception as e:
        yield f"data: {json.dumps({'reply': f'Runtime Error: {str(e)}'})}\n\n"

# --- API Endpoints ---
@app.post("/chat")
async def chat_endpoint(req: dict):
    return StreamingResponse(
        stream_agent_logic(req.get('message', ''), req.get('history', [])),
        media_type="text/event-stream"
    )

@app.get("/")
def home():
    try:
        with open("static/index.html", "r", encoding="utf-8") as f:
            return HTMLResponse(f.read())
    except:
        return HTMLResponse("<h1>Frontend (static/index.html) not found</h1>")

if __name__ == "__main__":
    os.makedirs(WORKSPACE, exist_ok=True)
    os.makedirs("static", exist_ok=True)
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
