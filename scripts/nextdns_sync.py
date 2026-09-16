#!/usr/bin/env python3
"""Bulk-add list domains to a NextDNS profile denylist, via the NextDNS API.

NextDNS's web UI takes one domain per entry, so the 116-entry strict list is
not realistically pasteable by hand -- the API is the only bulk path. This
script syncs a local list file into one profile's denylist and is
ADDITIVE-ONLY: it never removes, disables or reorders anything already there,
and there is no prune. Dry-run is the default.

Verified against the official API documentation (https://nextdns.github.io/api/,
retrieved 2026-09-16):

    Endpoint  https://api.nextdns.io/profiles/<profile>/denylist
    Auth      X-Api-Key header on every call. The key is read from the
              NEXTDNS_API_KEY environment variable only -- never a flag,
              never written to disk, never echoed.
    List      GET returns {"data": [{"id": "<domain>", "active": true}, ...]},
              paginated via meta.pagination.cursor.
    Add       POST one entry; body {"id": "<domain>"} (id is the only field
              the documented schema requires).
    Errors    the docs warn that *user* errors -- including "invalid domain"
              when adding to the denylist -- come back as HTTP 200 with
              {"errors": [...]}, not as 4xx, so a 2xx alone is not success.
    Limits    no published numbers ("reasonable use"); community reports use
              X-RateLimit-* response headers and HTTP 429 with Retry-After.
              This script paces writes (--delay, default 0.5s) and backs off
              on 429 before reporting the entry as failed.

Usage:
    NEXTDNS_API_KEY=... python scripts/nextdns_sync.py --profile abc123
    NEXTDNS_API_KEY=... python scripts/nextdns_sync.py --profile abc123 --apply
    python scripts/nextdns_sync.py --file lists/safe-domains.txt   # offline preview

Exit codes: 0 ok; 1 one or more API operations failed; 2 usage or config
error (missing key or profile for --apply, unreadable/empty list file).
Stdlib only, like the rest of scripts/. Install guide: docs/install.md.
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_FILE = ROOT / "lists" / "strict-domains.txt"
API_BASE = "https://api.nextdns.io"
ENV_VAR = "NEXTDNS_API_KEY"

# Outcome labels -- one line per domain as it is processed, counted at the end.
ADDED, EXISTS, SKIPPED, ERROR = "ADDED", "EXISTS", "SKIPPED", "ERROR"
EXISTS_DISABLED = "EXISTS (disabled)"  # present in the denylist, active:false

# Profile IDs are short alphanumerics (my.nextdns.io, Setup tab). The check is
# deliberately loose but keeps "/" and ".." out of the request path.
PROFILE_RE = re.compile(r"^[a-z0-9_-]{1,64}$", re.IGNORECASE)

_LABEL_CHARS = set("abcdefghijklmnopqrstuvwxyz0123456789-")

EPILOG = """\
examples:
  NEXTDNS_API_KEY=... python scripts/nextdns_sync.py --profile abc123
      preview what the strict list would add to a profile (no writes)
  NEXTDNS_API_KEY=... python scripts/nextdns_sync.py --profile abc123 --apply
      write the missing domains
  python scripts/nextdns_sync.py --file lists/safe-domains.txt
      offline preview, no key needed: shows the file side only

