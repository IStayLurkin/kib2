from __future__ import annotations


def is_moderation_error(exc: Exception) -> bool:
    message = str(exc).lower()
    patterns = (
        "moderation",
        "content policy",
        "policy violation",
        "safety system",
        "safety filters",
        "content filter",
        "flagged",
        "unsafe",
        "disallowed",
        "not allowed",
        "violat",
    )
    return any(pattern in message for pattern in patterns)


def format_media_error(exc: Exception, media_type: str, safety_mode: str) -> str:
    # Since we are using Ollama, we don't need to check for provider moderation blocks.
    # We just return the technical error if the local server crashes.
        return f"{media_type.title()} generation failed: {exc}"

    mode = (safety_mode or "balanced").strip().lower()
    media_label = media_type.lower()

    if mode == "strict":
        return (
            f"That {media_label} request was blocked by the provider's safety filters. "
            "Try a safer prompt and I can try again."
        )

    if mode == "creative":
        return (
            f"That {media_label} prompt hit the provider's safety filters. "
            "Try rewording the scene, mood, framing, or wording and I can take another shot."
        )

    return (
        f"I couldn't generate that {media_label} as written because the provider blocked the request. "
        "Try rephrasing the prompt and I can try a cleaner version."
    )
