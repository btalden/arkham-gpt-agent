# load env and fetch secrets
from dotenv import load_dotenv
import os, json, asyncio, datetime

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")
ARKHAM_WEBHOOK_TOKEN = os.getenv("ARKHAM_WEBHOOK_TOKEN")  # <- new
DB_PATH = os.getenv("DB_PATH", "arkham.db")

from fastapi import FastAPI, Request, Header, HTTPException
from fastapi.responses import JSONResponse
import openai
import httpx
import aiosqlite

app = FastAPI()

# ---------- DB helpers ----------
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS arkham_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            received_at TEXT,
            arkham_id TEXT,
            alert_name TEXT,
            headers TEXT,
            payload_json TEXT,
            processed_at TEXT,
            analysis TEXT,
            slack_status TEXT,
            error TEXT
        )
        """)
        await db.commit()

async def log_insert(headers: dict, payload: dict) -> int:
    received_at = datetime.datetime.utcnow().isoformat() + "Z"
    arkham_id = (
        payload.get("transfer", {}).get("id")
        or payload.get("id")
        or None
    )
    alert_name = payload.get("alertName")

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """INSERT INTO arkham_alerts
               (received_at, arkham_id, alert_name, headers, payload_json)
               VALUES (?, ?, ?, ?, ?)""",
            (received_at, arkham_id, alert_name, json.dumps(headers), json.dumps(payload))
        )
        await db.commit()
        return cur.lastrowid

async def log_update(row_id: int, *, analysis: str | None = None,
                     slack_status: str | None = None, error: str | None = None):
    processed_at = datetime.datetime.utcnow().isoformat() + "Z"
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """UPDATE arkham_alerts
               SET processed_at = COALESCE(processed_at, ?),
                   analysis = COALESCE(?, analysis),
                   slack_status = COALESCE(?, slack_status),
                   error = COALESCE(?, error)
               WHERE id = ?""",
            (processed_at, analysis, slack_status, error, row_id)
        )
        await db.commit()

# ---------- App startup ----------
@app.on_event("startup")
async def _startup():
    await init_db()

# ---------- Core logic ----------
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
    resp = openai.chat.completions.create(
        model="gpt-5",
        messages=[{"role": "user", "content": prompt}]
    )
    return resp.choices[0].message.content

async def send_to_slack(message: str) -> str:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(SLACK_WEBHOOK_URL, json={"text": message})
            print("Slack response:", resp.status_code, resp.text)
            return f"{resp.status_code} {resp.text[:200]}"
    except Exception as e:
        print("Slack error:", e)
        return f"error: {e}"

async def process_payload(payload: dict, row_id: int):
    try:
        analysis = await analyze_alert(payload)
        await log_update(row_id, analysis=analysis)
        slack_status = await send_to_slack(analysis)
        await log_update(row_id, slack_status=slack_status)
    except Exception as e:
        print("Processing error:", e)
        await log_update(row_id, error=str(e))

# ---------- Routes ----------
@app.get("/arkham-webhook")
async def arkham_webhook_get():
    return {"status": "ok", "message": "webhook alive"}

@app.post("/")
@app.post("/arkham-webhook")
async def arkham_webhook(request: Request, authorization: str = Header(None)):
    headers = dict(request.headers)
    print("HEADERS:", headers)  # log all headers

    # Optional token validation
    if ARKHAM_WEBHOOK_TOKEN:
        expected = f"Bearer {ARKHAM_WEBHOOK_TOKEN}"
        if authorization != expected:
            print("Token mismatch:", authorization, "expected:", expected)
            raise HTTPException(status_code=401, detail="Invalid token")

    try:
        raw = await request.body()
        print("ARKHAM REQUEST ->", request.method, headers.get("content-type"), raw[:1000])
        try:
            payload = await request.json()
        except Exception:
            payload = {}
    except Exception as e:
        print("Error reading request:", e)
        headers, payload = {}, {}

    row_id = await log_insert(headers, payload)
    asyncio.create_task(process_payload(payload, row_id))
    return {"status": "ok"}

@app.api_route("/health", methods=["GET", "HEAD"])
async def health_check(_request: Request):
    return JSONResponse(content={"status": "alive"})

@app.api_route("/", methods=["GET", "HEAD"])
async def root():
    return {"status": "ok"}

@app.get("/logs")
async def get_logs(limit: int = 50):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            """SELECT id, received_at, alert_name, arkham_id,
                      processed_at, slack_status, error
               FROM arkham_alerts
               ORDER BY id DESC
               LIMIT ?""",
            (limit,)
        )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
