from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any


class BridgeError(RuntimeError):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


class BridgeClient:
    def __init__(self, base_url: str, key: str, timeout: float = 15):
        self.base_url = base_url.rstrip("/")
        self.key = key
        self.timeout = timeout

    def _request(
        self, method: str, path: str, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        body = None
        headers = {
            "X-Bridge-Key": self.key,
            "Accept": "application/json",
        }
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json; charset=utf-8"

        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=body,
            headers=headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            raise BridgeError(
                f"Bridge returned HTTP {error.code}: {detail}", error.code
            ) from error
        except (urllib.error.URLError, TimeoutError) as error:
            raise BridgeError(f"Bridge connection failed: {error}") from error

    def health(self) -> dict[str, Any]:
        return self._request("GET", "/health")

    def events(self, after: int, limit: int = 100) -> dict[str, Any]:
        return self._request("GET", f"/events?after={after}&limit={limit}")

    def send_text(
        self,
        request_id: str,
        receiver: str,
        content: str,
        at_users: str = "",
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/send",
            {
                "request_id": request_id,
                "receiver": receiver,
                "content": content,
                "at_users": at_users,
            },
        )

