#!/usr/bin/env python3
"""Exercise publication against disposable local Git repositories."""

import io
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import build
import publish_lists

SCRIPTS = Path(__file__).resolve().parent


class PublicationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        directory = Path(temporary.name)
        environment = patch.dict(os.environ, {
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
        })
        environment.start()
        self.addCleanup(environment.stop)
        self.origin = directory / "origin.git"
        self.writer = directory / "writer"
        self.publisher = directory / "publisher"
        self.git(directory, "init", "--bare", "--initial-branch=main", str(self.origin))
        self.git(directory, "clone", str(self.origin), str(self.writer))
        self.git(self.writer, "config", "user.name", "Test Author")
        self.git(self.writer, "config", "user.email", "author@example.test")
        (self.writer / "scripts").mkdir()
        for name in ("build.py", "publish_lists.py"):
            shutil.copyfile(SCRIPTS / name, self.writer / "scripts" / name)
        self.write(self.writer, "src/safe.txt", "ads.lge.com # SAFE: fixture ads\n")
        self.write(self.writer, "src/strict.txt", "snu.lge.com # STRICT: fixture OTA\n")
        self.write(self.writer, "src/zones.txt", "lgtvcommon.com # ZONE: fixture anchor\n")
        self.git(self.writer, "add", ".")
        self.git(self.writer, "commit", "-m", "fixture baseline without generated files")
        self.base = self.git(self.writer, "rev-parse", "HEAD")
        self.git(self.writer, "push", "origin", "HEAD:refs/heads/main")
        self.git(directory, "clone", str(self.origin), str(self.publisher))
        checkout_paths = patch.multiple(
            build, ROOT=self.publisher, SRC=self.publisher / "src", LISTS=self.publisher / "lists",
        )
        checkout_paths.start()
        self.addCleanup(checkout_paths.stop)

    @staticmethod
    def git(cwd, *args):
        return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True,
                              text=True).stdout.strip()

    @staticmethod
    def write(repo, name, content):
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def origin_tip(self, branch="main"):
        return self.git(self.origin, "rev-parse", f"refs/heads/{branch}")

    def sync_writer(self):
        self.git(self.writer, "pull", "--ff-only", "origin", "main")

    def advance(self, path, content):
        self.write(self.writer, path, content)
        self.git(self.writer, "add", "--", path)
        self.git(self.writer, "commit", "-m", f"update {path}")
        self.git(self.writer, "push", "origin", "HEAD:refs/heads/main")
        return self.origin_tip()

    def invoke(self, head=None, branch="main"):
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            code = publish_lists.publish(head or self.base, branch)
        return code, stdout.getvalue()

    def expect(self, prefix, code=0, **kwargs):
        actual_code, output = self.invoke(**kwargs)
        self.assertEqual(code, actual_code, output)
        self.assertTrue(any(line.startswith(prefix) for line in output.splitlines()), output)

    def check_artifacts(self, parent):
        self.assertEqual(parent, self.git(self.origin, "rev-parse", "main^"))
        expected = build.dry_run()
        paths = {f"lists/{name}" for name in expected} | {"lists/SHA256SUMS"}
        changed = set(self.git(self.origin, "diff", "--name-only", parent, "main").splitlines())
        self.assertTrue(changed, "expected generated changes")
        self.assertLessEqual(changed, paths)
        for name, content in expected.items():
            actual = subprocess.run(
                ["git", "cat-file", "blob", f"main:lists/{name}"], cwd=self.origin,
                check=True, capture_output=True,
            ).stdout
            expected_lines = [line for line in content.encode("utf-8").split(b"\n")
                              if not line.startswith(b"# Updated:")]
            actual_lines = [line for line in actual.split(b"\n")
                            if not line.startswith(b"# Updated:")]
            self.assertEqual(expected_lines, actual_lines, name)
        self.sync_writer()
        self.assertEqual({"SHA256SUMS", *expected}, {p.name for p in (self.writer / "lists").iterdir()})
        subprocess.run(["sha256sum", "--strict", "-c", "SHA256SUMS"], cwd=self.writer / "lists",
                       check=True, capture_output=True)

    def test_cli_publishes_missing_outputs_then_leaves_valid_bytes_untouched(self):
        result = subprocess.run(
            [sys.executable, str(self.publisher / "scripts" / "publish_lists.py"),
             "--validated-head", self.base, "--branch", "main"],
            cwd=self.origin.parent, capture_output=True, text=True, check=True,
        )
        self.assertIn("PUBLISHED:", result.stdout)
        published = self.origin_tip()
        self.check_artifacts(self.base)
        before = {p.name: p.read_bytes() for p in build.LISTS.iterdir()}
        with patch.object(build, "now_utc", return_value="2001-01-01 00:00 UTC"):
            self.expect("UNCHANGED:", head=published)
        self.assertEqual(published, self.origin_tip())
        self.assertEqual(before, {p.name: p.read_bytes() for p in build.LISTS.iterdir()})
        self.assertEqual("", self.git(self.publisher, "status", "--porcelain"))

    def test_repairs_bad_manifest_and_stale_body(self):
        self.expect("PUBLISHED:")
        self.sync_writer()
        bad_manifest = self.advance("lists/SHA256SUMS", "not a checksum manifest\n")
        self.expect("PUBLISHED:", head=self.git(self.publisher, "rev-parse", "HEAD"))
        self.check_artifacts(bad_manifest)
        stale = self.advance("lists/safe-domains.txt", "stale.example.test\n")
        self.expect("PUBLISHED:", head=self.git(self.publisher, "rev-parse", "HEAD"))
        self.check_artifacts(stale)

    def test_docs_advance_before_fetch_becomes_generated_commit_parent(self):
        docs = self.advance("README.md", "preserve these docs\n")
        self.expect("PUBLISHED:")
        self.check_artifacts(docs)
        self.assertEqual("preserve these docs", self.git(self.origin, "show", "main:README.md"))

    def test_all_generation_input_paths_defer_until_new_head_is_validated(self):
        validated = self.base
        for path, content in (
            ("src/safe.txt", "beacon.lge.com # SAFE: fixture ads\n"),
            ("scripts/test_synthetic.py", "# fixture test change\n"),
            (".github/workflows/lint.yml", "# fixture workflow change\n"),
            (".gitattributes", "*.txt text eol=lf\n"),
        ):
            with self.subTest(path=path):
                advanced = self.advance(path, content)
                self.expect("DEFERRED:", head=validated)
                self.assertEqual(advanced, self.origin_tip())
                self.assertEqual(validated, self.git(self.publisher, "rev-parse", "HEAD"))
                self.assertFalse(build.LISTS.exists())
                self.git(self.publisher, "switch", "--detach", advanced)
                validated = advanced
        self.expect("PUBLISHED:", head=validated)
        self.check_artifacts(validated)
        self.assertIn("beacon.lge.com", self.git(self.origin, "show", "main:lists/safe-domains.txt"))

    def with_push(self, callback):
        real_git = publish_lists.git
        self.pushes = 0

        def dispatch(*args, check=True):
            if args[0] != "push":
                return real_git(*args, check=check)
            self.pushes += 1
            return callback(real_git, args)

        return patch.object(publish_lists, "git", side_effect=dispatch)

    def test_docs_advance_before_push_reconciles_once(self):
        def move_on_first_push(git, args):
            if self.pushes == 1:
                self.docs = self.advance("README.md", "concurrent docs\n")
            return git(*args, check=False)

        with self.with_push(move_on_first_push):
            self.expect("PUBLISHED:")
        self.assertEqual(2, self.pushes)
        self.check_artifacts(self.docs)
        self.assertEqual("concurrent docs", self.git(self.origin, "show", "main:README.md"))

    def test_docs_advance_after_push_negotiation_reconciles_once(self):
        self.write(self.writer, "README.md", "docs committed during push\n")
        self.git(self.writer, "add", "README.md")
        self.git(self.writer, "commit", "-m", "docs race")
        docs = self.git(self.writer, "rev-parse", "HEAD")
        hook = self.publisher / ".git" / "hooks" / "pre-push"
        hook.write_text(
            "#!/bin/sh\n"
            "if [ ! -e .git/advanced-once ]; then\n"
            "    touch .git/advanced-once\n"
            f"    git -C {shlex.quote(str(self.writer))} push origin HEAD:refs/heads/main\n"
            "fi\n",
            encoding="utf-8",
        )
        hook.chmod(0o700)
        with self.with_push(lambda git, args: git(*args, check=False)):
            self.expect("PUBLISHED:")
        self.assertEqual(2, self.pushes)
        self.check_artifacts(docs)

    def test_source_advance_before_push_defers_without_stale_lists(self):
        def move_then_push(git, args):
            self.new_source = self.advance("src/safe.txt", "beacon.lge.com # SAFE: fixture ads\n")
            return git(*args, check=False)

        with self.with_push(move_then_push):
            self.expect("DEFERRED:")
        self.assertEqual(1, self.pushes)
        self.assertEqual(self.new_source, self.origin_tip())
        self.assertEqual("", self.git(self.origin, "ls-tree", "main", "lists"))

    def test_second_push_race_stops(self):
        def move_then_push(git, args):
            self.docs = self.advance("README.md", f"docs revision {self.pushes}\n")
            return git(*args, check=False)

        with self.with_push(move_then_push):
            self.expect("ERROR:", code=1)
        self.assertEqual(2, self.pushes)
        self.assertEqual(self.docs, self.origin_tip())
        self.assertEqual("", self.git(self.origin, "ls-tree", "main", "lists"))

    def test_lost_reply_after_push_confirms_origin_without_second_write(self):
        def lose_reply(git, args):
            git(*args)
            return subprocess.CompletedProcess(args, 1, "", "lost connection after update")

        with self.with_push(lose_reply):
            self.expect("PUBLISHED:")
        self.assertEqual(1, self.pushes)
        self.check_artifacts(self.base)

    def test_denied_push_does_not_repeat_even_if_origin_advances(self):
        def deny(_git, args):
            self.docs = self.advance("README.md", "unrelated remote update\n")
            return subprocess.CompletedProcess(args, 1, "", "permission denied")

        with self.with_push(deny):
            self.expect("ERROR:", code=1)
        self.assertEqual(1, self.pushes)
        self.assertEqual(self.docs, self.origin_tip())
        self.assertEqual("", self.git(self.origin, "ls-tree", "main", "lists"))

    def test_same_origin_tip_does_not_retry_even_with_stale_ref_diagnostic(self):
        def reject(_git, args):
            output = "!\tHEAD:refs/heads/main\t[rejected] (non-fast-forward)\n"
            return subprocess.CompletedProcess(args, 1, output, "")

        with self.with_push(reject):
            self.expect("ERROR:", code=1)
        self.assertEqual(1, self.pushes)
        self.assertEqual(self.base, self.origin_tip())

    def test_unreadable_origin_after_uncertain_push_stops(self):
        def disconnect(_git, args):
            self.origin.rename(self.origin.with_name("unavailable.git"))
            return subprocess.CompletedProcess(args, 1, "", "connection lost")

        with self.with_push(disconnect):
            self.expect("ERROR:", code=1)
        self.assertEqual(1, self.pushes)

    def test_publication_to_named_ref_does_not_change_main(self):
        branch = "feature/offline"
        self.git(self.writer, "push", "origin", f"HEAD:refs/heads/{branch}")
        self.expect("PUBLISHED:", branch=branch)
        self.assertEqual(self.base, self.origin_tip())
        self.assertEqual(self.base, self.git(self.origin, "rev-parse", f"{branch}^"))
        self.assertIn("ads.lge.com", self.git(self.origin, "show", f"{branch}:lists/safe-domains.txt"))

    def test_bad_configuration_does_not_publish(self):
        self.expect("ERROR:", code=2, head=self.base[:7])
        self.expect("ERROR:", code=2, branch="../main")
        self.expect("ERROR:", code=2, head="0" * 40)
        self.write(self.publisher, "README.md", "untracked work\n")
        self.expect("ERROR:", code=2)
        self.assertEqual(self.base, self.origin_tip())
        self.assertFalse(build.LISTS.exists())


if __name__ == "__main__":
    unittest.main()
