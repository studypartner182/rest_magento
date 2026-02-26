from __future__ import annotations

import json
import logging
import random
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse
from jose import ExpiredSignatureError, JWTError
from pydantic import BaseModel

from . import config
from .auth import ADMIN_USER, authenticate_admin, create_token, decode_token

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("mock_magento")

app = FastAPI(title="Mock Magento REST API", version="1.0.0")


class TokenRequest(BaseModel):
    username: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


REQUEST_WINDOW_SECONDS = 60
request_tracker: dict[str, deque[float]] = defaultdict(deque)

DATA_DIR = Path(__file__).parent / "data"


def load_json_records(filename: str) -> list[dict[str, Any]]:
    with (DATA_DIR / filename).open("r", encoding="utf-8") as f:
        return json.load(f)


ORDERS = load_json_records("orders.json")
PRODUCTS = load_json_records("products.json")
CUSTOMERS = load_json_records("customers.json")


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    client_ip = request.client.host if request.client else "unknown"
    logger.info("%s %s from %s", request.method, request.url.path, client_ip)
    return await call_next(request)


def enforce_rate_limit(request: Request) -> None:
    client_ip = request.client.host if request.client else "unknown"
    now = time.time()
    timeline = request_tracker[client_ip]

    while timeline and (now - timeline[0]) > REQUEST_WINDOW_SECONDS:
        timeline.popleft()

    if len(timeline) >= config.MAX_REQUESTS_PER_MINUTE:
        retry_after_seconds = max(1, int(REQUEST_WINDOW_SECONDS - (now - timeline[0])))
        logger.warning("Rate limit violation for client IP %s", client_ip)
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded",
            headers={"Retry-After": str(retry_after_seconds)},
        )

    timeline.append(now)


def parse_iso_timestamp(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid updated_after timestamp") from exc


def apply_common_query_behaviors(
    records: list[dict[str, Any]],
    updated_after: str | None,
    fail: bool,
    delay: int,
    random_error: bool,
) -> list[dict[str, Any]]:
    if delay > 0:
        time.sleep(delay)

    if fail:
        raise HTTPException(status_code=500, detail="Simulated server error")

    if random_error and random.random() < 0.35:
        raise HTTPException(status_code=500, detail="Random simulated server error")

    filtered = records
    if updated_after:
        threshold = parse_iso_timestamp(updated_after)
        filtered = [
            item for item in records if parse_iso_timestamp(item["updated_at"]) > threshold
        ]

    return filtered


def paginate(records: list[dict[str, Any]], page_size: int, current_page: int) -> dict[str, Any]:
    start_index = (current_page - 1) * page_size
    end_index = start_index + page_size
    page_items = records[start_index:end_index] if start_index < len(records) else []

    return {"items": page_items, "total_count": len(records)}


def get_access_payload(authorization: str = Header(...)) -> dict[str, Any]:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer token")

    token = authorization.split(" ", 1)[1].strip()

    try:
        payload = decode_token(token)
    except ExpiredSignatureError as exc:
        raise HTTPException(status_code=401, detail="Token expired") from exc
    except JWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc

    if payload.get("token_type") != "access":
        raise HTTPException(status_code=403, detail="Wrong token type")

    return payload


@app.post(f"{config.API_PREFIX}/integration/admin/token")
def admin_token(request_data: TokenRequest, request: Request):
    enforce_rate_limit(request)

    if not authenticate_admin(request_data.username, request_data.password):
        logger.warning("Failed authentication attempt for username '%s'", request_data.username)
        raise HTTPException(status_code=401, detail="Invalid credentials")

    access_token = create_token(
        subject=ADMIN_USER["username"],
        role=ADMIN_USER["role"],
        token_type="access",
        expires_delta=config.ACCESS_TOKEN_EXPIRE,
    )
    refresh_token = create_token(
        subject=ADMIN_USER["username"],
        role=ADMIN_USER["role"],
        token_type="refresh",
        expires_delta=config.REFRESH_TOKEN_EXPIRE,
    )

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": int(config.ACCESS_TOKEN_EXPIRE.total_seconds()),
    }


@app.post(f"{config.API_PREFIX}/integration/admin/refresh")
def admin_refresh(request_data: RefreshRequest, request: Request):
    enforce_rate_limit(request)

    try:
        payload = decode_token(request_data.refresh_token)
    except ExpiredSignatureError as exc:
        raise HTTPException(status_code=401, detail="Token expired") from exc
    except JWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc

    if payload.get("token_type") != "refresh":
        raise HTTPException(status_code=403, detail="Wrong token type")

    access_token = create_token(
        subject=payload["sub"],
        role=payload["role"],
        token_type="access",
        expires_delta=config.ACCESS_TOKEN_EXPIRE,
    )
    refresh_token = create_token(
        subject=payload["sub"],
        role=payload["role"],
        token_type="refresh",
        expires_delta=config.REFRESH_TOKEN_EXPIRE,
    )

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": int(config.ACCESS_TOKEN_EXPIRE.total_seconds()),
    }


@app.get(f"{config.API_PREFIX}/orders")
def get_orders(
    request: Request,
    response: Response,
    access_payload: dict[str, Any] = Depends(get_access_payload),
    pageSize: int = Query(default=config.DEFAULT_PAGE_SIZE, ge=1),
    currentPage: int = Query(default=config.DEFAULT_CURRENT_PAGE, ge=1),
    updated_after: str | None = None,
    fail: bool = False,
    delay: int = Query(default=0, ge=0, le=20),
    random_error: bool = False,
):
    _ = access_payload
    _ = response
    enforce_rate_limit(request)
    records = apply_common_query_behaviors(ORDERS, updated_after, fail, delay, random_error)
    return paginate(records, pageSize, currentPage)


@app.get(f"{config.API_PREFIX}/products")
def get_products(
    request: Request,
    access_payload: dict[str, Any] = Depends(get_access_payload),
    pageSize: int = Query(default=config.DEFAULT_PAGE_SIZE, ge=1),
    currentPage: int = Query(default=config.DEFAULT_CURRENT_PAGE, ge=1),
    updated_after: str | None = None,
    fail: bool = False,
    delay: int = Query(default=0, ge=0, le=20),
    random_error: bool = False,
):
    _ = access_payload
    enforce_rate_limit(request)
    records = apply_common_query_behaviors(PRODUCTS, updated_after, fail, delay, random_error)
    return paginate(records, pageSize, currentPage)


@app.get(f"{config.API_PREFIX}/customers")
def get_customers(
    request: Request,
    access_payload: dict[str, Any] = Depends(get_access_payload),
    pageSize: int = Query(default=config.DEFAULT_PAGE_SIZE, ge=1),
    currentPage: int = Query(default=config.DEFAULT_CURRENT_PAGE, ge=1),
    updated_after: str | None = None,
    fail: bool = False,
    delay: int = Query(default=0, ge=0, le=20),
    random_error: bool = False,
):
    _ = access_payload
    enforce_rate_limit(request)
    records = apply_common_query_behaviors(CUSTOMERS, updated_after, fail, delay, random_error)
    return paginate(records, pageSize, currentPage)


@app.exception_handler(HTTPException)
async def http_exception_handler(_: Request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail}, headers=exc.headers)
