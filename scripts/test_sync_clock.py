"""Offline lifecycle tests for the clock hook; all effects stay in a sandbox."""

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOOK = ROOT / "examples/webos-hooks/04-sync-clock.sh"
SH = shutil.which("sh") or r"C:\Program Files\Git\bin\bash.exe"


def shell_path(path):
    if os.name != "nt":
        return str(path)
    return subprocess.check_output(
        [SH, "-c", 'cygpath -u "$1"', "sh", str(path)], text=True
    ).strip()


class ClockHookTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="clock-hook-test-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.root_sh = shell_path(self.root)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.sentinel = self.root / "sentinel"
        self.sentinel.mkdir()
        (self.sentinel / "keep").write_text("untouched", encoding="utf-8")
        self.stub(
            "date",
            'case "$1" in +%Y) echo 2021;; +%s) echo 0;; -d) echo "2026-09-16 07:34:45";; -s) echo date-set >> "$SANDBOX/events";; *) exit 1;; esac',
        )
        self.stub(
            "curl",
            'echo curl >> "$SANDBOX/events"; echo "Date: Wed, 16 Sep 2026 07:34:45 GMT"',
        )
        for name in ("tr", "grep", "head", "cat"):
            self.stub(name, f'exec /usr/bin/{name} "$@"')
        self.stub("mkdir", 'exec /usr/bin/mkdir "$@"')
        self.stub(
            "rm",
            'echo "$*" >> "$SANDBOX/removals"; case "$2" in "$SANDBOX"/owned-*) [ -s "$2/1-1" ] && echo output-present >> "$SANDBOX/outputs"; exec /usr/bin/rm "$@";; *) exit 1;; esac',
        )

    def stub(self, name, body):
        path = self.bin / name
        path.write_text("#!/bin/sh\n" + body + "\n", encoding="utf-8", newline="\n")
        path.chmod(0o755)

    def run_hook(self):
        text = HOOK.read_text(encoding="utf-8")
        # Relocate only fixed process boundaries; the lifecycle logic is unchanged.
        self.assertEqual(text.count("PATH=/usr/sbin:/usr/bin:/sbin:/bin"), 1)
        self.assertIn("LOG=/tmp/webosbrew_hook.log", text)
        text = text.replace("/tmp/", self.root_sh + "/")
        text = text.replace(
            "PATH=/usr/sbin:/usr/bin:/sbin:/bin", f'PATH="{self.root_sh}/bin"'
        )
        script = self.root / "hook.sh"
        script.write_text(text, encoding="utf-8", newline="\n")
        env = dict(
            os.environ,
            SANDBOX=self.root_sh,
            SYNC_URLS_OVERRIDE="http://offline.invalid/",
        )
        result = subprocess.run(
            [SH, shell_path(script)],
            env=env,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            (self.sentinel / "keep").read_text(encoding="utf-8"), "untouched"
        )
        return (self.root / "webosbrew_hook.log").read_text(encoding="utf-8")

    def test_unique_owned_directories_are_used_and_cleaned(self):
        # Keep allocation names unique even after the hook removes each directory.
        self.stub(
            "mktemp",
            'echo "$*" >> "$SANDBOX/templates"; if [ -f "$SANDBOX/allocated" ]; then n=2; else n=1; : > "$SANDBOX/allocated"; fi; d="$SANDBOX/owned-$n"; /usr/bin/mkdir "$d" || exit 1; echo "$d"',
        )
        for _ in range(2):
            self.assertIn("clock synced", self.run_hook())
        self.assertTrue((self.root / "templates").exists(), "mktemp was not invoked")
        self.assertEqual(
            (self.root / "templates").read_text().splitlines(),
            [f"-d {self.root_sh}/04-sync-clock.XXXXXX"] * 2,
        )
        self.assertEqual(
            (self.root / "removals").read_text().splitlines(),
            [f"-rf {self.root_sh}/owned-1", f"-rf {self.root_sh}/owned-2"],
        )
        self.assertFalse((self.root / "owned-1").exists())
        self.assertFalse((self.root / "owned-2").exists())
        self.assertEqual(
            (self.root / "outputs").read_text().splitlines(), ["output-present"] * 2
        )
        self.assertEqual(
            (self.root / "events").read_text().splitlines().count("date-set"), 2
        )

    def test_failed_mktemp_stdout_is_not_owned(self):
        self.stub("mktemp", 'echo "$SANDBOX/sentinel"; exit 1')
        self.assertIn("WARN: cannot create secure work dir", self.run_hook())
        self.assertFalse((self.root / "events").exists())
        self.assertFalse((self.root / "removals").exists())
        self.assertEqual(sorted(p.name for p in self.root.glob("04-sync-clock.*")), [])

    def test_missing_mktemp_skips_without_fallback(self):
        self.assertIn("WARN: cannot create secure work dir", self.run_hook())
        self.assertFalse((self.root / "events").exists())
        self.assertFalse((self.root / "removals").exists())
        self.assertEqual(sorted(p.name for p in self.root.glob("04-sync-clock.*")), [])


if __name__ == "__main__":
    unittest.main()
