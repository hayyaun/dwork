"""Render the stable formula or prepare a checksummed exact-commit Homebrew source."""

import argparse
import ast
import hashlib
import json
from pathlib import Path
import re
from string import Template
import subprocess

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = Path("packaging/homebrew/dwork.rb.in")
STABLE_SOURCE = Path("packaging/homebrew/stable.json")
STABLE_FORMULA = Path("packaging/homebrew/dwork.rb")


def render_formula(
    template: str, url: str, version: str, sha256: str, *, explicit_version: bool = True
) -> str:
    if not re.fullmatch(r"[0-9a-f]{64}", sha256):
        raise ValueError("A SHA-256 checksum is required")
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+[A-Za-z0-9.+-]*", version):
        raise ValueError("Expected a literal package version")
    if not url.startswith(("https://", "file://")) or any(c in url for c in "\r\n#{"):
        raise ValueError("Expected an HTTPS or local archive URL without interpolation")
    return Template(template).substitute(
        source_url=json.dumps(url),
        source_version_line=("  version " + json.dumps(version) + "\n") if explicit_version else "",
        source_sha256=json.dumps(sha256),
    )


def stable_formula(repository: Path) -> str:
    source = json.loads((repository / STABLE_SOURCE).read_text())
    return render_formula((repository / TEMPLATE).read_text(), **source, explicit_version=False)


def check_stable(repository: Path) -> None:
    if (repository / STABLE_FORMULA).read_text() != stable_formula(repository):
        raise ValueError("Stable formula differs from its template/metadata; regenerate dwork.rb")


def git(repository: Path, *arguments: str) -> str:
    return subprocess.check_output(["git", "-C", str(repository), *arguments], text=True).strip()


def package_version(source: str) -> str:
    for node in ast.parse(source).body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "__version__" for target in node.targets
        ):
            value = ast.literal_eval(node.value)
            if isinstance(value, str):
                return value
    raise ValueError("lib/dwork_version.py must define a literal __version__")


def prepare_checkout(repository: Path, output: Path, expected_revision: str) -> dict[str, str]:
    repository, output = repository.resolve(), output.resolve()
    # Reject ambiguous input before writing anything. Archive the captured commit ID,
    # never an uncommitted mixture or the current state of a remote main branch.
    revision = git(repository, "rev-parse", "HEAD")
    if (
        not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", expected_revision)
        or revision != expected_revision
    ):
        raise ValueError("Checkout HEAD does not match the expected full commit ID")
    if git(repository, "status", "--porcelain", "--untracked-files=normal"):
        raise ValueError(
            "Checkout must be clean; commit or isolate changes before preparing a revision"
        )
    if output.is_relative_to(repository):
        raise ValueError("Output must be outside the source checkout")
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError("Output must be a new or empty directory")
    check_stable(repository)
    template = git(repository, "show", revision + ":" + TEMPLATE.as_posix()) + "\n"
    version = package_version(git(repository, "show", revision + ":lib/dwork_version.py"))
    output.mkdir(parents=True, exist_ok=True)
    archive = output / ("dwork-" + revision + ".tar.gz")
    with archive.open("xb") as stream:
        subprocess.run(
            [
                "git",
                "-C",
                str(repository),
                "archive",
                "--format=tar.gz",
                "--prefix=dwork-" + revision + "/",
                revision,
            ],
            stdout=stream,
            check=True,
        )
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    formula = render_formula(template, archive.as_uri(), version, digest)
    with (output / "dwork.rb").open("x") as stream:
        stream.write(formula)
    metadata = {"revision": revision, "version": version, "archive": archive.name, "sha256": digest}
    with (output / "source.json").open("x") as stream:
        json.dump(metadata, stream, indent=2)
        stream.write("\n")
    return metadata


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--check-stable", action="store_true", help="Check generated stable formula parity"
    )
    mode.add_argument(
        "--render-stable", action="store_true", help="Print the stable formula to stdout"
    )
    mode.add_argument("--output", type=Path, help="New/empty directory outside this checkout")
    parser.add_argument(
        "--expected-revision", help="Full checked-out commit ID; required with --output"
    )
    args = parser.parse_args()
    if bool(args.output) != bool(args.expected_revision):
        parser.error("--output and --expected-revision must be used together")
    try:
        if args.check_stable:
            check_stable(ROOT)
            print("Stable Homebrew formula matches its template and metadata.")
        elif args.render_stable:
            print(stable_formula(ROOT), end="")
        else:
            print(json.dumps(prepare_checkout(ROOT, args.output, args.expected_revision), indent=2))
    except (OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError) as error:
        parser.exit(1, "Homebrew preparation failed: " + str(error) + "\n")


if __name__ == "__main__":
    main()
