"""Run the backend2 FastAPI server.

  cd backend2 && python run_api.py

Defaults to port 8001 (the legacy backend uses 8000). Override via env vars:
  BACKEND2_HOST  default 0.0.0.0
  BACKEND2_PORT  default 8001
  BACKEND2_RELOAD default true (set to "0" to disable hot reload)
"""
from __future__ import annotations

import os

import uvicorn


def main() -> None:
    host = os.environ.get("BACKEND2_HOST", "0.0.0.0")
    port = int(os.environ.get("BACKEND2_PORT", "8001"))
    reload = os.environ.get("BACKEND2_RELOAD", "1") not in ("0", "false", "False")
    uvicorn.run(
        "research.api.server:app",
        host=host,
        port=port,
        reload=reload,
        log_level="info",
    )


if __name__ == "__main__":
    main()
