# LG TV Blocklist Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish `github.com/furkan-bayrak/lg-tv-blocklist` — a curated, evidence-based LG TV/webOS telemetry blocklist with two tiers (safe/strict), compiled to three formats (plain domains, hosts, adblock) by a pure-stdlib build script, validated by CI, seeded from the G1 audit data.

**Architecture:** Source-of-truth text files under `src/` (`safe.txt`, `strict.txt` = delta, `zones.txt` = strict-only zone anchors) → deterministic `scripts/build.py` → generated `lists/` artifacts (never hand-edited) → GitHub Actions regenerates + commits artifacts on merge to main, validates on PRs. Content licensed CC BY 4.0, scripts MIT.

**Tech Stack:** Python 3 (stdlib only), GitHub Actions, git, gh CLI 2.94+.

## Global Constraints

- Local repo: `C:\Users\furka\projects\lg-tv-blocklist`, branch `main`, owner `furkan-bayrak`, email `<gh-id>+furkan-bayrak@users.noreply.github.com` (already configured repo-local).
- Every `src/` line MUST carry an inline comment: `domain # <TAG>: <function> — <evidence>`. Tags: `SAFE`, `STRICT`, `ZONE`. Weak-evidence entries say `weak`.
- `strict.txt` = DELTA ONLY. Compile: strict = safe ∪ strict.txt. Never duplicate safe content in strict.txt.
- `zones.txt` = strict-only apex domains; emitted as apex lines in domains/hosts outputs and as `||zone^` in adblock output. Never merged into safe.
- Exact-name semantics for domains/hosts outputs; `||x^` in adblock output.
- Formats emitted per tier: `{tier}-domains.txt`, `{tier}-hosts.txt` (`0.0.0.0 d`), `{tier}-adblock.txt` (`||d^`) + `SHA256SUMS`.
- build.py = Python 3 stdlib ONLY (argparse, hashlib, pathlib, re, sys, datetime). No third-party deps anywhere. Tests runnable without pytest: `python scripts/test_build.py`.
- All committed text files LF (`.gitattributes: * text=auto eol=lf`).
- License: content `LICENSE` = CC BY 4.0 (full legalcode), scripts `LICENSE-MIT` = MIT. Generated-list headers note CC BY 4.0.
- Generated headers: `# Title`, `# Updated: <YYYY-MM-DD HH:MM UTC>`, `# Entries: N`, `# License: CC BY 4.0` (timestamp injected on build only; `check` never touches disk).
- Never hand-edit `lists/`; contributors edit `src/` only.

---

### Task 1: Line-ending policy, licenses, and repo hygiene

**Files:**
- Create: `.gitattributes`, `.gitignore`, `LICENSE`, `LICENSE-MIT`

**Interfaces:**
- Produces: LF policy for all future commits; license texts referenced by generated-file headers and README.

- [ ] **Step 1: Create `.gitattributes`**

```
* text=auto eol=lf
```

- [ ] **Step 2: Create `.gitignore`**

```
__pycache__/
*.pyc
```

- [ ] **Step 3: Fetch CC BY 4.0 legalcode into `LICENSE`**

Run: `Invoke-WebRequest -Uri "https://creativecommons.org/licenses/by/4.0/legalcode.txt" -OutFile LICENSE` (PowerShell) or `curl -fsSL https://creativecommons.org/licenses/by/4.0/legalcode.txt -o LICENSE`
Verify: file starts with `Attribution 4.0 International` and contains `https://creativecommons.org/licenses/by/4.0/legalcode` near the top.

- [ ] **Step 4: Create `LICENSE-MIT`**

