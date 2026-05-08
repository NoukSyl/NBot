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

# --- Configuration ---
logging.basicConfig(level=logging.INFO)
app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
WORKSPACE = os.path.abspath("/app/workspace")
current_dir = WORKSPACE

SYSTEM_PROMPT = (
    "You are a High-Speed Terminal AI Agent. "
    "Current working directory: {cwd}\n"
    "RULES:\n"
    "1. If the user just greets, reply instantly without tools.\n"
    "2. If the user gives a task, use tools immediately. No yapping.\n"
    "3. When finished, provide a brief summary."
)

# --- Tools ---
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
        process = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=60, cwd=current_dir)
        return f"OUT: {process.stdout}\nERR: {process.stderr}".strip() or "Success"
    except Exception as e: return str(e)

def write_file(path: str, content: str) -> str:
    try:
        full_path = os.path.normpath(os.path.join(current_dir, path))
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "w", encoding="utf-8") as f: f.write(content)
        return f"Saved: {path}"
    except Exception as e: return str(e)

def read_file(path: str) -> str:
    try:
        full_path = os.path.normpath(os.path.join(current_dir, path))
        with open(full_path, "r", encoding="utf-8") as f: return f.read()
    except Exception as e: return str(e)

# --- Core Logic ---
async def stream_agent_logic(user_input, history):
    if not GEMINI_API_KEY:
        yield f"data: {json.dumps({'reply': 'Error: Missing API Key'})}\n\n"
        return
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel(
        model_name='gemini-3.1-flash-lite',
        tools=[execute_command, write_file, read_file],
        system_instruction=SYSTEM_PROMPT.format(cwd=current_dir)
    )
    chat = model.start_chat(history=[{"role": h["role"], "parts": [h["content"]]} for h in history[-5:]])
    try:
        response = chat.send_message(user_input)
        for _ in range(12):
            parts = response.candidates[0].content.parts
            calls = [p.function_call for p in parts if p.function_call]
            if not calls:
                yield f"data: {json.dumps({'reply': response.text})}\n\n"
                break
            tool_responses = []
            for fn in calls:
                args = dict(fn.args)
                if fn.name == "execute_command": res = execute_command(args.get("command", ""))
                elif fn.name == "write_file": res = write_file(args.get("path", ""), args.get("content", ""))
                elif fn.name == "read_file": res = read_file(args.get("path", ""))
                yield f"data: {json.dumps({'step': fn.name, 'result': res})}\n\n"
                tool_responses.append(genai.protos.Part(function_response=genai.protos.FunctionResponse(name=fn.name, response={'result': res})))
            response = chat.send_message(genai.protos.Content(parts=tool_responses))
            await asyncio.sleep(0.05)
    except Exception as e:
        yield f"data: {json.dumps({'reply': f'Error: {str(e)}'})}\n\n"

@app.post("/chat")
async def chat_endpoint(req: dict):
    return StreamingResponse(stream_agent_logic(req.get('message', ''), req.get('history', [])), media_type="text/event-stream")

@app.get("/", response_class=HTMLResponse)
def index():
    with open("static/index.html", "r", encoding="utf-8") as f: return f.read()

if __name__ == "__main__":
    os.makedirs(WORKSPACE, exist_ok=True)
    os.makedirs("static", exist_ok=True)
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
