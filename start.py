# start.py
import os
import uvicorn

# Render injects PORT at runtime. If it's missing (local dev), default to 8000.
port = int(os.environ.get("PORT", 8000))
print(f"[start.py] Using PORT={port}")
uvicorn.run("main:app", host="0.0.0.0", port=port)