```
MIT License

Copyright (c) 2026 furkan-bayrak

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

- [ ] **Step 5: Commit**

```bash
git add .gitattributes .gitignore LICENSE LICENSE-MIT
git commit -m "chore: repo hygiene, LF policy, licenses (CC BY 4.0 + MIT)"
```

---

### Task 2: Seed content — src/safe.txt, src/strict.txt, src/zones.txt

**Files:**
- Create: `src/safe.txt`, `src/strict.txt`, `src/zones.txt`

**Interfaces:**
- Consumes: annotation contract from Global Constraints.
- Produces: three source files parsed by build.py Task 4. Content is authoritative — matches spec §3.3.

- [ ] **Step 1: Create `src/safe.txt`**

```text
# LG TV Blocklist — SAFE tier (stock-TV-safe: store, app updates, logins,
# Netflix/Prime/HBO/YouTube keep working). Blocks proven telemetry/ad/ACR/promo
# hostnames only. Subdomain-level; exact-name semantics.
# Evidence basis: G1 (webOS) audit — 44.8k-packet capture, 267k-query AdGuard
# log, live blocking verified against Netflix/Prime/HBO/YouTube playback.
# License: CC BY 4.0. Additions require an inline annotation + evidence.

cdpbeacon.lgtvcommon.com # SAFE: telemetry/ACR beacon (6-min heartbeat pattern observed)
ads.lgtvcommon.com # SAFE: ad delivery (querylog family)
homeprv.lgtvcommon.com # SAFE: home-screen provisioning/promos
eic.nudge.lgtvcommon.com # SAFE: nudge/notification telemetry
recommend.lgtvcommon.com # SAFE: recommendations/promos
eic.wiseconfig.lgtvcommon.com # SAFE: cloud-config telemetry (blocked live, apps fine)
eic.lgtviot.com # SAFE: IoT telemetry (largest observed family, ~5.1k queries)
eic.api.lgtviot.com # SAFE: IoT telemetry API
eic.tv.wiselg.com # SAFE: TV telemetry (blocked live, apps fine)
de.nextlgsdp.com # SAFE: SDP region endpoint, telemetry
lgsmartad.com # SAFE: dedicated ad zone apex (whole family is ads)
de.info.lgsmartad.com # SAFE: ad info endpoint
de.emp.lgsmartplatform.com # SAFE: smart-platform telemetry
smart.adtvc.app # SAFE: ad serving (adtvc.app family)
adsdtvc.com # SAFE: ad zone
ad.lgappstv.com # SAFE: ad delivery on the lgappstv store CDN family (store unaffected)
us.lgtvsdp.com # SAFE: SDP telemetry, region endpoint
lgtvsdp.com # SAFE: SDP telemetry apex (service delivery platform beacons)
initscr.lge.com # SAFE: initial-setup telemetry (boot-time only)
```

- [ ] **Step 2: Create `src/strict.txt`**

```text
# LG TV Blocklist — STRICT tier DELTA (compiled as safe + this file).
# Rooted/privacy-max users: zero LG communication intended. Breaks BY DESIGN:
# firmware OTA updates, ThinQ cloud sync, LG Channels. Store may degrade.
# Weak-evidence entries are kept here by policy (never risk SAFE on a guess).
# License: CC BY 4.0.

