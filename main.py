from fastapi import FastAPI, Request, Header
from fastapi.responses import JSONResponse

app = FastAPI()

@app.get("/health")
async def health():
    return JSONResponse(content={"status": "alive"})

@app.get("/")
async def root():
    return {"status": "ok"}

# Unified handler for Arkham webhook
async def handle_arkham_request(request: Request, authorization: str | None):
    headers = dict(request.headers)
    body = await request.body()
    print("DEBUG REQUEST:", request.method, headers, body[:500])

    # Only care about POSTs for alerts
    if request.method == "POST":
        try:
            payload = await request.json()
        except Exception:
            payload = {}

        # If Arkham sends a challenge payload, echo it back
        if isinstance(payload, dict) and "challenge" in payload:
            print("Received challenge:", payload["challenge"])
            return {"challenge": payload["challenge"]}

        print("Received POST payload:", payload)

    return {"status": "ok"}

@app.api_route("/", methods=["GET", "POST", "OPTIONS", "HEAD"])
async def root_any(request: Request, authorization: str = Header(None)):
    return await handle_arkham_request(request, authorization)

@app.api_route("/arkham-webhook", methods=["GET", "POST", "OPTIONS", "HEAD"])
async def arkham_webhook(request: Request, authorization: str = Header(None)):
    return await handle_arkham_request(request, authorization)
