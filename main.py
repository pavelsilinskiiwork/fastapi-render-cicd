"""A deliberately small FastAPI service.

The service is not the point of this repository: the pipeline around it is. `/version` exists so
the pipeline can prove that the commit it just pushed is the one that is actually running.
"""

import os
import re
import time

from fastapi import FastAPI
from pydantic import BaseModel, Field

STARTED = time.time()
WORD = re.compile(r"\w+", re.UNICODE)

app = FastAPI(title="FastAPI Render CI/CD demo", version="1.0.0")


def commit_sha() -> str:
    """Render sets RENDER_GIT_COMMIT at runtime; CI and local Docker runs pass GIT_SHA."""
    return os.getenv("RENDER_GIT_COMMIT") or os.getenv("GIT_SHA") or "dev"


class TextIn(BaseModel):
    text: str = Field(min_length=1, max_length=10_000)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/version")
def version():
    return {"commit": commit_sha(), "uptime_seconds": round(time.time() - STARTED, 1)}


@app.post("/wordcount")
def wordcount(body: TextIn):
    words = [w.lower() for w in WORD.findall(body.text)]
    return {"words": len(words), "unique_words": len(set(words)), "characters": len(body.text)}
