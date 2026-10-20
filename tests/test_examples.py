"""Validate every shipped example against the real configuration parser."""
import importlib.util
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("dwork_examples_runtime", REPO / "lib/dwork.py")
runtime = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = runtime
SPEC.loader.exec_module(runtime)

class ExampleTests(unittest.TestCase):
    def test_all_shipped_examples_parse(self):
        expected = {
            "compose-only.yml": (True, 0, ["postgres", "redis"]),
            "backend-with-db.yml": (True, 1, ["postgres"]),
            "full-stack.yml": (True, 2, ["postgres"]),
            "host-only.yml": (False, 1, None),
        }
        self.assertEqual({p.name for p in (REPO / "examples").glob("*.yml")}, set(expected))
        for filename, (enabled, count, selected) in expected.items():
            with self.subTest(example=filename), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                (root / "backend").mkdir()
                (root / "frontend").mkdir()
                shutil.copy2(REPO / "examples" / filename, root / "dwork.yml")
                with patch.object(runtime, "read_model", return_value=(
                    "demo", {"postgres": {"healthcheck": {}}, "redis": {}})) as compose:
                    workspace = runtime.load_workspace(root)
                    self.assertEqual(workspace.enabled, enabled)
                    self.assertEqual(len(workspace.terminals), count)
                    self.assertEqual(workspace.selected, selected)
                    self.assertEqual(compose.call_count, int(enabled))
                    for task in workspace.terminals:
                        self.assertTrue(task.cwd.is_dir())
                        self.assertTrue(set(task.healthy) <= {"postgres", "redis"})

if __name__ == "__main__":
    unittest.main()
