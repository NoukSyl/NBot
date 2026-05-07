# 🤖 AI Agent v6 — Shell + Tools + Auth + Memory

## ✨ Features
- 🔐 **Auth** — password-protected, เฉพาะเจ้าของเข้าได้
- 🧠 **Supabase Memory** — บันทึก conversation ข้าม session
- 🛠️ **5 Tools** — shell, web_search, read_file, write_file, http_request
- ⚡ **Model** — Qwen/Qwen3-32B via HuggingFace (ฟรี)
- 🖥️ **Root Access** — รัน command บน Railway container ได้เต็มที่

---

## ⚙️ Environment Variables (Railway)

| Variable | Required | Description |
|----------|----------|-------------|
| `HF_TOKEN` | ✅ | HuggingFace API token |
| `ADMIN_PASSWORD` | ✅ | Password สำหรับเข้าใช้งาน |
| `SUPABASE_URL` | ✅ | เช่น `https://xxxx.supabase.co` |
| `SUPABASE_KEY` | ✅ | Supabase `anon` หรือ `service_role` key |
| `SUPABASE_TABLE` | No | ชื่อ table (default: `agent_memory`) |
| `MODEL_ID` | No | default: `Qwen/Qwen3-32B` |
| `MAX_TOKENS` | No | default: `4096` |
| `SHELL_TIMEOUT` | No | default: `30` (วินาที) |

---

## 🗄️ Supabase Setup

สร้าง table ใน Supabase SQL Editor:

```sql
create table agent_memory (
  id          bigserial primary key,
  session_id  text unique not null,
  messages    text not null,
  updated_at  timestamptz default now()
);

-- index สำหรับ lookup เร็ว
create index on agent_memory (session_id);
```

---

## 🚀 Deploy บน Railway

1. Push โค้ดขึ้น GitHub
2. Railway → New Project → Deploy from GitHub
3. ตั้ง Environment Variables ทั้งหมดข้างบน
4. Deploy → เปิด URL → หน้า Login จะขึ้น

---

## 🌐 Endpoints

| URL | Description |
|-----|-------------|
| `/` | Redirect ไป `/ui` (ต้อง login) |
| `/login` | หน้า Login |
| `/logout` | Logout |
| `/ui` | Gradio Chat UI |
| `/chat` | REST API (POST, ต้อง session cookie) |
| `/sessions` | List sessions (GET) |
| `/sessions/{id}` | Delete session (DELETE) |
| `/health` | Health check (public) |

---

## 🛠️ Tools

| Tool | Description |
|------|-------------|
| `shell` | รัน bash command (root, timeout 30s) |
| `web_search` | ค้นหาเว็บด้วย DuckDuckGo |
| `read_file` | อ่านไฟล์จาก filesystem |
| `write_file` | เขียนไฟล์ลง filesystem |
| `http_request` | HTTP GET/POST/PUT/DELETE ไปยัง URL ใดก็ได้ |

---

## 💬 Session Memory

- แต่ละ session มี `session_id` (default: `"default"`)
- ตั้งชื่อเองได้ เช่น `"work"`, `"research"`, `"project-x"`
- บันทึก auto ทุกครั้งที่ chat
- โหลด/ลบ session ได้จาก UI
