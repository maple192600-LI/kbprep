"""Lock real YouTube inventory fixtures as version-controlled evidence.

Fixtures:
- inventory_multi_lang.json: REAL recording from yt-dlp --dump-single-json for the
  owner-designated test video CAQ2pfhoPcs, processed through the project's
  _youtube_inventory_evidence. Captures the real automatic-caption language set.
- inventory_no_subtitle.json: derived from the real yt-dlp payload structure with
  subtitle fields emptied, representing videos yt-dlp returns with no captions
  (the no-subtitle case that triggers media fallback).

YouTube caption language sets drift over time; the multi-lang hash locks the recorded
snapshot so any silent change fails CI until the fixture is regenerated deliberately.
"""

import hashlib
import json
import unittest
from pathlib import Path

FIXTURE_DIR = Path(__file__).parent / "golden" / "formats" / "youtube"
MULTI_LANG_FIXTURE = FIXTURE_DIR / "inventory_multi_lang.json"
NO_SUBTITLE_FIXTURE = FIXTURE_DIR / "inventory_no_subtitle.json"

MULTI_LANG_SHA256 = "275588e8220c46d89224a7bf3c0bee68c17bf0a3030d940b2e3ada439faee384"
NO_SUBTITLE_SHA256 = "9fc83fa4e93ae5a6c6c4867fdfc4cc9d034046feebd2d4aab1f92ccc75b46d92"

SCHEMA = "kbprep.youtube_subtitle_inventory_evidence.v1"


class YoutubeInventoryFixtureTests(unittest.TestCase):
    def test_multi_lang_inventory_fixture_is_real_and_hash_locked(self) -> None:
        """Lock the real yt-dlp inventory recording for CAQ2pfhoPcs (157 auto-caption languages).

        Recorded via yt-dlp --dump-single-json --skip-download for the owner-designated
        test video, then processed through the project's _youtube_inventory_evidence.
        YouTube caption language sets drift, so the hash locks this snapshot; drift
        fails CI until the fixture is regenerated deliberately.
        """
        self.assertTrue(MULTI_LANG_FIXTURE.exists())
        data = json.loads(MULTI_LANG_FIXTURE.read_text(encoding="utf-8"))
        self.assertEqual(data["schema"], SCHEMA)
        self.assertEqual(data["id"], "CAQ2pfhoPcs")
        self.assertEqual(data["subtitle_languages"], [])
        auto = data["automatic_caption_languages"]
        self.assertGreater(len(auto), 100)
        self.assertIn("en", auto)
        self.assertIn("zh-Hans", auto)
        self.assertIn("zh-Hant", auto)
        actual_hash = hashlib.sha256(MULTI_LANG_FIXTURE.read_bytes()).hexdigest()
        self.assertEqual(
            actual_hash,
            MULTI_LANG_SHA256,
            "multi-lang inventory fixture drifted; regenerate via yt-dlp and update MULTI_LANG_SHA256",
        )

    def test_no_subtitle_inventory_fixture_is_hash_locked(self) -> None:
        """Lock the no-subtitle inventory form (derived from the real yt-dlp payload structure).

        Represents videos yt-dlp returns with empty subtitles and automatic_captions,
        which is the no-subtitle case that triggers media fallback. The form mirrors the
        real yt-dlp inventory evidence schema with subtitle fields emptied.
        """
        self.assertTrue(NO_SUBTITLE_FIXTURE.exists())
        data = json.loads(NO_SUBTITLE_FIXTURE.read_text(encoding="utf-8"))
        self.assertEqual(data["schema"], SCHEMA)
        self.assertEqual(data["subtitle_languages"], [])
        self.assertEqual(data["automatic_caption_languages"], [])
        actual_hash = hashlib.sha256(NO_SUBTITLE_FIXTURE.read_bytes()).hexdigest()
        self.assertEqual(
            actual_hash,
            NO_SUBTITLE_SHA256,
            "no-subtitle inventory fixture drifted; regenerate and update NO_SUBTITLE_SHA256",
        )


if __name__ == "__main__":
    unittest.main()
