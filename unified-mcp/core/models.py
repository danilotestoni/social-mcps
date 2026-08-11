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


# ── Content Queue (shared pipeline state, GCS-backed) ─────────────────────────
#
# Storage contract for queue_* tools — one Markdown file per news item in
# gs://<QUEUE_GCS_BUCKET>/queue/<id>.md, YAML frontmatter + body. `version`
# is the GCS object generation number, not a field stored in the frontmatter
# itself — queue_update/mark_published/mark_discarded require the caller's
# expected_version to match it exactly (enforced atomically via GCS
# if_generation_match) before a write is accepted, so two agents editing the
# same item can't silently clobber each other.

QUEUE_ESTADOS = ("pendiente", "preparada", "publicada", "descartada", "error")
QUEUE_CANALES = ("wordpress", "linkedin", "facebook", "instagram", "threads", "x")


class QueueChannelResult(BaseModel):
    estado: str = "pendiente"  # pendiente | publicado | error
    id: str | None = None
    url: str | None = None
    error: str | None = None


class QueueImage(BaseModel):
    proveedor: str | None = None  # pollinations | gemini | canva
    url: str | None = None
    canva_id: str | None = None


class QueueItemSummary(BaseModel):
    id: str
    version: int
    estado: str
    orden: int
    fecha_prevista: str | None = None
    fecha_publicada: str | None = None
    url_wordpress: str | None = None