snu.lge.com # STRICT: firmware OTA check server
su.lge.com # STRICT: OTA update server
su-dev.lge.com # STRICT: OTA update server (dev channel)
su-ssl.lge.com # STRICT: OTA update server (SSL)
ngfts.lge.com # STRICT: firmware/content file transfer
gfts.lge.com # STRICT: file transfer service
eic-ngfts.lge.com # STRICT: update-check/file-transfer telemetry (boot burst)
eic-gfts.lge.com # STRICT: file-transfer telemetry
ngfts.nextlgsdp.com # STRICT: update transfer on SDP family
eic-ngfts.tv.wiselg.com # STRICT: update transfer (wiselg family)
lss.lgthinq.com # STRICT: ThinQ cloud sync backend
eic-op-lss.lgthinq.com # STRICT: ThinQ operations telemetry
bss.lgechannel.com # STRICT: LG Channels (FAST) backend — feature kill by design
lgechannel.com # STRICT: LG Channels apex — feature kill by design
lgtvonline.lge.com # STRICT: weak — post-boot only, function unproven
am.lge.com # STRICT: weak — observed, function unproven
ig.lge.com # STRICT: weak — observed, function unproven
service.lgtvcommon.com # STRICT: weak — common-services endpoint, store interplay unproven
a.lgappstv.com # STRICT: weak — store-CDN-adjacent, app-update function unproven
lgappstv.com # STRICT: weak — store CDN apex (blocking apex = exact-name only in hosts/domains)
fms.lgunifiedsmart.com # STRICT: weak — smart-family messaging service
de.lgeapi.com # STRICT: weak — region API, store/billing interplay unproven
de.ibs.nextlgsdp.com # STRICT: weak — possible in-app billing path (store risk)
eic-ocp.lgtviot.com # STRICT: weak — unknown (DNS only; unrelated to the local panel-compensation daemon)
eic.cdplauncher.lgtvcommon.com # STRICT: weak — content-launcher/CDP service
eic.lgchhomeapp.lgtvcommon.com # STRICT: weak — home-app service
rdx2.lgtvsdp.com # STRICT: weak — unknown
```

- [ ] **Step 3: Create `src/zones.txt`**

```text
# LG TV Blocklist — STRICT-only zone anchors. Apex domains whose FULL subdomain
# space we do not enumerate. In the adblock output these become ||zone^ (whole
# zone); in domains/hosts outputs they block the apex only (exact-name
# semantics) — documented in README.
# License: CC BY 4.0.

lge.com # ZONE: umbrella zone — kills all lge.com subdomains in adblock format
lgeapi.com # ZONE: region API umbrella
wiselg.com # ZONE: TV/wiselg telemetry umbrella
lgthinq.com # ZONE: ThinQ umbrella
lgtviot.com # ZONE: IoT umbrella
nextlgsdp.com # ZONE: SDP umbrella
lgunifiedsmart.com # ZONE: smart-family umbrella
```

- [ ] **Step 4: Sanity-check the seed**

Run: `Select-String -Path src\*.txt -Pattern '^([a-z0-9.-]+) # (SAFE|STRICT|ZONE):' | Measure-Object`
Expected: 19 SAFE lines, 26 STRICT lines, 7 ZONE lines. No duplicate hostnames across safe.txt and strict.txt (check by eye: every strict entry differs from every safe entry).

- [ ] **Step 5: Commit**

```bash
git add src/
git commit -m "feat: seed safe/strict/zones content from G1 audit evidence"
```

---

### Task 3: build.py — parser, validator, compiler

**Files:**
- Create: `scripts/build.py`

**Interfaces:**
- Consumes: `src/safe.txt`, `src/strict.txt`, `src/zones.txt` (Task 2 format).
- Produces:
  - `parse_src(file: Path) -> list[str]` — annotated lines → validated lowercase hostnames; raises `ValueError` with line numbers on dupes/malformed/non-LG entries.
  - `compile_tier(tier: str, domains: list[str], zones: list[str]) -> dict[str, str]` — returns `{<tier>-domains.txt: str, <tier>-hosts.txt: str, <tier>-adblock.txt: str}` for tiers `safe` and `strict` (zones only ever merged into strict).
  - `make_headers(title: str, entries: int) -> list[str]`
  - CLI: `python scripts/build.py build|check`; build writes `lists/` + `SHA256SUMS`, check validates + dry-runs in memory (no disk writes), exit 1 on any error.
- Follows spec §5 (modes `build`/`check`; `test` lives in Task 4's test file).

- [ ] **Step 1: Write `scripts/build.py`**

```python
#!/usr/bin/env python3
"""Compile LG TV blocklist source files into distributable formats.

Pure stdlib. Formats: plain domains, hosts (0.0.0.0), adblock (||x^).
strict = safe + strict-delta (+ zone anchors). Zones become apex lines in
domains/hosts outputs and ||zone^ in the adblock output.
"""
import argparse
import hashlib
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
LISTS = ROOT / "lists"
HOSTNAME_RE = re.compile(r"^(?=.{1,253}\.?$)[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)*\.?$")
LG_SUFFIXES = ("lge.com", "lgappstv.com", "lgtvsdp.com", "lgtvcommon.com",
               "lgtviot.com", "lgthinq.com", "nextlgsdp.com", "lgsmartad.com",
               "lgsmartplatform.com", "lgeapi.com", "wiselg.com",
               "lgechannel.com", "adtvc.app", "adsdtvc.com",
               "lgunifiedsmart.com")

