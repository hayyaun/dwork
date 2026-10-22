"""Local named selections of registered workspaces; groups own no workloads."""

from dwork_common import DworkError, color, colored_name
import dwork_registry


def validate_group_name(name):
    try:
        dwork_registry.validate_workspace_name(name)
    except (DworkError, TypeError):
        raise DworkError(
            "Group name must contain letters, digits, dots, underscores, or hyphens"
            + " and start with a letter or digit."
        )


def _select_members(entries, members):
    selected = dwork_registry.select_registrations(entries, members)
    if not selected:
        raise DworkError("A group must contain at least one registered workspace; nothing changed.")
    for entry in selected:
        dwork_registry.check_ownership(entries, entry)
    targets = [entry["target"] for entry in selected if entry["target"] is not None]
    if targets and any(target != targets[0] for target in targets):
        raise DworkError(
            "Group members must use the same saved Docker target; host-only members are allowed."
            + " Nothing changed."
        )
    return selected


def _find_group(groups, name):
    if name not in groups:
        raise DworkError("Unknown group: " + str(name) + ". Run dwork group list; nothing changed.")
    return groups[name]


def select_group(entries, name):
    """Resolve and validate every saved member before planning any workload."""
    return _select_members(entries, _find_group(dwork_registry.read_groups(), name))


def group_names():
    return sorted(dwork_registry.read_groups())


def _cell(value):
    return "".join(char if char.isprintable() else repr(char)[1:-1] for char in value)


def group_command(entries, action, name=None, members=(), preview=False):
    """Manage only local references; mutation callers hold the registry lock."""
    groups = dwork_registry.read_groups()
    if action == "list":
        if not groups:
            print("No workspace groups. Create one with dwork group create GROUP NAME...")
            return 0
        width = max(len("NAME"), *(len(group) for group in groups))
        print(color("NAME", "bold") + " " * (width - 4) + "  " + color("MEMBERS", "bold"))
        for group in sorted(groups):
            print(
                colored_name(group)
                + " " * (width - len(group))
                + "  "
                + ", ".join(_cell(member) for member in groups[group])
            )
        return 0
    validate_group_name(name)
    if action == "show":
        selected = dwork_registry.select_registrations(entries, _find_group(groups, name))
        print("Group: " + colored_name(name))
        for entry in selected:
            target = entry["target"]
            label = (
                "host-only"
                if target is None
                else "Docker target " + _cell(target["context"]) + " / " + _cell(target["daemon"])
            )
            print("  " + _cell(entry["name"]) + " -> " + _cell(entry["path"]) + " (" + label + ")")
        return 0
    if action not in ("create", "add", "remove", "delete"):
        raise DworkError("Unknown group action: " + action)
    members = list(dict.fromkeys(members))
    if action == "create":
        if name in groups:
            raise DworkError("Group already exists: " + name + "; nothing changed.")
        selected = _select_members(entries, members)
        groups[name] = [entry["name"] for entry in selected]
    else:
        current = _find_group(groups, name)
        if action == "delete":
            if members:
                raise DworkError(
                    "Deleting a group does not accept workspace names; nothing changed."
                )
            del groups[name]
        elif action == "add":
            if not members:
                raise DworkError("Name at least one workspace to add; nothing changed.")
            selected = _select_members(entries, [*current, *members])
            groups[name] = [entry["name"] for entry in selected]
        else:
            if not members:
                raise DworkError("Name at least one workspace to remove; nothing changed.")
            missing = [member for member in members if member not in current]
            if missing:
                raise DworkError(
                    "Workspace(s) not in group "
                    + name
                    + ": "
                    + ", ".join(missing)
                    + "; nothing changed."
                )
            remaining = [member for member in current if member not in members]
            if not remaining:
                raise DworkError(
                    "Removing the last member would empty group "
                    + name
                    + ". Use dwork group delete "
                    + name
                    + " instead; nothing changed."
                )
            groups[name] = remaining
    if not preview:
        dwork_registry.save_registry(entries, groups=groups)
    descriptions = {
        "create": ("create group ", "Created group "),
        "add": ("add members to group ", "Added members to group "),
        "remove": ("remove members from group ", "Removed members from group "),
        "delete": ("delete group ", "Deleted group "),
    }
    future, completed = descriptions[action]
    print(("Would " + future if preview else completed) + colored_name(name) + ".")
    return 0
