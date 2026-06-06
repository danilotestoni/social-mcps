from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class SiteInfo(BaseModel):
    id: int
    name: str
    url: str
    description: str
    post_count: int


class PostItem(BaseModel):
    id: int
    title: str
    url: str
    short_url: str
    status: str
    date: str


class ToolResult(BaseModel):
    success: bool
    data: Any | None = None
    error: str | None = None
