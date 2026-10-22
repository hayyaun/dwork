"""Versioned, read-only snapshots for companion clients; no presentation parsing."""

from copy import deepcopy
from pathlib import Path
import os

from dwork_common import DworkError
import dwork_config
import dwork_docker
import dwork_registry
import dwork_tasks

SCHEMA_VERSION = 1


def docker_snapshot(required):
    if not required:
        return {"available": None, "target": None, "error": None}, []
    try:
        target = dwork_docker.docker_target()
        containers = dwork_docker.inventory()
        return {"available": True, "target": target, "error": None}, containers
    except (DworkError, OSError, ValueError, KeyError, TypeError) as error:
        return {"available": False, "target": None, "error": str(error)}, []


def snapshot(entries, *, scope, docker=None, containers=None):
    """Inspect copies only. Task credentials and saved environment/options never escape."""
    entries = deepcopy(entries)
    if scope == "registered":
        dwork_registry.refresh_locks(entries)
    if docker is None:
        docker, containers = docker_snapshot(any(entry["target"] is not None for entry in entries))
    unresolved = []
    records = (
        dwork_tasks.running(
            dwork_registry.registry_path().parent,
            on_error=lambda record, error: unresolved.append(record),
        )
        if entries
        else []
    )
    keep = {
        name.strip()
        for name in os.environ.get("DWORK_KEEP_PROJECTS", "").split(",")
        if name.strip()
    }
    rows = []
    for entry in sorted(entries, key=lambda item: item["name"]):
        directory_available = Path(entry["path"]).is_dir() and all(
            Path(member["directory"]).is_dir() for member in entry["members"]
        )
        current_target = entry["target"] is not None and entry["target"] == docker["target"]
        visible = entry["target"] is None or (docker["available"] and current_target)
        selected = [
            item
            for item in (containers or [])
            if current_target
            and any(
                member["enabled"]
                and (item.get("Config", {}).get("Labels") or {}).get("com.docker.compose.project")
                == member["project"]
                and (
                    member["services"] is None
                    or (item.get("Config", {}).get("Labels") or {}).get(
                        "com.docker.compose.service"
                    )
                    in member["services"]
                )
                for member in entry["members"]
            )
        ]

        def belongs(record):
            return record["workspace"] == entry.get("task_workspace", entry["path"]) and any(
                record["directory"] == member["directory"]
                and record["project"] == member["project"]
                for member in entry["members"]
            )

        running = sum(item["State"]["Status"] in ("running", "restarting") for item in selected)
        state = (
            "directory_unavailable"
            if not directory_available
            else "host_only"
            if entry["target"] is None
            else "docker_unavailable"
            if not docker["available"]
            else "different_target"
            if not current_target
            else "containers"
        )
        rows.append(
            {
                "name": entry["name"],
                "path": entry["path"],
                "status": state,
                "directory_available": directory_available,
                "target": entry["target"],
                "temporary_locked": entry.get("temporary_locked", False),
                "members": [
                    {
                        "project": member["project"],
                        "directory": member["directory"],
                        "enabled": member["enabled"],
                        "services": member["services"],
                        "locked": member.get("locked", False),
                        "protected": bool(dwork_registry.member_locked(entry, member)),
                        "kept": member["project"] in keep,
                    }
                    for member in entry["members"]
                ],
                "containers": {"running": running, "total": len(selected)} if visible else None,
                "tasks": {
                    "running": sum(belongs(record) for record in records),
                    "unresolved": sum(belongs(record) for record in unresolved),
                },
            }
        )
    return {"schema_version": SCHEMA_VERSION, "scope": scope, "docker": docker, "workspaces": rows}


def registered_snapshot():
    return snapshot(dwork_registry.read_registry(), scope="registered")


def current_snapshot(directory, options):
    workspaces, discovered = dwork_config.discover(directory, options)
    task_workspace = str(dwork_config.registration_directory(directory, options, discovered))
    docker, containers = docker_snapshot(any(workspace.enabled for workspace in workspaces))
    entries = [
        {
            "name": workspace.name,
            "path": str(workspace.directory),
            "target": docker["target"] if workspace.enabled else None,
            "task_workspace": task_workspace,
            "members": [
                {
                    "project": workspace.name,
                    "directory": str(workspace.directory),
                    "enabled": workspace.enabled,
                    "services": workspace.selected,
                    "locked": workspace.locked,
                }
            ],
        }
        for workspace in workspaces
    ]
    result = snapshot(entries, scope="current", docker=docker, containers=containers)
    # Docker failure must not make enabled Compose workspaces look host-only.
    if docker["available"] is False:
        for row, workspace in zip(result["workspaces"], sorted(workspaces, key=lambda w: w.name)):
            if workspace.enabled:
                row["status"], row["containers"] = "docker_unavailable", None
    return result
