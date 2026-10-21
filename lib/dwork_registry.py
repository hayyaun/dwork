"""Versioned workspace storage, locking, ownership, and registration display."""
from contextlib import contextmanager
from pathlib import Path
import json
import os
import re
import sys
import tempfile

from dwork_common import DworkError, color, colored_name
import dwork_config
import dwork_docker


def validate_workspace_name(name):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", name):
        raise DworkError("Workspace name must contain letters, digits, dots, underscores, or hyphens"
                         + " and start with a letter or digit.")


def registry_path():
    state = Path(os.environ.get("XDG_STATE_HOME", ""))
    if not state.is_absolute():
        state = Path.home() / ".local/state"
    return state / "dwork/workspaces.json"


def read_registry():
    path = registry_path()
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text())
        if type(data["version"]) is not int or data["version"] != 1 or not isinstance(data["workspaces"], list):
            raise ValueError()
        names, paths = set(), set()
        for entry in data["workspaces"]:
            if "direct" in entry and type(entry["direct"]) is not bool:
                raise ValueError()
            if (not isinstance(entry["name"], str) or not entry["name"]
                    or not isinstance(entry["path"], str) or not Path(entry["path"]).is_absolute()
                    or entry["name"] in names or entry["path"] in paths
                    or not isinstance(entry["options"], list)
                    or any(not isinstance(v, str) for v in entry["options"])
                    or not isinstance(entry["environment"], dict)
                    or any(k not in dwork_config.COMPOSE_ENV or not isinstance(v, str)
                           for k, v in entry["environment"].items())
                    or not isinstance(entry["members"], list) or not entry["members"]):
                raise ValueError()
            target = entry["target"]
            if target is not None and (not isinstance(target, dict) or set(target) != {"context", "daemon"}
                    or any(not isinstance(v, str) or not v for v in target.values())):
                raise ValueError()
            for member in entry["members"]:
                if not isinstance(member, dict):
                    raise ValueError()
                member.setdefault("locked", False)
                if (not isinstance(member["project"], str) or not member["project"]
                        or not isinstance(member["directory"], str)
                        or not Path(member["directory"]).is_absolute()
                        or type(member["enabled"]) is not bool or type(member["locked"]) is not bool
                        or (member["services"] is not None and
                            (not isinstance(member["services"], list) or
                             any(not isinstance(s, str) for s in member["services"])))):
                    raise ValueError()
            if (target is not None) != any(m["enabled"] for m in entry["members"]):
                raise ValueError()
            names.add(entry["name"])
            paths.add(entry["path"])
        return data["workspaces"]
    except (ValueError, KeyError, TypeError):
        raise DworkError("Invalid workspace registry: " + str(path)
                         + ". Restore or repair it before switching; nothing changed.")


@contextmanager
def registry_lock():
    # Serialize registry updates and switches; never hold a lock in read-only modes.
    import fcntl
    path = registry_path()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (path.parent / "workspaces.lock").open("a") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise DworkError("Another dwork registration or switch is in progress; try again when it finishes.")
        yield


