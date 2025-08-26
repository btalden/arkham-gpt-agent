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
    """
    Send Arkham alert payload to GPT for interpretation
    """
    # Simplify key info for GPT
    tx_summary = f"""
    Entity: {payload.get('entity_name')}
    From: {payload.get('from_address')}
    To: {payload.get('to_address')}
    Token: {payload.get('token_symbol')}
    Amount: {payload.get('amount')}
    USD Value: {payload.get('usd_value')}
    Network: {payload.get('network')}
    Time: {payload.get('timestamp')}
    """

    prompt = f"""
    You are a crypto trading analyst. Interpret the following Arkham alert:

    {tx_summary}

    Explain in plain English what this transaction likely means.
    Consider whether it's:
    - An exchange deposit (likely trading/selling)
    - An exchange withdrawal (likely storage or on-chain use)
    - A wallet-to-wallet move (likely custody reshuffle)
    - A DeFi interaction (staking, swapping, etc.)

    Be concise but insightful.
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

@app.get("/health")
async def health_check():
    return {"status": "alive"}

@app.post("/arkham-webhook")
async def arkham_webhook(request: Request):
    try:
        payload = await request.json()
    except Exception:
        # Arkham test ping or invalid JSON → always return OK
        return JSONResponse(content={"status": "ok"}, status_code=200)

    try:
        analysis = await analyze_alert(payload)
        await send_to_slack(analysis)
        return {"status": "ok", "analysis": analysis}
    except Exception as e:
        # Don’t let Arkham see a failure
        return JSONResponse(content={"status": "ok", "message": str(e)}, status_code=200)
