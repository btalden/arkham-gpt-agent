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
import asyncio

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
    # Requires openai>=1.0.0
    resp = openai.chat.completions.create(
        model="gpt-5",
        messages=[{"role": "user", "content": prompt}]
    )
    return resp.choices[0].message.content

async def send_to_slack(message: str):
    """Send interpreted message to Slack."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(SLACK_WEBHOOK_URL, json={"text": message})
            print("Slack response:", resp.status_code, resp.text)
            return resp.text
    except Exception as e:
        print("Slack error:", e)

async def process_payload(payload: dict):
    """Run the slow work after we’ve ACK’d Arkham."""
    try:
        analysis = await analyze_alert(payload)
        await send_to_slack(analysis)
    except Exception as e:
        print("Processing error:", e)

@app.get("/arkham-webhook")
async def arkham_webhook_get():
    # Optional GET for sanity checks
    return {"status": "ok", "message": "webhook alive"}

# --- IMPORTANT: return quickly, then process in background ---
@app.post("/")
@app.post("/arkham-webhook")
async def arkham_webhook(request: Request):
    # Log method/headers and a snippet of raw body to diagnose format issues
    try:
        ct = request.headers.get("content-type")
        raw = await request.body()
        print("ARKHAM REQUEST ->", request.method, ct, raw[:1000])
        try:
            payload = await request.json()
        except Exception:
            payload = {}
    except Exception as e:
        print("Error reading request:", e)
        payload = {}

    # Schedule async processing without blocking the response
    asyncio.create_task(process_payload(payload))

    # ACK immediately so Arkham treats the delivery as successful
    return {"status": "ok"}

@app.api_route("/health", methods=["GET", "HEAD"])
async def health_check(request: Request):
    return JSONResponse(content={"status": "alive"})

# Catch simple GET/HEAD root probes (e.g., uptime pings)
@app.api_route("/", methods=["GET", "HEAD"])
async def root():
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))  # Render injects PORT
    uvicorn.run("main:app", host="0.0.0.0", port=port)