LICENSE_LINE = "# License: CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/)"


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def parse_src(filename: str) -> list[str]:
    """Return sorted, validated hostnames from an annotated src file.

    Raises ValueError (with line numbers) on duplicate, malformed, or
    non-LG-related hostnames.
    """
    path = SRC / filename
    seen: dict[str, int] = {}
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        host = line.lower().rstrip(".")
        if not HOSTNAME_RE.match(host):
            raise ValueError(f"{filename}:{lineno}: malformed hostname: {line!r}")
        if not host.endswith(LG_SUFFIXES):
            raise ValueError(f"{filename}:{lineno}: not an LG family hostname: {host}")
        if host in seen:
            raise ValueError(f"{filename}:{lineno}: duplicate of {host} (first at line {seen[host]})")
        seen[host] = lineno
    return sorted(seen)


def make_headers(title: str, entries: int) -> list[str]:
    return [
        f"# Title: {title}",
        f"# Updated: {now_utc()}",
        f"# Entries: {entries}",
        LICENSE_LINE,
        "",
    ]


def compile_tier(tier: str, domains: list[str], zones: list[str]) -> dict[str, str]:
    """Return output filename -> content for one tier."""
    if tier == "strict":
        domains = sorted(set(domains) | set(zones))
    title = f"LG TV Blocklist ({tier})"
    outputs: dict[str, str] = {}
    outputs[f"{tier}-domains.txt"] = "\n".join(make_headers(title, len(domains)) + domains) + "\n"
    outputs[f"{tier}-hosts.txt"] = "\n".join(
        make_headers(title, len(domains)) + [f"0.0.0.0 {d}" for d in domains]) + "\n"
    outputs[f"{tier}-adblock.txt"] = "\n".join(
        make_headers(title, len(domains)) + [f"||{d}^" for d in domains]) + "\n"
    return outputs


def load_all() -> tuple[list[str], list[str], list[str]]:
    safe = parse_src("safe.txt")
    strict_delta = parse_src("strict.txt")
    zones = parse_src("zones.txt")
    overlap = set(safe) & set(strict_delta)
    if overlap:
        raise ValueError(f"strict.txt duplicates safe.txt: {sorted(overlap)} (strict is a delta)")
    if set(zones) & set(safe):
        raise ValueError("zones.txt overlaps safe.txt — zones are strict-only")
    return safe, strict_delta, zones


def dry_run() -> dict[str, str]:
    safe, strict_delta, zones = load_all()
    all_outputs: dict[str, str] = {}
    all_outputs.update(compile_tier("safe", safe, []))
    all_outputs.update(compile_tier("strict", safe + strict_delta, zones))
    return all_outputs


def build() -> None:
    all_outputs = dry_run()
    LISTS.mkdir(exist_ok=True)
    for name, content in sorted(all_outputs.items()):
        (LISTS / name).write_text(content, encoding="utf-8", newline="\n")
    checksums = []
    for name in sorted(all_outputs):
        digest = hashlib.sha256((LISTS / name).read_bytes()).hexdigest()
        checksums.append(f"{digest}  {name}")
    (LISTS / "SHA256SUMS").write_text("\n".join(checksums) + "\n", encoding="utf-8")
    for name in sorted(all_outputs):
        print(f"wrote lists/{name}")


