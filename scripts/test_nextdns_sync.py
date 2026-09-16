#!/usr/bin/env python3
"""Test suite for nextdns_sync.py. Run: python scripts/test_nextdns_sync.py
(stdlib only).

Deliberately offline: api_request() is the single network gate, and every
test either mocks it or pins a pure function, so nothing here opens a socket.
The mocks assert the wire contract from the official API docs: GET to list,
POST {"id": domain} to add, X-Api-Key auth, and a 200-with-errors body
treated as failure (the docs' documented way of rejecting a domain).
"""
import contextlib
import email.message
import http.client
import io
import json
import os
import sys
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import nextdns_sync  # noqa: E402  (after sys.path fix)

TEST_KEY = "test-key-do-not-log"


def http_error(code, body=b"{}", headers=None):
    """An HTTPError with a readable body, as urllib raises it."""
    hdrs = email.message.Message()
    for key, value in (headers or {}).items():
        hdrs[key] = value
    return urllib.error.HTTPError(
        "https://api.nextdns.io/profiles/x/denylist", code, "server error",
        hdrs, io.BytesIO(body))


def write_list(path, text):
    path.write_text(text, encoding="utf-8")
    return path


class TestIsDomain(unittest.TestCase):
    def test_accepts_plausible_domains(self):
        for name in ("snu.lge.com", "a-b.c-d.example", "1.2.example.com",
                     "de.emp.lgsmartplatform.com"):
            self.assertTrue(nextdns_sync.is_domain(name), name)

    def test_rejects_junk(self):
        for name in ("", "localhost", ".com", "a..b.com", "-a.com", "a-.com",
                     "a_b.com", "a b.com", "http://x.com", "*.lgtvcommon.com",
                     "a" * 64 + ".com", ("x" * 63 + ".") * 5 + "com"):
            self.assertFalse(nextdns_sync.is_domain(name), name)


class TestParseEntries(unittest.TestCase):
    def test_skips_comments_and_blanks_and_unwraps_built_formats(self):
        domains, skipped = nextdns_sync.parse_entries(
            "# Title: x\n"
            "\n"
            "snu.lge.com\n"
            "! adblock comment\n"
            "0.0.0.0 eic.lgtviot.com\n"
            "||lgsmartad.com^\n")
        self.assertEqual(domains, ["snu.lge.com", "eic.lgtviot.com", "lgsmartad.com"])
        self.assertEqual(skipped, [])

    def test_lowercases_and_keeps_file_order(self):
        domains, _ = nextdns_sync.parse_entries("B.Lge.COM\na.lge.com\n")
        self.assertEqual(domains, ["b.lge.com", "a.lge.com"])

    def test_bad_lines_are_skipped_with_line_numbers_and_reasons(self):
        domains, skipped = nextdns_sync.parse_entries(
            "good.lge.com\n"
            "*.lgtvcommon.com\n"
            "not a domain at all\n"
            "^[a-z]{2}\\.nextlgsdp\\.com$\n")
        self.assertEqual(domains, ["good.lge.com"])
        self.assertEqual([s[0] for s in skipped], [2, 3, 4])
        self.assertTrue(all(s[2] == "not a domain name" for s in skipped))

    def test_duplicate_lines_are_skipped_not_returned_twice(self):
        domains, skipped = nextdns_sync.parse_entries("dup.lge.com\ndup.lge.com\n")
        self.assertEqual(domains, ["dup.lge.com"])
        self.assertEqual(len(skipped), 1)
        self.assertIn("duplicate", skipped[0][2])

    def test_unicode_and_underscore_labels_are_rejected(self):
        domains, skipped = nextdns_sync.parse_entries("a_b.lge.com\ncaf\u00e9.lge.com\n")
        self.assertEqual(domains, [])
        self.assertEqual(len(skipped), 2)


