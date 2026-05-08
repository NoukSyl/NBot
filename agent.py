import os, subprocess, json, asyncio, google.generativeai as genai, uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
WORKSPACE = os.path.abspath("/app/workspace")
current_dir = WORKSPACE

# --- Fast Tools ---
def execute_command(command: str):
    global current_dir
    try:
        if command.strip().startswith("cd "):
            target = command.strip()[3:].strip()
            new_path = os.path.normpath(os.path.join(current_dir, target))
            if os.path.exists(new_path): current_dir = new_path; return f"dir: {current_dir}"
            return "err: path not found"
        res = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=30, cwd=current_dir)
        return f"{res.stdout}\n{res.stderr}".strip() or "Success"
    except Exception as e: return str(e)

async def stream_agent_logic(user_input, history):
    if not GEMINI_API_KEY: yield f"data: {json.dumps({'reply': 'No Key'})}\n\n"; return
    genai.configure(api_key=GEMINI_API_KEY)
    
    # --- ⚡ SHORT-CIRCUIT SPEED UP ⚡ ---
    # ถ้าข้อความสั้นและไม่มีคำสั่งรันระบบ ให้ใช้โมเดลแบบไม่มี Tools เพื่อความไวระดับ 1-2 วินาที
    is_task = any(word in user_input.lower() for word in ['run', 'sudo', 'ls', 'python', 'cat', 'write', 'mkdir', 'cd', 'git', 'rm'])
    
    model_name = 'gemini-3.1-flash-lite'
    tools_list = [execute_command] if is_task else []
    
    model = genai.GenerativeModel(
        model_name=model_name,
        tools=tools_list,
        system_instruction="Fast Agent. Reply briefly. If it's a greeting, just say hi. Current dir: " + current_dir
    )
    
    # ส่งประวัติแค่พอประมาณเพื่อความไว
    chat = model.start_chat(history=[{"role": h["role"], "parts": [h["content"]]} for h in history[-3:]])
    
    try:
        response = chat.send_message(user_input)
        
        # วนลูปเฉพาะเมื่อมี Task เท่านั้น
        for _ in range(10 if is_task else 1):
            parts = response.candidates[0].content.parts
            calls = [p.function_call for p in parts if p.function_call]
            
            if not calls:
                yield f"data: {json.dumps({'reply': response.text})}\n\n"
                break
            
            tool_responses = []
            for fn in calls:
                res = execute_command(fn.args.get("command", ""))
                yield f"data: {json.dumps({'step': fn.name, 'result': res})}\n\n"
                tool_responses.append(genai.protos.Part(function_response=genai.protos.FunctionResponse(name=fn.name, response={'result': res})))
            
            response = chat.send_message(genai.protos.Content(parts=tool_responses))
            await asyncio.sleep(0.01)
    except Exception as e:
        yield f"data: {json.dumps({'reply': f'Err: {str(e)}'})}\n\n"

@app.post("/chat")
async def chat_endpoint(req: Request):
    data = await req.json()
    return StreamingResponse(stream_agent_logic(data.get('message', ''), data.get('history', [])), media_type="text/event-stream")

@app.get("/", response_class=HTMLResponse)
def index():
    with open("static/index.html", "r", encoding="utf-8") as f: return f.read()

if __name__ == "__main__":
    os.makedirs(WORKSPACE, exist_ok=True)
    os.makedirs("static", exist_ok=True)
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