def save_registry(entries):
    path = registry_path()
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            json.dump({"version": 1, "workspaces": entries}, stream, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def registration(directory, options, workspaces, target, name, direct=False):
    entry = {"name": name, "path": str(directory.resolve()), "options": list(options),
            "environment": {key: os.environ[key] for key in dwork_config.COMPOSE_ENV if key in os.environ},
            "target": target,
            "members": [{"project": w.name, "directory": str(w.directory.resolve()),
                         "enabled": w.enabled, "services": w.selected, "locked": w.locked} for w in workspaces]}
    if direct:
        entry["direct"] = True
    return entry


def refresh_locks(entries):
    """Read lock policy without loading Compose or changing registered ownership."""
    changed = False
    for entry in entries:
        for member in entry["members"]:
            locked = member.get("locked", False)
            path = Path(member["directory"]) / "dwork.yml"
            try:
                path.stat()
                config = dwork_config.read_config(path)
                if type(config.get("version")) is not int or config["version"] != 1:
                    raise DworkError("version must be 1")
                locked = dwork_config.lock_value(config)
            except FileNotFoundError:
                pass  # Retain the last known policy when a directory/config disappears.
            except (DworkError, OSError, ValueError, TypeError) as error:
                locked = True
                print(color("Warning: protecting " + member["project"] + "; cannot read lock policy in "
                            + str(path) + ": " + str(error), "warning", sys.stderr), file=sys.stderr)
            changed = changed or member.get("locked", False) != locked
            member["locked"] = locked
    return changed


def locked_projects(entries, target):
    return sorted({m["project"] for e in entries if e["target"] == target
                   for m in e["members"] if m["enabled"] and m.get("locked", False)})


def check_ownership(entries, candidate):
    projects = {m["project"] for m in candidate["members"] if m["enabled"]}
    for entry in entries:
        if entry["path"] == candidate["path"]:
            continue
        if entry["target"] == candidate["target"] and projects.intersection(
                m["project"] for m in entry["members"] if m["enabled"]):
            raise DworkError("Compose project already registered to " + entry["name"]
                             + " (" + entry["path"] + "). Use a distinct Compose project name"
                             + " or forget the old registration; nothing changed.")


def registered_services(entries, target):
    """Return unlocked container ownership even when source directories are gone."""
    managed = {}
    for entry in entries:
        if entry["target"] != target:
            continue
        for member in entry["members"]:
            if member["enabled"] and not member.get("locked", False):
                project = member["project"]
                if project in managed:
                    raise DworkError("Ambiguous registered Compose project: " + project + "; nothing changed.")
                managed[project] = member["services"]
    return managed


def confirm_registration(entry):
    print("Register workspace " + colored_name(entry["name"], repr(entry["name"])) + " at " + entry["path"] + "?")
    if all(m.get("locked", False) for m in entry["members"]):
        print("This workspace is locked; switches and down will leave its containers and tracked commands running.")
    else:
        print("Future switches may stop its unlocked managed containers and tracked commands. Unregistered projects stay running.")
    try:
        return input("Register and switch? (y/N) ").strip().lower() == "y"
    except EOFError:
        return False


def list_registrations(entries):
    if not entries:
        print("No registered workspaces. Run dwork register in a project to remember it.")
        return 0
    refresh_locks(entries)
    containers, target = [], None
    if any(e["target"] is not None for e in entries):
        try:
            target = dwork_docker.docker_target()
            containers = dwork_docker.inventory()
        except (DworkError, OSError, ValueError, KeyError, TypeError) as error:
            print(color("Warning: Docker status unavailable: " + str(error), "warning", sys.stderr), file=sys.stderr)
    for entry in sorted(entries, key=lambda e: e["name"]):
        style = "warning"
        if not Path(entry["path"]).is_dir() or any(
                not Path(m["directory"]).is_dir() for m in entry["members"]):
            state = "unavailable directory"
        elif entry["target"] is None:
            state = "host-only; preview tracked commands with dwork down --dry-run"
            style = "dim"
        elif target is None:
            state = "Docker status unavailable"
        elif entry["target"] != target:
            state = "different Docker target (" + entry["target"]["context"] + ")"
        else:
            selected = [c for c in containers for m in entry["members"] if m["enabled"]
                        and (c.get("Config", {}).get("Labels") or {}).get("com.docker.compose.project") == m["project"]
                        and (m["services"] is None or (c.get("Config", {}).get("Labels") or {}).get("com.docker.compose.service") in m["services"])]
            running = sum(c["State"]["Status"] in ("running", "restarting") for c in selected)
            state = str(running) + "/" + str(len(selected)) + " containers running"
            style = "start" if running else "stop"
        protected = [m["project"] for m in entry["members"] if m.get("locked", False)]
        marker = " [locked]" if len(entry["members"]) == 1 and protected else (
            " [locked: " + ", ".join(protected) + "]" if protected else "")
        print(colored_name(entry["name"]) + "  " + entry["path"] + "  [" + color(state, style) + "]" + color(marker, "warning"))
    return 0
