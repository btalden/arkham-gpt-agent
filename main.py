#load env and fetch secrets

from dotenv import load_dotenv
import os

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")

#load other stuff

from fastapi import FastAPI, Request
import openai
import httpx
import os

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
        await client.post(SLACK_WEBHOOK_URL, json={"text": message})

from fastapi.responses import JSONResponse

@app.get("/arkham-webhook")
async def arkham_webhook_get():
    # For Arkham’s initial GET validation
    return {"status": "ok", "message": "webhook alive"}

@app.post("/arkham-webhook")
async def arkham_webhook(request: Request):
    try:
        payload = await request.json()
    except Exception:
        return {"status": "ok", "message": "ping acknowledged"}

    try:
        # Pass the full Arkham payload to GPT
        analysis = await analyze_alert(payload)
        await send_to_slack(analysis)
        return {"status": "ok", "analysis": analysis}
    except Exception as e:
        return {"status": "ok", "message": f"processing error: {str(e)}"}

