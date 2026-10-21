"""Workspace switching and shutdown, including plans and confirmations."""
from dataclasses import dataclass
from pathlib import Path
import os
import shlex
import shutil
import sys

from dwork_common import DworkError, color, colored_name
import dwork_common
import dwork_browsers
import dwork_config
import dwork_docker
import dwork_registry
import dwork_tasks
import dwork_terminals


def task_protection(record, entries, keep):
    entry = next((e for e in entries if e["path"] == record["workspace"]), None)
    if entry is None:
        return "workspace no longer registered"
    member = next((m for m in entry["members"] if m["directory"] == record["directory"]
                   and m["project"] == record["project"]), None)
    if member is None:
        return "workspace ownership changed"
    if dwork_registry.member_locked(entry, member):
        return "temporarily locked" if entry.get("temporary_locked", False) else "locked"
    if member["project"] in keep:
        return "DWORK_KEEP_PROJECTS"
    return None


def task_label(record, entries):
    name = next((e["name"] for e in entries if e["path"] == record["workspace"]), record["workspace"])
    return (colored_name(name + "/" + record["title"]) + " [" + colored_name(record["project"])
            + "] (PID " + str(record["pid"]) + ") -> "
            + shlex.join(record["command"]))


@dataclass
class ShutdownPlan:
    containers: list
    tasks: list
    protected_tasks: list


def keep_projects():
    return {n.strip() for n in os.environ.get("DWORK_KEEP_PROJECTS", "").split(",") if n.strip()}


def plan_shutdown(entries, target, containers, keep, exclude_workspace=None, task_records=None):
    """Select the same owned resources for down and switch, except the destination."""
    candidates = [e for e in entries if e["path"] != exclude_workspace]
    managed = dwork_registry.registered_services(candidates, target)
    selected = []
    for item in containers:
        labels = item.get("Config", {}).get("Labels") or {}
        project = labels.get("com.docker.compose.project")
        service = labels.get("com.docker.compose.service")
        if (project in managed and project not in keep
                and (managed[project] is None or service in managed[project])
                and item["State"]["Status"] in ("running", "restarting", "paused")):
            selected.append(item)
    if task_records is None:
        task_records = dwork_tasks.running(dwork_registry.registry_path().parent)
    selected_tasks, protected_tasks = [], []
    for record in task_records:
        if record["workspace"] == exclude_workspace:
            continue
        reason = task_protection(record, entries, keep)
        if reason:
            protected_tasks.append((record, reason))
        else:
            selected_tasks.append(record)
    return ShutdownPlan(selected, selected_tasks, protected_tasks)


def show_shutdown_plan(plan, entries):
    for record, reason in plan.protected_tasks:
        print("Keep task (" + reason + "): " + task_label(record, entries))
    for item in plan.containers:
        print(color("Would stop: ", "stop") + item["Id"][:12] + " (" + colored_name(dwork_docker.container_name(item)) + ")")
    for record in plan.tasks:
        print(color("Would stop task: ", "stop") + task_label(record, entries))


def recheck_shutdown(plan, entries, target, keep):
    # Lock policy can change while the confirmation prompt is open.
    changed = dwork_registry.refresh_locks(entries)
    allowed = plan_shutdown(entries, target, plan.containers, keep, task_records=plan.tasks)
    for item in plan.containers:
        if item not in allowed.containers:
            project = (item.get("Config", {}).get("Labels") or {}).get("com.docker.compose.project")
            print("Skipped stop: " + colored_name(project) + " is now locked.")
    for record, reason in allowed.protected_tasks:
        print("Skipped task (" + reason + "): " + task_label(record, entries))
    return allowed, changed


def shutdown_steps(plan, entries):
    steps = ["stop task " + task_label(record, entries) for record in plan.tasks]
    if plan.containers:
        steps.append("stop containers " + ", ".join(item["Id"] for item in plan.containers))
    return steps


