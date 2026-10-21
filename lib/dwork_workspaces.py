"""Workspace switching and shutdown, including plans and confirmations."""
from dataclasses import replace
from pathlib import Path
import os
import shlex
import shutil
import sys
from typing import Any

from dwork_common import DworkError, color, colored_name
import dwork_common
import dwork_browsers
import dwork_config
import dwork_docker
import dwork_registry
import dwork_tasks
import dwork_terminals
from dwork_plans import (Action, ActionResult, ActionStatus, ActivationPlan, ExecutionResult,
                         LaunchTerminal, OpenBrowser, ShutdownPlan, StartContainer,
                         StopContainers, StopTask, WaitHealthy, build_activation_plan, shutdown_actions)


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
        def controller_error(record, error):
            if record["workspace"] != exclude_workspace and not task_protection(record, entries, keep):
                raise DworkError("Cannot inspect tracked task " + task_label(record, entries) + ": " + str(error)
                                 + ". Shutdown blocked; no workloads changed. Restore controller access before retrying.")
        task_records = dwork_tasks.running(dwork_registry.registry_path().parent, on_error=controller_error)
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


def action_label(action: Action, entries: list[dict[str, Any]]) -> str:
    """Labels are presentation only; execution and recovery use action types."""
    if isinstance(action, StopTask):
        return "stop task " + task_label(action.record, entries)
    if isinstance(action, StopContainers):
        return "stop containers " + ", ".join(item.identifier for item in action.containers)
    if isinstance(action, StartContainer):
        item = action.container
        return "start " + item.identifier + " (" + item.project + "/" + item.service + ")"
    if isinstance(action, WaitHealthy):
        return "wait for healthy " + ", ".join(action.container_ids)
    if isinstance(action, LaunchTerminal):
        return ("background task " if action.task.window == "none" else "terminal ") + action.task.title
    if isinstance(action, OpenBrowser):
        return "browser " + action.browser.url
    raise TypeError("Unsupported lifecycle action: " + type(action).__name__)


def completed_labels(result: ActionResult, entries: list[dict[str, Any]]) -> list[str]:
    action = result.action
    if isinstance(action, StopTask):
        prefix = "finished task " if result.status is ActionStatus.ALREADY_FINISHED else "stopped task "
        return [prefix + task_label(action.record, entries)]
    if isinstance(action, StopContainers):
        return ["stop " + item.identifier + " (" + item.project + ")" for item in action.containers]
    if isinstance(action, LaunchTerminal):
        return [("launched background task " if action.task.window == "none" else "launched terminal ") + action.task.title]
    if isinstance(action, OpenBrowser):
        return ["opened browser " + action.browser.url]
    return [action_label(action, entries)]


def stop_containers(action: StopContainers, operation: str) -> None:
    print(color("Stopping registered workspace containers...", "stop"), flush=True)
    try:
        # Docker accepts multiple IDs; let its supported stop command handle the batch.
        dwork_docker.docker("stop", *(item.identifier for item in action.containers))
    except (DworkError, OSError, ValueError, KeyError, TypeError, KeyboardInterrupt):
        print(color(operation + " incomplete; the batch may have partially stopped containers.", "warning", sys.stderr), file=sys.stderr)
        try:
            current = {c["Id"]: c for c in dwork_docker.inventory()}
            for item in action.containers:
                state = current.get(item.identifier, {}).get("State", {}).get("Status", "not found; inspect manually")
                style = "stop" if state == "exited" else "warning"
                print(color(item.project + "/" + item.service + " / " + item.identifier[:12] + ": " + state, style, sys.stderr), file=sys.stderr)
        except (DworkError, OSError, ValueError, KeyError, TypeError):
            print("Could not refresh state; check docker ps --all before retrying.", file=sys.stderr)
        raise
    for item in action.containers:
        print(color("Stopped: " + item.project + "/" + item.service + " / " + item.identifier[:12], "stop"), flush=True)


def execute_action(result: ActionResult, entries: list[dict[str, Any]], operation: str) -> ActionStatus:
    action = result.action
    if isinstance(action, StopTask):
        record = action.record
        try:
            stopped = dwork_tasks.stop(record, dwork_registry.registry_path().parent)
            print(color("Stopped task: " if stopped else "Task already finished: ", "stop")
                  + task_label(record, entries), flush=True)
            return ActionStatus.COMPLETED if stopped else ActionStatus.ALREADY_FINISHED
        except (OSError, ValueError, KeyError, TypeError, DworkError) as error:
            raise DworkError(operation + " incomplete while stopping " + record["title"] + ": " + str(error)
                             + ". Earlier tasks may have stopped; inspect dwork down --dry-run before retrying.") from error
    if isinstance(action, StopContainers):
        stop_containers(action, operation)
    elif isinstance(action, (StartContainer, WaitHealthy)):
        label = action_label(action, entries)
        style = "start" if isinstance(action, StartContainer) else "warning"
        print("Executing: " + color(label, style), flush=True)
        if isinstance(action, StartContainer):
            dwork_docker.docker("start", action.container.identifier)
            print(color("Started: " + label.removeprefix("start "), style), flush=True)
        else:
            dwork_docker.wait_healthy(action.container_ids, action.timeout)
    elif isinstance(action, LaunchTerminal):
        task = action.task
        background = task.window == "none"
        if not dwork_terminals.confirm_terminal(task):
            print(("Skipped background task: " if background else "Skipped terminal: ") + colored_name(task.title), flush=True)
            return ActionStatus.SKIPPED
        print(("Starting background task: " if background else "Opening terminal: ") + colored_name(task.title), flush=True)
        result.supervisor_pid = dwork_terminals.open_terminal(task)
        if background:
            print("Started background task: " + colored_name(task.title)
                  + " (supervisor PID " + str(result.supervisor_pid) + ")", flush=True)
    elif isinstance(action, OpenBrowser):
        browser = action.browser
        if not dwork_browsers.confirm_browser(browser):
            print("Skipped browser: " + browser.url, flush=True)
            return ActionStatus.SKIPPED
        if browser.wait_url is not None:
            print("Waiting for HTTP readiness: " + browser.wait_url, flush=True)
        dwork_browsers.wait_ready(browser)
        print("Opening " + dwork_browsers.browser_label(browser) + ": " + browser.url, flush=True)
        dwork_browsers.open_browser(browser)
    else:
        raise TypeError("Unsupported lifecycle action: " + type(action).__name__)
    return ActionStatus.COMPLETED


