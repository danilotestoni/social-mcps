from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.editorial import (EditorialError, approve, begin, bind, finish, reserve, validate)


def news(topic="NVIDIA DGX Spark"):
    return {"id": "2026-10-08-noticia-1", "estado": "pendiente", "contenido_markdown": topic,
            "canales": {"facebook": {"estado": "pendiente"}}}


def prepared(topic="NVIDIA DGX Spark"):
    item = news(topic)
    begin(item, {"facebook": {"text": topic}, "threads": {"text": topic}}, "editor")
    e = item["editorial"]
    bind(item, e["generation_id"], {"sha256": "a" * 64, "object_name": "asset", "generation": 5,
                                   "source_url": "https://chatgpt.com/s/nvidia"}, "visual")
    return item


def approved():
    item = prepared()
    approve(item, item["editorial"]["review_id"], "Dani", "Veo NVIDIA DGX Spark, corresponde a esta noticia",
            True, True, ["facebook", "threads"])
    return item


def test_nvidia_approved_allowed():
    item = approved()
    validate(item, 1, 1, "facebook")
    reserve(item, 1, 1, "facebook", "publisher")
    assert item["editorial"]["attempts"]["facebook"]["state"] == "reserved"


@pytest.mark.parametrize("topic,observed", [("NVIDIA DGX Spark", "Claude"), ("Moonshot", "Gemini")])
def test_human_rejects_wrong_visual(topic, observed):
    item = prepared(topic)
    with pytest.raises(EditorialError):
        approve(item, item["editorial"]["review_id"], "Dani", f"La imagen representa {observed}",
                False, True, ["facebook"])
    with pytest.raises(EditorialError):
        validate(item, 1, 1, "facebook")


def test_without_approval_blocked():
    with pytest.raises(EditorialError):
        validate(prepared(), 1, 1, "facebook")


def test_changed_text_blocked():
    item = approved()
    item["contenido_markdown"] = "Claude"
    with pytest.raises(EditorialError):
        validate(item, 1, 1, "facebook")


def test_changed_payload_blocked():
    item = approved()
    item["editorial"]["payloads"]["facebook"]["text"] = "Claude"
    with pytest.raises(EditorialError):
        validate(item, 1, 1, "facebook")


def test_wrong_revision_blocked():
    with pytest.raises(EditorialError):
        validate(approved(), 1, 2, "facebook")


def test_duplicate_and_uncertain_attempt_blocked():
    item = approved()
    reserve(item, 1, 1, "facebook", "publisher")
    with pytest.raises(EditorialError):
        reserve(item, 1, 1, "facebook", "other-agent")
    finish(item, "facebook", {"success": False, "error": "timeout"})
    with pytest.raises(EditorialError):
        reserve(item, 1, 1, "facebook", "publisher")


def test_partial_failure_keeps_confirmed_channel():
    item = approved()
    reserve(item, 1, 1, "facebook", "publisher")
    finish(item, "facebook", {"success": True, "data": {"post_id": "123"}})
    before = copy.deepcopy(item["canales"]["facebook"])
    reserve(item, 1, 1, "threads", "publisher")
    finish(item, "threads", {"success": False, "error": "timeout"})
    assert item["canales"]["facebook"] == before
    assert item["editorial"]["attempts"]["threads"]["state"] == "uncertain"
    with pytest.raises(EditorialError):
        reserve(item, 1, 1, "facebook", "publisher")


def test_legacy_unapproved_and_published_preserved():
    item = news()
    with pytest.raises(EditorialError):
        validate(item, 1, 1, "facebook")
    item["estado"] = "publicada"
    with pytest.raises(EditorialError):
        begin(item, {"facebook": {"text": "NVIDIA"}}, "editor")


def test_binding_requires_specific_pending_generation():
    item = prepared()
    with pytest.raises(EditorialError):
        bind(item, "other-news-generation", {"sha256": "b" * 64}, "visual")


def test_success_without_external_id_is_uncertain():
    item = approved()
    reserve(item, 1, 1, "facebook", "publisher")
    finish(item, "facebook", {"success": True, "data": {}})
    assert item["editorial"]["attempts"]["facebook"]["state"] == "uncertain"
