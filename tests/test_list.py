"""Workspace tables preserve status details and align in terminals and plain logs."""
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch
import io
import os
import re
import sys
import tempfile
import unittest

import test_dwork as legacy

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from dwork_common import DworkError, Workspace
import dwork_docker
import dwork_registry

TARGET = {"context": "default", "daemon": "test-daemon"}


class Terminal(io.StringIO):
    def isatty(self):
        return True


class ListTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="dwork-list-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        target = patch.object(dwork_docker, "docker_target", return_value=TARGET)
        self.target = target.start()
        self.addCleanup(target.stop)
        inventory = patch.object(dwork_docker, "inventory", return_value=[])
        self.inventory = inventory.start()
        self.addCleanup(inventory.stop)
        environment = patch.dict(os.environ, {"TERM": "xterm", "NO_COLOR": ""})
        environment.start()
        self.addCleanup(environment.stop)

    def entry(self, name, *, host=False, locked=False, services=None, directory=None):
        directory = directory or self.root / name
        directory.mkdir(parents=True)
        workspace = Workspace(name, directory, {}, enabled=not host, selected=services, locked=locked)
        return dwork_registry.registration(directory, [], [workspace], None if host else TARGET, name)

    def show(self, entries, stream=None):
        stream = stream if stream is not None else io.StringIO()
        errors = io.StringIO()
        with redirect_stdout(stream), redirect_stderr(errors):
            self.assertEqual(dwork_registry.list_registrations(entries), 0)
        return stream.getvalue(), errors.getvalue()

    def test_sorted_table_aligns_columns_and_places_full_paths_last(self):
        entries = [self.entry("zeta-with-a-long-name", locked=True), self.entry("app")]
        output, errors = self.show(entries)
        self.assertEqual(errors, "")
        lines = output.splitlines()
        self.assertEqual(re.split(r" {2,}", lines[0]), ["NAME", "STATUS", "LOCKED", "PATH"])
        self.assertEqual(len(lines), 3)
        self.assertTrue(lines[1].startswith("app "))
        self.assertTrue(lines[2].startswith("zeta-with-a-long-name "))
        for line, entry, lock in zip(lines[1:], reversed(entries), ("-", "yes")):
            self.assertEqual(line.index("0/0 containers running"), lines[0].index("STATUS"))
            self.assertEqual(line.index(entry["path"]), lines[0].index("PATH"))
            self.assertEqual(re.split(r" {2,}", line)[2], lock)
            self.assertTrue(line.endswith(entry["path"]))
            self.assertEqual(line, line.rstrip())

    def test_color_preserves_visible_alignment_and_plain_output_has_no_ansi(self):
        entries = [self.entry("a", locked=True), self.entry("longer")]
        plain, _ = self.show(entries)
        colored, _ = self.show(entries, Terminal())
        self.assertNotIn("\033", plain)
        self.assertIn("\033[", colored)
        self.assertEqual(re.sub(r"\033\[[0-9;]*m", "", colored), plain)
        with patch.dict(os.environ, {"NO_COLOR": "1"}):
            uncolored, _ = self.show(entries, Terminal())
        self.assertEqual(uncolored, plain)

    def test_container_counts_respect_service_selection_and_restarting_state(self):
        entry = self.entry("app", services=["web"])
        self.inventory.return_value = [legacy.container("a", "app", "web", "running"),
                                       legacy.container("b", "app", "web", "restarting"),
                                       legacy.container("c", "app", "web", "exited"),
                                       legacy.container("d", "app", "db", "running"),
                                       legacy.container("e", "unregistered", "web", "running")]
        output, _ = self.show([entry])
        self.assertIn("2/3 containers running", output)

    def test_host_only_rows_are_compact_with_one_shared_hint_and_no_docker(self):
        output, _ = self.show([self.entry("a", host=True), self.entry("b", host=True)])
        lines = output.splitlines()
        self.assertEqual(re.split(r" {2,}", lines[1])[1], "host-only")
        self.assertEqual(re.split(r" {2,}", lines[2])[1], "host-only")
        self.assertEqual(output.count("preview tracked commands"), 1)
        self.assertIn("dwork down --dry-run", lines[-1])
        self.target.assert_not_called()
        self.inventory.assert_not_called()

    def test_group_locks_identify_protected_projects(self):
        entry = self.entry("stack")
        entry["members"] = [dict(entry["members"][0], project="db", locked=True),
                            dict(entry["members"][0], project="api", locked=False)]
        output, _ = self.show([entry])
        self.assertEqual(re.split(r" {2,}", output.splitlines()[1])[2], "db")

    def test_missing_directories_other_targets_and_offline_docker_stay_visible(self):
        missing = self.entry("missing")
        Path(missing["path"]).rmdir()
        remote = self.entry("remote")
        remote["target"] = {"context": "production", "daemon": "remote"}
        output, _ = self.show([missing, remote])
        self.assertIn("unavailable directory", output)
        self.assertIn("different Docker target (production)", output)
        self.target.side_effect = DworkError("offline")
        output, errors = self.show([remote])
        self.assertIn("Docker status unavailable", output)
        self.assertIn(remote["path"], output)
        self.assertIn("Warning: Docker status unavailable: offline", errors)
        self.assertNotIn("Warning:", output)

    def test_nonprinting_path_characters_cannot_break_a_table_row(self):
        entry = self.entry("app", host=True, directory=self.root / "with\nnewline\tand\033escape")
        output, _ = self.show([entry])
        row = output.splitlines()[1]
        self.assertIn(r"with\nnewline\tand\x1bescape", row)
        self.assertNotIn("\033", output)
        self.assertEqual(len(output.splitlines()), 4)

    def test_empty_registry_keeps_the_registration_hint_without_docker(self):
        output, _ = self.show([])
        self.assertIn("No registered workspaces", output)
        self.assertIn("dwork register", output)
        self.target.assert_not_called()


if __name__ == "__main__":
    unittest.main()
