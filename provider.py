from __future__ import annotations

import asyncio
import hashlib
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode

import requests

from onda_provider_sdk import ProviderError, ScrobbleProvider, Track


API_URL = "https://ws.audioscrobbler.com/2.0/"
AUTH_URL = "https://www.last.fm/api/auth/"
REQUEST_TIMEOUT = (10, 20)


class Provider(ScrobbleProvider):
    def __init__(self, context: Any) -> None:
        self.context = context
        self._pending_token: str | None = None

    async def begin_authentication(self) -> dict[str, Any]:
        api_key, shared_secret = self._app_credentials()
        payload = await self._signed_call(
            "auth.getToken",
            {},
            api_key=api_key,
            shared_secret=shared_secret,
        )
        token = str(payload.get("token", "")).strip()
        if not token:
            raise ProviderError(
                "AUTH_RESPONSE_INVALID",
                "Last.fm no devolvió un token de autorización.",
            )
        self._pending_token = token
        return {
            "authorization_url": f"{AUTH_URL}?{urlencode({'api_key': api_key, 'token': token})}",
            "message": "Autoriza ONDA en Last.fm y vuelve a la aplicación.",
        }

    async def complete_authentication(self) -> dict[str, Any]:
        token = self._pending_token
        if not token:
            raise ProviderError(
                "AUTH_NOT_STARTED",
                "Inicia de nuevo la autorización de Last.fm.",
            )
        api_key, shared_secret = self._app_credentials()
        try:
            payload = await self._signed_call(
                "auth.getSession",
                {"token": token},
                api_key=api_key,
                shared_secret=shared_secret,
            )
        finally:
            self._pending_token = None
        session = payload.get("session") if isinstance(payload, dict) else None
        if not isinstance(session, dict):
            raise ProviderError(
                "AUTH_RESPONSE_INVALID",
                "Last.fm no devolvió una sesión válida.",
            )
        session_key = str(session.get("key", "")).strip()
        username = str(session.get("name", "")).strip()
        if not session_key:
            raise ProviderError(
                "AUTH_RESPONSE_INVALID",
                "Last.fm devolvió una sesión vacía.",
            )
        return {
            "secrets": {"session_key": session_key},
            "message": "Cuenta de Last.fm conectada.",
            "details": {"usuario": username} if username else {},
        }

    async def check_configuration(self) -> dict[str, Any]:
        missing = self._missing_credentials()
        if missing:
            return {
                "success": False,
                "message": f"Falta configurar: {', '.join(missing)}.",
            }
        payload = await self._call("user.getInfo", {})
        user = payload.get("user") if isinstance(payload, dict) else None
        name = user.get("name", "") if isinstance(user, dict) else ""
        return {
            "success": True,
            "message": "Cuenta de Last.fm conectada.",
            "details": {"usuario": str(name)},
        }

    async def now_playing(self, track: Track, position_ms: int) -> None:
        del position_ms
        await self._call("track.updateNowPlaying", _track_params(track))

    async def scrobble(self, track: Track, played_at: str) -> None:
        params = _track_params(track)
        params["timestamp"] = str(_unix_timestamp(played_at))
        await self._call("track.scrobble", params)

    async def _call(self, method: str, params: dict[str, str]) -> dict[str, Any]:
        api_key, shared_secret, session_key = self._credentials()
        return await self._signed_call(
            method,
            {"sk": session_key, **params},
            api_key=api_key,
            shared_secret=shared_secret,
        )

    async def _signed_call(
        self,
        method: str,
        params: dict[str, str],
        *,
        api_key: str,
        shared_secret: str,
    ) -> dict[str, Any]:
        signed = {
            "api_key": api_key,
            "method": method,
            **params,
        }
        signed["api_sig"] = _signature(signed, shared_secret)
        body = {**signed, "format": "json"}
        return await asyncio.to_thread(self._post, body)

    def _app_credentials(self) -> tuple[str, str]:
        values = tuple(
            str(self.context.get_secret(key) or "").strip()
            for key in ("api_key", "shared_secret")
        )
        if not all(values):
            raise ProviderError(
                "AUTH_REQUIRED",
                "Configura la API key y el shared secret de Last.fm.",
            )
        return values

    def _missing_credentials(self) -> list[str]:
        labels = {
            "api_key": "API key",
            "shared_secret": "shared secret",
            "session_key": "session key",
        }
        return [
            label
            for key, label in labels.items()
            if not str(self.context.get_secret(key) or "").strip()
        ]

    def _credentials(self) -> tuple[str, str, str]:
        values = tuple(
            str(self.context.get_secret(key) or "").strip()
            for key in ("api_key", "shared_secret", "session_key")
        )
        if not all(values):
            raise ProviderError(
                "AUTH_REQUIRED",
                "Configura la API key, el shared secret y la session key de Last.fm.",
            )
        return values

    @staticmethod
    def _post(body: dict[str, str]) -> dict[str, Any]:
        try:
            response = requests.post(API_URL, data=body, timeout=REQUEST_TIMEOUT)
        except requests.RequestException as exc:
            raise ProviderError(
                "NETWORK_ERROR",
                "No se pudo contactar a Last.fm.",
                retryable=True,
            ) from exc

        if response.status_code == 429 or response.status_code >= 500:
            raise ProviderError(
                "SERVICE_UNAVAILABLE",
                "Last.fm no está disponible temporalmente.",
                retryable=True,
            )
        if response.status_code >= 400:
            raise ProviderError(
                "SUBMISSION_REJECTED",
                f"Last.fm rechazó la solicitud ({response.status_code}).",
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise ProviderError(
                "INVALID_RESPONSE", "Last.fm devolvió una respuesta inválida."
            ) from exc
        if not isinstance(payload, dict):
            raise ProviderError("INVALID_RESPONSE", "Respuesta inesperada de Last.fm.")
        if "error" in payload:
            code = int(payload.get("error", 0) or 0)
            message = str(payload.get("message", "Last.fm rechazó la solicitud."))
            if code in {4, 9, 10, 13, 26}:
                raise ProviderError("AUTH_INVALID", message)
            if code in {11, 16, 29}:
                raise ProviderError("SERVICE_UNAVAILABLE", message, retryable=True)
            raise ProviderError("SUBMISSION_REJECTED", message)
        return payload


def _signature(params: dict[str, str], shared_secret: str) -> str:
    source = "".join(
        f"{key}{params[key]}"
        for key in sorted(params)
        if key not in {"format", "callback", "api_sig"}
    )
    return hashlib.md5(
        f"{source}{shared_secret}".encode("utf-8"), usedforsecurity=False
    ).hexdigest()


def _track_params(track: Track) -> dict[str, str]:
    if not track.title.strip() or not track.artists:
        raise ProviderError("INVALID_TRACK", "La canción no tiene título o artista.")
    params = {"artist": ", ".join(track.artists), "track": track.title}
    if track.album:
        params["album"] = track.album
    if track.duration_ms and track.duration_ms > 0:
        params["duration"] = str(max(1, round(track.duration_ms / 1000)))
    mbid = _first_external_ref(
        track, "recording_mbid", "musicbrainz_recording", "musicbrainz"
    )
    if mbid:
        params["mbid"] = mbid
    return params


def _first_external_ref(track: Track, *keys: str) -> str | None:
    for key in keys:
        value = track.external_refs.get(key)
        if value:
            return value
    return None


def _unix_timestamp(value: str) -> int:
    try:
        normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ProviderError("INVALID_TIMESTAMP", "La fecha de reproducción no es válida.") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return int(parsed.timestamp())