class TestErrorHelpers(unittest.TestCase):
    def test_api_error_detail_prefers_detail_then_code(self):
        self.assertEqual(
            nextdns_sync.api_error_detail(
                {"errors": [{"code": "invalid", "detail": "\"foo\" is not a domain"}]}),
            "\"foo\" is not a domain")
        self.assertEqual(
            nextdns_sync.api_error_detail({"errors": [{"code": "invalid"}]}),
            "invalid")

    def test_api_error_detail_none_when_absent(self):
        for payload in ({}, {"errors": []}, None, "not a dict", {"errors": ""}):
            self.assertIsNone(nextdns_sync.api_error_detail(payload), payload)

    def test_http_error_text_surfaces_the_api_errors_body(self):
        body = json.dumps({"errors": [{"detail": "nope"}]}).encode()
        with contextlib.closing(http_error(400, body)) as exc:
            self.assertEqual(nextdns_sync.http_error_text(exc), "HTTP 400: nope")
        with contextlib.closing(http_error(502, b"<html>bad</html>")) as exc:
            self.assertIn("HTTP 502", nextdns_sync.http_error_text(exc))

    def test_retry_after_numeric_header_wins(self):
        with contextlib.closing(http_error(429, headers={"Retry-After": "7"})) as exc:
            self.assertEqual(nextdns_sync.retry_after_seconds(exc, 1), 7.0)

    def test_retry_after_date_header_falls_back_to_backoff(self):
        with contextlib.closing(http_error(
                429, headers={"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"})) as exc:
            self.assertEqual(nextdns_sync.retry_after_seconds(exc, 2), 20.0)

    def test_backoff_grows_with_attempt_and_caps_at_60(self):
        with contextlib.closing(http_error(429)) as exc:
            self.assertEqual(nextdns_sync.retry_after_seconds(exc, 1), 10.0)
            self.assertEqual(nextdns_sync.retry_after_seconds(exc, 99), 60.0)


class TestFetchDenylist(unittest.TestCase):
    def test_collects_ids_lowercased_and_follows_the_cursor(self):
        pages = [
            (200, {"data": [{"id": "A.lge.com"}, {"id": "b.lge.com"}],
                   "meta": {"pagination": {"cursor": "next"}}}),
            (200, {"data": [{"id": "c.lge.com", "active": False}],
                   "meta": {"pagination": {"cursor": None}}}),
        ]
        calls = []

        def fake(method, path, **kw):
            calls.append((method, path, kw))
            return pages.pop(0)

        with mock.patch.object(nextdns_sync, "api_request", side_effect=fake):
            ids = nextdns_sync.fetch_denylist("abc123", TEST_KEY, 15.0)
        self.assertEqual(ids, {"a.lge.com": True, "b.lge.com": True,
                               "c.lge.com": False})
        self.assertEqual(calls[0][0], "GET")
        self.assertEqual(calls[0][1], "/profiles/abc123/denylist")
        self.assertEqual(calls[0][2]["key"], TEST_KEY)
        self.assertIn("cursor=next", calls[1][1])
        self.assertEqual(len(calls), 2)

    def test_entries_are_mapped_to_their_active_flag(self):
        # Only an explicit active:false counts as disabled; a missing flag
        # and the tolerated plain-string entry shape stay active.
        payload = (200, {"data": [
            {"id": "on.lge.com", "active": True},
            {"id": "off.lge.com", "active": False},
            {"id": "flagless.lge.com"},
            "plain.lge.com",
        ], "meta": {}})
        with mock.patch.object(nextdns_sync, "api_request",
                               return_value=payload):
            ids = nextdns_sync.fetch_denylist("abc123", TEST_KEY, 15.0)
        self.assertEqual(ids, {"on.lge.com": True, "off.lge.com": False,
                               "flagless.lge.com": True, "plain.lge.com": True})

    def test_a_200_with_errors_is_not_a_denylist(self):
        with mock.patch.object(nextdns_sync, "api_request",
                               return_value=(200, {"errors": [{"detail": "bad key"}]})), \
             self.assertRaises(ValueError):
            nextdns_sync.fetch_denylist("abc123", TEST_KEY, 15.0)

    def test_missing_data_list_raises(self):
        with mock.patch.object(nextdns_sync, "api_request",
                               return_value=(200, {"meta": {}})), \
             self.assertRaises(ValueError):
            nextdns_sync.fetch_denylist("abc123", TEST_KEY, 15.0)

    def test_non_200_raises(self):
        with mock.patch.object(nextdns_sync, "api_request",
                               return_value=(500, None)), \
             self.assertRaises(ValueError):
            nextdns_sync.fetch_denylist("abc123", TEST_KEY, 15.0)


