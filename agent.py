import os, subprocess, logging, google.generativeai as genai, uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

# --- Fast Config ---
logging.basicConfig(level=logging.INFO)
app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

WORKSPACE = os.path.abspath("/app/workspace")
current_dir = WORKSPACE
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# === 1. Execution Tools ===
def execute_command(command: str) -> str:
    global current_dir
    cmd = command.strip()
    try:
        if cmd.startswith("cd "):
            target = cmd[3:].strip()
            new_path = os.path.normpath(os.path.join(current_dir, target))
            if os.path.exists(new_path): 
                current_dir = new_path
                return f"dir: {current_dir}"
            return "err: not found"
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=60, cwd=current_dir)
        return f"{res.stdout}\n{res.stderr}".strip() or "Success"
    except Exception as e: return f"err: {str(e)}"

def write_file(path: str, content: str) -> str:
    try:
        p = os.path.normpath(os.path.join(current_dir, path))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f: f.write(content)
        return f"saved: {path}"
    except Exception as e: return f"err: {str(e)}"

def read_file(path: str) -> str:
    try:
        p = os.path.normpath(os.path.join(current_dir, path))
        with open(p, "r", encoding="utf-8") as f: return f.read()
    except Exception as e: return f"err: {str(e)}"

# === 2. AI Core (Autonomous & Minimal Thinking) ===
def run_agent(user_input: str, history: list) -> dict:
    if not GEMINI_API_KEY: return {"reply": "Key missing", "steps": []}
    genai.configure(api_key=GEMINI_API_KEY)
    
    model = genai.GenerativeModel(
        model_name='gemini-3.1-flash-lite', 
        tools=[execute_command, write_file, read_file],
        generation_config={
            "temperature": 1.0,
            "thinking_level": "minimal", # ความเร็วระดับสูงสุด
            "top_p": 0.95,
        }
    )

    chat = model.start_chat(history=[{"role": h["role"], "parts": [h["content"]]} for h in history[-3:]])
    sys_logic = f"CWD: {current_dir}\nTask: {user_input}\nAction: Autonomous. Execute until done. Be very concise."

    steps = []
    try:
        response = chat.send_message(sys_logic)
        for _ in range(10): # สคริปต์ออโต้ตามที่คุณต้องการ
            parts = response.candidates[0].content.parts
            calls = [p.function_call for p in parts if p.function_call]
            if not calls: break
            
            tool_responses = []
            for fn in calls:
                args = dict(fn.args)
                if fn.name == "execute_command": res = execute_command(args.get("command"))
                elif fn.name == "write_file": res = write_file(args.get("path"), args.get("content"))
                else: res = read_file(args.get("path"))
                
                steps.append({"tool": fn.name, "result": res})
                tool_responses.append(genai.protos.Part(function_response=genai.protos.FunctionResponse(name=fn.name, response={'result': res})))
            
            response = chat.send_message(genai.protos.Content(parts=tool_responses))
            
        return {"reply": response.text, "steps": steps}
    except Exception as e: return {"reply": f"Error: {str(e)}", "steps": steps}

# === 3. Entry Points ===
class ChatReq(BaseModel): message: str; history: list = []

@app.post("/chat")
async def api(req: ChatReq): return run_agent(req.message, req.history)

@app.get("/", response_class=HTMLResponse)
def index():
    try:
        with open("static/index.html", "r", encoding="utf-8") as f: return f.read()
    except: return "<h1>Frontend missing in /static/index.html</h1>"

if __name__ == "__main__":
    os.makedirs(WORKSPACE, exist_ok=True)
    os.makedirs("static", exist_ok=True)
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
