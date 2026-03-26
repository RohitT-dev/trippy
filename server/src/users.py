"""User preference routes — CRUD backed by MongoDB."""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from typing import Optional, Any

from .auth import get_current_user
from .database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/users", tags=["users"])


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class UserProfilePayload(BaseModel):
    name: Optional[str] = None
    age: Optional[str] = None


class PreferencesSaveRequest(BaseModel):
    user_profile: Optional[UserProfilePayload] = None
    preferences: Optional[dict[str, Any]] = Field(
        default=None,
        description="Travel preferences object (budget_level, travel_pace, etc.)",
    )


class PreferencesResponse(BaseModel):
    found: bool
    data: Optional[dict[str, Any]] = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/preferences", response_model=PreferencesResponse)
async def get_preferences(user: dict = Depends(get_current_user)):
    """Load saved preferences for the authenticated user."""
    db = get_db()
    doc = await db.users.find_one(
        {"uid": user["uid"]},
        {"_id": 0},
    )
    return PreferencesResponse(found=doc is not None, data=doc)


@router.post("/preferences")
async def save_preferences(
    body: PreferencesSaveRequest,
    user: dict = Depends(get_current_user),
):
    """Upsert user preferences in MongoDB."""
    db = get_db()

    update_doc: dict[str, Any] = {
        "uid": user["uid"],
        "email": user.get("email"),
        "last_updated": datetime.now(timezone.utc),
    }
    if body.user_profile is not None:
        update_doc["user_profile"] = body.user_profile.model_dump(exclude_none=True)
    if body.preferences is not None:
        update_doc["preferences"] = body.preferences

    await db.users.find_one_and_update(
        {"uid": user["uid"]},
        {"$set": update_doc},
        upsert=True,
    )

    return {"success": True}


@router.delete("/preferences")
async def clear_preferences(user: dict = Depends(get_current_user)):
    """Clear all preferences for the authenticated user (keeps the document)."""
    db = get_db()
    await db.users.find_one_and_update(
        {"uid": user["uid"]},
        {"$set": {
            "preferences": {},
            "user_profile": {},
            "last_updated": datetime.now(timezone.utc),
        }},
    )
    return {"success": True, "message": "Preferences cleared"}
