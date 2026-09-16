#!/usr/bin/env python3
"""Test suite for build.py. Run: python scripts/test_build.py (stdlib only)."""
import io
import re
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

    def test_ueiwsp_accepted(self):
        # ueiwsp.com (QuickSet Cloud / UEI) allowlisted 2026-09-11, issue #3.
        self.write("strict.txt", (
            "ueiwsp.com # STRICT: weak — interop: QuickSet Cloud (UEI) discovery API; "
            "community report 2026-09-11 (repo issue #3 querylog; device unstated; "
            "not observed on G1; www subdomain observed live on G1 2026-09-12); "
            "breakage untested\n"
            "www.ueiwsp.com # STRICT: interop: QuickSet Cloud (UEI) discovery API; "
            "community report 2026-09-11 (repo issue #3 querylog); "
            "observed on G1 2026-09-12 (11 queries / 48 min; AGH querylog via Fritz relay); "
            "breakage untested\n"
        ))
        self.assertEqual(build.parse_src("strict.txt"),
                         ["ueiwsp.com", "www.ueiwsp.com"])

    def test_ueiwsp_near_misses_rejected(self):
        # Suffix matching must be label-boundary exact: "notueiwsp.com" ends
        # with "ueiwsp.com" as a bare string (no dot boundary), while
        # "ueiwsp.com.evil.example" only has it as a leading label.
        for host in ("notueiwsp.com", "ueiwsp.com.evil.example"):
            with self.subTest(host=host):
                self.write("strict.txt", f"{host} # STRICT: weak — near-miss fixture\n")
                with self.assertRaises(ValueError) as ctx:
                    build.parse_src("strict.txt")
                self.assertIn("not an LG family hostname", str(ctx.exception))

    def test_meethue_accepted(self):
        # meethue.com (Philips Hue cloud discovery) allowlisted 2026-09-14, issue #12.
        self.write("strict.txt", (
            "discovery.meethue.com # STRICT: interop: Philips Hue cloud bridge discovery "
            "(N-UPnP), called by LG TV background discovery; reported on webOS 25 "
            "(repo issue #12, @rugk); observed on G1 (webOS 6) 2026-06-11..2026-09-14 "
            "(pcap frame 25919: TLS SNI to 34.117.13.189:443; AGH ~4,100 lookups, "
            "~5-min cadence); cloud discovery only, local mDNS unaffected; "
            "breakage unverified (no Hue bridge)\n"
        ))
        self.assertEqual(build.parse_src("strict.txt"), ["discovery.meethue.com"])

    def test_meethue_near_misses_rejected(self):
        # Label-boundary exactness for the meethue.com allowlist entry (same
        # class as the ueiwsp.com near-misses): bare-string suffix collisions
        # and leading-label-only matches must not pass.
        for host in ("notmeethue.com", "meethue.com.evil.example"):
            with self.subTest(host=host):
                self.write("strict.txt", f"{host} # STRICT: near-miss fixture\n")
                with self.assertRaises(ValueError) as ctx:
                    build.parse_src("strict.txt")
                self.assertIn("not an LG family hostname", str(ctx.exception))

    def test_malformed_rejected(self):
        self.write("safe.txt", "not a hostname!! # nope\n")
        with self.assertRaises(ValueError):
            build.parse_src("safe.txt")

    def test_non_lg_rejected(self):
        self.write("safe.txt", "evil.example.com # not LG\n")
        with self.assertRaises(ValueError):
            build.parse_src("safe.txt")

    def test_suffix_lookalike_rejected(self):
        # "evillge.com" string-ends with "lge.com" but is not in the LG family.
        self.write("safe.txt", "evillge.com # lookalike suffix\n")
        with self.assertRaises(ValueError) as ctx:
            build.parse_src("safe.txt")
        self.assertIn("not an LG family hostname", str(ctx.exception))

    def test_single_trailing_dot_stripped(self):
        self.write("safe.txt", "snu.lge.com. # exactly one trailing dot\n")
        self.assertEqual(build.parse_src("safe.txt"), ["snu.lge.com"])

    def test_multiple_trailing_dots_rejected(self):
        for host in ("snu.lge.com..", "snu.lge.com..."):
            with self.subTest(host=host):
                self.write("safe.txt", f"{host} # extra trailing dots\n")
                with self.assertRaises(ValueError) as ctx:
                    build.parse_src("safe.txt")
                self.assertIn("safe.txt:1: malformed hostname", str(ctx.exception))

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

    def test_check_missing_source_file_reports_error(self):
        with tempfile.TemporaryDirectory() as td:
            old = build.SRC
            build.SRC = Path(td)
            try:
                err = io.StringIO()
                with redirect_stderr(err):
                    rc = build.main(["check"])
                self.assertEqual(rc, 1)
                self.assertIn("ERROR", err.getvalue())
                self.assertIn("safe.txt", err.getvalue())
            finally:
                build.SRC = old

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