def check() -> None:
    safe, strict_delta, zones = load_all()
    outputs = dry_run()
    safe_n = len(safe)
    strict_n = len(set(safe) | set(strict_delta) | set(zones))
    print(f"check OK: safe={safe_n} strict={strict_n} zone-anchors={len(zones)} "
          f"outputs={len(outputs)}")
    print(f"source files: {[p.name for p in sorted(SRC.glob('*.txt'))]}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compile LG TV blocklists")
    parser.add_argument("mode", choices=["build", "check"], help="build writes lists/; check validates only")
    args = parser.parse_args(argv)
    try:
        if args.mode == "build":
            build()
        else:
            check()
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run `check` — expect OK and no files written**

Run: `python scripts/build.py check`
Expected: `check OK: safe=19 strict=52 zone-anchors=7 outputs=6` (52 = 19 safe + 26 strict-delta + 7 zones) and exit code 0. Confirm no `lists/` directory appeared: `Test-Path lists` → False.

- [ ] **Step 3: Verify the delta rule fails loudly**

Temporarily append `cdpbeacon.lgtvcommon.com # SAFE dup test` to `src/strict.txt`, run `python scripts/build.py check`, expect `ERROR: strict.txt duplicates safe.txt: ['cdpbeacon.lgtvcommon.com']` and exit code 1. Then remove the appended line and re-run check → OK.

- [ ] **Step 4: Commit**

```bash
git add scripts/build.py
git commit -m "feat: build.py compiles src into 3 formats x 2 tiers"
```

---

### Task 4: Tests — scripts/test_build.py

**Files:**
- Create: `scripts/test_build.py`

**Interfaces:**
- Consumes: `build.py` functions `parse_src`, `compile_tier`, `make_headers`, `load_all`, `dry_run`.
- Produces: runnable suite — `python scripts/test_build.py` → exit 0. Used by CI (Task 6).

- [ ] **Step 1: Write `scripts/test_build.py`**

```python
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
        self.assertIn("duplicate", str(ctx.exception))
        self.assertIn("line 2", str(ctx.exception))


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
        self.assertEqual(out["safe-hosts.txt"].splitlines()[4], "0.0.0.0 a.lge.com")


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
```

- [ ] **Step 2: Run the suite — expect all pass**

Run: `python scripts/test_build.py`
Expected: `OK (Ran N tests)` — every test green, exit 0.

- [ ] **Step 3: Commit**

```bash
git add scripts/test_build.py
git commit -m "test: build.py validation and compilation suite"
```

---

### Task 5: Generate lists/ and add README, CONTRIBUTING, issue templates, CI

**Files:**
- Create: `.github/ISSUE_TEMPLATE/01_new_domain.md`, `.github/ISSUE_TEMPLATE/02_breakage.md`, `.github/workflows/build.yml`, `README.md`, `CONTRIBUTING.md`
- Generate: `lists/*` (via build.py)

**Interfaces:**
- Consumes: Task 3 CLI (`build` mode), Task 2 src files.
- Produces: committed artifacts + contributor-facing docs + CI wiring. Raw URLs used by README resolve only after Task 7 publishes the repo.

- [ ] **Step 1: Generate the lists**

Run: `python scripts/build.py build` (fallback if `python` is absent: `py -3 scripts/build.py build`)
Verify: six files + `SHA256SUMS` exist under `lists/`; spot-check:
`Get-Content lists\safe-domains.txt | Select-Object -First 5` shows header then first domain; `Get-Content lists\strict-adblock.txt | Select-Object -Last 3` shows `||lgunifiedsmart.com^` last.

- [ ] **Step 2: Create `.github/workflows/build.yml`**

```yaml
name: Build blocklists

on:
  pull_request:
    paths: ['src/**', 'scripts/**']
  push:
    branches: [main]
    paths: ['src/**', 'scripts/**']
  workflow_dispatch:

concurrency:
  group: lists
  cancel-in-progress: false

permissions:
  contents: write

jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Validate source + compile dry-run
        run: python3 scripts/build.py check
      - name: Run test suite
        run: python3 scripts/test_build.py

  publish:
    if: github.event_name != 'pull_request'
    needs: check
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Compile lists
        run: python3 scripts/build.py build
      - name: Commit generated lists
        run: |
          if ! git diff --quiet -- lists; then
            git config user.name "github-actions[bot]"
            git config user.email "github-actions[bot]@users.noreply.github.com"
            git add lists/
            git commit -m "chore: regenerate blocklists [skip ci]"
            git push
          fi
```