def execute_actions(result: ExecutionResult, entries: list[dict[str, Any]], operation: str) -> ExecutionResult:
    """Record every outcome without replaying an already-used execution result."""
    if any(item.status is not ActionStatus.PENDING for item in result.results):
        raise ValueError("Execution result has already been used; build and approve a fresh plan.")
    for item in result.results:
        result.current = item
        item.status = ActionStatus.RUNNING
        try:
            item.status = execute_action(item, entries, operation)
        except (DworkError, OSError, ValueError, KeyError, TypeError, KeyboardInterrupt) as error:
            item.status = ActionStatus.INTERRUPTED if isinstance(error, KeyboardInterrupt) else ActionStatus.FAILED
            item.error = str(error)
            raise
    result.current = None
    return result


def stop_workspaces(plan: ShutdownPlan, entries: list[dict[str, Any]], operation: str) -> ExecutionResult:
    """Switch and down use the same typed actions and executor."""
    return execute_actions(ExecutionResult(shutdown_actions(plan)), entries, operation)


def report_failure(result: ExecutionResult, plan: ActivationPlan, entries: list[dict[str, Any]]) -> None:
    current = result.current.action if result.current is not None else None
    step = ("workspace shutdown" if isinstance(current, (StopTask, StopContainers))
            else action_label(current, entries) if current is not None else "before execution")
    completed = [label for item in result.completed for label in completed_labels(item, entries)]
    pending = [action_label(item.action, entries) for item in result.pending]
    print(color("Switch incomplete at: " + step, "warning", sys.stderr), file=sys.stderr)
    print("Completed: " + ("; ".join(completed) or "none"), file=sys.stderr)
    print("Not confirmed complete: " + ("; ".join(pending) or "none"), file=sys.stderr)
    print("The interrupted or failed operation may have changed state; inspect before retrying.", file=sys.stderr)
    print("No automatic rollback was attempted. Inspect tracked host commands with dwork down --dry-run.", file=sys.stderr)
    try:
        current_inventory = dwork_docker.inventory() if plan.inventory else []
        running = [((item.get("Config", {}).get("Labels") or {}).get("com.docker.compose.project", "?")
                    + "/" + item["Id"][:12]) for item in current_inventory
                   if item["State"]["Status"] in ("running", "restarting")]
        print("Still running/restarting: " + (", ".join(running) or "none"), file=sys.stderr)
    except (DworkError, OSError, ValueError, KeyError, TypeError):
        print("Could not refresh container state; check docker ps --all.", file=sys.stderr)
    print("Inspect current state: dwork status; preview a retry: dwork --dry-run (use the same Compose options).", file=sys.stderr)
    for item in result.completed:
        if isinstance(item.action, StopContainers):
            for container in item.action.containers:
                print("To restore the stopped container if appropriate: docker start " + container.identifier, file=sys.stderr)
    print("For a failed container: docker inspect <container-id> and docker logs --tail 50 <container-id>.", file=sys.stderr)


def execute_activation(plan: ActivationPlan, entries: list[dict[str, Any]],
                       *, result: ExecutionResult | None = None) -> ExecutionResult:
    result = result if result is not None else ExecutionResult(plan.actions)
    if result.actions != plan.actions:
        raise ValueError("Execution actions do not match the activation plan.")
    try:
        return execute_actions(result, entries, "Switch")
    except (DworkError, OSError, ValueError, KeyError, TypeError, KeyboardInterrupt):
        report_failure(result, plan, entries)
        raise


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
    plan = build_activation_plan(directory.resolve(),
        [replace(workspace, directory=workspace.directory.resolve()) for workspace in workspaces],
        containers, shutdown, preview=preview)
    shutdown = plan.shutdown
    starts = plan.starts
    tasks = [action.task for action in plan.terminals]
    browsers = [action.browser for action in plan.browsers]
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
    for warning in plan.warnings:
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
    for action in starts:
        item = action.container
        print(color("Would start existing: ", "start") + item.identifier[:12] + " (" + colored_name(item.project + "/" + item.service) + ")")
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
    execute_activation(replace(plan, shutdown=shutdown), entries)
    return 0
