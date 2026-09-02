"""Read-only public web tools: fetch evidence and open a verified public URL."""
from __future__ import annotations

import ipaddress
import socket
import webbrowser
from datetime import datetime, timezone
from typing import Type
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field

from core.tools.base_tool import BaseTool


class PublicWebError(ValueError):
    pass


def validate_public_url(raw_url: str) -> str:
    url = raw_url.strip()
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise PublicWebError("Only complete public http:// or https:// URLs are allowed.")
    hostname = parsed.hostname.lower().rstrip(".")
    if hostname in {"localhost", "localhost.localdomain"} or hostname.endswith(".local"):
        raise PublicWebError("Local or private network URLs are not allowed.")
    try:
        addresses = {info[4][0] for info in socket.getaddrinfo(hostname, None)}
    except socket.gaierror as exc:
        raise PublicWebError(f"Could not resolve public host '{hostname}'.") from exc
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if not ip.is_global:
            raise PublicWebError("Local or private network URLs are not allowed.")
    return url


class FetchURLInput(BaseModel):
    url: str = Field(..., description="Public http(s) URL to retrieve as read-only evidence.")
    max_characters: int = Field(default=6000, ge=500, le=12000)


class FetchURLOutput(BaseModel):
    success: bool
    url: str
    final_url: str = ""
    title: str = ""
    excerpt: str = ""
    retrieved_at: str = ""
    warning: str = ""


class FetchURL(BaseTool[FetchURLInput, FetchURLOutput]):
    @property
    def name(self) -> str:
        return "fetch_url"

    @property
    def description(self) -> str:
        return "Read a public webpage as evidence. Returns title, final URL, retrieval time, and a text excerpt. Never logs in or submits anything."

    @property
    def input_schema(self) -> Type[FetchURLInput]:
        return FetchURLInput

    @property
    def output_schema(self) -> Type[FetchURLOutput]:
        return FetchURLOutput

    def run(self, input_data: FetchURLInput) -> FetchURLOutput:
        try:
            url = validate_public_url(input_data.url)
            response = requests.get(url, headers={"User-Agent": "JarvisPublicResearch/1.0"}, timeout=(5, 20), allow_redirects=True)
            response.raise_for_status()
            final_url = validate_public_url(response.url)
            content_type = response.headers.get("content-type", "").lower()
            if "html" not in content_type and "text/plain" not in content_type:
                return FetchURLOutput(success=False, url=url, final_url=final_url, warning="The URL did not return an HTML or plain-text page.")
            soup = BeautifulSoup(response.text, "html.parser")
            for tag in soup(["script", "style", "noscript", "svg", "iframe"]):
                tag.decompose()
            title = soup.title.get_text(" ", strip=True) if soup.title else urlparse(final_url).netloc
            excerpt = " ".join(soup.get_text(" ", strip=True).split())[: input_data.max_characters]
            if not excerpt:
                return FetchURLOutput(success=False, url=url, final_url=final_url, title=title, warning="The page had no readable text.")
            return FetchURLOutput(success=True, url=url, final_url=final_url, title=title, excerpt=excerpt,
                                  retrieved_at=datetime.now(timezone.utc).isoformat())
        except (PublicWebError, requests.RequestException) as exc:
            return FetchURLOutput(success=False, url=input_data.url, warning=str(exc))


class OpenURLInput(BaseModel):
    url: str = Field(..., description="Public http(s) URL to open in the operating system's default browser.")


class OpenURLOutput(BaseModel):
    success: bool
    url: str
    message: str


class OpenURL(BaseTool[OpenURLInput, OpenURLOutput]):
    @property
    def name(self) -> str:
        return "open_url"

    @property
    def description(self) -> str:
        return "Open a verified public URL in the default browser. This only opens the page; it cannot interact with the website."

    @property
    def input_schema(self) -> Type[OpenURLInput]:
        return OpenURLInput

    @property
    def output_schema(self) -> Type[OpenURLOutput]:
        return OpenURLOutput

    def run(self, input_data: OpenURLInput) -> OpenURLOutput:
        try:
            url = validate_public_url(input_data.url)
            if not webbrowser.open(url, new=2):
                return OpenURLOutput(success=False, url=url, message="The operating system did not confirm opening the default browser.")
            return OpenURLOutput(success=True, url=url, message="Opened the public URL in the default browser. No website interaction was performed.")
        except PublicWebError as exc:
            return OpenURLOutput(success=False, url=input_data.url, message=str(exc))
