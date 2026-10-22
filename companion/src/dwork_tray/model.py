"""Shared menu data independent of native GUI frameworks."""

from dataclasses import dataclass

from dwork_tray.platforms import CompanionError


def plain(value, limit=160):
    return "".join(char if char.isprintable() else " " for char in str(value))[:limit]


@dataclass(frozen=True)
class WorkspaceItem:
    name: str
    label: str
    available: bool


def workspace_items(snapshot):
    result = []
    for row in snapshot["workspaces"]:
        members = row.get("members")
        containers = row.get("containers")
        tasks = row.get("tasks")

        def counts(value, fields):
            return isinstance(value, dict) and all(
                type(value.get(field)) is int and value[field] >= 0 for field in fields
            )

        if (
            type(row.get("directory_available")) is not bool
            or not isinstance(members, list)
            or any(not isinstance(member, dict) for member in members)
            or (containers is not None and not counts(containers, ("running", "total")))
            or not counts(tasks, ("running", "unresolved"))
        ):
            raise CompanionError(
                "Incomplete version-1 workspace status; update matching CLI/companion builds."
            )
        status = row["status"].replace("_", " ")
        if containers is not None:
            status += (
                " (" + str(containers["running"]) + "/" + str(containers["total"]) + " containers)"
            )
        status += "; " + str(tasks.get("running", 0)) + " commands"
        if tasks.get("unresolved", 0):
            status += "; unresolved controllers"
        protection = [
            bool(member.get("protected", False) or member.get("kept", False))
            for member in row["members"]
        ]
        suffix = (
            " [protected]"
            if row.get("temporary_locked", False) or (protection and all(protection))
            else " [partly protected]"
            if any(protection)
            else ""
        )
        label = plain(row["name"]) + " — " + plain(status) + suffix
        result.append(WorkspaceItem(row["name"], label, row["directory_available"]))
    return tuple(result)
