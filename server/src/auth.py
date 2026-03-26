"""Firebase token verification middleware.

Uses the Firebase REST API (lookup endpoint) to validate ID tokens,
so no service-account JSON is required for local development.
Falls back to firebase-admin verify_id_token when a service account is configured.
"""

import os
import logging
from typing import Optional

import httpx
from fastapi import Request, HTTPException

logger = logging.getLogger(__name__)

FIREBASE_API_KEY = os.getenv(
    "FIREBASE_WEB_API_KEY",
    "AIzaSyAdPcr2SZWE1LaI2AX-uCPErjnoAPz6uF4",
)

# Optional: if a service-account is available, we can use firebase-admin
_admin_initialized = False


def init_firebase() -> None:
    """Try to initialise Firebase Admin SDK. Non-fatal if no credentials found."""
    global _admin_initialized
    if _admin_initialized:
        return

    cred_path = os.getenv("FIREBASE_CREDENTIALS_PATH") or os.getenv(
        "GOOGLE_APPLICATION_CREDENTIALS"
    )
    if cred_path:
        try:
            import firebase_admin
            from firebase_admin import credentials as fb_creds
            cred = fb_creds.Certificate(cred_path)
            firebase_admin.initialize_app(cred)
            _admin_initialized = True
            logger.info("Firebase Admin SDK initialized with service account")
        except Exception as exc:
            logger.warning("Firebase Admin SDK init failed: %s — using REST fallback", exc)
    else:
        logger.info("No Firebase service account configured — using REST API for token verification")


async def _verify_token_rest(id_token: str) -> dict:
    """Verify a Firebase ID token by calling the getAccountInfo REST endpoint.

    This avoids needing a service-account JSON on the server.
    """
    url = (
        f"https://identitytoolkit.googleapis.com/v1/accounts:lookup"
        f"?key={FIREBASE_API_KEY}"
    )
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(url, json={"idToken": id_token})

    if resp.status_code != 200:
        body = resp.json()
        error_msg = body.get("error", {}).get("message", "UNKNOWN")
        if "INVALID_ID_TOKEN" in error_msg or "TOKEN_EXPIRED" in error_msg:
            raise HTTPException(status_code=401, detail="Token expired or invalid")
        raise HTTPException(status_code=401, detail=f"Token verification failed: {error_msg}")

    users = resp.json().get("users", [])
    if not users:
        raise HTTPException(status_code=401, detail="No user found for token")

    user = users[0]
    return {
        "uid": user["localId"],
        "email": user.get("email", ""),
        "email_verified": user.get("emailVerified", False),
    }


async def get_current_user(request: Request) -> dict:
    """FastAPI dependency that verifies the Firebase ID token from the
    Authorization header and returns user claims.

    Uses firebase-admin if available, otherwise falls back to REST API.
    """
    auth_header: Optional[str] = request.headers.get("authorization")

    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Authorization token")

    id_token = auth_header.removeprefix("Bearer ").strip()

    # Prefer Admin SDK when available (cryptographic verification)
    if _admin_initialized:
        try:
            from firebase_admin import auth as firebase_auth
            decoded = firebase_auth.verify_id_token(id_token)
            return decoded
        except Exception:
            # Fall through to REST verification
            pass

    # REST API fallback
    return await _verify_token_rest(id_token)
        