"""Versioned registry persistence and the operation lock; no workload policy."""

from contextlib import contextmanager
from pathlib import Path
import json
import os
import tempfile

from dwork_common import DworkError
from dwork_config_parse import COMPOSE_ENV


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
        if (
            type(data["version"]) is not int
            or data["version"] != 1
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
        return data["workspaces"]
    except (ValueError, KeyError, TypeError):
        raise DworkError(
            "Invalid workspace registry: "
            + str(path)
            + ". Restore or repair it before switching; nothing changed."
        )


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
