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
            if os.path.exists(new_path): current_dir = new_path; return f"Changed dir to: {current_dir}"
            return "Error: Path not found"
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=60, cwd=current_dir)
        return f"OUT: {res.stdout}\nERR: {res.stderr}".strip() or "Success"
    except Exception as e: return f"System Error: {str(e)}"

def write_file(path: str, content: str) -> str:
    try:
        p = os.path.normpath(os.path.join(current_dir, path))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f: f.write(content)
        return f"Saved: {path}"
    except Exception as e: return f"Write Error: {str(e)}"

def read_file(path: str) -> str:
    try:
        p = os.path.normpath(os.path.join(current_dir, path))
        with open(p, "r", encoding="utf-8") as f: return f.read()
    except Exception as e: return f"Read Error: {str(e)}"

# === 2. Autonomous Agent Engine (Your Logic) ===

def run_agent(user_input: str, history: list) -> dict:
    if not GEMINI_API_KEY: return {"reply": "Missing API Key", "steps": []}
    
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel(
        model_name='gemini-flash-latest', 
        tools=[execute_command, write_file, read_file]
    )

    # ส่งประวัติย้อนหลัง 3 ข้อความเพื่อให้จำบริบทได้
    chat = model.start_chat(history=[{"role": h["role"], "parts": [h["content"]]} for h in history[-3:]])

    # สั่งให้ AI รู้ตัวว่าเป็นคนคุม ถ้างานไม่จบให้สั่ง Tool ต่อ ถ้าจบให้สรุปผล
    sys_logic = f"CWD: {current_dir}\nTask: {user_input}\nInstruction: You are the controller. Use tools until the task is 100% complete. If you need more steps, keep calling tools. If finished, provide a final summary."

    steps = []
    try:
        # 1. ส่งคำสั่งครั้งแรกเพื่อเริ่มภารกิจ
        response = chat.send_message(sys_logic)

        # 2. Autonomous Loop: ตราบใดที่ AI ยังตัดสินใจส่ง Tool Call มา Script จะไม่หยุดส่งกลับ
        while True:
            parts = response.candidates[0].content.parts
            calls = [p.function_call for p in parts if p.function_call]
            
            # ถ้าไม่มีคำสั่ง Tool Call เพิ่มเติม แสดงว่า AI ตัดสินใจว่า "เสร็จงาน" แล้ว -> ออกจากลูป
            if not calls:
                break
            
            tool_responses = []
            for fn in calls:
                args = dict(fn.args)
                # รันงานตามที่ AI สั่งมาในรอบนั้นๆ
                if fn.name == "execute_command": res = execute_command(args.get("command"))
                elif fn.name == "write_file": res = write_file(args.get("path"), args.get("content"))
                else: res = read_file(args.get("path"))
                
                steps.append({"tool": fn.name, "args": args, "result": res})
                
                # เก็บผลลัพธ์ใส่กล่อง เตรียมส่งกลับไปถาม AI รอบถัดไป
                tool_responses.append(genai.protos.Part(
                    function_response=genai.protos.FunctionResponse(name=fn.name, response={'result': res})
                ))
            
            # 3. สคริปต์ออโต้ส่งผลลัพธ์กลับไปให้ AI ตัดสินใจว่าจะทำอะไรต่อ (วนไปเรื่อยๆ)
            response = chat.send_message(genai.protos.Content(parts=tool_responses))
            
            # Safety Brake: ป้องกัน AI วนวนอยู่ที่เดิมเกิน 15 รอบ
            if len(steps) > 15: break

        return {"reply": response.text, "steps": steps}
    except Exception as e: return {"reply": f"Loop Error: {str(e)}", "steps": steps}

# === 3. API Entry ===

class ChatReq(BaseModel): message: str; history: list = []

@app.post("/chat")
async def api(req: ChatReq): return run_agent(req.message, req.history)

@app.get("/", response_class=HTMLResponse)
def index():
    try:
        with open("static/index.html", "r", encoding="utf-8") as f: return f.read()
    except: return "Ready."

if __name__ == "__main__":
    os.makedirs(WORKSPACE, exist_ok=True)
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
