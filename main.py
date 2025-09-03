# load env and fetch secrets
from dotenv import load_dotenv
import os

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")

# load other stuff
from fastapi import FastAPI, Request
import openai
import httpx
from fastapi.responses import JSONResponse

app = FastAPI()

async def analyze_alert(payload: dict) -> str:
    prompt = f"""
    You are monitoring blockchain alerts from Arkham Intelligence.

    Here is a new alert payload (JSON):
    {payload}

    Please explain in plain English what happened, including:
    - Who sent the tokens (entity + label if available)
    - Who received them (entity + label if available)
    - What token was moved, how much, and USD value if included
    - What the most likely interpretation is (trade, custody, bridge, etc.)
    - Any alternative explanations worth noting
    """
    response = openai.chat.completions.create(
        model="gpt-5",
        messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content

async def send_to_slack(message: str):
    """
    Send interpreted message to Slack
    """
    async with httpx.AsyncClient() as client:
        resp = await client.post(SLACK_WEBHOOK_URL, json={"text": message})
        print("Slack response:", resp.status_code, resp.text)
        return resp.text

@app.get("/arkham-webhook")
async def arkham_webhook_get():
    # For Arkham’s initial GET validation
    return {"status": "ok", "message": "webhook alive"}

from fastapi import Header, HTTPException

ARKHAM_SECRET = "JTzghWzJI327Vh"  # copy from Arkham webhook settings

@app.post("/arkham-webhook")
async def arkham_webhook(request: Request, arkham_webhook_token: str = Header(None)):
    # Validate Arkham webhook token
    if arkham_webhook_token != ARKHAM_SECRET:
        print("⚠️ Invalid Arkham token:", arkham_webhook_token)
        raise HTTPException(status_code=403, detail="Invalid webhook token")

    try:
        payload = await request.json()
        print("Incoming payload:", payload)
    except Exception:
        return {"status": "ok", "message": "ping acknowledged"}

    try:
        analysis = await analyze_alert(payload)
        await send_to_slack(analysis)
        return {"status": "ok", "analysis": analysis}
    except Exception as e:
        print("Processing error:", e)
        return {"status": "ok", "message": f"processing error: {str(e)}"}

@app.api_route("/health", methods=["GET", "HEAD"])
async def health_check(request: Request):
    return JSONResponse(content={"status": "alive"})

if __name__ == "__main__":
    import uvicorn, os
    port = int(os.environ.get("PORT", 8000))  # Render injects PORT
    uvicorn.run("main:app", host="0.0.0.0", port=port)
