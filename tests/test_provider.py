from __future__ import annotations

import asyncio
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch


SDK_ROOT = (
    Path(__file__).resolve().parents[2]
    / "onda"
    / "packages"
    / "onda_runtime_python"
    / "android"
    / "src"
    / "main"
    / "python"
)
sys.path.insert(0, str(SDK_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
if "requests" not in sys.modules:
    sys.modules["requests"] = types.SimpleNamespace(
        RequestException=OSError,
        post=None,
    )

from onda_provider_sdk import ProviderRef, Track  # noqa: E402
from provider import Provider, _signature  # noqa: E402


class Context:
    def __init__(self, values):
        self.values = values

    def get_secret(self, name):
        return self.values.get(name)


class Response:
    status_code = 200

    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return self.payload


def context():
    return Context(
        {"api_key": "api", "shared_secret": "secret", "session_key": "session"}
    )


def track():
    return Track(
        source_ref=ProviderRef("dev.test.metadata", "track", "42"),
        title="Song",
        artists=("Artist",),
        album="Album",
        duration_ms=180000,
    )


class ProviderTests(unittest.TestCase):
    def test_signature_sorts_parameters_and_excludes_format(self):
        value = _signature(
            {"method": "track.scrobble", "api_key": "api", "format": "json"},
            "secret",
        )
        self.assertEqual(value, "985cc7968ee83542766bbab28f6d8105")

    @patch("provider.requests.post")
    def test_configuration_checks_authenticated_user(self, post):
        post.return_value = Response({"user": {"name": "listener"}})
        result = asyncio.run(Provider(context()).check_configuration())
        self.assertTrue(result["success"])
        self.assertEqual(result["details"]["usuario"], "listener")
        self.assertEqual(post.call_args.kwargs["data"]["method"], "user.getInfo")

    @patch("provider.requests.post")
    def test_now_playing_sends_metadata(self, post):
        post.return_value = Response({"nowplaying": {}})
        asyncio.run(Provider(context()).now_playing(track(), 0))
        body = post.call_args.kwargs["data"]
        self.assertEqual(body["method"], "track.updateNowPlaying")
        self.assertEqual(body["artist"], "Artist")
        self.assertEqual(body["duration"], "180")
        self.assertIn("api_sig", body)

    @patch("provider.requests.post")
    def test_scrobble_sends_start_timestamp(self, post):
        post.return_value = Response({"scrobbles": {"@attr": {"accepted": "1"}}})
        asyncio.run(
            Provider(context()).scrobble(track(), "2026-09-20T12:00:00Z")
        )
        body = post.call_args.kwargs["data"]
        self.assertEqual(body["method"], "track.scrobble")
        self.assertEqual(body["timestamp"], "1789905600")


if __name__ == "__main__":
    unittest.main()
