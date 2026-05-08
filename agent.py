import os
import subprocess
import json
from groq import Groq

client = Groq(api_key=os.environ["GROQ_API_KEY"])

# === Tools ที่ agent ใช้ได้ ===
tools = [
    {
        "type": "function",
        "function": {
            "name": "execute_command",
            "description": "รัน shell command จริงใน terminal เช่น ls, mkdir, cat, python3, git",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "Shell command ที่จะรัน"
                    }
                },
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "เขียนไฟล์ลง disk จริงๆ",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "path ของไฟล์"},
                    "content": {"type": "string", "description": "เนื้อหาในไฟล์"}
                },
                "required": ["path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "อ่านไฟล์จาก disk",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"}
                },
                "required": ["path"]
            }
        }
    }
]

# === Tool Executor ===
def execute_command(command: str) -> str:
    try:
        result = subprocess.run(
            command, shell=True, capture_output=True,
            text=True, timeout=30, cwd=os.getcwd()
        )
        output = result.stdout or ""
        error = result.stderr or ""
        return f"stdout:\n{output}\nstderr:\n{error}\nreturncode: {result.returncode}"
    except subprocess.TimeoutExpired:
        return "Error: command timeout (30s)"
    except Exception as e:
        return f"Error: {str(e)}"

def write_file(path: str, content: str) -> str:
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True) if os.path.dirname(path) else None
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"✅ เขียนไฟล์ {path} สำเร็จ ({len(content)} chars)"
    except Exception as e:
        return f"Error: {str(e)}"

def read_file(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"Error: {str(e)}"

def run_tool(name: str, args: dict) -> str:
    if name == "execute_command":
        return execute_command(args["command"])
    elif name == "write_file":
        return write_file(args["path"], args["content"])
    elif name == "read_file":
        return read_file(args["path"])
    return "Unknown tool"

# === Agent Loop ===
SYSTEM = """คุณคือ AI agent ที่มี terminal access จริงๆ
เมื่อได้รับคำสั่ง ให้ใช้ tools เพื่อทำงานจริง ไม่ต้องถามซ้ำ
ถ้าต้องสร้างไฟล์ → write_file
ถ้าต้องรัน command → execute_command
คิดทีละขั้น ดู output แล้วทำขั้นต่อไป"""

def agent(user_input: str):
    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": user_input}
    ]

    print(f"\n🧠 Agent กำลังคิด...")

    # ReAct loop — วนจนเสร็จ
    while True:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            tools=tools,
            tool_choice="auto",
            max_tokens=2048
        )

        msg = response.choices[0].message

        # ไม่มี tool call = คิดเสร็จแล้ว ตอบ user
        if not msg.tool_calls:
            print(f"\n🤖 Agent: {msg.content}")
            break

        # มี tool call → รันจริง
        messages.append(msg)

        for tool_call in msg.tool_calls:
            name = tool_call.function.name
            args = json.loads(tool_call.function.arguments)

            print(f"\n⚙️  Tool: {name}")
            print(f"   Args: {json.dumps(args, ensure_ascii=False)}")

            result = run_tool(name, args)
            print(f"   Result: {result[:200]}...")  # แสดงแค่ 200 chars

            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": result
            })

# === Main ===
if __name__ == "__main__":
    print("🚀 AI Terminal Agent (Groq + LLaMA 3.3)")
    print("พิมพ์ 'exit' เพื่อออก\n")

    while True:
        user = input("You: ").strip()
        if user.lower() == "exit":
            break
        if user:
            agent(user)