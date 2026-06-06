from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class TokenData(BaseModel):
    access_token: str
    token_expiry: int  # Unix timestamp; 0 means never expires (Page Access Token)


class PageInfo(BaseModel):
    id: str
    name: str
    category: str
    fan_count: int
    followers_count: int


class PostItem(BaseModel):
    id: str
    message: str
    created_time: str
    full_picture: str | None = None
    permalink_url: str | None = None


class ToolResult(BaseModel):
    success: bool
    data: Any | None = None
    error: str | None = None
