"""Timeline presentation tests: real waveform peaks (FFmpeg-decoded,
never invented), and the original-app timeline markers in the UI."""
import os
import re
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
WINDOWS = os.path.dirname(HERE)
sys.path.insert(0, WINDOWS)

from vibeedit_core.waveform import waveform_peaks  # noqa: E402


def read(rel):
    with open(os.path.join(WINDOWS, rel), encoding="utf-8") as fh:
        return fh.read()


def make_wav(path, freq=440.0, seconds=1.0, volume=0.5):
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "lavfi",
         "-i", f"sine=frequency={freq}:duration={seconds}",
         "-af", f"volume={volume}", path],
        check=True)


class TestWaveform(unittest.TestCase):
    def test_sine_peaks_are_real_and_normalised(self):
        with tempfile.TemporaryDirectory() as td:
            wav = os.path.join(td, "tone.wav")
            make_wav(wav)
            peaks = waveform_peaks(wav, buckets=32)
            self.assertEqual(len(peaks), 32)
            self.assertTrue(all(0.0 <= p <= 1.0 for p in peaks))
            self.assertGreater(max(peaks), 0.5)

    def test_silence_is_all_zero(self):
        with tempfile.TemporaryDirectory() as td:
            wav = os.path.join(td, "silence.wav")
            subprocess.run(
                ["ffmpeg", "-v", "error", "-y", "-f", "lavfi",
                 "-i", "anullsrc=r=11025:cl=mono", "-t", "1", wav],
                check=True)
            self.assertEqual(waveform_peaks(wav, buckets=16), [0.0] * 16)

    def test_missing_file_raises_not_fakes(self):
        with self.assertRaises(FileNotFoundError):
            waveform_peaks("/nonexistent/nope.wav")


class TestTimelinePresentation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = read("static/index.html")
        cls.js = read("static/app.js")
        cls.css = read("static/style.css")

    def test_red_playhead_and_time_ruler(self):
        self.assertIn("#ef4444", self.css)
        self.assertIn("ruler-tick", self.js)
        self.assertIn("ruler-tick", self.css)

    def test_main_clip_filename_and_duration(self):
        self.assertIn("baseName", self.js)
        self.assertIn("toFixed(1)", self.js)

    def test_captions_word_chips(self):
        self.assertIn("word-chip", self.js)
        self.assertIn("word-chip", self.css)
        self.assertIn("karaoke", self.js)

    def test_waveform_strip_from_real_api(self):
        self.assertIn("/api/waveform", self.js)
        self.assertIn("wave-strip", self.js)
        self.assertIn("wave-bar", self.css)

    def test_capabilities_panel_is_honest(self):
        for marker in ("timeline-capabilities", "Not yet in this Windows port",
                       "voice cloning", "VieNeu TTS", "silence cutting",
                       "in-app LLM chat generation",
                       "no strip is drawn rather than a fake shape"):
            self.assertIn(marker, self.html, marker)


if __name__ == "__main__":
    unittest.main()
