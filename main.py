import os
import json
import aiosqlite
import httpx
from fastapi import FastAPI, Request, Header
from fastapi.responses import JSONResponse
from openai import AsyncOpenAI

# Load env vars
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")
ARKHAM_WEBHOOK_TOKEN = os.getenv("ARKHAM_WEBHOOK_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Clients
client = AsyncOpenAI(api_key=OPENAI_API_KEY)
app = FastAPI()

# ---------- DB Setup ----------
DB_FILE = "alerts.db"

async def init_db():
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            payload TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        await db.commit()

@app.on_event("startup")
async def startup_event():
    await init_db()

# ---------- Utils ----------
async def log_alert(payload: dict):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("INSERT INTO alerts (payload) VALUES (?)", [json.dumps(payload)])
        await db.commit()

async def post_to_slack(text: str):
    if not SLACK_WEBHOOK_URL:
        print("Slack webhook not set.")
        return
    async with httpx.AsyncClient() as http:
        await http.post(SLACK_WEBHOOK_URL, json={"text": text})

async def analyze_alert(payload: dict) -> str:
    """Send alert payload to GPT for summarization."""
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
async def arkham_webhook(request: Request, authorization: str = Header(None)):
    # Token check
    expected = f"Bearer {ARKHAM_WEBHOOK_TOKEN}"
    if not authorization or authorization != expected:
        print("Token mismatch:", authorization, "expected:", expected)
        return JSONResponse(status_code=401, content={"error": "Invalid token"})

    payload = await request.json()
    print("Received payload:", payload)

    # Arkham challenge handshake
    if "challenge" in payload:
        return {"challenge": payload["challenge"]}

    # Log it
    await log_alert(payload)

    # Analyze + post to Slack
    summary = await analyze_alert(payload)
    await post_to_slack(summary)

    return {"status": "processed"}

@app.get("/logs")
async def get_logs():
    async with aiosqlite.connect(DB_FILE) as db:
        cursor = await db.execute("SELECT id, payload, created_at FROM alerts ORDER BY id DESC LIMIT 10")
        rows = await cursor.fetchall()
    return {"alerts": [{"id": r[0], "payload": json.loads(r[1]), "created_at": r[2]} for r in rows]}
