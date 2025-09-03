# start.py
import uvicorn

if __name__ == "__main__":
    # Force uvicorn to bind to 8000 so it matches Render's env var
    print("[start.py] Using PORT=8000")
    uvicorn.run("main:app", host="0.0.0.0", port=8000)
