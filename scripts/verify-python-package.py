"""Build, validate, and smoke-test wheels and sdists in isolated environments."""

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import venv

ROOT = Path(__file__).resolve().parents[1]


def run(*args, cwd=None, env=None):
    subprocess.run([str(a) for a in args], cwd=cwd, env=env, check=True)


def main():
    # Invoke this script with an interpreter that has build and twine installed.
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, help="Retain verified wheel and sdist in an empty directory"
    )
    args = parser.parse_args()
    output = args.output.expanduser().resolve() if args.output else None
    if output and output.exists() and (not output.is_dir() or any(output.iterdir())):
        parser.error("--output must name a new or empty directory")
    with tempfile.TemporaryDirectory(prefix="dwork-python-package-") as temp:
        work = Path(temp)
        dist = work / "dist"
        run(sys.executable, "-m", "build", "--outdir", dist, cwd=ROOT)
        artifacts = list(dist.glob("*.whl")) + list(dist.glob("*.tar.gz"))
        if len(artifacts) != 2:
            raise RuntimeError("Expected exactly one wheel and one sdist")
        run(sys.executable, "-m", "twine", "check", "--strict", *artifacts)
        # The extracted source installer offers TRAY=1 without the Git checkout.
        # Keep the companion project and runtime artwork in the root sdist.
        with tarfile.open(next(dist.glob("*.tar.gz"))) as archive:
            names = archive.getnames()
            for relative in (
                "companion/pyproject.toml",
                "companion/README.md",
                "companion/LICENSE",
                "companion/src/dwork_tray/__main__.py",
                "companion/src/dwork_tray/assets/tray.png",
                "companion/src/dwork_tray/assets/tray.svg",
            ):
                member = next((name for name in names if name.endswith("/" + relative)), None)
                if (
                    member is None
                    or archive.extractfile(member).read() != (ROOT / relative).read_bytes()
                ):
                    raise RuntimeError("Source archive lacks matching tray input: " + relative)
        workspace = work / "workspace"
        workspace.mkdir()
        config = workspace / "dwork.yml"
        cli_env = {**os.environ, "XDG_STATE_HOME": str(work / "state")}
        expected_version = subprocess.check_output(
            [sys.executable, str(ROOT / "lib/dwork.py"), "--version"], text=True
        ).strip()
        for i, artifact in enumerate(artifacts):
            env = work / ("env-" + str(i))
            venv.EnvBuilder(with_pip=True).create(env)
            python = env / "bin/python"
            command = env / "bin/dwork"
            run(python, "-m", "pip", "install", artifact)
            run(command, "--help", cwd=workspace, env=cli_env)
            reported = subprocess.check_output(
                [str(command), "--version"], cwd=workspace, env=cli_env, text=True
            ).strip()
            metadata_version = subprocess.check_output(
                [
                    str(python),
                    "-c",
                    "from importlib.metadata import version; print('dwork ' + version('dwork-cli'))",
                ],
                cwd=workspace,
                text=True,
            ).strip()
            if reported != expected_version or metadata_version != expected_version:
                raise RuntimeError("CLI and package versions disagree")
            init_workspace = work / f"init-{i}"
            init_workspace.mkdir()
            preview = subprocess.check_output(
                [str(command), "init", "--dry-run"], cwd=init_workspace, env=cli_env, text=True
            )
            if "AGENTS.md" not in preview or any(init_workspace.iterdir()):
                raise RuntimeError("Packaged init must preview AGENTS.md without writing files")
            run(command, "init", cwd=init_workspace, env=cli_env)
            guidance = (init_workspace / "AGENTS.md").read_text()
            if any(
                instruction not in guidance
                for instruction in ("`dwork --dry-run`", "update `dwork.yml`", "`dwork validate`")
            ):
                raise RuntimeError("Packaged init did not write the expected agent guidance")
            run(command, "validate", cwd=init_workspace, env=cli_env)
            config.write_text(
                "version: 1\ncompose:\n  enabled: false\nbrowsers:\n  - url: http://localhost:3000\n"
            )
            run(command, "--dry-run", cwd=workspace, env=cli_env)
            run(command, "validate", cwd=workspace, env=cli_env)
            # Installed console entry point must preserve source CLI failures.
            config.write_text("version: 99\n")
            result = subprocess.run(
                [str(command)], cwd=workspace, env=cli_env, capture_output=True, text=True
            )
            if (
                result.returncode != 1
                or "dwork:" not in result.stderr
                or "Traceback" in result.stderr
            ):
                raise RuntimeError(
                    "Packaged CLI did not preserve friendly errors: " + result.stderr
                )
        if output:
            output.mkdir(parents=True, exist_ok=True)
            for artifact in artifacts:
                shutil.copy2(artifact, output / artifact.name)
        print("Wheel and sdist installs, init guidance, YAML support, and CLI errors passed.")


if __name__ == "__main__":
    main()
