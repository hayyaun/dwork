"""Build recipes must provide the real Git used by local-archive regressions."""

from email.parser import Parser
import os
from pathlib import Path
import re
import subprocess
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]


class PackagingDependencyTests(unittest.TestCase):
    def provisioned(self, script, package_manager):
        # Stop at the first dependency installation, before any package, user,
        # filesystem, or build commands can change the host. Execute the actual
        # recipe's shell expansion rather than duplicating its argument list.
        if package_manager == "sudo":
            fake = """sudo() {
              [[ $1 == apt-get ]] || return 74
              shift
              [[ $1 != update ]] || return 0
              printf '%s\\0' "$@"
              return 73
            }
            """
        else:
            self.assertIn(package_manager, ("dnf", "pacman"))
            fake = package_manager + "() { printf '%s\\0' \"$@\"; return 73; }\n"
        environment = dict(os.environ)
        environment.pop("BASH_ENV", None)
        environment.pop("ENV", None)
        result = subprocess.run(
            ["bash", "-e", "-c", fake + script, "dependency-regression", "0.4.1"],
            env=environment,
            capture_output=True,
            timeout=15,
        )
        self.assertEqual(result.returncode, 73, result.stderr.decode())
        return set(result.stdout.decode().split("\0")) - {""}

    def arch_dependencies(self, relative):
        result = subprocess.run(
            [
                "bash",
                "-e",
                "-c",
                'source "$1"; printf "runtime=%s\\n" "${depends[@]}"; '
                'printf "check=%s\\n" "${checkdepends[@]}"',
                "dependency-regression",
                str(ROOT / relative),
            ],
            env={**os.environ, "DWORK_VERSION": "0.4.1", "DWORK_SOURCE_SHA256": "a" * 64},
            text=True,
            capture_output=True,
            check=True,
            timeout=15,
        )
        fields = {"runtime": set(), "check": set()}
        for line in result.stdout.splitlines():
            kind, _, package = line.partition("=")
            fields[kind].add(re.split(r"[<>=]", package)[0])
        return fields

    def test_fedora_declares_and_provisions_git_for_source_checks_only(self):
        spec = (ROOT / "packaging/fedora/dwork.spec").read_text()
        build = set(re.findall(r"^BuildRequires:\s+(\S+)", spec, re.MULTILINE))
        runtime = set(re.findall(r"^Requires:\s+(\S+)", spec, re.MULTILINE))
        supplied = self.provisioned(
            (ROOT / "packaging/fedora/build-in-container.sh").read_text(), "dnf"
        )
        self.assertIn("git-core", build)
        self.assertTrue(
            build <= supplied, f"Unprovisioned Fedora build dependencies: {build - supplied}"
        )
        self.assertTrue({"git", "git-core"}.isdisjoint(runtime))

    def test_arch_declares_and_provisions_git_for_source_checks_only(self):
        dependencies = self.arch_dependencies("packaging/arch/PKGBUILD")
        supplied = self.provisioned(
            (ROOT / "packaging/arch/build-in-container.sh").read_text(), "pacman"
        )
        self.assertIn("git", dependencies["check"])
        self.assertTrue(dependencies["check"] <= supplied)
        self.assertNotIn("git", dependencies["runtime"])

    def test_aur_declares_and_provisions_git_for_source_checks_only(self):
        dependencies = self.arch_dependencies("packaging/aur/PKGBUILD")
        supplied = self.provisioned(
            (ROOT / "packaging/aur/verify-in-arch.sh").read_text(), "pacman"
        )
        self.assertIn("git", dependencies["check"])
        self.assertTrue(dependencies["check"] <= supplied)
        self.assertNotIn("git", dependencies["runtime"])

    def test_debian_declares_and_provisions_git_for_source_checks_only(self):
        paragraphs = (ROOT / "packaging/debian/control").read_text().split("\n\n")
        source = Parser().parsestr(paragraphs[0])
        binary = Parser().parsestr(paragraphs[1])
        build = set(re.findall(r"(?:^|,)\s*([a-z0-9+.-]+)", source["Build-Depends"]))
        runtime = set(re.findall(r"(?:^|,)\s*([a-z0-9+.-]+)", binary["Depends"]))
        self.assertIn("git", build)
        self.assertNotIn("git", runtime)
        for workflow, job in (("packaging.yml", "debian"), ("release.yml", "packages")):
            with self.subTest(workflow=workflow):
                data = yaml.safe_load((ROOT / ".github/workflows" / workflow).read_text())
                script = next(
                    step["run"]
                    for step in data["jobs"][job]["steps"]
                    if "apt-get install" in step.get("run", "")
                )
                self.assertIn("git", self.provisioned(script, "sudo"))


if __name__ == "__main__":
    unittest.main()
