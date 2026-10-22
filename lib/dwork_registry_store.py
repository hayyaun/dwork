"""Versioned registry persistence and the operation lock; no workload policy."""

from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
import json
import os
import re
import tempfile

from dwork_common import DworkError
from dwork_config_parse import COMPOSE_ENV


def registry_path():
    state = Path(os.environ.get("XDG_STATE_HOME", ""))
    if not state.is_absolute():
        state = Path.home() / ".local/state"
    return state / "dwork/workspaces.json"


def _validate_document(data):
    if (
        type(data["version"]) is not int
        or data["version"] not in (1, 2)
        or not isinstance(data["workspaces"], list)
    ):
        raise ValueError()
    names, paths = set(), set()
    for entry in data["workspaces"]:
        if "direct" in entry and type(entry["direct"]) is not bool:
            raise ValueError()
        if "temporary_locked" in entry and type(entry["temporary_locked"]) is not bool:
            raise ValueError()
        if (
            not isinstance(entry["name"], str)
            or not entry["name"]
            or not isinstance(entry["path"], str)
            or not Path(entry["path"]).is_absolute()
            or entry["name"] in names
            or entry["path"] in paths
            or not isinstance(entry["options"], list)
            or any(not isinstance(v, str) for v in entry["options"])
            or not isinstance(entry["environment"], dict)
            or any(
                k not in COMPOSE_ENV or not isinstance(v, str)
                for k, v in entry["environment"].items()
            )
            or not isinstance(entry["members"], list)
            or not entry["members"]
        ):
            raise ValueError()
        target = entry["target"]
        if target is not None and (
            not isinstance(target, dict)
            or set(target) != {"context", "daemon"}
            or any(not isinstance(v, str) or not v for v in target.values())
        ):
            raise ValueError()
        for member in entry["members"]:
            if not isinstance(member, dict):
                raise ValueError()
            member.setdefault("locked", False)
            if (
                not isinstance(member["project"], str)
                or not member["project"]
                or not isinstance(member["directory"], str)
                or not Path(member["directory"]).is_absolute()
                or type(member["enabled"]) is not bool
                or type(member["locked"]) is not bool
                or (
                    member["services"] is not None
                    and (
                        not isinstance(member["services"], list)
                        or any(not isinstance(s, str) for s in member["services"])
                    )
                )
            ):
                raise ValueError()
        if (target is not None) != any(m["enabled"] for m in entry["members"]):
            raise ValueError()
        names.add(entry["name"])
        paths.add(entry["path"])
    groups = data.get("groups", {})
    if (data["version"] == 1 and "groups" in data) or (
        data["version"] == 2 and ("groups" not in data or not groups)
    ):
        raise ValueError()
    if not isinstance(groups, dict):
        raise ValueError()
    by_name = {entry["name"]: entry for entry in data["workspaces"]}
    for name, members in groups.items():
        if (
            not isinstance(name, str)
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", name)
            or not isinstance(members, list)
            or not members
            or any(not isinstance(member, str) or member not in by_name for member in members)
            or len(set(members)) != len(members)
        ):
            raise ValueError()
        targets = [
            by_name[member]["target"] for member in members if by_name[member]["target"] is not None
        ]
        if targets and any(target != targets[0] for target in targets):
            raise ValueError()


def _invalid_registry(path):
    return DworkError(
        "Invalid workspace registry: "
        + str(path)
        + ". Restore or repair it before switching; nothing changed."
    )


def _read_document():
    path = registry_path()
    if not path.exists():
        return {"version": 1, "workspaces": []}
    try:
        data = json.loads(path.read_text())
        _validate_document(data)
        return data
    except (ValueError, KeyError, TypeError, AttributeError):
        raise _invalid_registry(path)


def read_registry():
    """Keep the existing entries-only API while validating the full document."""
    return _read_document()["workspaces"]


def read_groups():
    """Read flat references without creating state or consulting live workloads."""
    return _read_document().get("groups", {})


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
            raise DworkError(
                "Another dwork registration or switch is in progress; try again when it finishes."
            )
        yield


def save_registry(entries, *, groups=None):
    """Atomically save entries and references; callers retain the operation lock.

    Entries-only callers preserve groups. A rename is recognized by its stable
    registration path, so explicit rename and re-registration update references
    in this same replacement. Forgetting a referenced path is blocked.
    """
    path = registry_path()
    data = _read_document()
    if groups is None:
        groups = deepcopy(data.get("groups", {}))
        by_path = {entry["path"]: entry["name"] for entry in entries}
        old_by_name = {entry["name"]: entry for entry in data["workspaces"]}
        for group, members in groups.items():
            for member in members:
                if old_by_name[member]["path"] not in by_path:
                    raise DworkError(
                        "Workspace "
                        + member
                        + " is referenced by group "
                        + group
                        + ". Remove it with dwork group remove "
                        + group
                        + " "
                        + member
                        + " or delete the group with dwork group delete "
                        + group
                        + " before forgetting it; nothing changed."
                    )
            groups[group] = [by_path[old_by_name[member]["path"]] for member in members]
    if groups:
        data["groups"] = deepcopy(groups)
        data["version"] = 2
    else:
        data.pop("groups", None)
        data["version"] = 1
    data["workspaces"] = deepcopy(entries)
    try:
        _validate_document(data)
    except (ValueError, KeyError, TypeError, AttributeError):
        raise _invalid_registry(path)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(data, stream, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
