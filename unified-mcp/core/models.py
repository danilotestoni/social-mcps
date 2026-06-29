from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ToolResult(BaseModel):
    success: bool
    data: Any | None = None
    error: str | None = None


# ── LinkedIn ────────────────────────────────────────────────────────────────

class LinkedInTokenData(BaseModel):
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


# ── Facebook ─────────────────────────────────────────────────────────────────

class FacebookTokenData(BaseModel):
    access_token: str
    token_expiry: int  # Unix timestamp; 0 means never expires (Page Access Token)


class PageInfo(BaseModel):
    id: str
    name: str
    category: str
    fan_count: int
    followers_count: int


class FacebookPostItem(BaseModel):
    id: str
    message: str
    created_time: str
    full_picture: str | None = None
    permalink_url: str | None = None


# ── Instagram ────────────────────────────────────────────────────────────────

class InstagramTokenData(BaseModel):
    access_token: str
    token_expiry: int  # Unix timestamp; 0 means never expires


class InstagramAccountInfo(BaseModel):
    id: str
    username: str
    name: str
    followers_count: int
    media_count: int


class MediaItem(BaseModel):
    id: str
    caption: str
    media_type: str
    timestamp: str
    permalink: str


# ── Threads ──────────────────────────────────────────────────────────────────

class ThreadsTokenData(BaseModel):
    access_token: str
    token_expiry: int  # Unix timestamp; 0 means never expires


class ThreadsAccountInfo(BaseModel):
    id: str
    username: str
    name: str


class ThreadItem(BaseModel):
    id: str
    text: str
    media_type: str
    timestamp: str
    permalink: str


# ── WordPress ─────────────────────────────────────────────────────────────────

class SiteInfo(BaseModel):
    id: int
    name: str
    url: str
    description: str
    post_count: int


class WPPostItem(BaseModel):
    id: int
    title: str
    url: str
    short_url: str
    status: str
    date: str
