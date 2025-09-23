from fastapi import FastAPI
from fastapi.responses import JSONResponse

app = FastAPI()

@app.get("/health")
async def health():
    return JSONResponse(content={"status": "alive"})

@app.get("/")
async def root():
    return {"status": "ok"}
