#!/usr/bin/env python3
"""Test suite for check_blocking.py. Run: python scripts/test_check_blocking.py.

Deliberately offline: sockets and urllib are mocked, so every classification
and exit-code rule is exercised without sending a packet. Wire-format tests
use hand-built golden bytes instead of a live resolver.
"""
import argparse
import contextlib
import io
import ipaddress
import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_blocking  # noqa: E402  (after sys.path fix)

TXID = 0x1234
SERVER = "192.0.2.53"


def response_bytes(txid=TXID, rcode=0, addrs=("93.184.216.34",)):
    """A DNS response for example.com: echoed question plus A answers."""
    header = struct.pack(">HHHHHH", txid, 0x8180 | rcode, 1, len(addrs), 0, 0)
    question = b"\x07example\x03com\x00\x00\x01\x00\x01"
    body = b""
    for addr in addrs:
        body += (b"\xc0\x0c" + struct.pack(">HHIH", 1, 1, 60, 4)
                 + bytes(int(part) for part in addr.split(".")))
    return header + question + body


def cname_then_a_response(txid=TXID):
    """One CNAME record followed by the A record (a common real shape)."""
    header = struct.pack(">HHHHHH", txid, 0x8180, 1, 2, 0, 0)
    question = b"\x07example\x03com\x00\x00\x01\x00\x01"
    cname = b"\xc0\x0c" + struct.pack(">HHIH", 5, 1, 60, 2) + b"\xc0\x0c"
    a = (b"\xc0\x0c" + struct.pack(">HHIH", 1, 1, 60, 4)
         + bytes([93, 184, 216, 34]))
    return header + question + cname + a


class FakeSocket:
    """Stands in for a UDP socket: scripted recvfrom results, recorded sends.

    A response item may be an exception (raised), a bytes packet (received
    from the default peer), or a (peer, bytes) tuple.
    """

    def __init__(self, responses, peer=SERVER):
        self.responses = list(responses)
        self.peer = peer
        self.sent = []
        self.timeouts = []

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def settimeout(self, value):
        self.timeouts.append(value)

    def sendto(self, data, addr):
        self.sent.append((data, addr))
        return len(data)

    def recvfrom(self, bufsize):
        item = self.responses.pop(0)
        if isinstance(item, BaseException):
            raise item
        if isinstance(item, tuple):
            peer, data = item
        else:
            peer, data = self.peer, item
        return data, (peer, 53)


class FakeHTTPResponse:
    """Minimal context-manager stand-in for urlopen()'s return value."""

    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def read(self):
        return self.body


# ---------------------------------------------------------------------------
# Wire format