class TestAddDomain(unittest.TestCase):
    def call(self, responses, delay=0.0, max_retries=3):
        """Run add_domain against scripted responses; returns (calls, sleep)."""
        calls = []

        def fake(method, path, **kw):
            calls.append((method, path, kw))
            result = responses.pop(0)
            if isinstance(result, Exception):
                raise result
            return result

        with mock.patch.object(nextdns_sync, "api_request", side_effect=fake), \
             mock.patch.object(nextdns_sync.time, "sleep") as sleep:
            nextdns_sync.add_domain("abc123", "snu.lge.com", TEST_KEY,
                                    timeout=15.0, delay=delay,
                                    max_retries=max_retries)
        return calls, sleep

    def test_posts_the_documented_payload_with_the_key_header(self):
        calls, _ = self.call([(204, None)])
        method, path, kw = calls[0]
        self.assertEqual(method, "POST")
        self.assertEqual(path, "/profiles/abc123/denylist")
        self.assertEqual(kw["body"], {"id": "snu.lge.com"})
        self.assertEqual(kw["key"], TEST_KEY)

    def test_200_with_errors_is_a_rejection_not_a_success(self):
        body = {"errors": [{"code": "invalid", "detail": "\"x\" is not a domain"}]}
        with self.assertRaises(RuntimeError) as caught:
            self.call([(200, body)])
        self.assertIn("is not a domain", str(caught.exception))

    def test_429_waits_retry_after_then_succeeds(self):
        calls, sleep = self.call([http_error(429, headers={"Retry-After": "1"}),
                                  (204, None)])
        self.assertEqual(len(calls), 2)
        sleep.assert_called_once_with(1.0)

    def test_429_gives_up_after_max_retries(self):
        with self.assertRaises(RuntimeError) as caught:
            self.call([http_error(429) for _ in range(3)], max_retries=2)
        self.assertIn("429", str(caught.exception))

    def test_server_error_reported_without_retry(self):
        with self.assertRaises(RuntimeError) as caught:
            self.call([http_error(500, b"boom")])
        self.assertIn("HTTP 500", str(caught.exception))

    def test_transport_error_reported(self):
        with self.assertRaises(RuntimeError) as caught:
            self.call([urllib.error.URLError("no route to host")])
        self.assertIn("URLError", str(caught.exception))

    def test_pacing_sleeps_between_writes(self):
        _, sleep = self.call([(204, None)], delay=0.5)
        sleep.assert_called_once_with(0.5)


