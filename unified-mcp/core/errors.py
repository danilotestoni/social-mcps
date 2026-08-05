from __future__ import annotations


def describe_exception(exc: Exception) -> str:
    """
    httpx/httpcore timeout and low-level connection errors often carry no
    message at all (str(httpx.ReadTimeout()) == ""), which surfaces to the
    MCP caller as an opaque, empty error string otherwise. Always fall back
    to the exception's type name so there's something to look at.
    """
    text = str(exc)
    return text if text else f"{type(exc).__name__} (no further detail available)"
