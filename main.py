import os
import json
import httpx
from collections import deque
from fastapi import FastAPI, Request, Header
from fastapi.responses import JSONResponse
from openai import AsyncOpenAI

# Env vars
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")
ARKHAM_WEBHOOK_TOKEN = os.getenv("ARKHAM_WEBHOOK_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

client = AsyncOpenAI(api_key=OPENAI_API_KEY)
app = FastAPI()

# In-memory log of last 10 alerts
recent_alerts = deque(maxlen=10)

# ---------- Utils ----------
async def post_to_slack(text: str):
    if not SLACK_WEBHOOK_URL:
        print("Slack webhook not set.")
        return
    async with httpx.AsyncClient() as http:
        r = await http.post(SLACK_WEBHOOK_URL, json={"text": text})
        print("Slack response:", r.status_code, r.text)

async def analyze_alert(payload: dict) -> str:
    try:
        resp = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are an assistant that summarizes Arkham crypto alerts for Slack."},
                {"role": "user", "content": f"Summarize this Arkham alert:\n\n{json.dumps(payload, indent=2)}"}
            ],
            max_tokens=200,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        return f"(Error analyzing alert: {e})"

# ---------- Routes ----------
@app.get("/health")
async def health():
    return {"status": "alive"}

@app.api_route("/", methods=["GET", "HEAD", "OPTIONS"])
async def root():
    return {"status": "ok"}

@app.api_route("/arkham-webhook", methods=["POST"])
@app.api_route("/", methods=["POST"])  # also catch root POSTs
async def arkham_webhook(request: Request, authorization: str = Header(None)):
    payload = await request.json()
    print("Received payload:", payload)

    # Always log the attempt (for debugging)
    recent_alerts.append({
        "auth_header": authorization,
        "payload": payload
    })

    # Handle Arkham handshake
    if "challenge" in payload:
        return {"challenge": payload["challenge"]}

    # Token check
    expected = f"Bearer {ARKHAM_WEBHOOK_TOKEN}"
    if authorization != expected:
        return JSONResponse(
            status_code=401,
            content={"error": "Invalid token", "received_auth": authorization}
        )

    # Process inline (guaranteed to run before returning)
    summary = await analyze_alert(payload)
    await post_to_slack(summary)

    return {"status": "accepted"}

@app.get("/logs")
async def get_logs():
    return {"alerts": list(recent_alerts)}