def stop_workspaces(plan, entries, operation, completed=None, pending=None):
    """Stop host commands before containers for every workspace lifecycle command."""
    if completed is None:
        completed = []
    if pending is None:
        pending = shutdown_steps(plan, entries)
    # Stop host commands first so they can release connections before databases
    # shut down. A failed controller request aborts remaining work with an error.
    for record in plan.tasks:
        try:
            stopped = dwork_tasks.stop(record, dwork_registry.registry_path().parent)
            label = task_label(record, entries)
            print(color("Stopped task: " if stopped else "Task already finished: ", "stop") + label, flush=True)
            completed.append(("stopped task " if stopped else "finished task ") + label)
            pending.pop(0)
        except (OSError, ValueError, KeyError, TypeError, DworkError) as error:
            raise DworkError(operation + " incomplete while stopping " + record["title"] + ": " + str(error)
                             + ". Earlier tasks may have stopped; inspect dwork down --dry-run before retrying.")
    if not plan.containers:
        return
    print(color("Stopping registered workspace containers...", "stop"), flush=True)
    try:
        # Docker accepts multiple IDs; let its supported stop command handle the batch.
        dwork_docker.docker("stop", *(item["Id"] for item in plan.containers))
    except (DworkError, OSError, ValueError, KeyError, TypeError, KeyboardInterrupt):
        print(color(operation + " incomplete; the batch may have partially stopped containers.", "warning", sys.stderr), file=sys.stderr)
        try:
            current = {c["Id"]: c for c in dwork_docker.inventory()}
            for item in plan.containers:
                state = current.get(item["Id"], {}).get("State", {}).get("Status", "not found; inspect manually")
                style = "stop" if state == "exited" else "warning"
                print(color(dwork_docker.container_name(item) + " / " + item["Id"][:12] + ": " + state, style, sys.stderr), file=sys.stderr)
        except (DworkError, OSError, ValueError, KeyError, TypeError):
            print("Could not refresh state; check docker ps --all before retrying.", file=sys.stderr)
        raise
    for item in plan.containers:
        print(color("Stopped: " + dwork_docker.container_name(item) + " / " + item["Id"][:12], "stop"), flush=True)
        project = (item.get("Config", {}).get("Labels") or {}).get("com.docker.compose.project")
        completed.append("stop " + item["Id"] + " (" + project + ")")
    pending.pop(0)


def down_workspaces(entries, preview):
    """Stop registered containers and locally supervised tasks after confirmation."""
    locks_changed = dwork_registry.refresh_locks(entries)
    has_compose = any(e["target"] is not None for e in entries)
    target = dwork_docker.docker_target() if has_compose else None
    containers = dwork_docker.inventory() if has_compose else []
    if has_compose:
        dwork_docker.show_target()
    keep = keep_projects()
    plan = plan_shutdown(entries, target, containers, keep)
    print("Down plan: " + str(len(plan.containers)) + " container(s), " + str(len(plan.tasks))
          + " tracked command(s) to stop across registered workspaces.")
    print("Protected projects (DWORK_KEEP_PROJECTS): " + (", ".join(sorted(keep)) or "none"))
    print("Locked projects: " + (", ".join(dwork_registry.locked_projects(entries, target)) or "none"))
    show_shutdown_plan(plan, entries)
    if not plan.containers and not plan.tasks:
        if locks_changed and not preview:
            dwork_registry.save_registry(entries)
        print("No registered containers or tracked commands need stopping.")
        return 0
    if preview:
        return 0
    if not dwork_common.confirm_action("Stop all listed containers and tracked commands?"):
        print("Cancelled; nothing changed.")
        return 0
    plan, changed = recheck_shutdown(plan, entries, target, keep)
    if changed or locks_changed:
        dwork_registry.save_registry(entries)
    stop_workspaces(plan, entries, "Down")
    if plan.containers:
        print("Stopped " + str(len(plan.containers)) + " container(s). Registrations, containers, networks, and volumes were kept.")
    else:
        print("Down finished. Terminal windows were left open.")
    return 0


