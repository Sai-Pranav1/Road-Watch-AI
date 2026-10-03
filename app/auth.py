"""
Admin authentication: password from .env (ADMIN_PASSWORD) -> signed HttpOnly cookie.
"""

import hashlib
import hmac
import time
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from app.config import settings

COOKIE_NAME = "rg_admin"
SESSION_SECONDS = 8 * 60 * 60

router = APIRouter(prefix="/api/v1/admin", tags=["Admin Auth"])

_failed = defaultdict(list)  # ip -> [timestamps]


def _key() -> bytes:
    return hashlib.sha256(("roadguard-admin::" + settings.ADMIN_PASSWORD).encode()).digest()


def _sign(expiry: int) -> str:
    sig = hmac.new(_key(), str(expiry).encode(), hashlib.sha256).hexdigest()
    return f"{expiry}.{sig}"


def is_valid_token(token) -> bool:
    if not token or not settings.ADMIN_PASSWORD:
        return False
    try:
        expiry_s, sig = token.split(".", 1)
        expiry = int(expiry_s)
    except ValueError:
        return False
    if expiry < time.time():
        return False
    return hmac.compare_digest(_sign(expiry), f"{expiry_s}.{sig}")


def is_admin(request: Request) -> bool:
    return is_valid_token(request.cookies.get(COOKIE_NAME))


def require_admin(request: Request):
    if not is_admin(request):
        raise HTTPException(status_code=401, detail="Admin authentication required")


class LoginBody(BaseModel):
    password: str


@router.post("/login")
async def admin_login(body: LoginBody, request: Request, response: Response):
    if not settings.ADMIN_PASSWORD:
        raise HTTPException(status_code=503, detail="ADMIN_PASSWORD is not set in .env")

    ip = request.client.host if request.client else "unknown"
    now = time.time()
    _failed[ip] = [t for t in _failed[ip] if now - t < 60]
    if len(_failed[ip]) >= 5:
        raise HTTPException(status_code=429, detail="Too many attempts. Try again in a minute.")

    if not hmac.compare_digest(body.password.encode(), settings.ADMIN_PASSWORD.encode()):
        _failed[ip].append(now)
        raise HTTPException(status_code=401, detail="Incorrect password")

    _failed.pop(ip, None)
    response.set_cookie(
        COOKIE_NAME, _sign(int(now) + SESSION_SECONDS),
        max_age=SESSION_SECONDS, httponly=True, samesite="lax", path="/",
        secure=settings.BASE_URL.startswith("https://"),
    )
    return {"ok": True}


@router.post("/logout")
async def admin_logout(response: Response):
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"ok": True}


@router.get("/session")
async def admin_session(request: Request):
    return {"authenticated": is_admin(request)}
