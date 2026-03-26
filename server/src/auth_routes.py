"""Backend auth endpoints — proxies Firebase Auth REST API.

The frontend sends credentials here instead of using the Firebase JS SDK directly.
We call the Firebase Identity Toolkit REST API server-side and return the
ID token + user info to the client.
"""

import os
import logging
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])

FIREBASE_API_KEY = os.getenv(
    "FIREBASE_WEB_API_KEY",
    "AIzaSyAdPcr2SZWE1LaI2AX-uCPErjnoAPz6uF4",
)
_IDENTITY_BASE = "https://identitytoolkit.googleapis.com/v1/accounts"
_TOKEN_BASE = "https://securetoken.googleapis.com/v1/token"


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class EmailPasswordRequest(BaseModel):
    email: str
    password: str


class GoogleLoginRequest(BaseModel):
    id_token: str  # Google OAuth credential from the frontend


class RefreshRequest(BaseModel):
    refresh_token: str


class AuthResponse(BaseModel):
    id_token: str
    refresh_token: str
    uid: str
    email: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ERROR_MAP: dict[str, str] = {
    "EMAIL_NOT_FOUND": "No account found with this email.",
    "INVALID_PASSWORD": "Invalid email or password.",
    "INVALID_LOGIN_CREDENTIALS": "Invalid email or password.",
    "USER_DISABLED": "This account has been disabled.",
    "EMAIL_EXISTS": "An account with this email already exists.",
    "WEAK_PASSWORD": "Password should be at least 6 characters.",
    "TOO_MANY_ATTEMPTS_TRY_LATER": "Too many attempts. Please try again later.",
    "INVALID_ID_TOKEN": "Invalid Google credential.",
}


async def _firebase_rest(endpoint: str, payload: dict) -> dict:
    """Call a Firebase Identity Toolkit REST endpoint and return the JSON body.

    Raises HTTPException on Firebase errors.
    """
    url = f"{_IDENTITY_BASE}:{endpoint}?key={FIREBASE_API_KEY}"

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(url, json=payload)

    body = resp.json()

    if resp.status_code != 200:
        error = body.get("error", {})
        code = error.get("message", "UNKNOWN_ERROR")
        human = _ERROR_MAP.get(code, code)
        # Map to sensible HTTP status
        status = 401 if "PASSWORD" in code or "CREDENTIALS" in code or "NOT_FOUND" in code else 400
        raise HTTPException(status_code=status, detail=human)

    return body


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/signup", response_model=AuthResponse)
async def signup(req: EmailPasswordRequest):
    """Create a new user with email & password via Firebase REST API."""
    data = await _firebase_rest("signUp", {
        "email": req.email,
        "password": req.password,
        "returnSecureToken": True,
    })
    return AuthResponse(
        id_token=data["idToken"],
        refresh_token=data["refreshToken"],
        uid=data["localId"],
        email=data["email"],
    )


@router.post("/login", response_model=AuthResponse)
async def login(req: EmailPasswordRequest):
    """Sign in with email & password via Firebase REST API."""
    data = await _firebase_rest("signInWithPassword", {
        "email": req.email,
        "password": req.password,
        "returnSecureToken": True,
    })
    return AuthResponse(
        id_token=data["idToken"],
        refresh_token=data["refreshToken"],
        uid=data["localId"],
        email=data["email"],
    )


@router.post("/google", response_model=AuthResponse)
async def google_login(req: GoogleLoginRequest):
    """Exchange a Google OAuth id_token for a Firebase ID token."""
    data = await _firebase_rest("signInWithIdp", {
        "postBody": f"id_token={req.id_token}&providerId=google.com",
        "requestUri": "http://localhost",
        "returnSecureToken": True,
        "returnIdpCredential": True,
    })
    return AuthResponse(
        id_token=data["idToken"],
        refresh_token=data["refreshToken"],
        uid=data["localId"],
        email=data.get("email", ""),
    )


@router.post("/refresh", response_model=AuthResponse)
async def refresh_token(req: RefreshRequest):
    """Exchange a refresh token for a new ID token."""
    url = f"{_TOKEN_BASE}?key={FIREBASE_API_KEY}"
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(url, data={
            "grant_type": "refresh_token",
            "refresh_token": req.refresh_token,
        })
    body = resp.json()
    if resp.status_code != 200:
        raise HTTPException(status_code=401, detail="Failed to refresh token.")

    return AuthResponse(
        id_token=body["id_token"],
        refresh_token=body["refresh_token"],
        uid=body["user_id"],
        email=body.get("email", ""),
    )