class TestRedirectRefusal(unittest.TestCase):
    """A redirect must never carry the API key to another origin.

    The key rides on every request, so the only safe behavior on a 3xx is a
    failed call. _NoRedirect makes urllib surface the redirect as an
    HTTPError instead of rebuilding the request against the Location origin.
    This drives the real opener machinery with HTTPSConnection replaced by a
    recording fake (no sockets): exactly one request may ever be made, to
    api.nextdns.io, and it is the request that carried the key.
    """

    class FakeResponse(io.BytesIO):
        """Minimal http.client.HTTPResponse stand-in."""

        def __init__(self, status, reason, headers):
            super().__init__(b"")
            self.status = status
            self.code = status
            self.reason = reason
            self.msg = reason
            self._headers = headers

        def info(self):
            return self._headers

    def test_redirect_is_refused_and_the_key_stays_on_the_api_origin(self):
        sent = []

        class FakeHTTPSConnection:
            sock = None  # do_open() checks h.sock on recent CPythons

            def __init__(self, host, timeout=None, **kwargs):
                self.host = host

            def set_debuglevel(self, level):
                pass

            def request(self, method, url, body=None, headers=None,
                        encode_chunked=False):
                sent.append({"host": self.host, "method": method,
                             "url": url, "headers": dict(headers or {})})

            def getresponse(self):
                headers = email.message.Message()
                headers["Location"] = "https://evil.example/profiles/abc123/denylist"
                return TestRedirectRefusal.FakeResponse(302, "Found", headers)

        # A fresh opener (same _NoRedirect handler, no OS proxy) so the test
        # is immune to HTTP(S)_PROXY in the environment.
        opener = urllib.request.build_opener(
            nextdns_sync._NoRedirect, urllib.request.ProxyHandler({}))
        with mock.patch.object(nextdns_sync, "_OPENER", opener), \
             mock.patch.object(http.client, "HTTPSConnection", FakeHTTPSConnection), \
             self.assertRaises(RuntimeError) as caught:
            nextdns_sync.add_domain("abc123", "snu.lge.com", TEST_KEY,
                                    timeout=5.0, delay=0.0, max_retries=0)

        self.assertIn("HTTP 302", str(caught.exception))
        # One request only, to the API origin: the redirect was not followed.
        self.assertEqual([entry["host"] for entry in sent], ["api.nextdns.io"])
        self.assertEqual(sent[0]["method"], "POST")
        self.assertEqual(sent[0]["url"], "/profiles/abc123/denylist")
        key_headers = [value for name, value in sent[0]["headers"].items()
                       if name.lower() == "x-api-key"]
        self.assertEqual(key_headers, [TEST_KEY])


