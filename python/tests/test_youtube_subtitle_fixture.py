"""Lock the real YouTube subtitle fixture as version-controlled evidence."""

import hashlib
import unittest
from pathlib import Path

FIXTURE = Path(__file__).parent / "golden" / "formats" / "youtube" / "subtitle_en_caQ2pfhoPcs.txt"
FIXTURE_SHA256 = "17c779ec130acef5799f9f41caa5378f97bde4d1ccd72c157d3f0683fda2db38"


class YoutubeSubtitleFixtureTests(unittest.TestCase):
    def test_real_youtube_subtitle_fixture_is_version_controlled(self) -> None:
        """Lock the real YouTube subtitle fixture (video CAQ2pfhoPcs, en) as evidence.

        The fixture was produced by downloading auto subtitles via yt-dlp (the project
        wrapper's YouTube subtitle tool) for the owner-designated test video, then
        stripping WebVTT timing and cue tags. It is an evidence snapshot, not a
        deterministic re-run target: YouTube subtitle availability and exact text can
        vary, so this test asserts the fixture exists and is a reasonable English
        transcript rather than re-downloading.
        """
        self.assertTrue(FIXTURE.exists(), f"youtube subtitle fixture missing: {FIXTURE}")
        text = FIXTURE.read_text(encoding="utf-8").strip()
        self.assertGreater(len(text), 200)
        self.assertLess(len(text), 5000)
        self.assertRegex(text, r"[A-Za-z]")

    def test_real_youtube_subtitle_fixture_hash_is_locked(self) -> None:
        """Content-hash lock that catches silent fixture drift in CI."""
        self.assertTrue(FIXTURE.exists(), f"youtube subtitle fixture missing: {FIXTURE}")
        actual = hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
        self.assertEqual(
            actual,
            FIXTURE_SHA256,
            "youtube subtitle fixture content drifted from the locked snapshot; regenerate "
            "it deliberately and update FIXTURE_SHA256",
        )


if __name__ == "__main__":
    unittest.main()
