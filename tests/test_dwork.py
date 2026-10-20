"""Behavior tests using a fake Docker executable; never contacts Docker."""
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1] / "dwork.sh"
FAKE_DOCKER = r"""#!/usr/bin/env python3
import json, os
from pathlib import Path
import sys
args = sys.argv[1:]
with open(os.environ["DWORK_TEST_LOG"], "a") as stream:
    stream.write(json.dumps(args) + "\n")
containers = json.loads(os.environ.get("DWORK_TEST_CONTAINERS", "[]"))
if args[:2] == ["context", "show"]:
    print(os.environ.get("DWORK_TEST_CONTEXT", "default"))
elif args[0] == "info":
    print(os.environ.get("DWORK_TEST_DAEMON", "test-daemon"))
elif args[0] == "compose":
    if "config" not in args:
        sys.exit("Forbidden Compose mutation")
    directory = Path.cwd()
    if "--project-directory" in args:
        directory = Path(args[args.index("--project-directory") + 1]).resolve()
    if "-f" in args:
        candidates = [Path(args[args.index("-f") + 1])]
    else:
        candidates = [folder / name for folder in (directory, *directory.parents)
                      for name in ("compose.yaml", "compose.yml", "docker-compose.yaml", "docker-compose.yml")]
    file = next((p for p in candidates if p.is_file()), None)
    if file is None:
        sys.exit("no configuration file provided: not found")
    model = json.loads(file.read_text())
    if model.get("fail"):
        sys.exit("invalid Compose config")
    print(json.dumps(model))
elif args[0] == "ps":
    if os.environ.get("DWORK_TEST_FAIL") == "ps":
        sys.exit("Cannot connect to Docker daemon")
    print("\n".join(c["Id"] for c in containers))
elif args[0] == "inspect":
    calls = [json.loads(line) for line in Path(os.environ["DWORK_TEST_LOG"]).read_text().splitlines()]
    started = {identifier for call in calls if call[0] == "start" for identifier in call[1:]}
    stopped = {identifier for call in calls if call[0] == "stop" for identifier in call[1:]}
    partial = set(json.loads(os.environ.get("DWORK_TEST_STOPPED", "[]")))
    for item in containers:
        if item["Id"] in started and os.environ.get("DWORK_TEST_FAIL") != "start":
            item["State"]["Status"] = "running"
        elif item["Id"] in stopped and (os.environ.get("DWORK_TEST_FAIL") != "stop" or item["Id"] in partial):
            item["State"]["Status"] = "exited"
    print(json.dumps([item for item in containers if item["Id"] in args[3:]]))
elif args[0] in ("stop", "start"):
    if args[0] == os.environ.get("DWORK_TEST_FAIL"):
        sys.exit("simulated Docker failure")
    print(args[1])
else:
    sys.exit("Forbidden Docker command")
"""

def container(identifier, project, service="web", state="exited"):
    return {"Id": identifier, "Config": {"Labels": {
        "com.docker.compose.project": project,
        "com.docker.compose.service": service}},
        "State": {"Status": state}}

class DworkTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="dwork-test-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / "repo"
        self.root.mkdir()
        self.bin = self.base / "bin"
        self.bin.mkdir()
        executable = self.bin / "docker"
        executable.write_text(FAKE_DOCKER)
        executable.chmod(0o755)
        self.log = self.base / "docker.jsonl"
        self.shells = [s for s in ("bash", "zsh") if shutil.which(s)]
        self.assertTrue(self.shells, "Bash or Zsh is required")

    def model(self, directory, name, **extra):
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "compose.yaml").write_text(json.dumps({
            "name": name, "services": {"web": {}}, **extra}))

    def run_dwork(self, shell, args="", answer="", containers=(), cwd=None,
                  register_current=True, managed_projects=(), **overrides):
        env = {k: v for k, v in os.environ.items() if not k.startswith(("COMPOSE_", "DWORK_"))}
        env.update(PATH=str(self.bin) + os.pathsep + env["PATH"],
                   DWORK_TEST_LOG=str(self.log),
                   XDG_STATE_HOME=str(self.base / "state"),
                   DWORK_TEST_CONTAINERS=json.dumps(containers))
        env.update(overrides)
        source = ". " + shlex.quote(str(SOURCE)) + "\ndwork "
        for project in managed_projects:
            directory = self.base / ("registered-" + project)
            self.model(directory, project)
            subprocess.run([shell, "-c", source + "register"], cwd=directory,
                           input="", text=True, capture_output=True, env=env, check=True)
        # Existing behavior tests exercise already-registered workspaces. Registry
        # tests disable this setup to exercise the first-run consent path itself.
        if register_current and not args.startswith(("register", "scan", "list", "switch", "forget", "down")):
            words = shlex.split(args)
            if words and words[0] in ("--dry-run", "status", "doctor"):
                words.pop(0)
            subprocess.run([shell, "-c", source + "register " + shlex.join(words)],
                           cwd=cwd or self.root, input="", text=True, capture_output=True, env=env)
        self.log.write_text("")
        result = subprocess.run(
            [shell, "-c", ". " + shlex.quote(str(SOURCE)) + "\ndwork " + args],
            cwd=cwd or self.root, input=answer, text=True, capture_output=True, env=env)
        calls = [json.loads(line) for line in self.log.read_text().splitlines()]
        mutations = [call for call in calls if call[0] in ("stop", "start")]
        return result, mutations, calls

    def test_children_switch_together(self):
        self.model(self.root / "backend", "api")
        self.model(self.root / "frontend", "ui")
        inventory = [container("a", "api"), container("b", "ui", state="created"),
                     container("c", "api", state="running"),
                     container("d", "outside", state="running"),
                     container("e", "infra", state="running")]
        for shell in self.shells:
            with self.subTest(shell=shell):
                result, changes, _ = self.run_dwork(
                    shell, answer="Y\n", containers=inventory, DWORK_KEEP_PROJECTS="infra",
                    managed_projects=("outside", "infra"))
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(changes, [["stop", "d"], ["start", "a"], ["start", "b"]])
                self.assertIn("(y/N)", result.stdout)
                self.assertIn("backend -> api", result.stdout)
                self.assertIn("frontend -> ui", result.stdout)

    def test_cancel_and_eof_change_nothing(self):
        self.model(self.root / "backend", "api")
        for shell in self.shells:
            for answer in ("\n", "n\n", "yes\n", ""):
                with self.subTest(shell=shell, answer=answer):
                    result, changes, _ = self.run_dwork(shell, answer=answer)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(changes, [])
                    self.assertIn("Cancelled", result.stdout)

    def test_dry_run_does_not_prompt(self):
        self.model(self.root / "backend", "api")
        for shell in self.shells:
            result, changes, _ = self.run_dwork(shell, "--dry-run",
                                               containers=[container("a", "api")])
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(changes, [])
            self.assertNotIn("(y/N)", result.stdout)
            self.assertIn("Would start existing: a", result.stdout)

    def test_does_not_search_grandchildren(self):
        self.model(self.root / "backend" / "nested", "deep")
        for shell in self.shells:
            result, changes, calls = self.run_dwork(shell, answer="y\n")
            self.assertEqual(result.returncode, 1)
            self.assertEqual(changes, [])
            self.assertEqual(len(calls), 1)
            self.assertIn("immediate subdirectories", result.stderr)

    def test_normal_config_takes_precedence_without_prompt(self):
        self.model(self.root, "main")
        self.model(self.root / "backend", "api")
        inventory = [container("a", "main"), container("b", "api", state="running")]
        for shell in self.shells:
            result, changes, _ = self.run_dwork(shell, containers=inventory)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn("(y/N)", result.stdout)
            self.assertEqual(changes, [["start", "a"]])

    def test_parent_config_takes_precedence(self):
        self.model(self.root, "main")
        child = self.root / "child"
        self.model(child / "nested", "nested")
        for shell in self.shells:
            result, _, _ = self.run_dwork(shell, "--dry-run", cwd=child)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Current Compose project: main", result.stdout)
            self.assertNotIn("nested ->", result.stdout)

    def test_invalid_root_does_not_fall_back(self):
        self.model(self.root, "main", fail=True)
        self.model(self.root / "backend", "api")
        for shell in self.shells:
            result, changes, calls = self.run_dwork(shell, answer="y\n")
            self.assertEqual(result.returncode, 1)
            self.assertEqual(changes, [])
            self.assertEqual(len(calls), 1)
            self.assertNotIn("(y/N)", result.stdout)

    def test_invalid_child_aborts_before_switch(self):
        self.model(self.root / "a", "first")
        self.model(self.root / "b", "second", fail=True)
        for shell in self.shells:
            result, changes, _ = self.run_dwork(shell, answer="y\n")
            self.assertEqual(result.returncode, 1)
            self.assertEqual(changes, [])
            self.assertNotIn("(y/N)", result.stdout)

    def test_duplicate_project_names_abort(self):
        self.model(self.root / "a", "same")
        self.model(self.root / "b", "same")
        for shell in self.shells:
            result, changes, _ = self.run_dwork(shell, answer="y\n")
            self.assertEqual(result.returncode, 1)
            self.assertEqual(changes, [])
            self.assertIn("same Compose project", result.stderr)

    def test_explicit_config_does_not_discover_children(self):
        self.model(self.root / "backend", "api")
        for shell in self.shells:
            result, changes, _ = self.run_dwork(
                shell, "-f missing.yaml", answer="y\n")
            self.assertEqual(result.returncode, 1)
            self.assertEqual(changes, [])
            self.assertNotIn("(y/N)", result.stdout)

    def test_existing_only_and_missing_warnings(self):
        self.model(self.root, "main")
        inventory = [container("a", "main", state="running"),
                     container("b", "main", service="old-job"),
                     container("c", "main", service="paused", state="paused")]
        for shell in self.shells:
            result, changes, _ = self.run_dwork(shell, containers=inventory)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(changes, [["start", "b"]])
            self.assertIn("paused", result.stderr)
            result, changes, _ = self.run_dwork(shell)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(changes, [])
            self.assertIn("has no container", result.stderr)

    def test_stop_failure_prevents_start(self):
        self.model(self.root, "main")
        for shell in self.shells:
            result, changes, _ = self.run_dwork(
                shell, containers=[container("a", "main"),
                                   container("b", "other", state="running")],
                DWORK_TEST_FAIL="stop", managed_projects=("other",))
            self.assertEqual(result.returncode, 1)
            self.assertEqual(changes, [["stop", "b"]])

    def test_skips_symlinked_children(self):
        self.model(self.base / "external", "external")
        (self.root / "linked").symlink_to(self.base / "external", target_is_directory=True)
        for shell in self.shells:
            result, changes, _ = self.run_dwork(shell, answer="y\n")
            self.assertEqual(result.returncode, 1)
            self.assertEqual(changes, [])

if __name__ == "__main__":
    unittest.main()
