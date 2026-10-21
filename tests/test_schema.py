"""Keep editor validation aligned with the real loader; no Docker or network."""

from contextlib import redirect_stdout
from copy import deepcopy
from io import StringIO
from pathlib import Path
from unittest.mock import patch
import json
import sys
import tempfile
import unittest

from jsonschema import Draft7Validator

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "lib"))

import dwork_config
import dwork_docker
from dwork_common import DworkError, LAUNCHERS

SCHEMA = json.loads((REPO / "schemas/dwork.schema.json").read_text())
MODELINE = "# yaml-language-server: $schema=" + SCHEMA["$id"]


class SchemaTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        for directory in ("backend", "frontend"):
            (self.root / directory).mkdir()
        model = patch.object(
            dwork_docker,
            "read_model",
            return_value=("demo", {"db": {}, "postgres": {}, "redis": {}}),
        )
        model.start()
        self.addCleanup(model.stop)
        self.validator = Draft7Validator(SCHEMA)

    def check_config(self, config, valid):
        errors = list(self.validator.iter_errors(config))
        self.assertEqual(not errors, valid, [error.message for error in errors])
        (self.root / "dwork.yml").write_text(json.dumps(config))
        if valid:
            return dwork_config.load_workspace(self.root)
        with self.assertRaises(DworkError):
            dwork_config.load_workspace(self.root)

    def test_schema_is_valid_and_has_no_remote_references(self):
        Draft7Validator.check_schema(SCHEMA)

        def check(value):
            if isinstance(value, dict):
                if "$ref" in value:
                    self.assertTrue(value["$ref"].startswith("#/"))
                for child in value.values():
                    check(child)
            elif isinstance(value, list):
                for child in value:
                    check(child)

        check(SCHEMA)

    def test_shipped_examples_validate_and_keep_the_editor_association(self):
        for example in sorted((REPO / "examples").glob("*.yml")):
            with self.subTest(example=example.name):
                text = example.read_text()
                self.assertEqual(text.splitlines()[0], MODELINE)
                (self.root / "dwork.yml").write_text(text)
                config = dwork_config.read_config(self.root / "dwork.yml")
                self.validator.validate(config)
                dwork_config.load_workspace(self.root)

    def test_init_and_preview_emit_identical_associated_valid_yaml(self):
        for enabled in (False, True):
            with self.subTest(compose=enabled):
                directory = self.root / str(enabled)
                directory.mkdir()
                if enabled:
                    (directory / "compose.yaml").write_text("services: {}\n")
                preview = StringIO()
                with redirect_stdout(preview):
                    dwork_config.init_workspace(directory, preview=True)
                self.assertFalse((directory / "dwork.yml").exists())
                with redirect_stdout(StringIO()):
                    dwork_config.init_workspace(directory)
                path = directory / "dwork.yml"
                text = path.read_text()
                self.assertEqual(text.splitlines()[0], MODELINE)
                self.assertEqual(preview.getvalue(), "Would create " + str(path) + ":\n" + text)
                self.validator.validate(dwork_config.read_config(path))
                self.assertEqual(dwork_config.load_workspace(directory).enabled, enabled)

    def test_minimal_config_and_documented_defaults_match_runtime(self):
        workspace = self.check_config({"version": 1}, True)
        props = SCHEMA["properties"]
        self.assertEqual(props["confirm"]["default"], workspace.confirm)
        self.assertEqual(props["locked"]["default"], workspace.locked)
        self.assertEqual(props["compose"]["properties"]["enabled"]["default"], workspace.enabled)
        self.assertEqual(props["terminals"]["default"], workspace.terminals)
        self.assertEqual(props["browsers"]["default"], workspace.browsers)
        workspace = self.check_config(
            {
                "version": 1,
                "compose": {"enabled": False},
                "terminals": [{"command": ["echo"]}],
                "browsers": [{"url": "http://localhost:3000"}],
            },
            True,
        )
        terminal = SCHEMA["definitions"]["terminal"]["properties"]
        task = workspace.terminals[0]
        for key in ("window", "launcher", "confirm"):
            self.assertEqual(terminal[key]["default"], getattr(task, key))
        self.assertEqual(terminal["wait_for"]["properties"]["timeout"]["default"], task.timeout)
        browser = SCHEMA["definitions"]["browser"]["properties"]
        task = workspace.browsers[0]
        self.assertEqual(browser["browser"]["default"], task.browser)
        self.assertEqual(browser["confirm"]["default"], task.confirm)
        self.assertEqual(
            browser["wait_for"]["anyOf"][1]["properties"]["timeout"]["default"], task.timeout
        )

    def test_supported_choices_and_boundary_values_match_runtime(self):
        self.assertEqual(
            set(SCHEMA["definitions"]["terminal"]["properties"]["launcher"]["enum"]), set(LAUNCHERS)
        )
        for launcher in LAUNCHERS:
            for window in ("new", "current", "none"):
                with self.subTest(launcher=launcher, window=window):
                    self.check_config(
                        {
                            "version": 1,
                            "locked": True,
                            "confirm": False,
                            "compose": {"files": ["compose.yaml"], "services": ["db"]},
                            "terminals": [
                                {
                                    "title": "Backend",
                                    "command": ["echo", "3000", "yes"],
                                    "cwd": "backend",
                                    "window": window,
                                    "launcher": launcher,
                                    "confirm": False,
                                    "wait_for": {"healthy": ["db"], "timeout": 0.1},
                                }
                            ],
                            "browsers": [
                                {
                                    "url": "https://localhost:8443/path?email=a@b#ready",
                                    "browser": "Google Chrome",
                                    "confirm": False,
                                    "wait_for": {
                                        "url": "HTTP://[::1]:3000/health",
                                        "timeout": 3600,
                                    },
                                }
                            ],
                        },
                        True,
                    )
        for wait in (False, {}, {"timeout": 0.1}, {"timeout": 3600}):
            with self.subTest(wait=wait):
                self.check_config(
                    {
                        "version": 1,
                        "compose": {"enabled": False},
                        "terminals": [{"command": ["echo"], "wait_for": {"timeout": 3600}}],
                        "browsers": [{"url": "http://localhost/", "wait_for": wait}],
                    },
                    True,
                )

    def test_invalid_fields_types_and_ranges_match_runtime(self):
        base = {
            "version": 1,
            "compose": {},
            "terminals": [{"command": ["echo"], "wait_for": {}}],
            "browsers": [{"url": "http://localhost:3000", "wait_for": {}}],
        }
        cases = [
            (("version",), [None, True, "1", 2]),
            (("confirm",), [None, 0, "false"]),
            (("locked",), [None, 1, "true"]),
            (("compose",), [None, [], False]),
            (("compose", "enabled"), [None, 0, "false"]),
            (("compose", "files"), [[], "compose.yaml", [""], [1], ["nul\0"]]),
            (("compose", "services"), [[], "db", [False], [""], ["nul\0"]]),
            (("terminals",), [None, {}, [None], [{}]]),
            (
                ("terminals", 0, "command"),
                [
                    None,
                    [],
                    "echo hi",
                    [1],
                    [True],
                    [""],
                    ["echo; ls"],
                    ["echo\n"],
                    ["echo\r"],
                    ["echo\0"],
                ],
            ),
            (("terminals", 0, "title"), [None, "", 1, "bad;title", "bad\n"]),
            (("terminals", 0, "cwd"), [None, "", False, "bad;cwd"]),
            (("terminals", 0, "window"), [None, "tab", 0]),
            (("terminals", 0, "launcher"), [None, "unknown", False]),
            (("terminals", 0, "confirm"), [None, "false", 0]),
            (("terminals", 0, "wait_for"), [None, False, []]),
            (("terminals", 0, "wait_for", "healthy"), [[], "db", [False], [""]]),
            (("terminals", 0, "wait_for", "timeout"), [None, 0, -1, 3600.1, True, "60"]),
            (("browsers",), [None, {}, [None], [{}]]),
            (
                ("browsers", 0, "url"),
                [
                    None,
                    1,
                    "",
                    "/relative",
                    "ftp://host",
                    "http://",
                    "http://user:password@host",
                    "http://host/back\\slash",
                    "http://host/space here",
                    "http://host/é",
                    "http://host/\n",
                ],
            ),
            (
                ("browsers", 0, "browser"),
                [None, 1, "", " firefox", "firefox ", "-firefox", "firefox\n"],
            ),
            (("browsers", 0, "confirm"), [None, "false", 0]),
            (("browsers", 0, "wait_for"), [None, True, [], 0, "false"]),
            (("browsers", 0, "wait_for", "url"), [None, "https://user@host", "/health"]),
            (("browsers", 0, "wait_for", "timeout"), [None, 0, -1, 3600.1, False, "60"]),
        ]
        for path, values in cases:
            for value in values:
                with self.subTest(path=path, value=value):
                    config = deepcopy(base)
                    parent = config
                    for key in path[:-1]:
                        parent = parent[key]
                    parent[path[-1]] = value
                    self.check_config(config, False)
        for config in (None, [], "version: 1", {}, {"compose": {"enabled": False}}):
            with self.subTest(root=config):
                self.check_config(config, False)

    def test_unknown_keys_are_rejected_at_every_mapping_level(self):
        base = {
            "version": 1,
            "compose": {},
            "terminals": [{"command": ["echo"], "wait_for": {}}],
            "browsers": [{"url": "http://localhost/", "wait_for": {}}],
        }
        for path in (
            (),
            ("compose",),
            ("terminals", 0),
            ("terminals", 0, "wait_for"),
            ("browsers", 0),
            ("browsers", 0, "wait_for"),
        ):
            with self.subTest(path=path):
                config = deepcopy(base)
                target = config
                for key in path:
                    target = target[key]
                target["typo"] = True
                self.check_config(config, False)

    def test_huge_integer_timeouts_are_rejected_without_overflow(self):
        for key, task in (
            ("terminals", {"command": ["echo"]}),
            ("browsers", {"url": "http://localhost/"}),
        ):
            for timeout in (10**400, -(10**400)):
                with self.subTest(key=key, timeout=timeout):
                    self.check_config(
                        {
                            "version": 1,
                            "compose": {"enabled": False},
                            key: [{**task, "wait_for": {"timeout": timeout}}],
                        },
                        False,
                    )

    def test_disabled_compose_rejects_files_services_and_health_prerequisites(self):
        for extra in ({"files": ["compose.yaml"]}, {"services": ["db"]}):
            with self.subTest(extra=extra):
                self.check_config({"version": 1, "compose": {"enabled": False, **extra}}, False)
        self.check_config(
            {
                "version": 1,
                "compose": {"enabled": False},
                "terminals": [{"command": ["echo"], "wait_for": {"healthy": ["db"]}}],
            },
            False,
        )

    def test_environment_and_cross_file_checks_remain_runtime_checks(self):
        # A static schema cannot know filesystem contents or services in another file.
        for config in (
            {
                "version": 1,
                "compose": {"enabled": False},
                "terminals": [{"command": ["echo"], "cwd": "missing-directory"}],
            },
            {"version": 1, "compose": {"services": ["missing-service"]}},
            {
                "version": 1,
                "compose": {"services": ["db"]},
                "terminals": [{"command": ["echo"], "wait_for": {"healthy": ["redis"]}}],
            },
        ):
            with self.subTest(config=config):
                self.validator.validate(config)
                (self.root / "dwork.yml").write_text(json.dumps(config))
                with self.assertRaises(DworkError):
                    dwork_config.load_workspace(self.root)

    def test_loader_keeps_yaml_number_spelling_and_detailed_url_checks(self):
        # JSON Schema considers 1.0 an integer; YAML preserves it as a float.
        # URL patterns intentionally leave full host/port parsing to dwork.
        for config in (
            {"version": 1.0},
            {"version": 1, "browsers": [{"url": "http://localhost:0"}]},
            {"version": 1, "browsers": [{"url": "http://localhost:65536"}]},
        ):
            with self.subTest(config=config):
                self.validator.validate(config)
                (self.root / "dwork.yml").write_text(json.dumps(config))
                with self.assertRaises(DworkError):
                    dwork_config.load_workspace(self.root)


if __name__ == "__main__":
    unittest.main()
