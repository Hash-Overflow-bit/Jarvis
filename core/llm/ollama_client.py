"""
core/llm/ollama_client.py
=========================
Thin wrapper around the Ollama REST API.

Supports:
- Multi-turn chat (with message history)
- Single-shot generation
- Streaming responses
- Health check

Cross-platform: Talks to http://localhost:11434 — same URL on Mac and Windows.
The only OS difference is where Ollama is installed; the API is identical.
"""

import json
from collections.abc import Generator
from typing import overload, Literal, Any

import requests

from core.config import settings


class OllamaError(Exception):
    """Raised when Ollama returns an error or is unreachable."""


class OllamaClient:
    """
    Wrapper for the Ollama /api/chat and /api/generate endpoints.
    Always use the module-level `ollama` singleton.
    """

    def __init__(self, base_url: str | None = None, model: str | None = None):
        self.base_url = (base_url or settings.ollama_base_url).rstrip("/")
        self.model = model or settings.ollama_model

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    def is_running(self) -> bool:
        """Returns True if the Ollama server is reachable."""
        try:
            resp = requests.get(f"{self.base_url}/api/tags", timeout=5)
            return resp.status_code == 200
        except requests.exceptions.ConnectionError:
            return False

    def list_models(self) -> list[str]:
        """Returns a list of locally available model names."""
        try:
            resp = requests.get(f"{self.base_url}/api/tags", timeout=5)
            resp.raise_for_status()
            return [m["name"] for m in resp.json().get("models", [])]
        except Exception as e:
            raise OllamaError(f"Failed to list models: {e}") from e

    # ------------------------------------------------------------------
    # generate_compat — mirrors client's exact call pattern
    # Uses /api/generate with a plain prompt string (no message history)
    # Client config: OLLAMA_URL = "http://localhost:11434/api/generate"
    # ------------------------------------------------------------------

    @overload
    def generate_compat(
        self,
        prompt: str,
        model: str | None = None,
        temperature: float = 0.7,
        stream: Literal[False] = False,
    ) -> str: ...

    @overload
    def generate_compat(
        self,
        prompt: str,
        model: str | None = None,
        temperature: float = 0.7,
        stream: Literal[True] = ...,
    ) -> Generator[str, None, None]: ...

    def generate_compat(
        self,
        prompt: str,
        model: str | None = None,
        temperature: float = 0.7,
        stream: bool = False,
    ) -> str | Generator[str, None, None]:
        """
        Single-shot generation via /api/generate.
        Matches the client's existing call pattern exactly:
            POST http://localhost:11434/api/generate
            {"model": "llama3.1", "prompt": "...", "stream": false}

        Use this for backwards compatibility with the client's setup.
        For multi-turn conversation, use chat() instead.
        """
        payload = {
            "model": model or self.model,
            "prompt": prompt,
            "stream": stream,
            "options": {"temperature": temperature},
        }
        try:
            resp = requests.post(
                settings.ollama_generate_url,
                json=payload,
                stream=stream,
                timeout=settings.ollama_request_timeout,
            )
            resp.raise_for_status()
        except requests.exceptions.ConnectionError:
            raise OllamaError(
                f"Cannot connect to Ollama at {self.base_url}. "
                "Is Ollama running? Try: ollama serve"
            )
        except requests.exceptions.Timeout as e:
            raise OllamaError(
                f"Ollama request timed out after {settings.ollama_request_timeout:g} seconds."
            ) from e
        except requests.exceptions.HTTPError as e:
            raise OllamaError(f"Ollama HTTP error: {e}") from e

        if stream:
            return self._stream_generate(resp)

        data = resp.json()
        return data.get("response", "")

    # ------------------------------------------------------------------
    # Chat (multi-turn, uses conversation history)
    # ------------------------------------------------------------------

    @overload
    def chat(
        self,
        messages: list[dict],
        model: str | None = None,
        stream: Literal[False] = False,
        temperature: float = 0.7,
        format: str | None = None,
        tools: list[dict] | None = None,
        options: dict | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]: ...

    @overload
    def chat(
        self,
        messages: list[dict],
        model: str | None = None,
        stream: Literal[True] = ...,
        temperature: float = 0.7,
        format: str | None = None,
        tools: list[dict] | None = None,
        options: dict | None = None,
        **kwargs: Any,
    ) -> Generator[str, None, None]: ...

    def chat(
        self,
        messages: list[dict],
        model: str | None = None,
        stream: bool = False,
        temperature: float = 0.7,
        format: str | None = None,
        tools: list[dict] | None = None,
        options: dict | None = None,
        **kwargs: Any,
    ) -> dict[str, Any] | Generator[str, None, None]:
        """
        Send a multi-turn chat request via /api/chat.
        Used by SessionManager for full conversation history.

        Client note: The client's OLLAMA_URL uses /api/generate (single-shot).
        We use /api/chat here because it natively supports message history,
        which is essential for the multi-turn conversational state machine (M1).

        Args:
            messages: List of {"role": "user"|"assistant"|"system", "content": "..."}
            model:    Override the default model from settings.
            stream:   If True, returns a generator of text chunks.
            temperature: Sampling temperature.
            format:   If "json", forces JSON output (for tool calling in M6).
            tools:    Optional list of tool schemas for function calling.
            options:  Optional options dictionary.

        Returns:
            The message dict containing 'content' and optional 'tool_calls' (or generator if stream=True).
        """
        request_timeout = float(kwargs.pop("request_timeout", settings.ollama_request_timeout))
        payload_options = {"temperature": temperature}
        if options:
            payload_options.update(options)

        payload = {
            "model": model or self.model,
            "messages": messages,
            "stream": stream,
            "keep_alive": settings.ollama_keep_alive,
            "options": payload_options,
        }
        if format:
            payload["format"] = format
        if tools:
            payload["tools"] = tools

        try:
            from opentelemetry import trace
            tracer = trace.get_tracer("jarvis")
            with tracer.start_as_current_span("OllamaClient.chat") as span:
                span.set_attribute("llm.model", model or self.model)
                span.set_attribute("llm.temperature", temperature)
                if format:
                    span.set_attribute("llm.format", format)

                resp = requests.post(
                    settings.ollama_chat_url,   # http://localhost:11434/api/chat
                    json=payload,
                    stream=stream,
                    timeout=request_timeout,
                )
                resp.raise_for_status()
                span.set_attribute("llm.status_code", resp.status_code)
        except requests.exceptions.ConnectionError:
            raise OllamaError(
                f"Cannot connect to Ollama at {self.base_url}. "
                "Is Ollama running? Try: ollama serve"
            )
        except requests.exceptions.Timeout as e:
            raise OllamaError(
                f"Ollama request timed out after {request_timeout:g} seconds."
            ) from e
        except requests.exceptions.HTTPError as e:
            raise OllamaError(f"Ollama HTTP error: {e}") from e

        if stream:
            return self._stream_chat(resp)
        else:
            try:
                data = resp.json()
                message = data["message"]
            except (ValueError, KeyError, TypeError) as e:
                raise OllamaError("Ollama returned an invalid chat response.") from e
            return message

    def _stream_chat(self, response: requests.Response) -> "Generator[str, None, None]":
        """Generator that yields text chunks from a streaming /api/chat response."""
        for line in response.iter_lines():
            if line:
                chunk = json.loads(line)
                if not chunk.get("done", False):
                    yield chunk["message"]["content"]

    def _stream_generate(self, response: requests.Response) -> "Generator[str, None, None]":
        """Generator that yields text chunks from a streaming /api/generate response."""
        for line in response.iter_lines():
            if line:
                chunk = json.loads(line)
                if not chunk.get("done", False):
                    yield chunk.get("response", "")

    # ------------------------------------------------------------------
    # Generate (single-shot, no history)
    # ------------------------------------------------------------------

    def generate(
        self,
        prompt: str,
        system: str | None = None,
        model: str | None = None,
        temperature: float = 0.7,
    ) -> str:
        """
        Single-shot text generation via /api/generate (no conversation history).
        Used for code generation in M5.
        Endpoint: http://localhost:11434/api/generate (matches client's OLLAMA_URL)
        """
        payload = {
            "model": model or self.model,
            "prompt": prompt,
            "stream": False,
            "keep_alive": settings.ollama_keep_alive,
            "options": {"temperature": temperature},
        }
        if system:
            payload["system"] = system

        try:
            resp = requests.post(
                settings.ollama_generate_url,   # http://localhost:11434/api/generate
                json=payload,
                timeout=settings.ollama_request_timeout,
            )
            resp.raise_for_status()
        except requests.exceptions.ConnectionError:
            raise OllamaError(
                f"Cannot connect to Ollama at {self.base_url}. "
                "Is Ollama running? Try: ollama serve"
            )
        except requests.exceptions.Timeout as e:
            raise OllamaError(
                f"Ollama request timed out after {settings.ollama_request_timeout:g} seconds."
            ) from e
        except requests.exceptions.HTTPError as e:
            raise OllamaError(f"Ollama HTTP error: {e}") from e

        return resp.json()["response"]


# ---------------------------------------------------------------------------
# Singleton — import this everywhere
# ---------------------------------------------------------------------------
ollama = OllamaClient()