The API key is read from the NEXTDNS_API_KEY environment variable (bottom of
https://my.nextdns.io/account). It is never accepted as a flag and never
printed. Writing is additive-only: existing denylist entries -- including any
you added by hand -- are never removed, disabled or reordered. Re-running is
safe and reports them as EXISTS; an entry that is present but disabled
(active:false) is flagged as EXISTS (disabled) instead, and is never
re-enabled or removed by this script.

Step-by-step install and update guidance: docs/install.md in this repository.

exit codes:
  0  success: dry-run completed, or --apply wrote everything missing.
     Skipped lines (comments, duplicates, non-domains) are warnings, not
     failures.
  1  one or more API operations failed, or --apply could not read the
     existing denylist and wrote nothing.
  2  usage or configuration error: bad flags, missing key or profile for
     --apply, unreadable or empty list file.
"""


def is_domain(name: str) -> bool:
    """Basic sanity only: 2+ dot-separated labels, no empty or overlong one,
    no leading/trailing hyphen, ASCII letters/digits/hyphens only.

    Not a DNS validator -- enough to reject prose, URLs and the regex lines
    from the wildcard files ("*.x", "^[a-z]{2}\\.x$") before they reach the
    API, where an invalid domain surfaces as a 200-with-errors response.
    """
    if len(name) > 253:
        return False
    labels = name.split(".")
    if len(labels) < 2:
        return False
    return all(
        label and len(label) <= 63 and label[0] != "-" and label[-1] != "-"
        and all(c in _LABEL_CHARS for c in label)
        for label in labels
    )


def parse_entries(text: str) -> tuple[list[str], list[tuple[int, str, str]]]:
    """Parse a domains list into (domains, skipped).

    domains: valid FQDNs, lowercased, deduplicated, in file order.
    skipped: (line number, raw line, reason) for every line not used.

    Blank lines and #/! comments are ignored silently -- same rules as the
    built lists. The repo's other built formats ("0.0.0.0 name", "||name^")
    are unwrapped too, so -hosts.txt and -adblock.txt files work as --file.
    """
    domains: list[str] = []
    skipped: list[tuple[int, str, str]] = []
    seen: set[str] = set()
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith(("#", "!")):
            continue
        if line.startswith("0.0.0.0 "):
            line = line[len("0.0.0.0 "):].strip()
        elif line.startswith("||") and line.endswith("^"):
            line = line[2:-1]
        name = line.lower()
        if not is_domain(name):
            skipped.append((lineno, raw.strip(), "not a domain name"))
        elif name in seen:
            skipped.append((lineno, raw.strip(), "duplicate of an earlier line"))
        else:
            seen.add(name)
            domains.append(name)
    return domains, skipped


def api_error_detail(payload: object) -> str | None:
    """Readable one-liner from the API's {"errors": [...]}, else None.

    The official docs: user errors -- e.g. an invalid domain when adding to
    the denylist -- arrive as HTTP 200 with this body, so callers must check
    for it instead of trusting the status code alone.
    """
    errors = payload.get("errors") if isinstance(payload, dict) else None
    if not errors:
        return None
    items = errors if isinstance(errors, list) else [errors]
    parts = []
    for item in items:
        if isinstance(item, dict):
            parts.append(str(item.get("detail") or item.get("code") or item))
        else:
            parts.append(str(item))
    return "; ".join(parts) or None


def http_error_text(exc: urllib.error.HTTPError) -> str:
    """Readable detail from an HTTPError, preferring the API's errors[].

    Consumes exc's body; the caller keeps ownership and should close exc.
    """
    body = ""
    try:
        body = exc.read().decode("utf-8", "replace")
    except (OSError, ValueError):
        pass
    detail = None
    if body:
        try:
            detail = api_error_detail(json.loads(body))
        except json.JSONDecodeError:
            detail = None
    if not detail:
        detail = " ".join(body.split())[:200]
    return f"HTTP {exc.code}: {detail}" if detail else f"HTTP {exc.code}"


def retry_after_seconds(exc: urllib.error.HTTPError, attempt: int) -> float:
    """Seconds to wait after a 429: a sane Retry-After, else 10s x attempt.

    Retry-After may be seconds or an HTTP date; only a numeric value <= 300
    is honored (dates are rare here and would need clock handling). The
    fallback caps at 60s: enough for NextDNS's window to slide without
    letting one hostile response hang a bulk run for minutes.
    """
    header = exc.headers.get("Retry-After") if exc.headers else None
    if header is not None:
        try:
            seconds = float(header)
        except ValueError:
            seconds = -1.0
        if 0 <= seconds <= 300:
            return seconds
    return float(min(10 * attempt, 60))


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Refuse redirects: the API key must only ever go to api.nextdns.io."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # urllib then surfaces the redirect as an HTTPError


_OPENER = urllib.request.build_opener(_NoRedirect)


def api_request(method: str, path: str, *, key: str, body: dict | None = None,
                timeout: float = 15.0) -> tuple[int, object]:
    """One API call. Returns (status, parsed JSON body or None).

    Raises urllib.error.HTTPError for non-2xx and URLError/OSError for
    transport failures; callers map those to outcomes, so a single bad
    request never aborts a run.
    """
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"X-Api-Key": key, "User-Agent": "lg-tv-blocklist-nextdns-sync"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(f"{API_BASE}{path}", data=data, headers=headers,
                                 method=method)
    with _OPENER.open(req, timeout=timeout) as resp:
        raw = resp.read()
        status = resp.status
    payload = None
    if raw:
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            payload = None
    return status, payload


def fetch_denylist(profile: str, key: str, timeout: float) -> dict[str, bool]:
    """Every denylist ID (lowercased) mapped to its active flag, following
    pagination.

    active=False means the entry is present but not enforced, so the caller
    must not report it as satisfied. Raises the underlying urllib errors and
    ValueError on a malformed body -- the caller decides whether that aborts
    a run. It must for --apply: writing without knowing what exists would
    risk duplicates.
    """
    path = f"/profiles/{urllib.parse.quote(profile, safe='')}/denylist"
    ids: dict[str, bool] = {}
    cursor: str | None = None
    for _ in range(100):  # a bulk run should never loop forever
        url = path + (f"?cursor={urllib.parse.quote(cursor, safe='')}" if cursor else "")
        status, payload = api_request("GET", url, key=key, timeout=timeout)
        if status != 200 or not isinstance(payload, dict):
            raise ValueError(f"unexpected response (HTTP {status})")
        detail = api_error_detail(payload)
        if detail:
            raise ValueError(detail)
        data = payload.get("data")
        if not isinstance(data, list):
            raise ValueError("response has no data list")
        for entry in data:
            if isinstance(entry, dict):
                entry_id = entry.get("id")
                active = bool(entry.get("active", True))
            else:
                entry_id = entry
                active = True
            if isinstance(entry_id, str) and entry_id:
                ids[entry_id.lower()] = active
        meta = payload.get("meta")
        cursor = None
        if isinstance(meta, dict) and isinstance(meta.get("pagination"), dict):
            cursor = meta["pagination"].get("cursor")
        if not cursor:
            return ids
    raise ValueError("pagination did not terminate after 100 pages")


def add_domain(profile: str, domain: str, key: str, *, timeout: float,
               delay: float, max_retries: int, sleep=None) -> None:
    """POST one domain to the denylist. Raises RuntimeError on failure.

    Success is a 2xx *and* no "errors" key (see api_error_detail). HTTP 429
    is retried up to max_retries times, waiting retry_after_seconds() between
    attempts; every other failure is reported immediately so the run moves on
    and the caller can collect it.
    """
    sleep = sleep or time.sleep
    path = f"/profiles/{urllib.parse.quote(profile, safe='')}/denylist"
    for attempt in range(1, max_retries + 2):
        try:
            status, payload = api_request("POST", path, key=key,
                                          body={"id": domain}, timeout=timeout)
        except urllib.error.HTTPError as exc:
            try:
                if exc.code == 429 and attempt <= max_retries:
                    sleep(retry_after_seconds(exc, attempt))
                    continue
                raise RuntimeError(http_error_text(exc)) from exc
            finally:
                # HTTPError owns a body stream; close it or it lingers until
                # garbage collection (ResourceWarning on CPython 3.14).
                exc.close()
        except (urllib.error.URLError, OSError) as exc:
            raise RuntimeError(f"{type(exc).__name__}: {exc}") from exc
        if not 200 <= status < 300:
            raise RuntimeError(f"unexpected response (HTTP {status})")
        detail = api_error_detail(payload)
        if detail:
            raise RuntimeError(f"rejected: {detail}")
        if delay > 0:
            sleep(delay)  # polite pacing between writes
        return


def positive_float(value: str) -> float:
    """argparse type for --timeout: a number > 0, clean error otherwise."""
    try:
        number = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not a number: {value!r}") from None
    if number <= 0:
        raise argparse.ArgumentTypeError(f"must be > 0, got {number}")
    return number


def non_negative_float(value: str) -> float:
    """argparse type for --delay: a number >= 0, clean error otherwise."""
    try:
        number = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not a number: {value!r}") from None
    if number < 0:
        raise argparse.ArgumentTypeError(f"must be >= 0, got {number}")
    return number


def non_negative_int(value: str) -> int:
    """argparse type for --max-retries: an int >= 0, clean error otherwise."""
    try:
        number = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not an integer: {value!r}") from None
    if number < 0:
        raise argparse.ArgumentTypeError(f"must be >= 0, got {number}")
    return number


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Bulk-add list domains to a NextDNS profile denylist "
                    "(additive-only; dry-run unless --apply)",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--profile", metavar="ID", default=None,
                        help="NextDNS profile ID (required with --apply; "
                             "my.nextdns.io, Setup tab)")
    parser.add_argument("--file", type=Path, default=DEFAULT_FILE,
                        help=f"list file to sync (default: {DEFAULT_FILE.name})")
    parser.add_argument("--apply", action="store_true",
                        help="actually write to NextDNS; without it nothing is sent")
    parser.add_argument("--no-fetch", action="store_true",
                        help="dry-run only: never contact the API, not even to "
                             "read the existing denylist")
    parser.add_argument("--delay", type=non_negative_float, default=0.5, metavar="S",
                        help="pause between writes, in seconds (default: 0.5)")
    parser.add_argument("--timeout", type=positive_float, default=15.0, metavar="S",
                        help="per-request timeout, in seconds (default: 15)")
    parser.add_argument("--max-retries", type=non_negative_int, default=3, metavar="N",
                        help="retries after HTTP 429 before reporting the entry "
                             "as failed (default: 3)")
    args = parser.parse_args(argv)

    if args.apply and args.no_fetch:
        print("ERROR: --no-fetch cannot be combined with --apply", file=sys.stderr)
        return 2
    if args.profile is not None and not PROFILE_RE.fullmatch(args.profile):
        print(f"ERROR: --profile {args.profile!r} does not look like a profile "
              "ID (letters/digits, at most 64)", file=sys.stderr)
        return 2
    if not args.file.is_file():
        print(f"ERROR: no such file: {args.file} (run build.py build first)",
              file=sys.stderr)
        return 2
    domains, skipped = parse_entries(args.file.read_text(encoding="utf-8"))
    if not domains:
        # Show why every line was rejected: the common miss is pointing --file
        # at a regex/wildcard file, whose entries are not plain domains.
        for lineno, raw, reason in skipped:
            print(f"SKIPPED {raw} (line {lineno}: {reason})", file=sys.stderr)
        print(f"ERROR: no domains parsed from {args.file}", file=sys.stderr)
        return 2

    key = os.environ.get(ENV_VAR, "").strip()
    if args.apply:
        if not key:
            print(f"ERROR: {ENV_VAR} is not set -- create a key at the bottom of "
                  f"https://my.nextdns.io/account; --apply needs it", file=sys.stderr)
            return 2
        if not args.profile:
            print("ERROR: --profile is required with --apply", file=sys.stderr)
            return 2

    print(f"nextdns-sync ({'apply' if args.apply else 'dry-run'}): "
          f"{len(domains)} domains from {args.file}"
          + (f", profile {args.profile}" if args.profile else ""))
    if not args.apply:
        print("dry-run: no changes will be made; pass --apply to write")

    # The existing denylist is read only when it can be: a key, a profile and
    # no --no-fetch. Without it the preview lists the file side only.
    existing: set[str] | None = None
    if not args.no_fetch and key and args.profile:
        try:
            existing = fetch_denylist(args.profile, key, args.timeout)
        except urllib.error.HTTPError as exc:
            try:
                message = http_error_text(exc)
                if exc.code in (400, 401, 403, 404):
                    print(f"ERROR: cannot read the denylist: {message}",
                          file=sys.stderr)
                    return 2
                if args.apply:
                    print(f"ERROR: cannot read the existing denylist "
                          f"({message}); nothing was written", file=sys.stderr)
                    return 1
                print(f"warning: cannot read the existing denylist "
                      f"({message}); showing the file-side plan only",
                      file=sys.stderr)
            finally:
                exc.close()
        except (urllib.error.URLError, OSError, ValueError) as exc:
            if args.apply:
                print(f"ERROR: cannot read the existing denylist "
                      f"({type(exc).__name__}: {exc}); nothing was written",
                      file=sys.stderr)
                return 1
            print(f"warning: cannot read the existing denylist "
                  f"({type(exc).__name__}: {exc}); showing the file-side plan only",
                  file=sys.stderr)
    elif not args.apply:
        if args.no_fetch:
            print("note: --no-fetch -- every entry is listed as if the denylist "
                  "were empty")
        elif not key:
            print(f"note: {ENV_VAR} is not set -- every entry is listed as if "
                  "the denylist were empty")
        else:
            print("note: no --profile -- every entry is listed as if the "
                  "denylist were empty")

    added = exists = disabled = failed = 0
    for lineno, raw, reason in skipped:
        print(f"SKIPPED {raw} (line {lineno}: {reason})")
    for domain in domains:
        if existing is not None and domain in existing:
            if existing[domain]:
                exists += 1
                print(f"EXISTS  {domain}")
            else:
                # Present but active:false blocks nothing; the entry is not
                # satisfied. Never re-enabled by this script (additive-only).
                disabled += 1
                print(f"{EXISTS_DISABLED} {domain}")
        elif not args.apply:
            added += 1
            print(f"WOULD ADD {domain}")
        else:
            try:
                add_domain(args.profile, domain, key, timeout=args.timeout,
                           delay=args.delay, max_retries=args.max_retries)
            except RuntimeError as exc:
                failed += 1
                print(f"ERROR   {domain} ({exc})")
            else:
                added += 1
                print(f"ADDED   {domain}")

    verb = "added" if args.apply else "to add"
    print(f"summary: {added} {verb}, {exists} already present, "
          f"{disabled} present but disabled, {len(skipped)} skipped, "
          f"{failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
