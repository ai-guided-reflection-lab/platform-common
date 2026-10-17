"""Start local SDL with the provider configured in its own .env file."""
import argparse
import os
from pathlib import Path

from dotenv import dotenv_values
import uvicorn


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8100)
    parser.add_argument("--no-reload", action="store_true")
    args = parser.parse_args()
    settings = dotenv_values(Path(__file__).resolve().parent.parent / ".env")
    for key, value in settings.items():
        if value is not None and (key.startswith(("OPENAI_", "GROQ_", "ADAPTIVE_AI_", "ADAPTIVE_ALLOW_DEMO_")) or key == "LLM_PROVIDER"):
            os.environ[key] = value
    uvicorn.run("app.main:app", host="127.0.0.1", port=args.port, reload=not args.no_reload)
