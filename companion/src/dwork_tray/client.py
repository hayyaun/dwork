"""Shared JSON protocol validation; platform transports own process execution."""

import json

from dwork_tray.platforms import CompanionError


def parse_status(result):
    if result.returncode:
        raise CompanionError(result.stderr.strip() or "dwork list --json failed")
    try:
        data = json.loads(result.stdout)
        if (
            type(data.get("schema_version")) is not int
            or data["schema_version"] != 1
            or data.get("scope") != "registered"
            or not isinstance(data.get("workspaces"), list)
        ):
            raise ValueError("unsupported status schema")
        for row in data["workspaces"]:
            if (
                not isinstance(row, dict)
                or not isinstance(row.get("name"), str)
                or not isinstance(row.get("status"), str)
            ):
                raise ValueError("invalid workspace row")
        return data
    except (ValueError, TypeError, AttributeError) as error:
        raise CompanionError(
            "Expected dwork's version-1 JSON status interface. Install a dwork build containing the companion interface; older 0.3.0 releases do not include it."
        ) from error


def validate_operation(action, name):
    if (
        action not in ("switch", "down")
        or (action == "switch" and not isinstance(name, str))
        or (action == "down" and name is not None)
    ):
        raise CompanionError("Unsupported companion action")
