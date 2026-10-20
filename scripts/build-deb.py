"""Build unsigned Debian binaries in a temporary source tree."""
import argparse
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "dist/debian")
    args = parser.parse_args()
    output = args.output.expanduser().resolve()
    if not shutil.which("dpkg-buildpackage"):
        parser.error("Install dpkg-dev and the dependencies in packaging/debian/control first.")
    with tempfile.TemporaryDirectory(prefix="dwork-debian-") as temp:
        work = Path(temp)
        source = work / "dwork"
        shutil.copytree(ROOT, source, ignore=shutil.ignore_patterns(
            ".git", "dist", "build", "*.egg-info", ".venv*", "__pycache__", "*.pyc"))
        shutil.copytree(ROOT / "packaging/debian", source / "debian")
        (source / "debian/README.md").unlink()
        (source / "debian/rules").chmod(0o755)
        subprocess.run(["dpkg-buildpackage", "-us", "-uc", "-b"], cwd=source, check=True)
        artifacts = [p for p in work.iterdir() if p.is_file()]
        if not any(p.suffix == ".deb" for p in artifacts):
            raise RuntimeError("Build produced no .deb package")
        output.mkdir(parents=True, exist_ok=True)
        for artifact in artifacts:
            shutil.copy2(artifact, output / artifact.name)
    print("Debian artifacts: " + str(output))

if __name__ == "__main__":
    main()
