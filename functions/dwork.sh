# Shared functions for Bash and Zsh.
# dwork [--dry-run] [Docker Compose global options]
# Optional shared projects: export DWORK_KEEP_PROJECTS=infra,monitoring
dwork() {
    command -v python3 >/dev/null 2>&1 || {
        printf "%s\n" "dwork: python3 is required." >&2
        return 1
    }
    python3 -c '
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

class DworkError(Exception):
    pass

def docker(*args, cwd=None):
    result = subprocess.run(["docker", *args], cwd=cwd, text=True, capture_output=True)
    if result.returncode:
        raise DworkError(result.stderr.strip() or "Docker command failed.")
    return result.stdout

def read_model(directory, options):
    raw = docker("compose", *options, "config", "--no-interpolate",
                 "--no-env-resolution", "--format", "json", cwd=directory)
    model = json.loads(raw)
    name = model.get("name", "")
    if not isinstance(name, str) or not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", name):
        raise DworkError("Cannot identify a valid Compose project; nothing changed.")
    services = model.get("services", {})
    if not isinstance(services, dict):
        raise DworkError("Invalid Compose service definitions; nothing changed.")
    return name, services

def main():
    options = sys.argv[1:]
    preview = bool(options and options[0] == "--dry-run")
    if preview:
        options = options[1:]
    if options and options[0] in ("--help", "-h"):
        print("Usage: dwork [--dry-run] [Docker Compose global options]")
        print("Stop other Compose projects and start existing stopped containers.")
        print("With no default config, discover immediate child directories only.")
        print("Child-project switching requires confirmation (y/N).")
        print("Dry-run previews changes without confirmation or mutation.")
        print("Never creates, rebuilds, recreates, or removes containers.")
        print("DWORK_KEEP_PROJECTS: comma-separated projects to leave running.")
        return 0
    if not shutil.which("docker"):
        raise DworkError("docker is not available.")
    directory = Path.cwd()
    filenames = ("compose.yaml", "compose.yml", "docker-compose.yaml", "docker-compose.yml")
    discovered = False
    try:
        name, services = read_model(directory, options)
        projects = {name: (directory, services)}
    except DworkError:
        # Respect explicit Compose configuration. Invalid existing configurations
        # must fail rather than silently switch to a different set of projects.
        ancestors = (directory, *directory.parents)
        configured = (
            bool(options)
            or bool(os.environ.get("COMPOSE_FILE"))
            or bool(os.environ.get("COMPOSE_ENV_FILES"))
            or any((folder / file).is_file() for folder in ancestors for file in filenames)
            or any((folder / ".env").is_file() for folder in ancestors)
        )
        if configured:
            raise
        children = [
            child for child in sorted(directory.iterdir())
            if child.name != ".git" and not child.is_symlink() and child.is_dir()
            and any((child / file).is_file() for file in filenames)
        ]
        if not children:
            raise DworkError("No Compose config here, in parent directories, or in immediate subdirectories; nothing changed.")
        projects = {}
        for child in children:
            name, services = read_model(child, [])
            if name in projects:
                raise DworkError("Child directories resolve to the same Compose project: " + name + "; use explicit Compose options.")
            projects[name] = (child, services)
        discovered = True

    ids = docker("ps", "--all", "--quiet", "--filter", "label=com.docker.compose.project").split()
    containers = json.loads(docker("inspect", "--type", "container", *ids)) if ids else []
    if not isinstance(containers, list):
        raise DworkError("Invalid container inventory; nothing changed.")
    keep = {name.strip() for name in os.environ.get("DWORK_KEEP_PROJECTS", "").split(",") if name.strip()}
    stops, starts = [], []
    present = set()
    warnings = []
    for container in containers:
        labels = container.get("Config", {}).get("Labels") or {}
        project = labels.get("com.docker.compose.project")
        if not project:
            continue
        service = labels.get("com.docker.compose.service", "(unknown service)")
        identifier = container["Id"]
        state = container["State"]["Status"]
        if project in projects:
            present.add((project, service))
            if state in ("created", "exited"):
                starts.append((identifier, project, service))
            elif state not in ("running", "restarting"):
                warnings.append("Container " + identifier[:12] + " is " + state + "; handle it manually.")
        elif project not in keep and state in ("running", "restarting"):
            stops.append((identifier, project))
    for name, (_, services) in projects.items():
        for service in services:
            if (name, service) not in present:
                warnings.append("Service " + name + "/" + service + " has no container; create it manually if needed (it may be profile-specific).")

    if discovered:
        print("Compose projects found in immediate subdirectories:")
        for name, (folder, _) in projects.items():
            print("  " + str(folder.relative_to(directory)) + " -> " + name)
    else:
        print("Current Compose project: " + next(iter(projects)))
    for warning in warnings:
        print("Warning: " + warning, file=sys.stderr)
    if discovered or preview:
        for identifier, project in stops:
            print("Would stop: " + identifier[:12] + " (" + project + ")")
        for identifier, project, service in starts:
            print("Would start existing: " + identifier[:12] + " (" + project + "/" + service + ")")
        if not stops and not starts:
            print("No container changes needed.")
    if preview:
        return 0
    if discovered:
        try:
            answer = input("Switch all listed projects together? (y/N) ")
        except EOFError:
            answer = ""
        if answer.strip().lower() != "y":
            print("Cancelled; nothing changed.")
            return 0
    # Stop outside projects once; never stop one of the selected child projects.
    for identifier, project in stops:
        print("Stopping: " + identifier[:12] + " (" + project + ")", flush=True)
        docker("stop", identifier)
    for identifier, project, service in starts:
        print("Starting existing: " + identifier[:12] + " (" + project + "/" + service + ")", flush=True)
        docker("start", identifier)
    return 0

try:
    sys.exit(main())
except (DworkError, OSError, ValueError, KeyError, TypeError) as error:
    print("dwork: " + str(error), file=sys.stderr)
    sys.exit(1)
except KeyboardInterrupt:
    print("\ndwork: cancelled.", file=sys.stderr)
    sys.exit(130)
' "$@"
}