class TestBuildQuery(unittest.TestCase):
    def test_golden_packet(self):
        packet = check_blocking.build_query("snu.lge.com", TXID)
        self.assertEqual(
            packet,
            b"\x12\x34\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00"
            b"\x03snu\x03lge\x03com\x00\x00\x01\x00\x01")

    def test_trailing_dot_is_ignored(self):
        self.assertEqual(check_blocking.build_query("snu.lge.com.", TXID),
                         check_blocking.build_query("snu.lge.com", TXID))

    def test_rejects_bad_labels(self):
        for name in ("", "a" * 64 + ".com", "b\xe4d.lge.com", ".example.com"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                check_blocking.build_query(name, TXID)


class TestParseResponse(unittest.TestCase):
    def test_answer_record(self):
        rcode, addrs = check_blocking.parse_response(response_bytes(), TXID)
        self.assertEqual(rcode, 0)
        self.assertEqual(addrs, ["93.184.216.34"])

    def test_cname_is_skipped_and_a_collected(self):
        rcode, addrs = check_blocking.parse_response(cname_then_a_response(), TXID)
        self.assertEqual(rcode, 0)
        self.assertEqual(addrs, ["93.184.216.34"])

    def test_nxdomain(self):
        rcode, addrs = check_blocking.parse_response(
            response_bytes(rcode=3, addrs=()), TXID)
        self.assertEqual(rcode, check_blocking.RCODE_NXDOMAIN)
        self.assertEqual(addrs, [])

    def test_noerror_without_answers(self):
        rcode, addrs = check_blocking.parse_response(
            response_bytes(addrs=()), TXID)
        self.assertEqual(rcode, 0)
        self.assertEqual(addrs, [])

    def test_short_header_is_malformed(self):
        with self.assertRaises(ValueError):
            check_blocking.parse_response(b"\x00" * 11, TXID)

    def test_transaction_id_mismatch_is_malformed(self):
        with self.assertRaises(ValueError):
            check_blocking.parse_response(response_bytes(txid=0x9999), TXID)

    def test_truncated_rdata_is_malformed(self):
        with self.assertRaises(ValueError):
            check_blocking.parse_response(response_bytes()[:-2], TXID)

    def test_truncated_pointer_is_malformed(self):
        packet = struct.pack(">HHHHHH", TXID, 0x8180, 1, 0, 0, 0) + b"\xc0"
        with self.assertRaises(ValueError):
            check_blocking.parse_response(packet, TXID)

    def test_too_many_labels_is_malformed(self):
        question = b"\x01a" * 128 + b"\x00" + b"\x00\x01\x00\x01"
        packet = struct.pack(">HHHHHH", TXID, 0x8180, 1, 0, 0, 0) + question
        with self.assertRaises(ValueError):
            check_blocking.parse_response(packet, TXID)


class TestSkipName(unittest.TestCase):
    def test_plain_label(self):
        self.assertEqual(check_blocking.skip_name(b"\x03abc\x00", 0), 5)
        self.assertEqual(check_blocking.skip_name(b"\x00\x03abc\x00", 1), 6)

    def test_pointer(self):
        self.assertEqual(check_blocking.skip_name(b"\xc0\x0c", 0), 2)

    def test_truncated_pointer(self):
        with self.assertRaises(ValueError):
            check_blocking.skip_name(b"\xc0", 0)


# ---------------------------------------------------------------------------
# Local classification


class TestLocalState(unittest.TestCase):
    def test_real_answer(self):
        state, detail = check_blocking.local_state(0, ["93.184.216.34"])
        self.assertEqual((state, detail),
                         (check_blocking.L_ANSWERED, "93.184.216.34"))

    def test_sinkhole_addresses(self):
        for addr in ("0.0.0.0", "127.0.0.1"):
            with self.subTest(addr=addr):
                state, detail = check_blocking.local_state(0, [addr])
                self.assertEqual(state, check_blocking.L_SINKHOLED)
                self.assertIn("sinkholed", detail)

    def test_mixed_answers_are_not_a_sinkhole(self):
        state, _ = check_blocking.local_state(0, ["0.0.0.0", "93.184.216.34"])
        self.assertEqual(state, check_blocking.L_ANSWERED)

    def test_no_answer(self):
        state, _ = check_blocking.local_state(0, [])
        self.assertEqual(state, check_blocking.L_NO_ANSWER)

    def test_nxdomain(self):
        state, detail = check_blocking.local_state(3, [])
        self.assertEqual((state, detail), (check_blocking.L_NXDOMAIN, "NXDOMAIN"))

    def test_servfail_and_refused_are_failures_not_verdicts(self):
        for rcode, name in ((2, "SERVFAIL"), (5, "REFUSED")):
            with self.subTest(rcode=rcode):
                state, detail = check_blocking.local_state(rcode, [])
                self.assertEqual(state, check_blocking.L_FAILED)
                self.assertIn(name, detail)


class TestQueryLocal(unittest.TestCase):
    def query(self, responses, attempts=2):
        fake = FakeSocket(responses)
        with mock.patch.object(check_blocking, "new_txid", return_value=TXID), \
             mock.patch.object(check_blocking.socket, "socket", return_value=fake):
            result = check_blocking.query_local(
                "example.com", SERVER, 53, 1.0, attempts=attempts)
        return result, fake

    def test_answer(self):
        (state, detail), fake = self.query([response_bytes()])
        self.assertEqual((state, detail),
                         (check_blocking.L_ANSWERED, "93.184.216.34"))
        self.assertEqual(fake.sent[0][1], (SERVER, 53))
        self.assertEqual(fake.sent[0][0][:2], b"\x12\x34")
        self.assertEqual(fake.timeouts, [1.0])

    def test_nxdomain(self):
        (state, _), _ = self.query([response_bytes(rcode=3, addrs=())])
        self.assertEqual(state, check_blocking.L_NXDOMAIN)

    def test_servfail_is_a_failure(self):
        (state, detail), _ = self.query([response_bytes(rcode=2, addrs=())])
        self.assertEqual(state, check_blocking.L_FAILED)
        self.assertIn("SERVFAIL", detail)

    def test_timeout_after_all_attempts(self):
        (state, detail), fake = self.query([TimeoutError(), TimeoutError()])
        self.assertEqual(state, check_blocking.L_TIMEOUT)
        self.assertEqual(len(fake.sent), 2)  # one resend before giving up
        self.assertIn("no response", detail)

    def test_timeout_then_answer_uses_the_retry(self):
        (state, _), fake = self.query([TimeoutError(), response_bytes()])
        self.assertEqual(state, check_blocking.L_ANSWERED)
        self.assertEqual(len(fake.sent), 2)

    def test_connection_reset_counts_as_no_response(self):
        # Windows turns an ICMP port-unreachable into a reset on recv: the
        # resolver still did not answer, so this must not become ERROR.
        (state, _), _ = self.query([ConnectionResetError(), ConnectionResetError()])
        self.assertEqual(state, check_blocking.L_TIMEOUT)

    def test_stray_datagram_is_ignored(self):
        (state, _), fake = self.query(
            [("198.51.100.9", response_bytes()), response_bytes()])
        self.assertEqual(state, check_blocking.L_ANSWERED)
        self.assertEqual(len(fake.sent), 2)

    def test_wrong_transaction_id_is_malformed(self):
        (state, detail), _ = self.query(
            [response_bytes(txid=0x9999), TimeoutError()])
        self.assertEqual(state, check_blocking.L_FAILED)
        self.assertIn("malformed", detail)

    def test_send_oserror_is_a_failure(self):
        fake = FakeSocket([])
        fake.sendto = mock.Mock(side_effect=OSError("network down"))
        with mock.patch.object(check_blocking, "new_txid", return_value=TXID), \
             mock.patch.object(check_blocking.socket, "socket", return_value=fake):
            state, detail = check_blocking.query_local(
                "example.com", SERVER, 53, 1.0)
        self.assertEqual(state, check_blocking.L_FAILED)
        self.assertIn("cannot send", detail)

    def test_socket_error_is_a_failure(self):
        with mock.patch.object(check_blocking.socket, "socket",
                               side_effect=OSError("no sockets")):
            state, detail = check_blocking.query_local(
                "example.com", SERVER, 53, 1.0)
        self.assertEqual(state, check_blocking.L_FAILED)
        self.assertIn("socket error", detail)

    def test_unusable_name_is_a_failure(self):
        state, detail = check_blocking.query_local(
            "b\xe4d.lge.com", SERVER, 53, 1.0)
        self.assertEqual(state, check_blocking.L_FAILED)
        self.assertIn("unusable name", detail)


# ---------------------------------------------------------------------------
# DoH cross-check


class TestCrossClassify(unittest.TestCase):
    def test_resolves(self):
        state, detail = check_blocking.cross_classify({
            "Status": 0,
            "Answer": [{"type": 5, "data": "cname.example"},
                       {"type": 1, "data": "93.184.216.34"}],
        })
        self.assertEqual((state, detail),
                         (check_blocking.X_RESOLVES, "93.184.216.34"))

    def test_nxdomain(self):
        state, detail = check_blocking.cross_classify({"Status": 3})
        self.assertEqual((state, detail), (check_blocking.X_NXDOMAIN, "NXDOMAIN"))

    def test_noerror_without_a_record_exists(self):
        for payload in ({"Status": 0}, {"Status": 0, "Answer": []},
                        {"Status": 0, "Answer": [{"type": 6, "data": "soa"}]}):
            with self.subTest(payload=payload):
                state, _ = check_blocking.cross_classify(payload)
                self.assertEqual(state, check_blocking.X_EXISTS)

    def test_unexpected_status_is_an_error(self):
        for payload in ({"Status": 2}, {"Status": None}, {}):
            with self.subTest(payload=payload):
                state, _ = check_blocking.cross_classify(payload)
                self.assertEqual(state, check_blocking.X_ERROR)

    def test_non_dict_payload_is_an_error(self):
        # A DoH endpoint could legitimately return a JSON list or string;
        # that must not abort the run (regression class from verify.py).
        for payload in ([], "not a dict", None, 42):
            with self.subTest(payload=payload):
                state, _ = check_blocking.cross_classify(payload)
                self.assertEqual(state, check_blocking.X_ERROR)

    def test_malformed_answer_section_is_an_error(self):
        for answers in ([1, 2], {"type": 1}, "answer"):
            with self.subTest(answers=answers):
                state, _ = check_blocking.cross_classify(
                    {"Status": 0, "Answer": answers})
                self.assertEqual(state, check_blocking.X_ERROR)


class TestCrossLookup(unittest.TestCase):
    def lookup(self, body, provider="google"):
        calls = []

        def fake_urlopen(req, timeout=None):
            calls.append(req)
            return FakeHTTPResponse(body)

        with mock.patch.object(check_blocking.urllib.request, "urlopen",
                               side_effect=fake_urlopen):
            result = check_blocking.cross_lookup("example.com", provider, 1.0)
        return result, calls

    def test_success_uses_google_by_default(self):
        (state, detail), calls = self.lookup(
            b'{"Status": 0, "Answer": [{"type": 1, "data": "93.184.216.34"}]}')
        self.assertEqual((state, detail),
                         (check_blocking.X_RESOLVES, "93.184.216.34"))
        self.assertIn("dns.google", calls[0].full_url)
        self.assertIn("name=example.com", calls[0].full_url)

    def test_cloudflare_provider_sends_accept_header(self):
        (state, _), calls = self.lookup(b'{"Status": 3}', provider="cloudflare")
        self.assertEqual(state, check_blocking.X_NXDOMAIN)
        self.assertIn("cloudflare-dns.com", calls[0].full_url)
        self.assertEqual(calls[0].get_header("Accept"), "application/dns-json")

    def test_non_dict_json_is_an_error_not_a_crash(self):
        (state, detail), _ = self.lookup(b"[]")
        self.assertEqual(state, check_blocking.X_ERROR)
        self.assertIn("malformed DoH payload", detail)

    def test_invalid_json_is_an_error(self):
        state, _ = self.lookup(b"not json")[0]
        self.assertEqual(state, check_blocking.X_ERROR)

    def test_network_error_is_an_error(self):
        with mock.patch.object(check_blocking.urllib.request, "urlopen",
                               side_effect=check_blocking.urllib.error.URLError("boom")):
            state, detail = check_blocking.cross_lookup("example.com", "google", 1.0)
        self.assertEqual(state, check_blocking.X_ERROR)
        self.assertIn("URLError", detail)


# ---------------------------------------------------------------------------
# The verdict merge


class TestClassifyLocal(unittest.TestCase):
    def verdict(self, local, cross=None):
        return check_blocking.classify_local(local, cross)

    def test_answered_is_resolves(self):
        self.assertEqual(
            self.verdict((check_blocking.L_ANSWERED, "93.184.216.34"))[0],
            check_blocking.RESOLVES)

    def test_sinkholed_with_a_resolving_cross_check_is_blocked(self):
        verdict, detail = self.verdict(
            (check_blocking.L_SINKHOLED, "sinkholed to 0.0.0.0"),
            (check_blocking.X_RESOLVES, "93.184.216.34"))
        self.assertEqual(verdict, check_blocking.BLOCKED)
        self.assertIn("cross-check", detail)

    def test_sinkholed_without_cross_check_is_not_blocked(self):
        # A wildcard-null resolver answers the same way for DEAD names, so a
        # null answer without ground truth must never become BLOCKED.
        verdict, _ = self.verdict((check_blocking.L_SINKHOLED, "sinkholed to 0.0.0.0"))
        self.assertEqual(verdict, check_blocking.ERROR)
        self.assertNotEqual(verdict, check_blocking.BLOCKED)

    def test_sinkhole_on_both_sides_is_dead(self):
        for cross in ((check_blocking.X_NXDOMAIN, "NXDOMAIN"),
                      (check_blocking.X_EXISTS, "no A record")):
            with self.subTest(cross=cross):
                verdict, _ = self.verdict(
                    (check_blocking.L_SINKHOLED, "sinkholed to 0.0.0.0"), cross)
                self.assertEqual(verdict, check_blocking.DEAD)

    def test_sinkholed_with_failed_cross_check_is_not_blocked(self):
        verdict, _ = self.verdict(
            (check_blocking.L_SINKHOLED, "sinkholed to 0.0.0.0"),
            (check_blocking.X_ERROR, "URLError: boom"))
        self.assertEqual(verdict, check_blocking.ERROR)
        self.assertNotEqual(verdict, check_blocking.BLOCKED)

    def test_nxdomain_with_cross_check_resolves_is_blocked(self):
        verdict, detail = self.verdict(
            (check_blocking.L_NXDOMAIN, "NXDOMAIN"),
            (check_blocking.X_RESOLVES, "93.184.216.34"))
        self.assertEqual(verdict, check_blocking.BLOCKED)
        self.assertIn("cross-check", detail)

    def test_nxdomain_on_both_sides_is_dead(self):
        verdict, _ = self.verdict(
            (check_blocking.L_NXDOMAIN, "NXDOMAIN"),
            (check_blocking.X_NXDOMAIN, "NXDOMAIN"))
        self.assertEqual(verdict, check_blocking.DEAD)

    def test_nxdomain_against_existing_apex_is_blocked(self):
        verdict, _ = self.verdict(
            (check_blocking.L_NXDOMAIN, "NXDOMAIN"),
            (check_blocking.X_EXISTS, "no A record"))
        self.assertEqual(verdict, check_blocking.BLOCKED)

    def test_nxdomain_without_cross_check_is_not_blocked(self):
        verdict, _ = self.verdict((check_blocking.L_NXDOMAIN, "NXDOMAIN"))
        self.assertEqual(verdict, check_blocking.ERROR)
        self.assertNotEqual(verdict, check_blocking.BLOCKED)

    def test_nxdomain_with_failed_cross_check_is_not_blocked(self):
        verdict, _ = self.verdict(
            (check_blocking.L_NXDOMAIN, "NXDOMAIN"),
            (check_blocking.X_ERROR, "URLError: boom"))
        self.assertEqual(verdict, check_blocking.ERROR)
        self.assertNotEqual(verdict, check_blocking.BLOCKED)

    def test_no_answer_with_cross_check_resolves_is_blocked(self):
        verdict, _ = self.verdict(
            (check_blocking.L_NO_ANSWER, "NOERROR without an A record"),
            (check_blocking.X_RESOLVES, "93.184.216.34"))
        self.assertEqual(verdict, check_blocking.BLOCKED)

    def test_no_answer_on_both_sides_is_not_a_verdict(self):
        verdict, detail = self.verdict(
            (check_blocking.L_NO_ANSWER, "NOERROR without an A record"),
            (check_blocking.X_EXISTS, "no A record"))
        self.assertEqual(verdict, check_blocking.ERROR)
        self.assertIn("not a blocking verdict", detail)

    def test_no_answer_against_nxdomain_is_dead(self):
        verdict, _ = self.verdict(
            (check_blocking.L_NO_ANSWER, "NOERROR without an A record"),
            (check_blocking.X_NXDOMAIN, "NXDOMAIN"))
        self.assertEqual(verdict, check_blocking.DEAD)

    def test_timeout_is_unreachable_never_blocked(self):
        # The core promise: a silent resolver is not evidence of blocking,
        # with or without a cross-check result.
        for cross in (None, (check_blocking.X_RESOLVES, "93.184.216.34")):
            with self.subTest(cross=cross):
                verdict, _ = self.verdict(
                    (check_blocking.L_TIMEOUT, "no response within 3s"), cross)
                self.assertEqual(verdict, check_blocking.UNREACHABLE)
                self.assertNotEqual(verdict, check_blocking.BLOCKED)

    def test_failed_is_error_even_with_ground_truth(self):
        verdict, _ = self.verdict(
            (check_blocking.L_FAILED, "SERVFAIL (rcode 2)"),
            (check_blocking.X_RESOLVES, "93.184.216.34"))
        self.assertEqual(verdict, check_blocking.ERROR)


class TestCheckOne(unittest.TestCase):
    def test_answered_skips_the_cross_check(self):
        with mock.patch.object(
                check_blocking, "query_local",
                return_value=(check_blocking.L_ANSWERED, "93.184.216.34")), \
             mock.patch.object(check_blocking, "cross_lookup") as cross:
            verdict = check_blocking.check_one("x.example", SERVER, 53, 1.0, "google")
        cross.assert_not_called()
        self.assertEqual(verdict[0], check_blocking.RESOLVES)

    def test_nxdomain_triggers_the_cross_check(self):
        with mock.patch.object(
                check_blocking, "query_local",
                return_value=(check_blocking.L_NXDOMAIN, "NXDOMAIN")), \
             mock.patch.object(
                check_blocking, "cross_lookup",
                return_value=(check_blocking.X_RESOLVES, "93.184.216.34")) as cross:
            verdict = check_blocking.check_one("x.example", SERVER, 53, 1.0, "google")
        cross.assert_called_once_with("x.example", "google", 1.0)
        self.assertEqual(verdict[0], check_blocking.BLOCKED)

    def test_sinkholed_triggers_the_cross_check(self):
        # A null answer alone is ambiguous (wildcard-null vs deliberate
        # sinkhole), so the cross-check must run and have the final say.
        with mock.patch.object(
                check_blocking, "query_local",
                return_value=(check_blocking.L_SINKHOLED, "sinkholed to 0.0.0.0")), \
             mock.patch.object(
                check_blocking, "cross_lookup",
                return_value=(check_blocking.X_NXDOMAIN, "NXDOMAIN")) as cross:
            verdict = check_blocking.check_one("x.example", SERVER, 53, 1.0, "google")
        cross.assert_called_once_with("x.example", "google", 1.0)
        self.assertEqual(verdict[0], check_blocking.DEAD)


class TestCheckManyAndCounts(unittest.TestCase):
    def test_order_is_preserved(self):
        with mock.patch.object(check_blocking, "check_one",
                               side_effect=lambda domain, *args:
                               (check_blocking.BLOCKED, domain)):
            results = check_blocking.check_many(
                ["b.example", "a.example"], SERVER, 53, 1.0, "google")
        self.assertEqual(list(results), ["b.example", "a.example"])

    def test_counts_include_every_verdict_even_when_zero(self):
        counts = check_blocking.count_verdicts({
            "a.example": (check_blocking.BLOCKED, ""),
            "b.example": (check_blocking.BLOCKED, ""),
            "c.example": (check_blocking.RESOLVES, ""),
        })
        self.assertEqual(counts, {check_blocking.BLOCKED: 2,
                                  check_blocking.DEAD: 0,
                                  check_blocking.RESOLVES: 1,
                                  check_blocking.UNREACHABLE: 0,
                                  check_blocking.ERROR: 0})


# ---------------------------------------------------------------------------
# Inputs and configuration


class TestReadDomains(unittest.TestCase):
    def parse(self, text):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "list.txt"
            path.write_text(text, encoding="utf-8")
            return check_blocking.read_domains(path)

    def test_skips_comments_and_blanks(self):
        self.assertEqual(
            self.parse("# Title: x\n\nsnu.lge.com\n! adblock comment\n"),
            ["snu.lge.com"])

    def test_accepts_all_three_built_formats(self):
        for text in ("snu.lge.com\n", "0.0.0.0 snu.lge.com\n", "||snu.lge.com^\n"):
            with self.subTest(text=text):
                self.assertEqual(self.parse(text), ["snu.lge.com"])

    def test_dedupes_and_keeps_file_order(self):
        self.assertEqual(self.parse("b.lge.com\na.lge.com\nb.lge.com\n"),
                         ["b.lge.com", "a.lge.com"])

    def test_lowercases(self):
        self.assertEqual(self.parse("SNU.LGE.COM\n"), ["snu.lge.com"])


class TestArgparseTypes(unittest.TestCase):
    def test_resolver_address_canonicalizes(self):
        self.assertEqual(check_blocking.resolver_address(" 192.0.2.53 "),
                         "192.0.2.53")
        self.assertEqual(check_blocking.resolver_address("2001:0db8::0001"),
                         "2001:db8::1")

    def test_resolver_address_rejects_hostnames(self):
        with self.assertRaises(argparse.ArgumentTypeError):
            check_blocking.resolver_address("dns.example")

    def test_port_range(self):
        self.assertEqual(check_blocking.port_number("5353"), 5353)
        for value in ("0", "65536", "abc"):
            with self.subTest(value=value), \
                 self.assertRaises(argparse.ArgumentTypeError):
                check_blocking.port_number(value)

    def test_timeout_must_be_positive(self):
        self.assertEqual(check_blocking.positive_seconds("1.5"), 1.5)
        for value in ("0", "-1", "fast"):
            with self.subTest(value=value), \
                 self.assertRaises(argparse.ArgumentTypeError):
                check_blocking.positive_seconds(value)

    def test_cross_provider_aliases(self):
        for value, expected in (("google", "google"), ("8.8.8.8", "google"),
                                ("Google", "google"),
                                ("cloudflare", "cloudflare"),
                                ("1.1.1.1", "cloudflare")):
            with self.subTest(value=value):
                self.assertEqual(check_blocking.cross_provider(value), expected)

    def test_cross_provider_rejects_unknown(self):
        with self.assertRaises(argparse.ArgumentTypeError):
            check_blocking.cross_provider("quad9")


class TestSystemResolver(unittest.TestCase):
    def test_posix_parser_takes_first_valid_nameserver(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "resolv.conf"
            path.write_text("# comment\nnameserver garbage\n"
                            "nameserver 192.168.178.1\n"
                            "nameserver 8.8.8.8\n", encoding="utf-8")
            self.assertEqual(check_blocking._posix_resolver(path), "192.168.178.1")

    def test_posix_parser_without_nameservers(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "resolv.conf"
            path.write_text("search lan\n", encoding="utf-8")
            self.assertIsNone(check_blocking._posix_resolver(path))

    def test_posix_parser_missing_file(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertIsNone(
                check_blocking._posix_resolver(Path(td) / "missing.conf"))

    @unittest.skipUnless(sys.platform == "win32", "Windows registry only")
    def test_windows_resolver_is_an_ip_or_none(self):
        result = check_blocking._windows_resolver()
        if result is not None:
            ipaddress.ip_address(result)  # raises if not a valid IP


# ---------------------------------------------------------------------------
# main() output and exit codes


class TestMain(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.list_file = Path(tmp.name) / "list.txt"
        self.list_file.write_text("# Title: x\n\nsnu.lge.com\nexample.com\n",
                                  encoding="utf-8")

    def run_main(self, argv, results, os_resolver="192.0.2.53"):
        captured = {}

        def fake_check_many(domains, server, port, timeout, cross_provider):
            captured.update(domains=list(domains), server=server, port=port,
                            timeout=timeout, cross_provider=cross_provider)
            return {domain: results[domain] for domain in domains}

        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(check_blocking, "check_many",
                               side_effect=fake_check_many), \
             mock.patch.object(check_blocking, "system_resolver",
                               return_value=os_resolver), \
             contextlib.redirect_stdout(out), \
             contextlib.redirect_stderr(err):
            rc = check_blocking.main(argv)
        return rc, out.getvalue(), err.getvalue(), captured

    def test_expect_blocked_exits_zero_when_all_blocked(self):
        rc, _, err, _ = self.run_main(
            ["--file", str(self.list_file), "--expect-blocked"],
            {"snu.lge.com": (check_blocking.BLOCKED, "sinkholed to 0.0.0.0"),
             "example.com": (check_blocking.BLOCKED, "sinkholed to 0.0.0.0")})
        self.assertEqual(rc, 0)
        self.assertIn("BLOCKED=2", err)

    def test_expect_blocked_exits_one_when_a_domain_resolves(self):
        rc, _, err, _ = self.run_main(
            ["--file", str(self.list_file), "--expect-blocked"],
            {"snu.lge.com": (check_blocking.BLOCKED, "sinkholed to 0.0.0.0"),
             "example.com": (check_blocking.RESOLVES, "resolves to 93.184.216.34")})
        self.assertEqual(rc, 1)
        self.assertIn("example.com", err)
        self.assertIn("not confirmed BLOCKED", err)

    def test_expect_blocked_exits_one_on_unreachable(self):
        rc, _, _, _ = self.run_main(
            ["--file", str(self.list_file), "--expect-blocked"],
            {"snu.lge.com": (check_blocking.UNREACHABLE, "no response"),
             "example.com": (check_blocking.BLOCKED, "sinkholed to 0.0.0.0")})
        self.assertEqual(rc, 1)

    def test_without_expect_blocked_not_blocked_still_exits_zero(self):
        rc, out, _, _ = self.run_main(
            ["--file", str(self.list_file)],
            {"snu.lge.com": (check_blocking.BLOCKED, "sinkholed to 0.0.0.0"),
             "example.com": (check_blocking.RESOLVES, "resolves to 93.184.216.34")})
        self.assertEqual(rc, 0)
        lines = out.strip().splitlines()
        self.assertEqual(len(lines), 2)
        self.assertTrue(lines[0].startswith("BLOCKED"))
        self.assertIn("snu.lge.com", lines[0])
        self.assertTrue(lines[1].startswith("RESOLVES"))

    def test_json_shape(self):
        rc, out, err, _ = self.run_main(
            ["--file", str(self.list_file), "--json"],
            {"snu.lge.com": (check_blocking.BLOCKED, "sinkholed to 0.0.0.0"),
             "example.com": (check_blocking.RESOLVES, "resolves to 93.184.216.34")})
        self.assertEqual(rc, 0)
        report = json.loads(out)  # stdout must be pure JSON
        self.assertEqual(report["server"], "192.0.2.53")
        self.assertEqual(report["port"], 53)
        self.assertEqual(report["cross_check"], "google")
        self.assertEqual(report["counts"], {
            check_blocking.BLOCKED: 1, check_blocking.DEAD: 0,
            check_blocking.RESOLVES: 1, check_blocking.UNREACHABLE: 0,
            check_blocking.ERROR: 0})
        self.assertEqual([row["domain"] for row in report["results"]],
                         ["snu.lge.com", "example.com"])
        self.assertEqual(report["results"][0]["classification"],
                         check_blocking.BLOCKED)
        self.assertEqual(report["results"][0]["detail"], "sinkholed to 0.0.0.0")
        self.assertIn("BLOCKED=1", err)

    def test_domains_flag_replaces_the_file(self):
        rc, out, _, captured = self.run_main(
            ["--domains", "Example.COM, snu.lge.com ,example.com"],
            {"example.com": (check_blocking.BLOCKED, "sinkholed to 0.0.0.0"),
             "snu.lge.com": (check_blocking.BLOCKED, "sinkholed to 0.0.0.0")})
        self.assertEqual(rc, 0)
        self.assertEqual(captured["domains"], ["example.com", "snu.lge.com"])
        self.assertEqual([line.split()[1] for line in out.strip().splitlines()],
                         ["example.com", "snu.lge.com"])

    def test_explicit_server_and_options_are_passed_through(self):
        rc, _, _, captured = self.run_main(
            ["--domains", "example.com", "--server", "192.0.2.9",
             "--port", "5353", "--timeout", "1.5", "--cross-check", "1.1.1.1"],
            {"example.com": (check_blocking.BLOCKED, "sinkholed to 0.0.0.0")})
        self.assertEqual(rc, 0)
        self.assertEqual(captured["server"], "192.0.2.9")
        self.assertEqual(captured["port"], 5353)
        self.assertEqual(captured["timeout"], 1.5)
        self.assertEqual(captured["cross_provider"], "cloudflare")

    def test_missing_file_is_a_config_error(self):
        rc, _, err, _ = self.run_main(
            ["--file", str(self.list_file) + ".nope"], {})
        self.assertEqual(rc, 2)
        self.assertIn("no such file", err)

    def test_empty_file_is_a_config_error(self):
        empty = self.list_file.parent / "empty.txt"
        empty.write_text("# only comments\n", encoding="utf-8")
        rc, _, err, _ = self.run_main(["--file", str(empty)], {})
        self.assertEqual(rc, 2)
        self.assertIn("no entries parsed", err)

    def test_empty_domains_flag_is_a_config_error(self):
        for value in ("", ", ", " , "):
            with self.subTest(value=value):
                rc, _, err, _ = self.run_main(["--domains", value], {})
                self.assertEqual(rc, 2)
                self.assertIn("no domain names", err)

    def test_undetectable_os_resolver_is_a_config_error(self):
        rc, _, err, _ = self.run_main(["--file", str(self.list_file)], {},
                                      os_resolver=None)
        self.assertEqual(rc, 2)
        self.assertIn("--server", err)

    def test_invalid_values_are_argparse_errors(self):
        cases = (["--server", "dns.example"], ["--port", "0"],
                 ["--timeout", "nope"], ["--cross-check", "quad9"])
        for argv in cases:
            with self.subTest(argv=argv):
                with contextlib.redirect_stderr(io.StringIO()), \
                     self.assertRaises(SystemExit) as caught:
                    check_blocking.main(argv + ["--domains", "example.com"])
                self.assertEqual(caught.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
