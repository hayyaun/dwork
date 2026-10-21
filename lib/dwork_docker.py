"""Docker and Compose commands, container inventory, health gates, and status."""
import json
import os
import re
import time

from dwork_common import DworkError, color, colored_name
from dwork_process import run_command


def container_name(item):
    labels = item.get("Config", {}).get("Labels") or {}
    return labels.get("com.docker.compose.project", "?") + "/" + labels.get("com.docker.compose.service", "?")


def docker_target():
    target = {"context": docker("context", "show").strip(),
              "daemon": docker("info", "--format", "{{.ID}}").strip()}
    if not all(target.values()):
        raise DworkError("Cannot identify the Docker target; nothing changed.")
    return target


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