class TestWildcard(unittest.TestCase):
    """The regex outputs, and the guarantee that they change nothing else."""

    SHIPPED = ("safe-domains.txt", "safe-hosts.txt", "safe-adblock.txt",
               "strict-domains.txt", "strict-hosts.txt", "strict-adblock.txt")

    def setUp(self):
        self.orig_src = build.SRC
        self.orig_now = build.now_utc
        build.now_utc = lambda: "2026-01-01 00:00 UTC"   # stable headers to diff

    def tearDown(self):
        build.SRC = self.orig_src
        build.now_utc = self.orig_now

    def write_src(self, safe="", strict="", zones=""):
        build.SRC = Path(tempfile.mkdtemp())
        for name, text in (("safe.txt", safe), ("strict.txt", strict),
                           ("zones.txt", zones)):
            (build.SRC / name).write_text(text, encoding="utf-8")

    # ---- condition 3: the six shipped lists must not move -------------------

    def test_six_shipped_outputs_are_identical_without_the_tags(self):
        real = self.orig_src
        tagged = build.dry_run()

        build.SRC = Path(tempfile.mkdtemp())
        for name in ("safe.txt", "strict.txt", "zones.txt"):
            text = (real / name).read_text(encoding="utf-8")
            # strip the tag itself, then any space it left behind, so a tag
            # written without a leading space is still removed
            stripped = "\n".join(
                line.replace(build.REGION_TAG, "").rstrip()
                for line in text.splitlines()) + "\n"
            (build.SRC / name).write_text(stripped, encoding="utf-8")
        untagged = build.dry_run()

        for name in self.SHIPPED:
            with self.subTest(output=name):
                self.assertEqual(tagged[name], untagged[name])
        # ...and the test is not vacuous: the wildcard file does change.
        self.assertNotEqual(tagged["safe-wildcard.txt"], untagged["safe-wildcard.txt"])

    # ---- what the files actually contain ------------------------------------

    def test_golden_output_for_a_known_source_tree(self):
        """Pins both line kinds. Fails if either generator half goes missing."""
        self.write_src(
            safe="de.nextlgsdp.com # SAFE: telemetry [REGION-SCOPED]\n"
                 "lgsmartad.com # SAFE: ad zone apex\n",
            strict="snu.lge.com # STRICT: OTA\n"
                   "de.lgeapi.com # STRICT: weak — region API [REGION-SCOPED]\n",
            zones="lge.com # ZONE: umbrella\n")
        out = build.dry_run()
        body = lambda name: [l for l in out[name].splitlines()
                             if l and not l.startswith("#")]
        # SAFE never carries a strict.txt family, and never a zone anchor.
        self.assertEqual(body("safe-wildcard.txt"),
                         [r"^[a-z][a-z]\.nextlgsdp\.com$"])
        # STRICT carries both tiers' families plus the zone anchors.
        self.assertEqual(body("strict-wildcard.txt"),
                         [r"^[a-z][a-z]\.lgeapi\.com$",
                          r"^[a-z][a-z]\.nextlgsdp\.com$",
                          r"(\.|^)lge\.com$"])

    def test_safe_file_carries_region_lines_only(self):
        """No whole-subtree line may reach the SAFE tier: zones are STRICT-only,
        and an exact-name entry like lgtvsdp.com must not become a subtree rule
        (docs/faq.md carves a store-comms exception out of exactly that reach)."""
        body = [l for l in build.dry_run()["safe-wildcard.txt"].splitlines()
                if l and not l.startswith("#")]
        self.assertTrue(body, "safe-wildcard.txt is empty")
        for line in body:
            with self.subTest(line=line):
                self.assertTrue(line.startswith("^[a-z][a-z]"), line)
        self.assertIn(r"^[a-z][a-z]\.nextlgsdp\.com$", body)

    def test_zone_anchors_mirror_zones_txt(self):
        zones = build.parse_src("zones.txt")
        body = [l for l in build.dry_run()["strict-wildcard.txt"].splitlines()
                if l.startswith("(")]
        self.assertEqual(len(body), len(zones))

    # ---- reach: the property that keeps this inside SAFE's promise ----------

    def test_region_line_reach_is_two_letter_prefixes_only(self):
        # Pi-hole's FTL matches unanchored (regexec), so search(), not match():
        # with match() a missing ^ would sail through this test.
        line = build.wildcard_lines(["nextlgsdp.com"], [])[0]
        region = re.compile(line)
        for hit in ("de.nextlgsdp.com", "br.nextlgsdp.com"):
            with self.subTest(host=hit):
                self.assertTrue(region.search(hit))
        # ngfts. is firmware transfer, ibs. is in-app billing, and the apex
        # itself is not SAFE's to block.
        for miss in ("nextlgsdp.com", "ngfts.nextlgsdp.com", "de.ibs.nextlgsdp.com",
                     "xde.nextlgsdp.com", "de.nextlgsdp.com.evil.test"):
            with self.subTest(host=miss):
                self.assertFalse(region.search(miss))

    def test_safe_region_line_matching_a_strict_host_is_a_hard_error(self):
        """su./am./ig..lge.com are STRICT and two letters wide: a SAFE tag on an
        lge.com host would put the OTA server behind a SAFE rule."""
        self.write_src(
            safe="kr.lge.com # SAFE: regional telemetry [REGION-SCOPED]\n",
            strict="su.lge.com # STRICT: OTA update server\n",
            zones="lge.com # ZONE: umbrella\n")
        with self.assertRaises(ValueError) as caught:
            build.dry_run()
        self.assertIn("su.lge.com", str(caught.exception))

    def test_every_line_is_valid_and_families_are_deduplicated(self):
        lines = build.wildcard_lines(["nextlgsdp.com", "nextlgsdp.com"], ["lge.com"])
        self.assertEqual(len(lines), 2)
        for line in lines:
            with self.subTest(line=line):
                re.compile(line)

    def test_family_under_a_zone_anchor_is_skipped(self):
        lines = build.wildcard_lines(["emp.lgsmartplatform.com"], ["lgsmartplatform.com"])
        self.assertEqual(lines, [r"(\.|^)lgsmartplatform\.com$"])

    def test_zone_anchor_deeper_than_two_labels_covers_its_descendants(self):
        # Last-two-labels dedupe missed an anchor deeper than the family's own
        # depth; the suffix boundary must still count it as covered.
        lines = build.wildcard_lines(["emp.reg.lgsmartplatform.com"],
                                     ["reg.lgsmartplatform.com"])
        self.assertEqual(lines, [r"(\.|^)reg\.lgsmartplatform\.com$"])

    # ---- condition 2: tag validation ---------------------------------------

    def test_malformed_tag_is_a_hard_error_never_silently_ignored(self):
        for tag in ("[REGION SCOPED]", "[region-scoped]", "[REGION-SCOPED: ar at]",
                    "[REGION-SCOPED"):
            with self.subTest(tag=tag):
                self.write_src(safe=f"de.nextlgsdp.com # SAFE: telemetry {tag}\n")
                with self.assertRaises(ValueError) as caught:
                    build.region_families("safe.txt")
                self.assertIn("safe.txt:1", str(caught.exception))

    def test_tag_survives_a_later_decommission_note(self):
        """src/ entries grow a trailing "| DECOMMISSIONED ..." note; 9 of 21 SAFE
        entries carry one today. A tagged host getting one must not break the
        build, so the tag's position in the annotation is free."""
        self.write_src(
            safe="de.nextlgsdp.com # SAFE: telemetry [REGION-SCOPED] | DECOMMISSIONED "
                 "2026-10-01: NXDOMAIN on Google+Cloudflare DoH\n")
        self.assertEqual(build.region_families("safe.txt"), ["nextlgsdp.com"])

    def test_prose_and_urls_are_not_mistaken_for_a_tag(self):
        """CONTRIBUTING requires an annotation on every line; the words and the
        evidence URLs people write there must stay legal."""
        self.write_src(
            safe="xx.lgeapi.com # SAFE: region-scoped promo beacon\n"
                 "de.lgtvsdp.com # SAFE: see https://example.test/region-scoped-endpoints\n")
        self.assertEqual(build.region_families("safe.txt"), [])

    def test_duplicate_tag_on_one_line_rejected(self):
        self.write_src(
            safe="de.nextlgsdp.com # SAFE: x [REGION-SCOPED] y [REGION-SCOPED]\n")
        with self.assertRaises(ValueError):
            build.region_families("safe.txt")

    def test_tag_without_two_letter_first_label_rejected(self):
        for host in ("lgtvsdp.com", "ngfts.nextlgsdp.com", "initscr.lge.com"):
            with self.subTest(host=host):
                self.write_src(safe=f"{host} # SAFE: x [REGION-SCOPED]\n")
                with self.assertRaises(ValueError) as caught:
                    build.region_families("safe.txt")
                self.assertIn("two-letter first label", str(caught.exception))

    def test_forbidden_family_tag_is_a_hard_error(self):
        """us.lgtvsdp.com is audited and shipped, but docs/faq.md's store
        carve-out keeps de.lgtvsdp.com reachable; a tag would emit
        ^[a-z][a-z]\\.lgtvsdp\\.com$ and block exactly that host."""
        self.write_src(
            safe="us.lgtvsdp.com # SAFE: SDP telemetry [REGION-SCOPED]\n")
        with self.assertRaises(ValueError) as caught:
            build.dry_run()
        message = str(caught.exception)
        self.assertIn("safe.txt:1", message)
        self.assertIn("lgtvsdp.com", message)
        # direct callers of the emitter hit the same guard
        with self.assertRaises(ValueError):
            build.wildcard_lines(["lgtvsdp.com"], [])

    def test_trailing_dot_does_not_produce_a_dead_regex(self):
        """parse_src tolerates one trailing dot; so must this, or the family
        silently compiles to a pattern that can never match."""
        self.write_src(safe="de.nextlgsdp.com. # SAFE: telemetry [REGION-SCOPED]\n")
        self.assertEqual(build.region_families("safe.txt"), ["nextlgsdp.com"])

    def test_tag_in_zones_txt_is_rejected_not_ignored(self):
        # The apex form trips the two-letter check; the region-prefixed form has
        # a family to return, so only an explicit reject catches it.
        for zone in ("lgeapi.com # ZONE: umbrella [REGION-SCOPED]",
                     "de.lgeapi.com # ZONE: region API umbrella [REGION-SCOPED]"):
            with self.subTest(zone=zone):
                self.write_src(safe="", strict="", zones=zone + "\n")
                with self.assertRaises(ValueError):
                    build.dry_run()

    def test_tag_on_a_line_with_no_entry_rejected(self):
        self.write_src(safe="# families are [REGION-SCOPED] in general\n")
        with self.assertRaises(ValueError) as caught:
            build.region_families("safe.txt")
        self.assertIn("no entry", str(caught.exception))

    def test_tag_on_an_entry_without_evidence_annotation_rejected(self):
        self.write_src(safe="de.nextlgsdp.com # [REGION-SCOPED]\n")
        with self.assertRaises(ValueError):
            build.region_families("safe.txt")

    def test_untagged_region_shaped_host_never_expands(self):
        """ad. is an ad host and su. is the OTA server, not Andorra and Sudan."""
        self.write_src(
            safe="ad.lgappstv.com # SAFE: ad delivery\nsu.lge.com # SAFE: OTA\n")
        self.assertEqual(build.region_families("safe.txt"), [])

    # ---- condition 1: the header -------------------------------------------

    def test_header_states_the_three_things_review_asked_for(self):
        head = build.dry_run()["safe-wildcard.txt"].split("\n\n")[0]
        self.assertIn("NOT AN ADLIST", head)
        self.assertIn("already carry their", head)      # derived from audited entries
        self.assertIn("Optional and additive", head)    # drop it, nothing changes
        self.assertIn("not a", head)                    # ...and not a replacement
        self.assertIn("keep the list subscribed", head)
        out = build.dry_run()["safe-wildcard.txt"]
        body = [l for l in out.splitlines() if l and not l.startswith("#")]
        self.assertIn(f"Entries: {len(body)}", head)    # count matches the body

    def test_strict_header_carries_the_widening_warning(self):
        strict_head = build.dry_run()["strict-wildcard.txt"].split("\n\n")[0]
        self.assertIn("WIDENING WARNING", strict_head)
        self.assertIn("whole zones", strict_head)
        self.assertIn("never listed or audited", strict_head)
        self.assertIn("lists/strict-domains.txt", strict_head)
        self.assertIn("docs/faq.md", strict_head)
        self.assertIn("I want STRICT but keep the LG Content Store", strict_head)
        safe_head = build.dry_run()["safe-wildcard.txt"].split("\n\n")[0]
        self.assertNotIn("WIDENING WARNING", safe_head)


if __name__ == "__main__":
    unittest.main()
