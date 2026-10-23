"""Read-only compatibility API for a self-hosted Zenshin Supabase database."""

import os
import time
from collections import deque
from typing import Annotated

import httpx
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
TABLE_NAME = os.environ.get("SUPABASE_TABLE", "store")
CACHE_SECONDS = max(60, int(os.environ.get("MAPPING_CACHE_SECONDS", "21600")))
RATE_LIMIT_PER_MINUTE = max(1, int(os.environ.get("ZENSHIN_RATE_LIMIT_PER_MINUTE", "60")))
LOOKUP_FIELDS = {"mal_id", "anilist_id", "thetvdb_id", "anidb_id"}
cache: dict[str, tuple[float, dict]] = {}
request_times: dict[str, deque[float]] = {}

app = FastAPI(title="Zenshin Mapping API", version="1.0.0")


@app.middleware("http")
async def rate_limit_public_api(request: Request, call_next):
    """Bound anonymous traffic without changing the nande-rpc request contract."""
    if request.url.path == "/health":
        return await call_next(request)

    # Render forwards the original client address. If it is unavailable, fall
    # back to the direct peer address rather than trusting a missing value.
    forwarded = request.headers.get("x-forwarded-for", "").split(",", 1)[0].strip()
    client = forwarded or (request.client.host if request.client else "unknown")
    now = time.monotonic()
    bucket = request_times.setdefault(client, deque())
    while bucket and now - bucket[0] >= 60:
        bucket.popleft()
    if len(bucket) >= RATE_LIMIT_PER_MINUTE:
        return JSONResponse(status_code=429, content={"detail": "Rate limit exceeded"})
    bucket.append(now)
    return await call_next(request)


def require_configuration() -> None:
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        raise HTTPException(status_code=503, detail="Server is missing Supabase credentials")


async def load_mapping(field: str, value: int) -> dict:
    cache_key = f"{field}:{value}"
    cached = cache.get(cache_key)
    if cached and cached[0] > time.time():
        return cached[1]

    headers = {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
    }
    params = {field: f"eq.{value}", "select": "data", "limit": "1"}
    url = f"{SUPABASE_URL}/rest/v1/{TABLE_NAME}"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, headers=headers, params=params)
    except httpx.HTTPError as error:
        raise HTTPException(status_code=502, detail="Supabase request failed") from error

    if response.status_code >= 500:
        raise HTTPException(status_code=502, detail="Supabase is unavailable")
    if response.status_code >= 400:
        raise HTTPException(status_code=502, detail="Supabase rejected the query")

    rows = response.json()
    if not rows:
        raise HTTPException(status_code=404, detail="Mapping not found")
    payload = rows[0].get("data")
    if not isinstance(payload, dict):
        raise HTTPException(status_code=502, detail="Stored mapping has an invalid shape")

    cache[cache_key] = (time.time() + CACHE_SECONDS, payload)
    return payload


@app.get("/health")
async def health() -> dict[str, str]:
    status = "ok" if SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY else "misconfigured"
    return {"status": status}


@app.get("/mappings")
async def mappings(
    mal_id: Annotated[int | None, Query(ge=1)] = None,
    anilist_id: Annotated[int | None, Query(ge=1)] = None,
    thetvdb_id: Annotated[int | None, Query(ge=1)] = None,
    anidb_id: Annotated[int | None, Query(ge=1)] = None,
) -> JSONResponse:
    require_configuration()
    candidates = {
        "mal_id": mal_id,
        "anilist_id": anilist_id,
        "thetvdb_id": thetvdb_id,
        "anidb_id": anidb_id,
    }
    provided = [(field, value) for field, value in candidates.items() if value is not None]
    if len(provided) != 1:
        raise HTTPException(
            status_code=400,
            detail="Provide exactly one of mal_id, anilist_id, thetvdb_id, or anidb_id",
        )

    field, value = provided[0]
    if field not in LOOKUP_FIELDS:
        raise HTTPException(status_code=400, detail="Unsupported mapping field")
    mapping = await load_mapping(field, value)
    return JSONResponse(mapping, headers={"Cache-Control": f"public, max-age={CACHE_SECONDS}"})
