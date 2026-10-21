"""Switch and down apply the same registered-workspace shutdown policy."""

import json
import unittest

import test_dwork as legacy


class ShutdownPolicyTests(unittest.TestCase):
    def setUp(self):
        self.fixture = legacy.DworkTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def cli(self, args, **kwargs):
        kwargs.setdefault("answer", "y\n")
        return self.fixture.run_dwork("bash", args, register_current=False, **kwargs)

    def register(self, name, **config):
        directory = self.fixture.base / name
        self.fixture.model(directory, name, services={"web": {}, "db": {}})
        (directory / "dwork.yml").write_text(json.dumps({"version": 1, **config}))
        result, changes, _ = self.cli("register " + name, cwd=directory)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(changes, [])
        return directory

    def test_switch_and_down_share_service_state_and_protection_policy(self):
        self.register("selected")
        self.register("outgoing", compose={"services": ["db"]})
        self.register("locked", locked=True)
        self.register("kept")
        inventory = [legacy.container("selected-running", "selected", state="running"),
                     legacy.container("selected-start", "selected", "db"),
                     legacy.container("outgoing-paused", "outgoing", "db", "paused"),
                     legacy.container("outgoing-unmanaged", "outgoing", "web", "running"),
                     legacy.container("locked", "locked", state="running"),
                     legacy.container("kept", "kept", state="running"),
                     legacy.container("unknown", "unknown", state="running")]
        result, changes, _ = self.cli("switch selected", containers=inventory, DWORK_KEEP_PROJECTS="kept")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(changes, [["stop", "outgoing-paused"], ["start", "selected-start"]])
        result, changes, _ = self.cli("down", containers=inventory, DWORK_KEEP_PROJECTS="kept")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(changes, [["stop", "selected-running", "outgoing-paused"]])

    def test_switch_stops_outgoing_containers_in_one_batch_before_start(self):
        self.register("selected")
        self.register("first")
        self.register("second")
        result, changes, _ = self.cli("switch selected", containers=[
            legacy.container("a", "first", state="running"),
            legacy.container("b", "second", state="restarting"),
            legacy.container("c", "selected", state="created")])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(changes, [["stop", "a", "b"], ["start", "c"]])

    def test_switch_to_host_only_stops_registered_containers_on_current_target(self):
        selected = self.fixture.base / "selected"
        selected.mkdir()
        (selected / "dwork.yml").write_text("version: 1\ncompose: {enabled: false}\n")
        result, _, _ = self.cli("register selected", cwd=selected)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.register("outgoing")
        result, changes, _ = self.cli("switch selected", containers=[
            legacy.container("a", "outgoing", state="running")])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(changes, [["stop", "a"]])

    def test_switch_uses_stored_ownership_for_missing_outgoing_directory(self):
        self.register("selected")
        outgoing = self.register("outgoing")
        outgoing.rename(self.fixture.base / "moved")
        result, changes, _ = self.cli("switch selected", containers=[
            legacy.container("a", "outgoing", state="running")])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(changes, [["stop", "a"]])

    def test_switch_does_not_stop_containers_owned_on_another_docker_target(self):
        self.register("selected")
        remote = self.fixture.base / "remote"
        self.fixture.model(remote, "remote")
        result, _, _ = self.cli("register remote", cwd=remote, DWORK_TEST_CONTEXT="remote")
        self.assertEqual(result.returncode, 0, result.stderr)
        result, changes, _ = self.cli("switch selected", containers=[
            legacy.container("a", "remote", state="running")])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(changes, [])


if __name__ == "__main__":
    unittest.main()
