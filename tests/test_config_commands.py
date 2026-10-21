"""Configuration commands use isolated files and fake Docker, never workloads."""

import json
import sys
import unittest

import test_dwork as legacy

sys.path.insert(0, str(legacy.SOURCE.parent / "lib"))
from dwork_version import __version__


class ConfigCommandTests(unittest.TestCase):
    def setUp(self):
        self.fixture = legacy.DworkTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.state = self.fixture.base / "state"

    def cli(self, args, **kwargs):
        return self.fixture.run_dwork("bash", args, register_current=False, **kwargs)

    def test_version_needs_no_valid_workspace_registry_or_docker(self):
        (self.root / "dwork.yml").write_text("invalid: [\n")
        for shell in self.fixture.shells:
            result, changes, calls = self.fixture.run_dwork(
                shell, "--version", register_current=False
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "dwork " + __version__ + "\n")
            self.assertEqual(calls, [])
            self.assertEqual(changes, [])
        self.assertFalse(self.state.exists())

    def test_init_preview_is_repeatable_and_does_not_write(self):
        outputs = []
        for _ in range(2):
            result, changes, calls = self.cli("init --dry-run", COMPOSE_FILE="missing.yml")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(calls, [])
            self.assertEqual(changes, [])
            outputs.append(result.stdout)
        self.assertEqual(outputs[0], outputs[1])
        self.assertIn(
            "# yaml-language-server: $schema=https://raw.githubusercontent.com/hayyaun/dwork/main/schemas/dwork.schema.json\n",
            outputs[0],
        )
        self.assertIn("enabled: false", outputs[0])
        self.assertFalse((self.root / "dwork.yml").exists())
        self.assertFalse(self.state.exists())

    def test_init_enables_compose_only_for_standard_local_files(self):
        for filename in (
            None,
            "compose.yaml",
            "compose.yml",
            "docker-compose.yaml",
            "docker-compose.yml",
        ):
            with self.subTest(filename=filename):
                directory = self.root / (filename or "host-only")
                directory.mkdir()
                if filename:
                    (directory / filename).write_text("not parsed during init")
                result, changes, calls = self.cli("init", cwd=directory)
                self.assertEqual(result.returncode, 0, result.stderr)
                expected = (
                    "# yaml-language-server: $schema=https://raw.githubusercontent.com/hayyaun/dwork/main/schemas/dwork.schema.json\n"
                    + "version: 1\ncompose:\n  enabled: "
                    + ("true" if filename else "false")
                    + "\nterminals: []\nbrowsers: []\n"
                )
                self.assertEqual((directory / "dwork.yml").read_text(), expected)
                self.assertEqual(calls, [])
                self.assertEqual(changes, [])
        self.assertFalse(self.state.exists())

    def test_init_never_overwrites_files_directories_or_links(self):
        target = self.fixture.base / "preserved.yml"
        target.write_text("preserve this")
        for kind in ("file", "directory", "link", "broken-link"):
            with self.subTest(kind=kind):
                directory = self.root / kind
                directory.mkdir()
                path = directory / "dwork.yml"
                if kind == "file":
                    path.write_text("")
                elif kind == "directory":
                    path.mkdir()
                else:
                    path.symlink_to(target if kind == "link" else self.fixture.base / "missing.yml")
                for args in ("init", "init --dry-run"):
                    result, changes, calls = self.cli(args, cwd=directory)
                    self.assertEqual(result.returncode, 1)
                    self.assertIn("already exists", result.stderr)
                    self.assertEqual(changes, [])
                    self.assertEqual(calls, [])
                self.assertTrue(path.exists() or path.is_symlink())
        self.assertEqual(target.read_text(), "preserve this")

    def test_initialized_host_workspace_validates_without_registry_or_docker(self):
        self.assertEqual(self.cli("init")[0].returncode, 0)
        config = self.root / "dwork.yml"
        before = config.read_bytes()
        result, changes, calls = self.cli("validate")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Valid workspace configuration: " + str(self.root), result.stdout)
        self.assertEqual(calls, [])
        self.assertEqual(changes, [])
        self.assertEqual(config.read_bytes(), before)
        self.assertFalse(self.state.exists())

    def test_validate_checks_compose_references_without_container_inventory(self):
        self.fixture.model(self.root, "app", services={"db": {}})
        config = self.root / "dwork.yml"
        for service, status in (("db", 0), ("missing", 1)):
            with self.subTest(service=service):
                config.write_text(json.dumps({"version": 1, "compose": {"services": [service]}}))
                result, changes, calls = self.cli("validate")
                self.assertEqual(result.returncode, status, result.stderr)
                self.assertTrue(calls)
                self.assertTrue(all(call[:1] == ["compose"] and "config" in call for call in calls))
                self.assertEqual(changes, [])
        self.assertFalse(self.state.exists())

    def test_validate_uses_ancestor_config_and_ignores_corrupt_registry(self):
        config = self.root / "dwork.yml"
        config.write_text("version: 1\ncompose: {enabled: false}\n")
        child = self.root / "child"
        child.mkdir()
        registry = self.state / "dwork/workspaces.json"
        registry.parent.mkdir(parents=True)
        registry.write_text("invalid registry")
        result, changes, calls = self.cli("validate", cwd=child)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(str(self.root), result.stdout)
        self.assertEqual(changes, [])
        self.assertEqual(calls, [])
        self.assertEqual(registry.read_text(), "invalid registry")

    def test_invalid_config_and_usage_fail_without_side_effects(self):
        config = self.root / "dwork.yml"
        for text in (
            "version: 99\n",
            "version: 1\nversion: 1\n",
            "version: 1\nunknown: true\n",
            "version: 1\ncompose: {enabled: false}\nterminals: [{command: [echo], cwd: missing}]\n",
        ):
            config.write_text(text)
            result, changes, calls = self.cli("validate")
            self.assertEqual(result.returncode, 1, result.stdout)
            self.assertEqual(changes, [])
            self.assertEqual(calls, [])
            self.assertEqual(config.read_text(), text)
        config.unlink()
        for args in (
            "--version extra",
            "init --version",
            "init extra",
            "init --force",
            "validate --dry-run",
        ):
            result, changes, calls = self.cli(args)
            self.assertEqual(result.returncode, 1, args)
            self.assertIn("Usage:", result.stderr)
            self.assertEqual(changes, [])
            self.assertEqual(calls, [])
        self.assertFalse(config.exists())
        self.assertFalse(self.state.exists())


if __name__ == "__main__":
    unittest.main()
