"""Exact-revision Homebrew inputs: real Git archives, no package installation or network."""

import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "homebrew_checkout", ROOT / "scripts/prepare-homebrew-checkout.py"
)
checkout = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checkout)


class CheckoutPackagingTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="dwork-packaging-tests-")
        self.addCleanup(temporary.cleanup)
        self.work = Path(temporary.name).resolve()
        self.repository = self.work / "repository"
        self.repository.mkdir()
        self.git("init", "-q")
        self.git("config", "user.name", "Packaging tests")
        self.git("config", "user.email", "packaging@example.invalid")
        self.git("config", "commit.gpgsign", "false")
        self.git("config", "core.hooksPath", str(self.work / "no-hooks"))
        for relative in (checkout.TEMPLATE, checkout.STABLE_SOURCE, checkout.STABLE_FORMULA):
            destination = self.repository / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / relative, destination)
        (self.repository / "lib").mkdir()
        (self.repository / "lib/dwork_version.py").write_text('__version__ = "7.8.9"\n')
        self.source = self.repository / "source.py"
        self.source.write_text('print("initial revision")\n')
        self.source.chmod(0o755)
        self.commit()
        self.output = self.work / "prepared source with spaces"

    def git(self, *arguments):
        return subprocess.check_output(
            ["git", "-C", str(self.repository), *arguments], text=True
        ).strip()

    def commit(self):
        self.git("add", ".")
        self.git("commit", "-qm", "test revision")
        self.revision = self.git("rev-parse", "HEAD")

    def prepare(self, output=None, revision=None):
        return checkout.prepare_checkout(
            self.repository, output or self.output, revision or self.revision
        )

    def test_source_is_the_exact_committed_revision_without_a_remote(self):
        previous = self.revision
        self.source.write_text('print("reviewed changes")\n')
        self.commit()
        self.assertNotEqual(self.revision, previous)
        metadata = self.prepare()
        archive = self.output / metadata["archive"]
        self.assertEqual(metadata["revision"], self.revision)
        self.assertEqual(metadata["version"], "7.8.9")
        self.assertEqual(metadata["sha256"], hashlib.sha256(archive.read_bytes()).hexdigest())
        self.assertEqual(json.loads((self.output / "source.json").read_text()), metadata)
        with tarfile.open(archive) as source:
            member = source.getmember("dwork-" + self.revision + "/source.py")
            self.assertTrue(member.mode & 0o111)
            self.assertEqual(source.extractfile(member).read(), self.source.read_bytes())
        formula = (self.output / "dwork.rb").read_text()
        self.assertIn('url "' + archive.as_uri() + '"', formula)
        self.assertIn('sha256 "' + metadata["sha256"] + '"', formula)
        self.assertIn('version "7.8.9"', formula)
        self.assertEqual(
            formula,
            checkout.render_formula(
                (self.repository / checkout.TEMPLATE).read_text(),
                archive.as_uri(),
                "7.8.9",
                metadata["sha256"],
            ),
        )
        self.assertEqual(self.git("remote"), "")
        self.assertEqual(self.git("status", "--porcelain"), "")

        # Moving the branch after validation must not change the captured source.
        expected_revision, expected_source = self.revision, self.source.read_bytes()
        real_git = checkout.git

        def move_branch(repository, *arguments):
            result = real_git(repository, *arguments)
            if arguments == ("status", "--porcelain", "--untracked-files=normal"):
                self.source.write_text('print("next concurrent revision")\n')
                self.commit()
            return result

        with patch.object(checkout, "git", side_effect=move_branch):
            other = checkout.prepare_checkout(
                self.repository, self.work / "concurrent", expected_revision
            )
        self.assertEqual(other["revision"], expected_revision)
        with tarfile.open(self.work / "concurrent" / other["archive"]) as source:
            self.assertEqual(
                source.extractfile("dwork-" + expected_revision + "/source.py").read(),
                expected_source,
            )

    def test_repeat_preparation_is_reproducible_and_does_not_overwrite(self):
        first = self.prepare()
        second = self.prepare(output=self.work / "second")
        self.assertEqual(first, second)
        before = {path.name: path.read_bytes() for path in self.output.iterdir()}
        with self.assertRaisesRegex(ValueError, "new or empty"):
            self.prepare()
        self.assertEqual({path.name: path.read_bytes() for path in self.output.iterdir()}, before)

    def test_staged_unstaged_and_untracked_changes_are_rejected_before_writes(self):
        original = self.source.read_text()
        for kind in ("unstaged", "staged", "untracked"):
            with self.subTest(kind=kind):
                if kind == "untracked":
                    (self.repository / "untracked.py").write_text("unreviewed\n")
                else:
                    self.source.write_text("unreviewed\n")
                    if kind == "staged":
                        self.git("add", "source.py")
                with self.assertRaisesRegex(ValueError, "must be clean"):
                    self.prepare()
                self.assertFalse(self.output.exists())
                if kind == "untracked":
                    (self.repository / "untracked.py").unlink()
                else:
                    self.source.write_text(original)
                    self.git("add", "source.py")

    def test_old_short_and_wrong_revision_are_rejected_before_writes(self):
        old = self.revision
        self.source.write_text("new revision\n")
        self.commit()
        for revision in (old, self.revision[:8], "0" * 40, "HEAD"):
            with (
                self.subTest(revision=revision),
                self.assertRaisesRegex(ValueError, "expected full commit"),
            ):
                self.prepare(revision=revision)
            self.assertFalse(self.output.exists())

    def test_output_must_be_outside_checkout_and_empty(self):
        for output in (self.repository / "generated", self.source):
            with (
                self.subTest(output=output),
                self.assertRaisesRegex(ValueError, "outside the source checkout"),
            ):
                self.prepare(output=output)
        self.output.write_text("keep this file")
        with self.assertRaisesRegex(ValueError, "new or empty"):
            self.prepare()
        self.assertEqual(self.output.read_text(), "keep this file")

    def test_committed_formula_drift_blocks_preparation(self):
        formula = self.repository / checkout.STABLE_FORMULA
        formula.write_text(formula.read_text().replace('"gmake"', '"unreviewed-installer"'))
        self.commit()
        with self.assertRaisesRegex(ValueError, "differs from its template"):
            self.prepare()
        self.assertFalse(self.output.exists())

    def test_shared_template_reproduces_stable_formula_and_shell_arguments(self):
        checkout.check_stable(ROOT)
        stable = checkout.stable_formula(ROOT)
        self.assertEqual(stable, (ROOT / checkout.STABLE_FORMULA).read_text())
        self.assertIn('_dwork "$@"', stable)
        self.assertNotIn("$$@", stable)

    def test_completion_sources_use_homebrew_formula_scoped_shared_directory(self):
        template = (ROOT / checkout.TEMPLATE).read_text()
        formulas = (
            checkout.stable_formula(ROOT),
            checkout.render_formula(template, "file:///tmp/source.tar.gz", "7.8.9", "a" * 64),
        )
        for formula in formulas:
            with self.subTest(source=formula.splitlines()[5]):
                self.assertIn('cp pkgshare/"completions/dwork.bash"', formula)
                self.assertIn('(pkgshare/"completions/_dwork").to_s.shellescape', formula)
                # Homebrew's strict audit rejects an explicitly repeated formula name.
                self.assertNotIn('share/"dwork/', formula)

    def test_rendering_requires_version_checksum_and_noninterpolated_url(self):
        template = (ROOT / checkout.TEMPLATE).read_text()
        for url, version, digest in (
            ("https://example.invalid/source.tar.gz", "7.8.9", "bad"),
            ("https://example.invalid/source.tar.gz", "7.8.9\ncode", "a" * 64),
            ("file:///tmp/#{code}.tar.gz", "7.8.9", "a" * 64),
        ):
            with (
                self.subTest(url=url, version=version, digest=digest),
                self.assertRaises(ValueError),
            ):
                checkout.render_formula(template, url, version, digest)

    def test_version_reading_is_literal_and_never_executes_python(self):
        self.assertEqual(
            checkout.package_version(
                '__version__ = "7.8.9"\nraise AssertionError("must not execute")'
            ),
            "7.8.9",
        )
        with self.assertRaises(ValueError):
            checkout.package_version("__version__ = str(123)")


if __name__ == "__main__":
    unittest.main()
