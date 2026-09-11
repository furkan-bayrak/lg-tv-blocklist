#!/usr/bin/env python3
"""Test suite for localize.py. Run: python scripts/test_localize.py (stdlib only)."""
import hashlib
import io
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import localize  # noqa: E402  (after sys.path fix)

HEADER = (
    "# Title: LG TV Blocklist (safe)\n"
    "# Updated: 2026-09-09 20:16 UTC\n"
    "# Entries: 3\n"
    "# License: CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/)\n"
    "\n"
)

MARKER_FR = ("# Localized: fr \u2014 regional endpoints are NOT audited for this region; "
             "verify before use.")

REGION_HOSTS = (
    "de.nextlgsdp.com",
    "de.info.lgsmartad.com",
    "de.emp.lgsmartplatform.com",
    "us.lgtvsdp.com",
    "de.lgeapi.com",
    "de.ibs.nextlgsdp.com",
)

# Two-letter labels that look like region prefixes but are not (recon-verified).
FALSE_POSITIVES = ("su.lge.com", "ad.lgappstv.com", "am.lge.com", "ig.lge.com")

ALL_FILES = (
    "safe-adblock.txt",
    "safe-domains.txt",
    "safe-hosts.txt",
    "strict-adblock.txt",
    "strict-domains.txt",
    "strict-hosts.txt",
)


def make_lists_dir(parent, entries=()):
    """Create the six built list files in parent; return the parent Path."""
    d = Path(parent)
    d.mkdir(parents=True, exist_ok=True)
    body = "".join(f"{e}\n" for e in entries)
    for name in ALL_FILES:
        (d / name).write_text(HEADER + body, encoding="utf-8")
    return d


class TestRewriteContent(unittest.TestCase):
    def test_rewrites_in_all_three_formats(self):
        cases = (
            ("de.nextlgsdp.com", "fr.nextlgsdp.com"),
            ("0.0.0.0 de.nextlgsdp.com", "0.0.0.0 fr.nextlgsdp.com"),
            ("||de.nextlgsdp.com^", "||fr.nextlgsdp.com^"),
        )
        for raw, want in cases:
            with self.subTest(raw=raw):
                out, count = localize.rewrite_content(HEADER + raw + "\n", "fr")
                self.assertEqual(count, 1)
                self.assertEqual(out.splitlines()[-1], want)

    def test_non_region_two_letter_labels_untouched(self):
        text = HEADER + "".join(f"{h}\n" for h in FALSE_POSITIVES)
        out, count = localize.rewrite_content(text, "fr")
        self.assertEqual(count, 0)
        entries = [l for l in out.splitlines() if l and not l.startswith("#")]
        self.assertEqual(entries, list(FALSE_POSITIVES))

    def test_header_marker_added_and_entries_line_unchanged(self):
        out, _ = localize.rewrite_content(HEADER + "de.nextlgsdp.com\n", "fr")
        lines = out.splitlines()
        self.assertEqual(lines[4], MARKER_FR)
        self.assertEqual(lines[5], "")
        self.assertEqual(lines[6], "fr.nextlgsdp.com")
        self.assertIn("# Entries: 3", out)
        self.assertEqual(out.count("# Localized:"), 1)

    def test_all_known_region_hostnames_rewritten(self):
        text = "".join(f"{h}\n" for h in REGION_HOSTS)
        out, count = localize.rewrite_content(text, "fr")
        self.assertEqual(count, 6)
        for host in REGION_HOSTS:
            want = "fr." + host.split(".", 1)[1]
            self.assertIn(want + "\n", out)
            self.assertNotIn(host + "\n", out)

    def test_target_equal_to_source_label_is_noop(self):
        text = HEADER + "de.nextlgsdp.com\n"
        out, count = localize.rewrite_content(text, "de")
        self.assertEqual(count, 0)
        self.assertIn("de.nextlgsdp.com\n", out)
        self.assertEqual(out.count("# Localized: de"), 1)


class TestCli(unittest.TestCase):
    def test_invalid_region_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out"
            for bad in ("USA", "u1", ""):
                with self.subTest(region=bad):
                    err = io.StringIO()
                    with redirect_stderr(err):
                        rc = localize.main(["--region", bad, "--out", str(out)])
                    self.assertEqual(rc, 2)
                    self.assertIn("region", err.getvalue().lower())
            self.assertFalse(out.exists())

    def test_missing_lists_dir_exits_2(self):
        with tempfile.TemporaryDirectory() as td:
            old = localize.LISTS
            localize.LISTS = Path(td) / "missing"
            try:
                err = io.StringIO()
                with redirect_stderr(err):
                    rc = localize.main(["--region", "fr", "--out", str(Path(td) / "out")])
                self.assertEqual(rc, 2)
                self.assertIn("lists", err.getvalue())
            finally:
                localize.LISTS = old


class TestLocalizeFiles(unittest.TestCase):
    def test_output_sha256sums_match_written_files(self):
        with tempfile.TemporaryDirectory() as td:
            src = make_lists_dir(Path(td) / "lists", entries=REGION_HOSTS)
            out = Path(td) / "out"
            counts = localize.localize(src, out, "fr")
            self.assertEqual(sorted(counts), sorted(ALL_FILES))
            sums = (out / "SHA256SUMS").read_text(encoding="utf-8")
            lines = sums.splitlines()
            self.assertEqual(len(lines), 6)
            names = []
            for line in lines:
                self.assertRegex(line, r"^[0-9a-f]{64}  [^ ]+$")
                digest, name = line.split("  ", 1)
                names.append(name)
                self.assertEqual(digest, hashlib.sha256((out / name).read_bytes()).hexdigest())
            self.assertEqual(names, sorted(ALL_FILES))
            self.assertTrue(sums.endswith("\n"))

    def test_refuses_to_write_into_source_lists_dir(self):
        with tempfile.TemporaryDirectory() as td:
            src = make_lists_dir(td, entries=("de.nextlgsdp.com",))
            before = (src / "safe-domains.txt").read_text(encoding="utf-8")
            with self.assertRaises(ValueError):
                localize.localize(src, src, "fr")
            self.assertEqual((src / "safe-domains.txt").read_text(encoding="utf-8"), before)


if __name__ == "__main__":
    unittest.main()
