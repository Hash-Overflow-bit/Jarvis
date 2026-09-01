"""
core/safety/confirmation_gate.py
================================
Confirmation gate to intercept risky actions and request user approval.
"""

import sys
import asyncio
from core.config import settings
from core.logging.audit_logger import audit_logger
from core.safety.risk_classifier import risk_classifier


class ConfirmationGate:
    """Handles prompt/response loops for approving high-risk tool execution."""

    async def confirm_action(
        self,
        tool_name: str,
        parameters: dict,
        mode: str = "text"
    ) -> bool:
        """
        Requests confirmation from the user via text or voice.
        Returns True if approved, False if denied or timed out.
        """
        # 1. Log the pending request
        audit_logger.log_action(
            tool_name=tool_name,
            parameters=parameters,
            status="PENDING",
            details="Awaiting user confirmation"
        )

        risk = risk_classifier.get_risk_level(tool_name)
        warning_msg = (
            f"\n[SECURITY WARNING] Jarvis is requesting permission to execute "
            f"a {risk.upper()} risk tool: '{tool_name}'\n"
            f"Parameters: {parameters}\n"
        )

        if mode == "audio":
            approved = await self._confirm_audio(tool_name, warning_msg)
            if not approved:
                print("\n[Audio confirmation failed or denied. Falling back to console prompt...]")
                approved = await self._confirm_text(warning_msg)
            return approved
        else:
            return await self._confirm_text(warning_msg)

    async def _confirm_text(self, warning_msg: str) -> bool:
        """Prompts the user via the terminal console."""
        print(warning_msg, flush=True)
        try:
            # Direct prompt on CLI without thread pool executor overhead to prevent Windows IOCP deadlock
            user_input = input("Do you want to proceed? (yes/no): ").strip().lower()
            approved = user_input in ["yes", "y", "confirm", "proceed"]
            return approved
        except Exception:
            return False



    async def _confirm_audio(self, tool_name: str, warning_msg: str) -> bool:
        """Prompts the user via TTS and listens for voice approval (STT)."""
        print(warning_msg)

        from core.audio.stt import get_stt
        from core.audio.tts import get_tts_singleton
        from core.audio.audio_device import audio_device

        tts = get_tts_singleton()
        stt = get_stt()

        # Speak the safety warning using TTS
        prompt_speech = f"Security alert. I need your permission to run {tool_name}. Say yes to proceed or no to cancel."
        tts.speak(prompt_speech)

        # Record response (max 10 seconds, stop on silence)
        print("[Listening for voice confirmation (yes/no)...]")
        try:
            audio_data = audio_device.record_until_silence(max_duration=10.0)
            if audio_data.size == 0 or not stt.is_speech(audio_data):
                print("[No speech detected. Confirmation DENIED.]")
                return False

            response_text = stt.transcribe(audio_data).strip().lower()
            print(f"[Voice response: {response_text!r}]")

            # Parse keywords
            approve_keywords = ["yes", "confirm", "proceed", "okay", "ok", "go ahead", "do it", "yeah", "yep", "yup", "sure", "approve", "allow"]
            deny_keywords = ["no", "cancel", "stop", "abort", "don't", "deny", "reject", "block", "never mind", "no way"]

            # Check if any keyword matches
            for word in approve_keywords:
                if word in response_text:
                    return True

            for word in deny_keywords:
                if word in response_text:
                    return False

            return False
        except Exception as e:
            print(f"[Error in voice confirmation: {e}. Defaulting to DENIED.]")
            return False


# Global confirmation gate singleton
confirmation_gate = ConfirmationGate()