- [ ] **Step 3: Create `.github/ISSUE_TEMPLATE/01_new_domain.md`**

```markdown
---
name: New LG telemetry domain
about: Propose a domain for the blocklist — evidence required
title: '[New domain] '
labels: new-domain
assignees: ''
---

**Domain(s)**
<!-- e.g. eic.example.lgtviot.com -->

**Device / webOS version**

**Evidence** (one of)
- [ ] AdGuard/Pi-hole querylog snippet (domain + timestamp + client)
- [ ] Packet capture (dns.qry.name or TLS SNI line)
- [ ] Other (describe)

**Suggested tier**
- [ ] SAFE — telemetry/ad, store-safe
- [ ] STRICT — update/ThinQ/Channels/feature-affecting
- [ ] Not sure — please classify

**Symptom if you block it** (what you tested still worked / broke)
```

- [ ] **Step 4: Create `.github/ISSUE_TEMPLATE/02_breakage.md`**

```markdown
---
name: Breakage report (false positive)
about: Something stopped working after using the list
title: '[Breakage] '
labels: breakage
assignees: ''
---

**App / feature affected**

**Tier in use**
- [ ] SAFE
- [ ] STRICT

**Symptom** (e.g. "Netflix shows error nw-2-5 on launch", "Content Store won't load")

**List entry you suspect** (leave blank if unknown)

**Did reverting that entry fix it?**
- [ ] Yes
- [ ] Not tested yet

**Device / webOS version**
```

- [ ] **Step 5: Create `CONTRIBUTING.md`**

```markdown
# Contributing

Thanks for helping maintain the LG TV blocklist. Two ground rules:

## 1. Evidence over guesses

This list is built from empirical observation, not speculation. Before adding
a domain, collect evidence:

- **Querylog**: AdGuard/Pi-hole log line showing the domain, who queried it,
  and when (a single random hit is not enough; boot-burst or heartbeat
  patterns are ideal).
- **Capture**: `dns.qry.name` or TLS SNI from a packet capture.
- **Repro**: what you did to trigger it (power-on, standby, app launch).

If you only have a hunch, open an issue with the `new-domain` template
instead of a PR — maintainers can verify from their own probes.

## 2. Edit src/, never lists/

- `src/safe.txt` — telemetry/ad hostnames that are safe for stock TVs.
- `src/strict.txt` — the DELTA over safe (updates, ThinQ, LG Channels,
  weak-evidence entries). Do not repeat safe entries here.
- `src/zones.txt` — strict-only family apexes for whole-zone blocking in the
  adblock format.

Every line needs an inline annotation:

    snu.lge.com # STRICT: firmware OTA check server

Line format: hostname, space, `#`, space, `TAG: function — evidence`. Tags:
`SAFE`, `STRICT`, `ZONE`. Lowercase only, no trailing dot, no wildcards —
this list is exact-name (see README "Format semantics"). Weak-evidence
entries are tagged `weak` and belong in strict.txt by policy.

CI runs `python3 scripts/build.py check` and the test suite on every PR —
malformed, duplicate, non-LG, or tier-misplaced lines fail the build.

## Workflow

1. Fork, branch off `main`.
2. Edit one or more files under `src/`.
3. Run `python3 scripts/build.py check && python3 scripts/test_build.py` locally.
4. Open the PR. The merge job regenerates `lists/` automatically — never
   commit generated files yourself.

## License

Content is CC BY 4.0, scripts MIT — see LICENSE and LICENSE-MIT.
```

- [ ] **Step 6: Create `README.md`**

```markdown
# LG TV Blocklist

