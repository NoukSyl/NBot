import os
import subprocess
import json
import asyncio
import logging
import uvicorn  # แก้ไขจุดที่ทำให้ NameError ตาม Log
import google.generativeai as genai
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from supabase import create_client, Client

# --- Setup & Config ---
logging.basicConfig(level=logging.INFO)
app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
WORKSPACE = os.path.abspath("/app/workspace")

# Connect Supabase
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL and SUPABASE_KEY else None

# --- Tools ---
def execute_command(command: str):
    try:
        # ป้องกันการรันคำสั่งที่ค้างนานเกินไป
        res = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=30, cwd=WORKSPACE)
        return f"STDOUT: {res.stdout}\nSTDERR: {res.stderr}".strip() or "Success"
    except Exception as e:
        return f"Error: {str(e)}"

def db_query(table: str, action: str, data: dict = None):
    """AI Tool สำหรับจัดการ Supabase"""
    if not supabase: return "Supabase not configured."
    try:
        if action == "insert":
            res = supabase.table(table).insert(data).execute()
        elif action == "select":
            res = supabase.table(table).select("*").limit(5).execute()
        return json.dumps(res.data)
    except Exception as e:
        return f"DB Error: {str(e)}"

# --- Core Engine ---
async def stream_agent_logic(user_input, history):
    if not GEMINI_API_KEY:
        yield f"data: {json.dumps({'reply': 'Missing API Key'})}\n\n"
        return

    genai.configure(api_key=GEMINI_API_KEY)
    
    # เช็คว่าเป็นคำสั่งเชิงเทคนิคหรือไม่ เพื่อเลือกใช้ Tools (Short-Circuit)
    tech_keywords = ['ls', 'run', 'python', 'db', 'sql', 'mkdir', 'write', 'cat', 'git']
    is_technical = any(k in user_input.lower() for k in tech_keywords)
    
    model = genai.GenerativeModel(
        model_name='gemini-3.1-flash-lite',
        tools=[execute_command, db_query] if is_technical else [],
        system_instruction=(
            "You are a Terminal Agent. "
            "If it's a simple chat, reply instantly. "
            "If it's a task, use tools. Be extremely concise."
        )
    )
    
    chat = model.start_chat(history=[{"role": h["role"], "parts": [h["content"]]} for h in history[-3:]])
    
    try:
        response = chat.send_message(user_input)
        
        # ลูปประมวลผล Tool (สูงสุด 10 รอบ)
        for _ in range(10):
            parts = response.candidates[0].content.parts
            calls = [p.function_call for p in parts if p.function_call]
            
            if not calls:
                # บันทึกลง Supabase (Background)
                if supabase:
                    try: supabase.table("logs").insert({"msg": user_input, "reply": response.text}).execute()
                    except: pass
                
                yield f"data: {json.dumps({'reply': response.text})}\n\n"
                break
            
            tool_responses = []
            for fn in calls:
                args = dict(fn.args)
                if fn.name == "execute_command":
                    result = execute_command(args.get("command", ""))
                elif fn.name == "db_query":
                    result = db_query(args.get("table", ""), args.get("action", ""), args.get("data", {}))
                
                yield f"data: {json.dumps({'step': fn.name, 'result': result})}\n\n"
                tool_responses.append(genai.protos.Part(
                    function_response=genai.protos.FunctionResponse(name=fn.name, response={'result': result})
                ))
            
            response = chat.send_message(genai.protos.Content(parts=tool_responses))
            await asyncio.sleep(0.01)

    except Exception as e:
        yield f"data: {json.dumps({'reply': f'Runtime Error: {str(e)}'})}\n\n"

@app.post("/chat")
async def chat_endpoint(req: Request):
    data = await req.json()
    return StreamingResponse(
        stream_agent_logic(data.get('message', ''), data.get('history', [])),
        media_type="text/event-stream"
    )

@app.get("/", response_class=HTMLResponse)
def index():
    try:
        with open("static/index.html", "r", encoding="utf-8") as f: return f.read()
    except: return "Frontend missing."

if __name__ == "__main__":
    os.makedirs(WORKSPACE, exist_ok=True)
    # รันเซิร์ฟเวอร์
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
