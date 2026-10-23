"""Day 1 only: deterministic routing stub, NOT a real LLM/Agent yet."""
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
import httpx

app = FastAPI(title="BankPilot Day1 Demo")

class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=300)

@app.post("/api/agent/chat")
async def chat(req: ChatRequest):
    message = req.message.strip()
    if not any(word in message for word in ["余额", "还有多少钱", "账户有多少钱"]):
        return {"reply": "今天的演示仅支持查询余额，请输入：查询我的余额。", "source": "demo-router"}
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get("http://127.0.0.1:8080/api/demo/balance")
            resp.raise_for_status()
            payload = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(status_code=503, detail="银行后端暂时不可用，请确认 Java 服务和 MySQL 已启动") from exc
    return {
        "reply": f"{payload['userName']}，您的模拟账户 {payload['accountNoMasked']} 当前余额为 ¥{float(payload['balance']):,.2f}。",
        "source": "mysql-via-java",
    }