class TestMain(unittest.TestCase):
    """main() with api_request mocked: exit codes, dry-run safety, outcomes."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "list.txt"

    def run_main(self, argv, routes, key=TEST_KEY):
        """routes(method, path, **kw) -> (status, payload); returns
        (rc, stdout, stderr, calls)."""
        calls = []

        def fake(method, path, **kw):
            calls.append((method, path, kw))
            return routes(method, path, **kw)

        with mock.patch.dict(os.environ, {nextdns_sync.ENV_VAR: key}), \
             mock.patch.object(nextdns_sync, "api_request", side_effect=fake), \
             mock.patch.object(nextdns_sync.time, "sleep"), \
             contextlib.redirect_stdout(io.StringIO()) as out, \
             contextlib.redirect_stderr(io.StringIO()) as err:
            rc = nextdns_sync.main(argv)
        return rc, out.getvalue(), err.getvalue(), calls

    @staticmethod
    def no_api(*args, **kwargs):
        raise AssertionError("the API must not be called")

    def test_dry_run_without_key_makes_no_api_calls(self):
        write_list(self.path, "a.lge.com\nb.lge.com\n")
        rc, out, _, calls = self.run_main(["--file", str(self.path)],
                                          self.no_api, key="")
        self.assertEqual(rc, 0)
        self.assertEqual(calls, [])
        self.assertIn("dry-run: no changes will be made", out)
        self.assertIn("WOULD ADD a.lge.com", out)
        self.assertIn("WOULD ADD b.lge.com", out)
        self.assertIn("summary: 2 to add", out)

    def test_dry_run_with_key_diffs_but_still_never_writes(self):
        write_list(self.path, "a.lge.com\nnew.lge.com\n")

        def routes(method, path, **kw):
            self.assertEqual(method, "GET")
            return 200, {"data": [{"id": "a.lge.com", "active": True}],
                         "meta": {"pagination": {"cursor": None}}}

        rc, out, _, calls = self.run_main(
            ["--file", str(self.path), "--profile", "abc123"], routes)
        self.assertEqual(rc, 0)
        self.assertTrue(all(method == "GET" for method, _, _ in calls))
        self.assertIn("EXISTS  a.lge.com", out)
        self.assertIn("WOULD ADD new.lge.com", out)
        self.assertIn("summary: 1 to add, 1 already present", out)

    def test_disabled_entry_is_flagged_in_dry_run(self):
        write_list(self.path, "a.lge.com\n")

        def routes(method, path, **kw):
            return 200, {"data": [{"id": "a.lge.com", "active": False}],
                         "meta": {"pagination": {"cursor": None}}}

        rc, out, _, _ = self.run_main(
            ["--file", str(self.path), "--profile", "abc123"], routes)
        self.assertEqual(rc, 0)
        self.assertIn("EXISTS (disabled) a.lge.com", out)
        self.assertNotIn("WOULD ADD", out)
        self.assertIn(
            "summary: 0 to add, 0 already present, 1 present but disabled", out)

    def test_apply_skips_a_disabled_entry_instead_of_adding_it(self):
        write_list(self.path, "a.lge.com\nnew.lge.com\n")

        def routes(method, path, **kw):
            if method == "GET":
                return 200, {"data": [{"id": "a.lge.com", "active": False}],
                             "meta": {"pagination": {"cursor": None}}}
            # The only write may be the missing domain: the disabled entry
            # must not be re-added (or re-enabled) as if it were satisfied.
            self.assertEqual(kw["body"], {"id": "new.lge.com"})
            return 204, None

        rc, out, _, _ = self.run_main(
            ["--file", str(self.path), "--profile", "abc123", "--apply"], routes)
        self.assertEqual(rc, 0)
        self.assertIn("EXISTS (disabled) a.lge.com", out)
        self.assertNotIn("ADDED   a.lge.com", out)
        self.assertIn("ADDED   new.lge.com", out)
        self.assertIn("0 already present, 1 present but disabled", out)

    def test_apply_adds_only_missing_domains(self):
        write_list(self.path, "a.lge.com\nnew.lge.com\nnew2.lge.com\n")

        def routes(method, path, **kw):
            if method == "GET":
                return 200, {"data": [{"id": "a.lge.com"}],
                             "meta": {"pagination": {"cursor": None}}}
            return 204, None

        rc, out, err, calls = self.run_main(
            ["--file", str(self.path), "--profile", "abc123", "--apply"], routes)
        self.assertEqual(rc, 0)
        self.assertEqual([kw["body"] for method, _, kw in calls if method == "POST"],
                         [{"id": "new.lge.com"}, {"id": "new2.lge.com"}])
        self.assertIn("EXISTS  a.lge.com", out)
        self.assertIn("ADDED   new.lge.com", out)
        self.assertIn("summary: 2 added, 1 already present", out)
        # The key must never leak into any output.
        self.assertNotIn(TEST_KEY, out + err)

    def test_apply_reports_partial_failure_with_exit_1(self):
        write_list(self.path, "good.lge.com\nbad.lge.com\n")

        def routes(method, path, **kw):
            if method == "GET":
                return 200, {"data": [], "meta": {"pagination": {"cursor": None}}}
            if kw["body"]["id"] == "bad.lge.com":
                raise http_error(500, b"boom")
            return 204, None

        rc, out, _, _ = self.run_main(
            ["--file", str(self.path), "--profile", "abc123", "--apply"], routes)
        self.assertEqual(rc, 1)
        self.assertIn("ADDED   good.lge.com", out)
        self.assertIn("ERROR   bad.lge.com (HTTP 500", out)
        self.assertIn("1 failed", out)

    def test_200_with_errors_on_post_is_reported_as_error_outcome(self):
        write_list(self.path, "x.lge.com\n")

        def routes(method, path, **kw):
            if method == "GET":
                return 200, {"data": [], "meta": {}}
            return 200, {"errors": [{"code": "invalid", "detail": "\"x\" is not a domain"}]}

        rc, out, _, _ = self.run_main(
            ["--file", str(self.path), "--profile", "abc123", "--apply"], routes)
        self.assertEqual(rc, 1)
        self.assertIn("ERROR   x.lge.com", out)
        self.assertIn("is not a domain", out)

    def test_apply_without_key_is_a_config_error(self):
        write_list(self.path, "a.lge.com\n")
        rc, _, err, calls = self.run_main(
            ["--file", str(self.path), "--profile", "abc123", "--apply"],
            self.no_api, key="")
        self.assertEqual(rc, 2)
        self.assertIn("NEXTDNS_API_KEY", err)
        self.assertEqual(calls, [])

    def test_apply_without_profile_is_a_config_error(self):
        write_list(self.path, "a.lge.com\n")
        rc, _, err, calls = self.run_main(
            ["--file", str(self.path), "--apply"], self.no_api)
        self.assertEqual(rc, 2)
        self.assertIn("--profile", err)
        self.assertEqual(calls, [])

    def test_apply_with_no_fetch_is_rejected(self):
        write_list(self.path, "a.lge.com\n")
        rc, _, err, calls = self.run_main(
            ["--file", str(self.path), "--profile", "abc123", "--apply",
             "--no-fetch"], self.no_api)
        self.assertEqual(rc, 2)
        self.assertIn("--no-fetch", err)
        self.assertEqual(calls, [])

    def test_bad_profile_id_is_rejected_before_any_call(self):
        write_list(self.path, "a.lge.com\n")
        for profile in ("../etc", "a/b", "x" * 65, ""):
            with self.subTest(profile=profile):
                rc, _, _, calls = self.run_main(
                    ["--file", str(self.path), "--profile", profile], self.no_api)
                self.assertEqual(rc, 2)
                self.assertEqual(calls, [])

    def test_apply_aborts_without_writing_when_denylist_unreadable(self):
        write_list(self.path, "a.lge.com\n")

        def routes(method, path, **kw):
            raise http_error(500, b"boom")

        rc, _, err, calls = self.run_main(
            ["--file", str(self.path), "--profile", "abc123", "--apply"], routes)
        self.assertEqual(rc, 1)
        self.assertIn("nothing was written", err)
        self.assertTrue(all(method == "GET" for method, _, _ in calls))

    def test_rejected_key_exits_2(self):
        write_list(self.path, "a.lge.com\n")

        def routes(method, path, **kw):
            raise http_error(401, json.dumps(
                {"errors": [{"detail": "unauthorized"}]}).encode())

        rc, _, err, _ = self.run_main(
            ["--file", str(self.path), "--profile", "abc123"], routes)
        self.assertEqual(rc, 2)
        self.assertIn("unauthorized", err)

    def test_dry_run_survives_a_dead_network_with_a_warning(self):
        write_list(self.path, "a.lge.com\n")

        def routes(method, path, **kw):
            raise urllib.error.URLError("network down")

        rc, out, err, _ = self.run_main(
            ["--file", str(self.path), "--profile", "abc123"], routes)
        self.assertEqual(rc, 0)
        self.assertIn("warning:", err)
        self.assertIn("WOULD ADD a.lge.com", out)

    def test_missing_file_is_a_config_error(self):
        rc, _, _, calls = self.run_main(
            ["--file", str(self.path) + ".nope"], self.no_api)
        self.assertEqual(rc, 2)
        self.assertEqual(calls, [])

    def test_file_without_valid_domains_is_a_config_error(self):
        write_list(self.path, "# only comments\n\n*.lgtvcommon.com\n")
        rc, _, err, _ = self.run_main(["--file", str(self.path)],
                                      self.no_api, key="")
        self.assertEqual(rc, 2)
        self.assertIn("no domains parsed", err)
        # The reason each line was rejected must be visible, not just "empty".
        self.assertIn("SKIPPED *.lgtvcommon.com (line 3: not a domain name)", err)

    def test_bad_lines_warn_but_do_not_fail_the_run(self):
        write_list(self.path, "a.lge.com\n*.lgtvcommon.com\n")
        rc, out, _, _ = self.run_main(["--file", str(self.path)],
                                      self.no_api, key="")
        self.assertEqual(rc, 0)
        self.assertIn("SKIPPED *.lgtvcommon.com (line 2: not a domain name)", out)
        self.assertIn("1 skipped", out)

    def test_flag_validation_errors_exit_2(self):
        write_list(self.path, "a.lge.com\n")
        for flag, value in (("--delay", "-1"), ("--timeout", "0"),
                            ("--max-retries", "-1"), ("--delay", "x")):
            with self.subTest(flag=flag, value=value):
                with contextlib.redirect_stderr(io.StringIO()), \
                     self.assertRaises(SystemExit) as caught:
                    nextdns_sync.main(["--file", str(self.path), flag, value])
                self.assertEqual(caught.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