def registry_command(directory, options, mode, preview, name, entries):
    if mode in ("switch", "forget"):
        entry = next((e for e in entries if e["name"] == name), None)
        if entry is None:
            raise DworkError("Unknown workspace: " + str(name) + ". Run dwork list.")
        if mode == "forget":
            dwork_registry.save_registry([e for e in entries if e is not entry])
            print("Forgot " + colored_name(name) + ". Containers, terminals, and project files were left alone.")
            return 0
        directory = Path(entry["path"])
        if not directory.is_dir():
            raise DworkError("Workspace directory unavailable: " + str(directory)
                             + ". Forget it and register the new location after a move.")
        original = Path.cwd()
        try:
            os.chdir(directory)
            with dwork_config.compose_environment(entry["environment"]):
                return switch_workspace(directory, entry["options"], mode, preview, entries, name)
        finally:
            os.chdir(original)
    return switch_workspace(directory, options, mode, preview, entries, name)


def switch_workspace(directory, options, mode, preview, entries, name=None):
    known = next((e for e in entries if e["path"] == str(directory)), None)
    direct = bool(known and known.get("direct", False))
    workspaces, discovered = ([dwork_config.load_workspace(directory, options)], False) if direct else dwork_config.discover(directory, options)
    root = directory if direct else dwork_config.registration_directory(directory, options, discovered)
    if root != directory:
        directory = root
        workspaces, discovered = dwork_config.discover(directory, options)
    active = {w.name: w for w in workspaces if w.enabled}
    if len(active) != sum(w.enabled for w in workspaces):
        raise DworkError("Child directories resolve to the same Compose project; use explicit Compose options.")
    if active and not shutil.which("docker"):
        raise DworkError("docker is not available.")
    if mode == "status":
        containers = dwork_docker.inventory() if active else []
        if active:
            dwork_docker.show_target()
        dwork_docker.show_status(workspaces, containers)
        return 0
    locks_changed = dwork_registry.refresh_locks(entries)
    target = dwork_docker.docker_target() if active else None
    existing = next((e for e in entries if e["path"] == str(directory)), None)
    direct = bool(existing and existing.get("direct", False))
    default_name = workspaces[0].name if len(workspaces) == 1 else directory.name
    name = name or (existing["name"] if existing else default_name)
    dwork_registry.validate_workspace_name(name)
    candidate = dwork_registry.registration(directory, options, workspaces, target, name, direct=direct)
    if existing and "temporary_locked" in existing:
        candidate["temporary_locked"] = existing["temporary_locked"]
    if any(e["name"] == name and e["path"] != candidate["path"] for e in entries):
        raise DworkError("Workspace name already registered: " + name + ". Use dwork register NAME with a unique name.")
    dwork_registry.check_ownership(entries, candidate)
    if mode == "register":
        dwork_registry.save_registry([e for e in entries if e["path"] != candidate["path"]] + [candidate])
        print("Registered " + colored_name(name) + " at " + str(directory) + ". No containers or terminals changed.")
        return 0
    if existing and candidate != existing:
        raise DworkError("Workspace configuration or Docker target changed since registration."
                         + " Review dwork --dry-run after running dwork register " + name
                         + " with the intended Compose options; nothing changed.")
    if mode == "switch" and not existing:
        raise DworkError("Workspace registration no longer matches its directory; register it again.")
    # A host-only destination must also shut down outgoing Compose workspaces.
    has_compose = bool(active) or any(e["target"] is not None for e in entries)
    shutdown_target = target if active else (dwork_docker.docker_target() if has_compose else None)
    containers = dwork_docker.inventory() if has_compose else []
    if has_compose:
        dwork_docker.show_target()
    keep = keep_projects()
    shutdown = plan_shutdown(entries, shutdown_target, containers, keep, exclude_workspace=str(directory))
    starts, warnings = [], []
    for c in containers:
        labels = c.get("Config", {}).get("Labels") or {}
        project = labels.get("com.docker.compose.project")
        if not project:
            continue
        service = labels.get("com.docker.compose.service", "(unknown service)")
        identifier, state = c["Id"], c["State"]["Status"]
        if project in active:
            if not active[project].manages(service):
                continue
            if state in ("created", "exited"):
                starts.append((identifier, project, service))
            elif state not in ("running", "restarting"):
                warnings.append("Container " + identifier[:12] + " is " + state + "; handle it manually.")
    gates, tasks, browsers = [], [], []
    for w in workspaces:
        browsers.extend(w.browsers)
        for service in w.services:
            if w.manages(service) and not dwork_docker.service_containers(containers, w.name, service):
                warnings.append("Service " + w.name + "/" + service + " has no container; create it manually if needed (it may be profile-specific).")
        for task in w.terminals:
            task.workspace = str(directory.resolve())
            task.directory = str(w.directory.resolve())
            task.project = w.name
            tasks.append(task)
            ids = []
            for service in task.healthy:
                matches = dwork_docker.service_containers(containers, w.name, service)
                if not matches:
                    message = "Required healthy service " + w.name + "/" + service + " has no existing container."
                    if not preview:
                        raise DworkError(message + " Create it manually; nothing changed.")
                    warnings.append(message + " Terminal launch would be blocked.")
                ids.extend(c["Id"] for c in matches)
            if ids:
                gates.append((ids, task.timeout))
    if not preview:
        dwork_terminals.preflight_terminals(tasks)
        dwork_browsers.preflight_browsers(browsers)
    if discovered:
        print("Projects found in immediate subdirectories:")
        for w in workspaces:
            print("  " + str(w.directory.relative_to(directory)) + " -> " + colored_name(w.name))
    else:
        print("Current Compose project: " + colored_name(workspaces[0].name) if active
              else "Current workspace: " + colored_name(workspaces[0].name) + " (Compose disabled)")
    for warning in warnings:
        print(color("Warning: " + warning, "warning", sys.stderr), file=sys.stderr)
    print("Switch plan: " + str(len(shutdown.containers)) + " stop(s), " + str(len(starts))
          + " start(s), " + str(len(tasks)) + " terminal task(s), " + str(len(browsers)) + " browser URL(s).")
    print("Tracked commands to stop: " + str(len(shutdown.tasks)))
    if has_compose:
        print("Scope: container stops affect only other registered workspaces on this Docker target.")
    print("Tracked command stops affect other registered workspaces on this machine.")
    if existing is None:
        print("Would register workspace: " + colored_name(name) + " -> " + str(directory))
    print("Protected projects (DWORK_KEEP_PROJECTS): " + (", ".join(sorted(keep)) or "none"))
    print("Locked projects: " + (", ".join(dwork_registry.locked_projects(entries, shutdown_target)) or "none"))
    show_shutdown_plan(shutdown, entries)
    for identifier, project, service in starts:
        print(color("Would start existing: ", "start") + identifier[:12] + " (" + colored_name(project + "/" + service) + ")")
    for task in tasks:
        if task.healthy:
            print("Would wait for healthy: " + ", ".join(task.healthy) + " (timeout " + str(task.timeout) + "s)")
        confirmation = " [confirmation required]" if task.confirm else " [confirm: false]"
        label = "Would run detached: " if task.window == "none" else "Would open terminal: "
        print(label + colored_name(task.title) + " -> " + color(shlex.join(task.command), "bold") + " in " + str(task.cwd) + confirmation)
    for browser in browsers:
        confirmation = " [confirmation required]" if browser.confirm else " [confirm: false]"
        print("Would open " + dwork_browsers.browser_label(browser) + ": " + browser.url + confirmation)
        if browser.wait_url is not None:
            print("Would wait for HTTP readiness: " + browser.wait_url + " (timeout " + str(browser.timeout) + "s)")
    if not shutdown.containers and not shutdown.tasks and not starts and not tasks and not browsers:
        print("No container changes needed.")
    # First-time activation already asks for combined registration/switch consent;
    # discovered groups retain their separate group prompt. Child opt-outs must
    # not silently approve a parent-directory group switch.
    confirm_activation = mode == "up" or (mode == "activate" and existing is not None and not discovered)
    skip_activation_confirmation = not discovered and not workspaces[0].confirm
    if confirm_activation:
        print("Workspace activation confirmation: " + ("skipped (confirm: false)" if skip_activation_confirmation else "required"))
    if preview:
        return 0
    if confirm_activation and not skip_activation_confirmation and not dwork_common.confirm_action("Apply the listed workspace plan?"):
        print("Cancelled; nothing changed.")
        return 0
    if discovered:
        try:
            answer = input("Switch all listed projects together? (y/N) ")
        except EOFError:
            answer = ""
        if answer.strip().lower() != "y":
            print("Cancelled; nothing changed.")
            return 0
    if existing is None:
        if not dwork_registry.confirm_registration(candidate):
            print("Cancelled; no workspace registered and no containers or terminals changed.")
            return 0
        entries.append(candidate)
    shutdown, changed = recheck_shutdown(shutdown, entries, shutdown_target, keep)
    locks_changed = changed or locks_changed
    if existing is None or locks_changed:
        dwork_registry.save_registry(entries)
    if existing is None:
        print("Registered " + colored_name(name) + " at " + str(directory) + ".")
    actions = []
    for identifier, project, service in starts:
        actions.append(("start " + identifier + " (" + project + "/" + service + ")",
                        lambda identifier=identifier: dwork_docker.docker("start", identifier)))
    for ids, timeout in gates:
        actions.append(("wait for healthy " + ", ".join(ids),
                        lambda ids=ids, timeout=timeout: dwork_docker.wait_healthy(ids, timeout)))
    completed = []
    pending = shutdown_steps(shutdown, entries) + [label for label, _ in actions] + [
        ("background task " if task.window == "none" else "terminal ") + task.title for task in tasks] + [
        "browser " + browser.url for browser in browsers]
    step = "before execution"
    try:
        if shutdown.containers or shutdown.tasks:
            step = "workspace shutdown"
            stop_workspaces(shutdown, entries, "Switch", completed, pending)
        for label, operation in actions:
            step = label
            style = "start" if label.startswith("start ") else "warning"
            print("Executing: " + color(label, style), flush=True)
            operation()
            if label.startswith("start "):
                print(color("Started: " + label.removeprefix("start "), style), flush=True)
            completed.append(label)
            pending.pop(0)
        for task in tasks:
            background = task.window == "none"
            step = ("background task " if background else "terminal ") + task.title
            if not dwork_terminals.confirm_terminal(task):
                print(("Skipped background task: " if background else "Skipped terminal: ") + colored_name(task.title), flush=True)
                pending.pop(0)
                continue
            print(("Starting background task: " if background else "Opening terminal: ") + colored_name(task.title), flush=True)
            pid = dwork_terminals.open_terminal(task)
            if background:
                print("Started background task: " + colored_name(task.title) + " (supervisor PID " + str(pid) + ")", flush=True)
            completed.append(("launched background task " if background else "launched terminal ") + task.title)
            pending.pop(0)
        for browser in browsers:
            step = "browser " + browser.url
            if not dwork_browsers.confirm_browser(browser):
                print("Skipped browser: " + browser.url, flush=True)
                pending.pop(0)
                continue
            if browser.wait_url is not None:
                print("Waiting for HTTP readiness: " + browser.wait_url, flush=True)
            dwork_browsers.wait_ready(browser)
            print("Opening " + dwork_browsers.browser_label(browser) + ": " + browser.url, flush=True)
            dwork_browsers.open_browser(browser)
            completed.append("opened browser " + browser.url)
            pending.pop(0)
    except (DworkError, OSError, ValueError, KeyError, TypeError, KeyboardInterrupt):
        dwork_docker.report_failure(completed, pending, step, containers)
        raise
    return 0
