import os, subprocess, json, asyncio, logging
import google.generativeai as genai
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from supabase import create_client, Client

# --- Setup ---
logging.basicConfig(level=logging.INFO)
app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# Config
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
WORKSPACE = os.path.abspath("/app/workspace")

# Connect Supabase
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL else None

# --- DB Tools ---
def db_query(table: str, query_type: str, data: dict = None):
    """Tool for AI to manage Supabase data"""
    try:
        if query_type == "insert":
            res = supabase.table(table).insert(data).execute()
        elif query_type == "select":
            res = supabase.table(table).select("*").limit(10).execute()
        return str(res.data)
    except Exception as e: return f"DB Error: {str(e)}"

def execute_command(command: str):
    try:
        res = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=30, cwd=WORKSPACE)
        return f"{res.stdout}\n{res.stderr}".strip() or "Success"
    except Exception as e: return str(e)

# --- Logic ---
async def stream_agent_logic(user_input, history):
    genai.configure(api_key=GEMINI_API_KEY)
    
    # บันทึกคำถามลง Supabase ทันที (Background Log)
    if supabase:
        try: supabase.table("logs").insert({"message": user_input, "role": "user"}).execute()
        except: pass

    # เช็คว่าเป็นคำสั่งระบบหรือไม่ (เพื่อความเร็ว)
    is_task = any(x in user_input.lower() for x in ['run', 'ls', 'db', 'sql', 'save', 'write'])
    
    model = genai.GenerativeModel(
        model_name='gemini-3.1-flash-lite',
        tools=[execute_command, db_query],
        system_instruction=f"Terminal Agent with Supabase. DB_URL: {SUPABASE_URL}. Work fast."
    )
    
    chat = model.start_chat(history=[{"role": h["role"], "parts": [h["content"]]} for h in history[-3:]])
    
    try:
        response = chat.send_message(user_input)
        for _ in range(10):
            parts = response.candidates[0].content.parts
            calls = [p.function_call for p in parts if p.function_call]
            
            if not calls:
                yield f"data: {json.dumps({'reply': response.text})}\n\n"
                # บันทึกคำตอบ AI ลง DB
                if supabase: supabase.table("logs").insert({"message": response.text, "role": "assistant"}).execute()
                break
            
            tool_responses = []
            for fn in calls:
                args = dict(fn.args)
                if fn.name == "execute_command": 
                    res = execute_command(args.get("command", ""))
                elif fn.name == "db_query":
                    res = db_query(args.get("table"), args.get("query_type"), args.get("data"))
                
                yield f"data: {json.dumps({'step': fn.name, 'result': res})}\n\n"
                tool_responses.append(genai.protos.Part(function_response=genai.protos.FunctionResponse(name=fn.name, response={'result': res})))
            
            response = chat.send_message(genai.protos.Content(parts=tool_responses))
            await asyncio.sleep(0.01)
    except Exception as e:
        yield f"data: {json.dumps({'reply': f'Error: {str(e)}'})}\n\n"

@app.post("/chat")
async def chat_endpoint(req: Request):
    data = await req.json()
    return StreamingResponse(stream_agent_logic(data.get('message', ''), data.get('history', [])), media_type="text/event-stream")

@app.get("/")
def index():
    with open("static/index.html", "r", encoding="utf-8") as f: return HTMLResponse(f.read())

if __name__ == "__main__":
    os.makedirs(WORKSPACE, exist_ok=True)
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
