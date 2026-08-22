"""Vercel serverless entrypoint — mounts the esp-atlas FastAPI backend under /api.

Deployed as a single Python function (@vercel/python) alongside the Next.js
frontend (apps/web, built by @vercel/next); vercel.json routes /api/(.*) here
and everything else to the Next.js build. Mounting keeps esp_atlas_api.main's
own route table (/health, /search, /wizard, /parts, /validate) unchanged, so
it behaves identically standalone (uvicorn esp_atlas_api.main:app) and here.
"""
from fastapi import FastAPI

from esp_atlas_api.main import app as _inner_app

app = FastAPI()
app.mount("/api", _inner_app)
