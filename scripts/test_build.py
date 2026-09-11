#!/usr/bin/env python3
"""Test suite for build.py. Run: python scripts/test_build.py (stdlib only)."""
import io
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build  # noqa: E402  (after sys.path fix)


class TestParseSrc(unittest.TestCase):
    def setUp(self):
        self.orig_src = build.SRC
        build.SRC = Path(tempfile.mkdtemp())

    def tearDown(self):
        build.SRC = self.orig_src

    def write(self, name, text):
        p = build.SRC / name
        p.write_text(text, encoding="utf-8")

    def test_annotations_and_comments_stripped(self):
        self.write("safe.txt", (
            "# comment line\n"
            "snu.lge.com # STRICT: OTA\n"
            "\n"
            "LGSMARTAD.com # caps lowered, comment stripped\n"
        ))
        self.assertEqual(build.parse_src("safe.txt"), ["lgsmartad.com", "snu.lge.com"])

    def test_new_lg_apexes_accepted(self):
        # lggalleryplus.com / lgsmartweb.com allowlisted 2026-09-11.
        self.write("strict.txt", (
            "lggalleryplus.com # STRICT: weak\n"
            "lgsmartweb.com # STRICT: weak\n"
        ))
        self.assertEqual(build.parse_src("strict.txt"),
                         ["lggalleryplus.com", "lgsmartweb.com"])

    def test_malformed_rejected(self):
        self.write("safe.txt", "not a hostname!! # nope\n")
        with self.assertRaises(ValueError):
            build.parse_src("safe.txt")

    def test_non_lg_rejected(self):
        self.write("safe.txt", "evil.example.com # not LG\n")
        with self.assertRaises(ValueError):
            build.parse_src("safe.txt")

    def test_duplicate_rejected_with_line_numbers(self):
        self.write("safe.txt", "snu.lge.com # one\nsnu.lge.com # two\n")
        with self.assertRaises(ValueError) as ctx:
            build.parse_src("safe.txt")
        self.assertIn("safe.txt:2: duplicate", str(ctx.exception))
        self.assertIn("first at line 1", str(ctx.exception))


class TestCompileTier(unittest.TestCase):
    def test_safe_has_three_formats_no_zones(self):
        out = build.compile_tier("safe", ["a.lge.com"], ["lge.com"])
        self.assertIn("0.0.0.0 a.lge.com", out["safe-hosts.txt"])
        self.assertIn("||a.lge.com^", out["safe-adblock.txt"])
        self.assertIn("a.lge.com", out["safe-domains.txt"])
        body = [l for l in out["safe-domains.txt"].splitlines() if not l.startswith("#")]
        self.assertNotIn("lge.com", body)

    def test_strict_merges_zones_as_apex_and_adblock_zone(self):
        out = build.compile_tier("strict", ["snu.lge.com"], ["lge.com"])
        self.assertIn("0.0.0.0 lge.com", out["strict-hosts.txt"])
        self.assertIn("||lge.com^", out["strict-adblock.txt"])

    def test_headers_shape_and_counts(self):
        out = build.compile_tier("safe", ["a.lge.com", "b.lge.com"], [])
        first = out["safe-domains.txt"].splitlines()
        self.assertEqual(first[0], "# Title: LG TV Blocklist (safe)")
        self.assertEqual(first[2], "# Entries: 2")
        self.assertIn(build.LICENSE_LINE, first)
        self.assertEqual(out["safe-hosts.txt"].splitlines()[5], "0.0.0.0 a.lge.com")


class TestLoadAll(unittest.TestCase):
    def test_strict_overlap_fails(self):
        with tempfile.TemporaryDirectory() as td:
            old = build.SRC
            build.SRC = Path(td)
            try:
                (build.SRC / "safe.txt").write_text("snu.lge.com\n", encoding="utf-8")
                (build.SRC / "strict.txt").write_text("snu.lge.com\n", encoding="utf-8")
                (build.SRC / "zones.txt").write_text("lge.com\n", encoding="utf-8")
                with self.assertRaises(ValueError):
                    build.load_all()
            finally:
                build.SRC = old

    def test_roundtrip_superset_counts(self):
        with tempfile.TemporaryDirectory() as td:
            old = build.SRC
            build.SRC = Path(td)
            try:
                (build.SRC / "safe.txt").write_text("a.lge.com\n", encoding="utf-8")
                (build.SRC / "strict.txt").write_text("snu.lge.com\n", encoding="utf-8")
                (build.SRC / "zones.txt").write_text("lge.com\n", encoding="utf-8")
                safe, delta, zones = build.load_all()
                strict_total = len(set(safe) | set(delta) | set(zones))
                self.assertEqual((safe, delta, zones), (["a.lge.com"], ["snu.lge.com"], ["lge.com"]))
                self.assertEqual(strict_total, 3)
            finally:
                build.SRC = old


class TestDryRunAndCheck(unittest.TestCase):
    def test_check_prints_ok_no_exception(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            build.check()
        self.assertIn("check OK", buf.getvalue())

    def test_check_exit_code_one_on_error(self):
        with tempfile.TemporaryDirectory() as td:
            old = build.SRC
            build.SRC = Path(td)
            try:
                (build.SRC / "safe.txt").write_text("bogus!!\n", encoding="utf-8")
                (build.SRC / "strict.txt").write_text("", encoding="utf-8")
                (build.SRC / "zones.txt").write_text("", encoding="utf-8")
                err = io.StringIO()
                with redirect_stderr(err):
                    rc = build.main(["check"])
                self.assertEqual(rc, 1)
                self.assertIn("ERROR", err.getvalue())
            finally:
                build.SRC = old


if __name__ == "__main__":
    unittest.main()
