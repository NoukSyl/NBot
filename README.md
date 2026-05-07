# 🤖 AI Agent — HuggingFace + Railway

AI Agent สำเร็จรูป ใช้ Hugging Face Serverless Inference API ฟรี 100%  
Deploy บน Railway ใน 5 นาที

## 🧠 Model: `Qwen/Qwen3-32B`
- **ทำไมถึงเลือก?** อันดับ 1 บน HF Open LLM Leaderboard (ณ พ.ค. 2026)
- **ฟรีหรือเปล่า?** ใช่ — HF Serverless Inference ฟรีสำหรับ registered users
- **Rate limit**: ~few hundred req/hr (free tier)
- **License**: Apache 2.0 ✅ ใช้เชิงพาณิชย์ได้

## 🚀 Deploy บน Railway

### วิธีที่ 1: One-Click (แนะนำ)
1. Push โค้ดขึ้น GitHub repo ของคุณ
2. ไปที่ [railway.app](https://railway.app) → New Project → Deploy from GitHub
3. เลือก repo นี้ — Railway จะ detect Dockerfile อัตโนมัติ
4. ไปที่ **Variables** แล้วเพิ่ม:
   ```
   HF_TOKEN = hf_xxxxxxxxxxxxxxxxxx
   ```
5. กด **Deploy** 🎉

### วิธีที่ 2: Railway CLI
```bash
npm install -g @railway/cli
railway login
railway init
railway up
railway variables set HF_TOKEN=hf_xxxxxxxxxxxxxxxxxx
```

## 🔑 วิธีขอ HuggingFace Token (ฟรี)
1. สมัคร [huggingface.co](https://huggingface.co) (ฟรี)
2. ไปที่ Settings → Access Tokens
3. New Token → Role: `Read` (ไม่ต้องจ่ายเงิน)
4. Copy token เริ่มต้นด้วย `hf_`

## ⚙️ Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `HF_TOKEN` | ✅ Yes | - | HuggingFace API token |
| `MODEL_ID` | No | `Qwen/Qwen3-32B` | Model ที่ต้องการใช้ |
| `PORT` | No | `7860` | Railway inject อัตโนมัติ |
| `MAX_TOKENS` | No | `1024` | Max output tokens |
| `SYSTEM_PROMPT` | No | default | Custom system prompt |

## 🔄 เปลี่ยน Model ได้เลย
เปลี่ยน `MODEL_ID` ใน Railway Variables:

| Model | ความสามารถ | ขนาด |
|-------|------------|------|
| `Qwen/Qwen3-32B` | 🏆 General + Reasoning | 32B |
| `Qwen/Qwen3-14B` | ⚡ เร็วกว่า ดีพอ | 14B |
| `meta-llama/Llama-3.3-70B-Instruct` | 💪 Strong general | 70B |
| `mistralai/Mistral-7B-Instruct-v0.3` | 🚀 เร็วมาก เบา | 7B |
| `deepseek-ai/DeepSeek-R1-Distill-Qwen-32B` | 🧮 Reasoning | 32B |

## 🌐 Endpoints หลังจาก Deploy

| URL | Description |
|-----|-------------|
| `https://your-app.railway.app/` | หน้าแรก |
| `https://your-app.railway.app/ui` | Chat UI (Gradio) |
| `https://your-app.railway.app/chat` | REST API (POST) |
| `https://your-app.railway.app/health` | Health check |
| `https://your-app.railway.app/docs` | Swagger API docs |

## 📡 ใช้ REST API

```bash
curl -X POST https://your-app.railway.app/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "สวัสดี ช่วยอธิบาย AI คืออะไร",
    "history": [],
    "temperature": 0.7,
    "max_tokens": 512
  }'
```

Response:
```json
{
  "response": "AI คือ...",
  "model": "Qwen/Qwen3-32B"
}
```

## 🗂️ โครงสร้างโปรเจกต์
```
ai-agent/
├── main.py          # FastAPI + Gradio + Agent logic
├── requirements.txt # Python dependencies
├── Dockerfile       # Container build
├── railway.toml     # Railway config
└── README.md
```

## 💡 Tips
- **Cold start**: HF model อาจใช้เวลา 30-60 วิตอนโหลดครั้งแรก
- **Rate limit**: หากถึง limit รอ 1 ชม. หรือ upgrade HF PRO ($9/mo)
- **ประหยัด token**: ลด `MAX_TOKENS` ถ้าต้องการคำตอบสั้นๆ
