import json
import shutil
import subprocess
from typing import Any

from app.config import Settings
from app.errors import KeitaroError


class KeitaroClient:
    def __init__(self, settings: Settings):
        self.base_url = settings.keitaro_base_url
        self.api_key = settings.keitaro_api_key

    def get_groups(self, group_type: str) -> list[dict]:
        return self._list("GET", f"/groups?type={group_type}")

    def get_sources(self) -> list[dict]:
        return self._list("GET", "/traffic_sources")

    def get_domains(self) -> list[dict]:
        return self._list("GET", "/domains")

    def get_offers(self) -> list[dict]:
        return self._list("GET", "/offers")

    def get_offer(self, offer_id: int) -> dict:
        return self._object("GET", f"/offers/{offer_id}")

    def get_campaign(self, campaign_id: int) -> dict:
        return self._object("GET", f"/campaigns/{campaign_id}")

    def create_campaign(self, payload: dict) -> dict:
        return self._object("POST", "/campaigns", payload)

    def delete_campaign(self, campaign_id: int) -> None:
        self._request("DELETE", f"/campaigns/{campaign_id}")

    def get_streams(self, campaign_id: int) -> list[dict]:
        return self._list("GET", f"/campaigns/{campaign_id}/streams")

    def create_stream(self, payload: dict) -> dict:
        return self._object("POST", "/streams", payload)

    def update_stream(self, stream_id: int, payload: dict) -> dict:
        return self._object("PUT", f"/streams/{stream_id}", payload)

    def _list(self, method: str, path: str, body: dict | None = None) -> list[dict]:
        payload = self._request(method, path, body)
        return _as_list(payload)

    def _object(self, method: str, path: str, body: dict | None = None) -> dict:
        payload = self._request(method, path, body)
        if not isinstance(payload, dict):
            raise KeitaroError(f"Keitaro вернул не объект на {path}")
        return payload

    def _request(self, method: str, path: str, body: dict | None = None) -> Any:
        if not self.api_key:
            raise KeitaroError("В .env не задан KEITARO_API_KEY")
        url = f"{self.base_url}/admin_api/v1{path}"
        command = [
            _curl_binary(),
            "-sS",
            "-X",
            method,
            url,
            "-H",
            f"Api-Key: {self.api_key}",
            "-H",
            "Accept: application/json",
            "-w",
            "\n%{http_code}",
        ]
        data = None
        if body is not None:
            command.extend(["-H", "Content-Type: application/json", "--data-binary", "@-"])
            data = json.dumps(body).encode("utf-8")
        try:
            completed = subprocess.run(
                command,
                input=data,
                capture_output=True,
                timeout=60,
                check=False,
            )
        except FileNotFoundError as exc:
            raise KeitaroError("Не найден curl, без него запрос в Keitaro не уходит") from exc
        except subprocess.TimeoutExpired as exc:
            raise KeitaroError("Keitaro не ответил за 60 секунд") from exc

        stdout = completed.stdout.decode("utf-8", errors="replace")
        if "\n" not in stdout:
            stderr = completed.stderr.decode("utf-8", errors="replace").strip()
            raise KeitaroError(stderr or "Пустой ответ Keitaro")
        raw_body, _, status_raw = stdout.rpartition("\n")
        try:
            status = int(status_raw.strip())
        except ValueError as exc:
            raise KeitaroError(f"Не удалось прочитать статус ответа Keitaro: {status_raw}") from exc
        if status >= 400:
            raise KeitaroError(f"Keitaro {status}: {_short(raw_body)}")
        if not raw_body.strip():
            return {}
        try:
            return json.loads(raw_body)
        except json.JSONDecodeError as exc:
            raise KeitaroError(f"Keitaro вернул не JSON: {_short(raw_body)}") from exc


def _curl_binary() -> str:
    for name in ("curl", "curl.exe"):
        found = shutil.which(name)
        if found:
            return found
    raise KeitaroError("Не найден curl, без него запрос в Keitaro не уходит")


def _as_list(payload: Any) -> list[dict]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("data", "rows", "items"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
    raise KeitaroError("Keitaro вернул список в неожиданном виде")


def _short(text: str) -> str:
    compact = " ".join(text.split())
    return compact[:500] or "пустой ответ"
