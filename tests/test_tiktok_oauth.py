"""Verifica o desafio PKCE exigido pelo Login Kit desktop do TikTok."""

import contextlib
import hashlib
import io
import json
import tempfile
import unittest
import urllib.parse
from unittest import mock

import tiktok_post


class TikTokDesktopOAuthTest(unittest.TestCase):
    def test_authorization_url_uses_hex_sha256_challenge(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            pkce_file = f"{temp_dir}/pkce.json"
            output = io.StringIO()
            with (
                mock.patch.object(tiktok_post, "CLIENT_KEY", "client-key"),
                mock.patch.object(tiktok_post, "CLIENT_SECRET", "client-secret"),
                mock.patch.object(
                    tiktok_post, "REDIRECT_URI", "http://localhost:3455/callback/"
                ),
                mock.patch.object(tiktok_post, "PKCE_FILE", pkce_file),
                contextlib.redirect_stdout(output),
            ):
                tiktok_post.cmd_auth_url()

            url = next(
                line for line in output.getvalue().splitlines()
                if line.startswith(tiktok_post.AUTH_URL)
            )
            params = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
            with open(pkce_file, encoding="utf-8") as file:
                saved = json.load(file)

            self.assertEqual(params["code_challenge_method"], ["S256"])
            self.assertEqual(
                params["code_challenge"],
                [hashlib.sha256(saved["verifier"].encode()).hexdigest()],
            )
            self.assertEqual(params["state"], [saved["state"]])


if __name__ == "__main__":
    unittest.main()
