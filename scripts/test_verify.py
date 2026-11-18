#!/usr/bin/env python3
"""Test suite for verify.py. Run: python scripts/test_verify.py (stdlib only).

Deliberately offline: classify() consumes DoH payloads, and orchestration tests
mock resolve() to exercise provider agreement, disagreement, and failures.
Nothing here makes a request.
"""
import contextlib
import http.client
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
        # Empty, SOA-only, and CNAME-only answers all lack an A record.
        # None alone establishes delegation, retirement, or AAAA reachability.
        for payload in ({"Status": 0},
                        {"Status": 0, "Answer": []},
                        {"Status": 0, "Answer": None},
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

    def test_status_must_be_an_actual_integer(self):
        self.assertEqual(verify.classify({})[0], verify.ERROR)
        for status in (False, 0.0, 3.0, "3", None):
            with self.subTest(status=status):
                self.assertEqual(verify.classify({"Status": status})[0], verify.ERROR)

    def test_malformed_answer_shapes_are_errors(self):
        for answers in ({}, "", False, 0, [1], [{}], [{"type": True}],
                        [{"type": 1.0}], [{"type": "1"}]):
            with self.subTest(answers=answers):
                self.assertEqual(verify.classify({"Status": 0, "Answer": answers})[0],
                                 verify.ERROR)

    def test_one_bad_a_record_invalidates_even_an_answer_with_a_valid_address(self):
        good = {"type": 1, "data": "192.0.2.1"}
        bad_records = [{"type": 1}] + [
            {"type": 1, "data": value} for value in (None, 123, "not an IP", "", "2001:db8::1")
        ]
        for bad in bad_records:
            with self.subTest(bad=bad):
                self.assertEqual(verify.classify({"Status": 0, "Answer": [good, bad]})[0],
                                 verify.ERROR)


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
        # Non-list Answer sections are inconclusive, not NO_A or crashes.
        cls, _ = self.resolve_with_body(b'{"Status": 0, "Answer": {"type": 1}}')
        self.assertEqual(cls, verify.ERROR)

    def test_normal_payload_still_classified(self):
        cls, detail = self.resolve_with_body(b'{"Status": 3}')
        self.assertEqual(cls, verify.NXDOMAIN)
        self.assertIn("does not exist", detail)

    def test_truncated_http_body_becomes_an_error_entry(self):
        resp = mock.MagicMock()
        resp.__enter__.return_value = resp
        resp.read.side_effect = http.client.IncompleteRead(b"{")
        with mock.patch.object(verify.urllib.request, "urlopen", return_value=resp):
            cls, detail = verify.resolve("example.com")
        self.assertEqual(cls, verify.ERROR)
        self.assertIn("IncompleteRead", detail)


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

    def test_accepts_all_four_built_formats(self):
        for text in ("snu.lge.com\n", "0.0.0.0 snu.lge.com\n", "||snu.lge.com^\n",
                     "address=/snu.lge.com/#\n"):
            with self.subTest(text=text):
                self.assertEqual(self.parse(text), ["snu.lge.com"])

    def test_dnsmasq_lines_parse_to_the_domain_between_the_slashes(self):
        # Without this parse the whole rule ("address=/name/#") would be
        # resolved as if it were a hostname and every entry would report ERROR.
        for target in ("#", "0.0.0.0"):
            text = (f"address=/snu.lge.com/{target}\n"
                    f"address=/de.lgeapi.com/{target}\n")
            with self.subTest(target=target):
                self.assertEqual(self.parse(text), ["de.lgeapi.com", "snu.lge.com"])

    def test_dedupes_and_sorts(self):
        self.assertEqual(self.parse("b.lge.com\na.lge.com\nb.lge.com\n"),
                         ["a.lge.com", "b.lge.com"])


class TestVerifyOrchestration(unittest.TestCase):
    def cross_check(self, first, second):
        outcomes = {
            ("candidate.lge.com", "google"): first,
            ("candidate.lge.com", "cloudflare"): second,
        }
        with mock.patch.object(verify, "resolve",
                               side_effect=lambda name, provider: outcomes[name, provider]) as resolve:
            results = verify.verify(["candidate.lge.com"], workers=2, cross_check=True)
        self.assertCountEqual(resolve.call_args_list, [
            mock.call("candidate.lge.com", "google"),
            mock.call("candidate.lge.com", "cloudflare"),
        ])
        return results

    def assert_provider_diagnostics(self, results, first, second):
        detail = results["candidate.lge.com"][1]
        out = verify.render(results, cross_check=True)
        entry = next(line for line in out.splitlines()
                     if line.startswith("- `candidate.lge.com`"))
        for provider, (classification, diagnostic) in (("google", first),
                                                       ("cloudflare", second)):
            with self.subTest(provider=provider):
                self.assertIn(f"{provider}={classification}", detail)
                self.assertIn(diagnostic, detail)
                self.assertIn(f"{provider}={classification}", entry)
                self.assertIn(diagnostic, entry)

    def test_agreement_keeps_classification_and_both_diagnostics(self):
        for classification in (verify.NO_A, verify.NXDOMAIN):
            with self.subTest(classification=classification):
                first = (classification, "primary evidence")
                second = (classification, "secondary evidence")
                results = self.cross_check(first, second)
                self.assertEqual(results["candidate.lge.com"][0], classification)
                self.assert_provider_diagnostics(results, first, second)

    def test_disagreement_and_single_provider_failure_are_inconclusive(self):
        for first_class, second_class in (
            (verify.NXDOMAIN, verify.LIVE),
            (verify.NO_A, verify.NXDOMAIN),
            (verify.ERROR, verify.NXDOMAIN),
            (verify.NO_A, verify.ERROR),
        ):
            with self.subTest(first=first_class, second=second_class):
                first = (first_class, "primary diagnostic")
                second = (second_class, "secondary diagnostic")
                results = self.cross_check(first, second)
                self.assertEqual(results["candidate.lge.com"][0], verify.ERROR)
                self.assert_provider_diagnostics(results, first, second)

    def test_both_provider_failures_keep_both_errors(self):
        first = (verify.ERROR, "TimeoutError: primary timed out")
        second = (verify.ERROR, "rcode 2")
        results = self.cross_check(first, second)
        self.assertEqual(results["candidate.lge.com"][0], verify.ERROR)
        self.assert_provider_diagnostics(results, first, second)

    def test_live_skips_second_provider_while_non_live_is_checked(self):
        outcomes = {
            ("live.lge.com", "google"): (verify.LIVE, "192.0.2.1"),
            ("candidate.lge.com", "google"): (verify.NO_A, "primary no A"),
            ("candidate.lge.com", "cloudflare"): (verify.NO_A, "secondary no A"),
        }
        with mock.patch.object(verify, "resolve",
                               side_effect=lambda name, provider: outcomes[name, provider]) as resolve:
            results = verify.verify(["live.lge.com", "candidate.lge.com"],
                                    workers=2, cross_check=True)
        self.assertEqual(results["live.lge.com"], (verify.LIVE, "192.0.2.1"))
        self.assertEqual(results["candidate.lge.com"][0], verify.NO_A)
        self.assertCountEqual(resolve.call_args_list, [
            mock.call("live.lge.com", "google"),
            mock.call("candidate.lge.com", "google"),
            mock.call("candidate.lge.com", "cloudflare"),
        ])

    def test_without_cross_check_preserves_primary_result(self):
        first = (verify.ERROR, "TimeoutError: primary timed out")
        with mock.patch.object(verify, "resolve", return_value=first) as resolve:
            results = verify.verify(["candidate.lge.com"], workers=1, cross_check=False)
        self.assertEqual(results, {"candidate.lge.com": first})
        resolve.assert_called_once_with("candidate.lge.com", "google")


class TestRender(unittest.TestCase):
    def test_report_states_counts_and_lists_dead_names(self):
        out = verify.render({
            "live.lge.com": (verify.LIVE, "1.2.3.4"),
            "cname.lge.com": verify.classify({
                "Status": 0, "Answer": [{"type": 5, "data": "target.example"}],
            }),
            "dead.lge.com": (verify.NXDOMAIN, "name does not exist"),
        }, cross_check=True)
        self.assertIn("| LIVE | 1 |", out)
        self.assertIn("| NXDOMAIN | 1 |", out)
        self.assertIn("`dead.lge.com`", out)
        self.assertIn("| NO_A | 1 |", out)
        self.assertIn("`cname.lge.com`", out)
        self.assertIn("NOERROR", out)
        self.assertIn("A-only", out)
        self.assertIn("AAAA", out)
        self.assertIn("TV routing", out)
        self.assertIn("TV caches", out)
        self.assertIn("attempted", out)
        self.assertIn("non-LIVE", out)
        self.assertNotIn("confirmed", out)
        self.assertNotIn("No action needed", out)
        self.assertNotIn("Delegated apexes", out)
        self.assertNotIn("decommissioned", out)

    def test_error_diagnostic_is_rendered_beside_domain(self):
        out = verify.render({
            "error.lge.com": (verify.ERROR, "TimeoutError: provider unavailable"),
        }, cross_check=False)
        entry = next(line for line in out.splitlines()
                     if line.startswith("- `error.lge.com`"))
        self.assertIn("TimeoutError: provider unavailable", entry)

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

    def test_fail_on_dead_does_not_fail_for_no_a_or_errors(self):
        rc = self.run_main(["--file", str(self.list_file), "--fail-on-dead"],
                           {"no-a.lge.com": (verify.NO_A, "NOERROR without an A record"),
                            "error.lge.com": (verify.ERROR, "rcode 2")})
        self.assertEqual(rc, 0)

    def test_unreadable_or_invalid_utf8_inputs_fail_before_dns(self):
        invalid = self.list_file.with_name("invalid.txt")
        invalid.write_bytes(b"example.com\n\xff")
        for path, read_error in ((invalid, None), (self.list_file, PermissionError("denied"))):
            with self.subTest(path=path), contextlib.ExitStack() as stack:
                if read_error:
                    stack.enter_context(mock.patch.object(Path, "read_text", side_effect=read_error))
                check = stack.enter_context(mock.patch.object(verify, "verify"))
                err = stack.enter_context(contextlib.redirect_stderr(io.StringIO()))
                self.assertEqual(verify.main(["--file", str(path)]), 2)
                self.assertIn(f"ERROR: cannot read {path}", err.getvalue())
                check.assert_not_called()

    def test_report_write_failure_is_a_config_error(self):
        directory = self.list_file.parent / "report.md"
        directory.mkdir()
        err = io.StringIO()
        with mock.patch.object(verify, "verify", return_value={
                "live.lge.com": (verify.LIVE, "192.0.2.1"),
        }), contextlib.redirect_stderr(err):
            code = verify.main(["--file", str(self.list_file), "--out", str(directory)])
        self.assertEqual(code, 2)
        self.assertIn(f"ERROR: cannot write {directory}", err.getvalue())
        self.assertNotIn("wrote", err.getvalue())

    def test_help_states_a_only_and_non_live_cross_check_without_lookup(self):
        stdout = io.StringIO()
        with mock.patch.object(verify, "verify") as run_verify, \
             contextlib.redirect_stdout(stdout), \
             self.assertRaises(SystemExit) as caught:
            verify.main(["--help"])
        self.assertEqual(caught.exception.code, 0)
        run_verify.assert_not_called()
        help_text = " ".join(stdout.getvalue().split())
        for limit in ("A-only", "AAAA", "non-LIVE", "TV routing", "TV caches"):
            self.assertIn(limit, help_text)

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
