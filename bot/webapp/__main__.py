"""Запуск Mini App: python -m bot.webapp"""
import os

import uvicorn


def main():
    host = os.getenv("WEBAPP_HOST", "0.0.0.0")
    port = int(os.getenv("PORT") or os.getenv("WEBAPP_PORT") or "8080")
    uvicorn.run(
        "bot.webapp.app:app",
        host=host,
        port=port,
        reload=os.getenv("WEBAPP_RELOAD", "").lower() in ("1", "true", "yes"),
    )


if __name__ == "__main__":
    main()
