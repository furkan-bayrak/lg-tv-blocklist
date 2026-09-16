#!/usr/bin/env python3
"""Test suite for verify.py. Run: python scripts/test_verify.py (stdlib only).

Deliberately offline: verify.py's judgement lives in classify(), which is a
pure function over a DoH payload, so the logic that decides "this entry is
dead" is tested without a network round-trip. Nothing here makes a request.
"""
import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import verify  # noqa: E402  (after sys.path fix)


class TestClassify(unittest.TestCase):
    def test_nxdomain(self):
        cls, detail = verify.classify({"Status": 3})
        self.assertEqual(cls, verify.NXDOMAIN)
        self.assertIn("does not exist", detail)

    def test_live_returns_first_a_record(self):
        cls, detail = verify.classify({
            "Status": 0,
            "Answer": [{"type": 5, "data": "cname.example"},
                       {"type": 1, "data": "52.30.34.160"},
                       {"type": 1, "data": "10.0.0.1"}],
        })
        self.assertEqual(cls, verify.LIVE)
        self.assertEqual(detail, "52.30.34.160")

    def test_noerror_without_a_record_is_not_dead(self):
        # A delegated apex (lgtvsdp.com is SOA-only) answers NOERROR with no A.
        # Calling that NXDOMAIN would wrongly condemn a deliberately blocked zone.
        for payload in ({"Status": 0},
                        {"Status": 0, "Answer": []},
                        {"Status": 0, "Answer": [{"type": 6, "data": "soa..."}]},
                        {"Status": 0, "Answer": [{"type": 5, "data": "cname.only"}]}):
            with self.subTest(payload=payload):
                cls, _ = verify.classify(payload)
                self.assertEqual(cls, verify.NO_A)
                self.assertNotEqual(cls, verify.NXDOMAIN)

    def test_other_rcodes_are_errors_not_verdicts(self):
        # SERVFAIL/REFUSED say nothing about existence -- never treat as dead.
        for status in (1, 2, 5, 9):
            with self.subTest(status=status):
                cls, _ = verify.classify({"Status": status})
                self.assertEqual(cls, verify.ERROR)

    def test_missing_status_is_an_error(self):
        self.assertEqual(verify.classify({})[0], verify.ERROR)


class TestResolveMalformedJson(unittest.TestCase):
    """A captive portal (or a wrong endpoint) can answer with valid JSON that
    is not a DoH object -- e.g. []. That must become an ERROR entry, never an
    uncaught crash that aborts the whole verify run."""

    def resolve_with_body(self, body: bytes):
        resp = mock.MagicMock()
        resp.read.return_value = body
        resp.__enter__.return_value = resp
        with mock.patch.object(verify.urllib.request, "urlopen", return_value=resp):
            return verify.resolve("dead.lge.com")

    def test_non_object_json_becomes_an_error_entry(self):
        for body in (b"[]", b'["a"]', b'"captive portal"', b"42", b"null"):
            with self.subTest(body=body):
                cls, detail = self.resolve_with_body(body)
                self.assertEqual(cls, verify.ERROR)
                self.assertIn("non-object", detail)

    def test_other_malformed_shapes_do_not_abort(self):
        # "Answer" as an object instead of a list raises AttributeError inside
        # classify(); the resolve() backstop must classify it, not propagate.
        cls, _ = self.resolve_with_body(b'{"Status": 0, "Answer": {"type": 1}}')
        self.assertEqual(cls, verify.ERROR)

    def test_normal_payload_still_classified(self):
        cls, detail = self.resolve_with_body(b'{"Status": 3}')
        self.assertEqual(cls, verify.NXDOMAIN)
        self.assertIn("does not exist", detail)


class TestReadEntries(unittest.TestCase):
    def parse(self, text):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "list.txt"
            p.write_text(text, encoding="utf-8")
            return verify.read_entries(p)

    def test_skips_comments_and_blanks(self):
        self.assertEqual(
            self.parse("# Title: x\n\nsnu.lge.com\n! adblock comment\n"),
            ["snu.lge.com"])

    def test_accepts_all_three_built_formats(self):
        for text in ("snu.lge.com\n", "0.0.0.0 snu.lge.com\n", "||snu.lge.com^\n"):
            with self.subTest(text=text):
                self.assertEqual(self.parse(text), ["snu.lge.com"])

    def test_dedupes_and_sorts(self):
        self.assertEqual(self.parse("b.lge.com\na.lge.com\nb.lge.com\n"),
                         ["a.lge.com", "b.lge.com"])


class TestRender(unittest.TestCase):
    def test_report_states_counts_and_lists_dead_names(self):
        out = verify.render({
            "live.lge.com": (verify.LIVE, "1.2.3.4"),
            "apex.lge.com": (verify.NO_A, "no A record"),
            "dead.lge.com": (verify.NXDOMAIN, "name does not exist"),
        }, cross_check=True)
        self.assertIn("| LIVE | 1 |", out)
        self.assertIn("| NXDOMAIN | 1 |", out)
        self.assertIn("`dead.lge.com`", out)
        self.assertIn("confirmed on a second provider", out)
        # A NO_A apex must not be presented as a problem to fix.
        self.assertIn("Not dead", out)

    def test_empty_buckets_are_omitted(self):
        out = verify.render({"live.lge.com": (verify.LIVE, "1.2.3.4")}, cross_check=False)
        self.assertNotIn("## NXDOMAIN", out)
        self.assertIn("--cross-check", out)


class TestMainExitCodes(unittest.TestCase):
    """main()'s exit-code contract: 0 clean, 1 dead with --fail-on-dead, 2 bad input."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.list_file = Path(tmp.name) / "list.txt"
        self.list_file.write_text("live.lge.com\n", encoding="utf-8")

    def run_main(self, argv, results):
        with mock.patch.object(verify, "verify", return_value=results), \
             contextlib.redirect_stdout(io.StringIO()), \
             contextlib.redirect_stderr(io.StringIO()):
            return verify.main(argv)

    def test_exit_zero_when_nothing_dead(self):
        rc = self.run_main(["--file", str(self.list_file)],
                           {"live.lge.com": (verify.LIVE, "1.2.3.4")})
        self.assertEqual(rc, 0)

    def test_fail_on_dead_exits_one(self):
        rc = self.run_main(["--file", str(self.list_file), "--fail-on-dead"],
                           {"dead.lge.com": (verify.NXDOMAIN, "name does not exist")})
        self.assertEqual(rc, 1)

    def test_refuses_out_inside_lists_dir(self):
        rc = self.run_main(["--file", str(self.list_file), "--out",
                            str(verify.ROOT / "lists" / "strict-domains.txt")], {})
        self.assertEqual(rc, 2)

    def test_refuses_out_equal_to_input(self):
        rc = self.run_main(["--file", str(self.list_file), "--out",
                            str(self.list_file)], {})
        self.assertEqual(rc, 2)

    def test_workers_zero_is_a_clean_argparse_error(self):
        with contextlib.redirect_stderr(io.StringIO()), \
             self.assertRaises(SystemExit) as caught:
            verify.main(["--file", str(self.list_file), "--workers", "0"])
        self.assertEqual(caught.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
