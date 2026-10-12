import os
import uvicorn

if __name__ == "__main__":
    # Local-only by default: don't expose the authenticated dashboard to the LAN.
    host = os.getenv("ARBX_HOST", "127.0.0.1")
    uvicorn.run("app.api.app:app", host=host, port=8000, reload=False)
