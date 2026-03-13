from __future__ import annotations

def is_moderation_error(exc: Exception) -> bool:
    """
    Always returns False to bypass all built-in keyword filtering.
    """
    return False

def format_media_error(exc: Exception, media_type: str, safety_mode: str) -> str:
    """
    Returns the raw technical error only, bypassing all safety-mode tone adjustments.
    """
    return f"{media_type.title()} generation failed: {exc}"