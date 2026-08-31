"""
core/tools/skyvern_tool.py
===========================
SkyvernTool implementation for Jarvis.
Provides vision-based browser automation, portal form navigation, visual field extraction,
and automatic artifact download routing to the user's OS Desktop.
"""

import json
import time
import urllib.request
import urllib.error
from pathlib import Path
from typing import Type
from core.tools.base_tool import BaseTool
from core.tools.sandbox_enforcer import enforcer
from core.config import settings
from schemas.skyvern_schema import SkyvernTaskInput, SkyvernTaskOutput


class SkyvernTool(BaseTool[SkyvernTaskInput, SkyvernTaskOutput]):
    """
    Automates visual browser portal navigation, web form interaction, data extraction,
    and file downloading via Skyvern's VLM engine.
    """

    @property
    def name(self) -> str:
        return "skyvern_tool"

    @property
    def description(self) -> str:
        return (
            "Automates browser tasks, visual web navigation, form filling, data extraction, "
            "and portal document downloading using Skyvern's vision AI engine. "
            "Requires target URL and navigation goal."
        )

    @property
    def input_schema(self) -> Type[SkyvernTaskInput]:
        return SkyvernTaskInput

    @property
    def output_schema(self) -> Type[SkyvernTaskOutput]:
        return SkyvernTaskOutput

    def run(self, input_data: SkyvernTaskInput) -> SkyvernTaskOutput:
        # Resolve target download directory (defaults to OS Desktop directory)
        target_dir = input_data.download_dir or str(settings.desktop_dir / "Jarvis Downloads")
        try:
            validated_dir = enforcer.validate(target_dir)
            validated_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            validated_dir = settings.desktop_dir

        base_url = settings.skyvern_base_url
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Jarvis-Skyvern-Bridge/1.0"
        }
        if settings.skyvern_api_key:
            headers["x-api-key"] = settings.skyvern_api_key

        payload = {
            "url": input_data.url,
            "navigation_goal": input_data.navigation_goal,
            "extracted_information_schema": input_data.extracted_fields or [],
            "download_directory": str(validated_dir)
        }

        # 1. Dispatch Task to Skyvern Engine
        try:
            req = urllib.request.Request(
                f"{base_url}/tasks",
                data=json.dumps(payload).encode("utf-8"),
                headers=headers,
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=10) as response:
                resp_data = json.loads(response.read().decode("utf-8"))
                task_id = resp_data.get("task_id") or resp_data.get("id", "skyvern-task-1")
        except Exception as e:
            return self._fallback_offline_response(input_data, validated_dir, str(e))

        # 2. Poll Task Execution Status
        start_time = time.time()
        poll_interval = 1.0
        timeout = settings.skyvern_task_timeout

        while (time.time() - start_time) < timeout:
            try:
                poll_req = urllib.request.Request(
                    f"{base_url}/tasks/{task_id}",
                    headers=headers,
                    method="GET"
                )
                with urllib.request.urlopen(poll_req, timeout=10) as response:
                    task_res = json.loads(response.read().decode("utf-8"))
                    status = task_res.get("status", "running").lower()

                    if status in ("completed", "success"):
                        extracted = task_res.get("extracted_information", {})
                        downloads = task_res.get("downloaded_files", [])
                        return SkyvernTaskOutput(
                            success=True,
                            task_id=task_id,
                            status="completed",
                            extracted_data=extracted,
                            downloaded_files=downloads,
                            message=f"Skyvern visual navigation completed successfully for URL: {input_data.url}"
                        )
                    elif status in ("failed", "error"):
                        err_msg = task_res.get("error_message", "Visual navigation task failed")
                        return SkyvernTaskOutput(
                            success=False,
                            task_id=task_id,
                            status="failed",
                            extracted_data={},
                            downloaded_files=[],
                            message=f"Skyvern task failed: {err_msg}"
                        )
            except Exception:
                pass

            time.sleep(poll_interval)

        return SkyvernTaskOutput(
            success=False,
            task_id=task_id,
            status="timeout",
            extracted_data={},
            downloaded_files=[],
            message=f"Skyvern task timed out after {timeout} seconds."
        )

    def _fallback_offline_response(self, input_data: SkyvernTaskInput, download_dir: Path, error_detail: str) -> SkyvernTaskOutput:
        """Helper to handle offline Skyvern service gracefully during development / testing."""
        return SkyvernTaskOutput(
            success=False,
            task_id="skyvern-offline",
            status="unreachable",
            extracted_data={},
            downloaded_files=[],
            message=f"Skyvern engine endpoint ({settings.skyvern_base_url}) is unreachable or offline: {error_detail}"
        )
