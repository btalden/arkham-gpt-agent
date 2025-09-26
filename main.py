from fastapi import FastAPI, Request, Header
from fastapi.responses import JSONResponse

app = FastAPI()

# Health check endpoint (Render probes this)
@app.get("/health")
async def health():
    return JSONResponse(content={"status": "alive"})

# Root endpoint - now accepts GET, HEAD, OPTIONS (so probes never 405)
@app.api_route("/", methods=["GET", "HEAD", "OPTIONS"])
async def root(request: Request):
    return {"status": "ok"}

# Unified handler for Arkham webhook
async def handle_arkham_request(request: Request, authorization: str | None):
    headers = dict(request.headers)
    body = await request.body()
    print("DEBUG REQUEST:", request.method, headers, body[:500])

    if request.method == "POST":
        try:
            payload = await request.json()
        except Exception:
            payload = {}

        # Echo back Arkham challenge if provided
        if isinstance(payload, dict) and "challenge" in payload:
            print("Received challenge:", payload["challenge"])
            return {"challenge": payload["challenge"]}

        print("Received POST payload:", payload)

    return {"status": "ok"}

# Handle Arkham POSTs at both / and /arkham-webhook
@app.api_route("/", methods=["POST"])
async def root_post(request: Request, authorization: str = Header(None)):
    return await handle_arkham_request(request, authorization)

@app.api_route("/arkham-webhook", methods=["GET", "POST", "OPTIONS", "HEAD"])
async def arkham_webhook(request: Request, authorization: str = Header(None)):
    return await handle_arkham_request(request, authorization)
