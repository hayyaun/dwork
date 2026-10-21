"""Docker and Compose commands, container inventory, health gates, and status."""
import json
import os
import re
import shlex
import subprocess
import sys
import time

from dwork_common import DworkError, color, colored_name


def container_name(item):
    labels = item.get("Config", {}).get("Labels") or {}
    return labels.get("com.docker.compose.project", "?") + "/" + labels.get("com.docker.compose.service", "?")


def docker_target():
    target = {"context": docker("context", "show").strip(),
              "daemon": docker("info", "--format", "{{.ID}}").strip()}
    if not all(target.values()):
        raise DworkError("Cannot identify the Docker target; nothing changed.")
    return target


def run_command(args, cwd=None, *, timeout=None):
    try:
        result = subprocess.run(args, cwd=cwd, text=True, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired as error:
        raise DworkError("Timed out running command: " + shlex.join(args)
                         + ". Inspect workload state before retrying.") from error
    if result.returncode:
        raise DworkError(result.stderr.strip() or "Command failed: " + shlex.join(args))
    return result.stdout


def docker(*args, cwd=None, timeout=None):
    return run_command(["docker", *args], cwd, timeout=timeout)


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


def inventory():
    ids = docker("ps", "--all", "--quiet", "--filter", "label=com.docker.compose.project").split()
    items = json.loads(docker("inspect", "--type", "container", *ids)) if ids else []
    if not isinstance(items, list):
        raise DworkError("Invalid container inventory; nothing changed.")
    return items


def service_containers(containers, project, service):
    return [c for c in containers
            if (c.get("Config", {}).get("Labels") or {}).get("com.docker.compose.project") == project
            and (c.get("Config", {}).get("Labels") or {}).get("com.docker.compose.service") == service]


def wait_healthy(ids, timeout):
    deadline = time.monotonic() + timeout
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise DworkError("Timed out waiting for healthy containers; terminals were not opened.")
        items = json.loads(docker("inspect", "--type", "container", *ids, timeout=remaining))
        if {c["Id"] for c in items} != set(ids):
            raise DworkError("A required container disappeared; terminals were not opened.")
        ready = True
        for item in items:
            state = item["State"]
            if state["Status"] in ("exited", "dead", "paused", "removing"):
                raise DworkError("A required container is " + state["Status"] + "; terminals were not opened.")
            health = state.get("Health", {}).get("Status")
            if health is None:
                raise DworkError("A required container has no Docker health check; terminals were not opened.")
            if health == "unhealthy":
                raise DworkError("A required container is unhealthy; terminals were not opened.")
            ready = ready and state["Status"] == "running" and health == "healthy"
        if ready:
            return
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise DworkError("Timed out waiting for healthy containers; terminals were not opened.")
        time.sleep(min(1, remaining))


def show_target():
    context = docker("context", "show").strip()
    print("Docker context: " + colored_name(context))
    # DOCKER_HOST can override the endpoint associated with the displayed context.
    if os.environ.get("DOCKER_HOST") and not os.environ.get("DOCKER_CONTEXT"):
        print("Docker endpoint override: DOCKER_HOST is set (value hidden).")


def show_status(workspaces, containers):
    for workspace in workspaces:
        marker = " [locked]" if workspace.locked else ""
        print("Workspace: " + colored_name(workspace.name) + " (" + str(workspace.directory) + ")" + color(marker, "warning"))
        if not workspace.enabled:
            print("  Compose disabled; preview tracked commands with dwork down --dry-run.")
            continue
        for item in containers:
            labels = item.get("Config", {}).get("Labels") or {}
            if labels.get("com.docker.compose.project") != workspace.name:
                continue
            service = labels.get("com.docker.compose.service", "(unknown service)")
            state = item["State"]
            health = state.get("Health", {}).get("Status", "no health check")
            managed = "managed" if workspace.manages(service) else "unmanaged"
            style = ("stop" if health == "unhealthy" or state["Status"] in ("exited", "dead")
                     else "start" if state["Status"] == "running" and health != "starting" else "warning")
            print("  " + colored_name(service) + " / " + item["Id"][:12] + ": "
                  + color(state["Status"] + ", " + health, style) + " (" + managed + ")")
        for service in workspace.services:
            if workspace.manages(service) and not service_containers(containers, workspace.name, service):
                print("  " + colored_name(service) + color(": missing container; run the project's initial setup manually.", "warning"))
    if any(w.terminals for w in workspaces):
        print("Host commands are configured; preview tracked commands with dwork down --dry-run.")


def report_failure(completed, pending, step, containers):
    print(color("Switch incomplete at: " + step, "warning", sys.stderr), file=sys.stderr)
    print("Completed: " + ("; ".join(completed) or "none"), file=sys.stderr)
    print("Not confirmed complete: " + ("; ".join(pending) or "none"), file=sys.stderr)
    print("The interrupted or failed operation may have changed state; inspect before retrying.", file=sys.stderr)
    print("No automatic rollback was attempted. Inspect tracked host commands with dwork down --dry-run.", file=sys.stderr)
    try:
        current = inventory() if containers else []
        running = [((c.get("Config", {}).get("Labels") or {}).get("com.docker.compose.project", "?")
                    + "/" + c["Id"][:12]) for c in current
                   if c["State"]["Status"] in ("running", "restarting")]
        print("Still running/restarting: " + (", ".join(running) or "none"), file=sys.stderr)
    except (DworkError, OSError, ValueError, KeyError, TypeError):
        print("Could not refresh container state; check docker ps --all.", file=sys.stderr)
    print("Inspect current state: dwork status; preview a retry: dwork --dry-run (use the same Compose options).", file=sys.stderr)
    for action in completed:
        if action.startswith("stop "):
            identifier = action.split()[1]
            print("To restore the stopped container if appropriate: docker start " + identifier, file=sys.stderr)
    print("For a failed container: docker inspect <container-id> and docker logs --tail 50 <container-id>.", file=sys.stderr)