Curated, evidence-based DNS blocklist for LG webOS TV telemetry, ads, and
phone-home traffic. Born from a two-week root-level audit of an LG G1:
44,800-packet captures, 267,000-query DNS logs, per-service investigation.
Every entry carries an annotation explaining what it blocks and the evidence.

Not affiliated with LG Electronics. LG is a trademark of LG Corp.

## Lists

| List | Domains (Pi-hole/NextDNS) | Hosts (/etc/hosts) | AdBlock (AdGuard Home/uBO) |
|---|---|---|---|
| **SAFE** — blocks telemetry/ads/ACR; store, app updates, Netflix/Prime/HBO/YouTube keep working | [safe-domains.txt](https://raw.githubusercontent.com/furkan-bayrak/lg-tv-blocklist/main/lists/safe-domains.txt) | [safe-hosts.txt](https://raw.githubusercontent.com/furkan-bayrak/lg-tv-blocklist/main/lists/safe-hosts.txt) | [safe-adblock.txt](https://raw.githubusercontent.com/furkan-bayrak/lg-tv-blocklist/main/lists/safe-adblock.txt) |
| **STRICT** — everything in SAFE plus OTA updates, ThinQ cloud, LG Channels. Rooted/privacy-max users only. **Things break on purpose.** | [strict-domains.txt](https://raw.githubusercontent.com/furkan-bayrak/lg-tv-blocklist/main/lists/strict-domains.txt) | [strict-hosts.txt](https://raw.githubusercontent.com/furkan-bayrak/lg-tv-blocklist/main/lists/strict-hosts.txt) | [strict-adblock.txt](https://raw.githubusercontent.com/furkan-bayrak/lg-tv-blocklist/main/lists/strict-adblock.txt) |

Checksums: [SHA256SUMS](https://raw.githubusercontent.com/furkan-bayrak/lg-tv-blocklist/main/lists/SHA256SUMS)

## Install

**Pi-hole** (v5/v6): Adlists → Add — paste the `-domains.txt` URL of your
tier, then `pihole -g`.

**AdGuard Home**: Filters → DNS blocklists → Add blocklist — paste the
`-adblock.txt` URL.

**NextDNS / Unbound / Technitium**: import the `-domains.txt` URL.

**Rooted webOS**: use the `-hosts.txt` entries in `/etc/hosts`. Advanced:
webosbrew init.d hook that rewrites the (tmpfs) hosts file at every boot —
see [docs](https://github.com/webosbrew/initrd-patches) for the init.d
mechanism; the domain set to mirror is `safe.txt` (or `strict.txt` for the
full lockdown).

## What breaks in STRICT (read this)

| Feature | SAFE | STRICT |
|---|---|---|
| Netflix / Prime / HBO / YouTube | works | works |
| LG Content Store | works | may degrade |
| Firmware OTA updates | works | blocked |
| ThinQ app / voice assistant cloud sync | works | blocked |
| LG Channels | works | blocked |
| LG account login | works | may fail |

## Format semantics

- `-domains.txt` / `-hosts.txt`: **exact-name** — `snu.lge.com` blocks that
  host only, not the whole zone.
- `-adblock.txt`: `||snu.lge.com^` also matches subdomains of that name.
- STRICT zone anchors (see `src/zones.txt`) only achieve whole-zone blocking
  in the adblock format; in domains/hosts they block the apex domain.

## The two caveats every LG owner should know

1. **LG hardcodes public resolvers.** webOS daemons have been observed using
   8.8.8.8 / 1.1.1.1 directly, bypassing your router's DNS entirely. A DNS
   blocklist alone is not a guarantee: block outbound port 53 and 853
   (DoT) at the firewall for the TV, or run the hosts-file approach on a
   rooted TV, where `0.0.0.0` entries win over any remote resolver.
2. **Exact-name vs wildcard.** Because we curate subdomain-level entries,
   whole-family coverage depends on enumeration. If your TV shows traffic to
   an LG domain not on the list, open a `new-domain` issue — that's exactly
   how the list grows.

## Annotated domains

The source of truth is annotated: `src/safe.txt`, `src/strict.txt`,
`src/zones.txt`. Reading the comments there tells you what every entry does
and the evidence behind it. The tier table above summarizes the trade-offs.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) — evidence required, edit `src/`
only, CI does the rest. Issue templates: [new domain](.github/ISSUE_TEMPLATE/01_new_domain.md) /
[breakage](.github/ISSUE_TEMPLATE/02_breakage.md).

## License

Content and generated lists: [CC BY 4.0](LICENSE). Scripts and workflows:
[MIT](LICENSE-MIT).
```

- [ ] **Step 7: Re-run check and commit everything**

Run: `python scripts/build.py check && python scripts/test_build.py` → both green.

```bash
git add lists/ .github/ README.md CONTRIBUTING.md
git commit -m "feat: generated lists, README, CONTRIBUTING, issue templates, CI workflow"
```

Verify commit contains `lists/` with six files + SHA256SUMS.

---

### Task 6: Publish to GitHub

**Files:**
- None (remote only).

**Interfaces:**
- Consumes: committed `main` with all artifacts.
- Produces: public repo `furkan-bayrak/lg-tv-blocklist`, push successful, repository settings (description, topics), README raw URLs live.

- [ ] **Step 1: Create and push the repository**

Run: `gh repo create furkan-bayrak/lg-tv-blocklist --public --source C:\Users\furka\projects\lg-tv-blocklist --push --description "Curated DNS blocklist for LG webOS TV telemetry, ads and phone-home traffic (safe + strict tiers)"`
Expected: prints `https://github.com/furkan-bayrak/lg-tv-blocklist`.

- [ ] **Step 2: Add topics and verify**

Run: `gh repo edit furkan-bayrak/lg-tv-blocklist --add-topic blocklist,dns,privacy,lg-tv,webos,adguard-home,pi-hole`
Verify: `gh repo view furkan-bayrak/lg-tv-blocklist --json url,visibility,topics` shows public + topics.

- [ ] **Step 3: Verify raw URLs serve**

Run: `Invoke-WebRequest -UseBasicParsing "https://raw.githubusercontent.com/furkan-bayrak/lg-tv-blocklist/main/lists/SHA256SUMS" | Select-Object -ExpandProperty Content`
Expected: six checksum lines.

- [ ] **Step 4: Verify the GitHub Actions run went green**

Run: `gh run list --repo furkan-bayrak/lg-tv-blocklist --limit 1`
Expected: latest run `success` (the publish job on initial push; if the auto-commit found no diff it still completes). If a `publish` commit happened, confirm it did not re-trigger a loop: `gh run list --repo furkan-bayrak/lg-tv-blocklist --limit 5` shows at most the push runs (bot commit has `[skip ci]`).

---

## Self-review notes

- Spec §3.1/3.2 → Task 2 (delta-only strict, zones) + Task 3 validation (overlap checks in `load_all`).
- Spec §3.3 seed tables → Task 2 Step 1–3 (all 19 SAFE + 26 STRICT + 7 ZONE rows; `service.lgtvcommon.com` moved to STRICT as weak per annotation contract; `lgtvcommon.com` intentionally not a zone — note in README caveats stays as-is because the FAQ link covers enumeration; strict rows are never duplicated in safe).
- Spec §5 → Task 3 (`build`/`check` modes, in-memory check, per-build header timestamp, no artifact diffing).
- Spec §6 → Task 5 Step 2 workflow (PR check job, merge publish job, `[skip ci]`, concurrency group, no secrets).
- Spec §7 → Task 5 Step 6 README.
- Spec §8 → Task 5 Steps 3–5 (templates + CONTRIBUTING).
- Spec §9 → Task 1 (LICENSE + LICENSE-MIT) and header line in build.py.
- Spec §10 → Task 6 publish; Task 5 Step 1 first local build.
- Spec §11 open questions: zone wording resolved in Task 2 Step 3 (7 anchors as approved in spec §3.3); GitHub identity resolved (`furkan-bayrak`, gh authed).
