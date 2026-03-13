from __future__ import annotations


class SongSessionService:
    QUESTIONS = (
        ("vibe", "What type of vibe do you want?"),
        ("bpm", "What BPM do you want?"),
        ("voice", "Do you want a male or female vocal style?"),
        ("vocal_mode", "Do you want lyrics, humming, or vocal chop style?"),
    )

    def __init__(self) -> None:
        self.sessions: dict[tuple[str, str], dict] = {}

    def begin_session(self, user_id: str, channel_id: str) -> str:
        key = (user_id, channel_id)
        self.sessions[key] = {
            "vibe": "",
            "bpm": "",
            "voice": "",
            "vocal_mode": "",
            "awaiting": "vibe",
        }
        return self.QUESTIONS[0][1]

    def has_session(self, user_id: str, channel_id: str) -> bool:
        return (user_id, channel_id) in self.sessions

    def cancel_session(self, user_id: str, channel_id: str) -> None:
        self.sessions.pop((user_id, channel_id), None)

    def handle_response(self, user_id: str, channel_id: str, content: str) -> dict:
        key = (user_id, channel_id)
        session = self.sessions.get(key)
        if session is None:
            return {"status": "missing"}

        awaiting = session["awaiting"]
        cleaned = " ".join(content.strip().split())

        if awaiting == "bpm":
            digits = "".join(ch for ch in cleaned if ch.isdigit())
            if not digits:
                return {
                    "status": "retry",
                    "message": "Give me a BPM number, like `90`, `120`, or `140`.",
                }
            bpm_value = max(50, min(180, int(digits)))
            session["bpm"] = str(bpm_value)
        elif awaiting == "voice":
            lowered = cleaned.lower()
            if "female" in lowered:
                session["voice"] = "female"
            elif "male" in lowered:
                session["voice"] = "male"
            else:
                return {
                    "status": "retry",
                    "message": "Tell me `male` or `female` for the vocal style.",
                }
        elif awaiting == "vocal_mode":
            lowered = cleaned.lower()
            if "hum" in lowered:
                session["vocal_mode"] = "humming"
            elif "chop" in lowered:
                session["vocal_mode"] = "vocal chop"
            elif "lyric" in lowered or "sing" in lowered or "words" in lowered:
                session["vocal_mode"] = "lyrics"
            else:
                return {
                    "status": "retry",
                    "message": "Tell me `lyrics`, `humming`, or `vocal chop` for the vocal mode.",
                }
        else:
            session["vibe"] = cleaned

        next_question = self._advance(session)
        if next_question is not None:
            return {
                "status": "question",
                "message": next_question,
            }

        prompt = self.build_prompt(session)
        self.sessions.pop(key, None)
        return {
            "status": "complete",
            "prompt": prompt,
            "vibe": session["vibe"],
            "bpm": int(session["bpm"]),
            "voice": session["voice"],
            "vocal_mode": session["vocal_mode"],
            "summary": (
                f"Vibe: {session['vibe']}\n"
                f"BPM: {session['bpm']}\n"
                f"Vocal style: {session['voice']}\n"
                f"Vocal mode: {session['vocal_mode']}"
            ),
        }

    def build_prompt(self, session: dict) -> str:
        return (
            f"{session['vibe']} vocal melody at {session['bpm']} BPM "
            f"with a {session['voice']} vocal style and {session['vocal_mode']} delivery"
        )

    def looks_like_song_request(self, content: str) -> bool:
        lowered = content.strip().lower()
        triggers = (
            "make me a song",
            "create a song",
            "generate a song",
            "make me vocals",
            "create vocals",
            "generate vocals",
            "make a vocal clip",
            "create a vocal clip",
            "generate a vocal clip",
            "make me a melody",
            "compose a song",
        )
        return any(trigger in lowered for trigger in triggers)

    def _advance(self, session: dict) -> str | None:
        if not session["vibe"]:
            session["awaiting"] = "vibe"
            return self.QUESTIONS[0][1]
        if not session["bpm"]:
            session["awaiting"] = "bpm"
            return self.QUESTIONS[1][1]
        if not session["voice"]:
            session["awaiting"] = "voice"
            return self.QUESTIONS[2][1]
        if not session["vocal_mode"]:
            session["awaiting"] = "vocal_mode"
            return self.QUESTIONS[3][1]

        session["awaiting"] = ""
        return None
