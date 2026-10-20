"""Build, validate, and smoke-test wheels and sdists in isolated environments."""
from pathlib import Path
import subprocess
import sys
import tempfile
import venv

ROOT = Path(__file__).resolve().parents[1]

def run(*args, cwd=None):
    subprocess.run([str(a) for a in args], cwd=cwd, check=True)

def main():
    # Invoke this script with an interpreter that has build and twine installed.
    with tempfile.TemporaryDirectory(prefix="dwork-python-package-") as temp:
        work = Path(temp)
        dist = work / "dist"
        run(sys.executable, "-m", "build", "--outdir", dist, cwd=ROOT)
        artifacts = list(dist.glob("*.whl")) + list(dist.glob("*.tar.gz"))
        if len(artifacts) != 2:
            raise RuntimeError("Expected exactly one wheel and one sdist")
        run(sys.executable, "-m", "twine", "check", "--strict", *artifacts)
        workspace = work / "workspace"
        workspace.mkdir()
        config = workspace / "dwork.yml"
        for i, artifact in enumerate(artifacts):
            env = work / ("env-" + str(i))
            venv.EnvBuilder(with_pip=True).create(env)
            python = env / "bin/python"
            command = env / "bin/dwork"
            run(python, "-m", "pip", "install", artifact)
            run(command, "--help", cwd=workspace)
            config.write_text("version: 1\ncompose:\n  enabled: false\n")
            run(command, "--dry-run", cwd=workspace)
            # Installed console entry point must preserve source CLI failures.
            config.write_text("version: 99\n")
            result = subprocess.run([str(command)], cwd=workspace, capture_output=True, text=True)
            if result.returncode != 1 or "dwork:" not in result.stderr or "Traceback" in result.stderr:
                raise RuntimeError("Packaged CLI did not preserve friendly errors: " + result.stderr)
        print("Wheel and sdist installs, YAML support, and CLI error handling passed.")

if __name__ == "__main__":
    main()
