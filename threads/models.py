from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class TokenData(BaseModel):
    access_token: str
    token_expiry: int  # Unix timestamp; 0 means never expires


class AccountInfo(BaseModel):
    id: str
    username: str
    name: str


class ThreadItem(BaseModel):
    id: str
    text: str
    media_type: str
    timestamp: str
    permalink: str


class ToolResult(BaseModel):
    success: bool
    data: Any | None = None
    error: str | None = None
