"""Pure ownership and protection rules for containers and tracked commands."""
from dwork_common import DworkError


def member_locked(entry, member):
    """Local workspace holds add protection without replacing YAML lock policy."""
    return entry.get("temporary_locked", False) or member.get("locked", False)


def locked_projects(entries, target):
    return sorted({m["project"] for e in entries if e["target"] == target
                   for m in e["members"] if m["enabled"] and member_locked(e, m)})


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
            if member["enabled"] and not member_locked(entry, member):
                project = member["project"]
                if project in managed:
                    raise DworkError("Ambiguous registered Compose project: " + project + "; nothing changed.")
                managed[project] = member["services"]
    return managed


def task_protection(record, entries, keep):
    entry = next((e for e in entries if e["path"] == record["workspace"]), None)
    if entry is None:
        return "workspace no longer registered"
    member = next((m for m in entry["members"] if m["directory"] == record["directory"]
                   and m["project"] == record["project"]), None)
    if member is None:
        return "workspace ownership changed"
    if member_locked(entry, member):
        return "temporarily locked" if entry.get("temporary_locked", False) else "locked"
    if member["project"] in keep:
        return "DWORK_KEEP_PROJECTS"
    return None


