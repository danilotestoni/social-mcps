from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class TokenData(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int
    token_expiry: int


class ProfileInfo(BaseModel):
    id: str
    first_name: str
    last_name: str
    person_urn: str


class UGCPostElement(BaseModel):
    urn: str
    text: str
    created_at: int


class ToolResult(BaseModel):
    success: bool
    data: Any | None = None
    error: str | None = None
