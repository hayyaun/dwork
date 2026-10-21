"""Typed lifecycle snapshots and action results; planning never executes work."""
from copy import deepcopy
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Sequence, TypedDict

from dwork_common import BrowserTask, DworkError, TerminalTask, Workspace


ContainerSnapshot = dict[str, Any]


class TaskRecord(TypedDict):
    socket: str
    token: str
    workspace: str
    directory: str
    project: str
    title: str
    pid: int
    command: list[str]


@dataclass(frozen=True)
class ContainerRef:
    identifier: str
    project: str
    service: str

    @classmethod
    def from_snapshot(cls, item: Mapping[str, Any]) -> "ContainerRef":
        labels = item.get("Config", {}).get("Labels") or {}
        return cls(item["Id"], labels.get("com.docker.compose.project", "?"),
                   labels.get("com.docker.compose.service", "?"))


@dataclass(frozen=True)
class StopTask:
    record: TaskRecord


@dataclass(frozen=True)
class StopContainers:
    containers: tuple[ContainerRef, ...]


@dataclass(frozen=True)
class StartContainer:
    container: ContainerRef


@dataclass(frozen=True)
class WaitHealthy:
    container_ids: tuple[str, ...]
    timeout: float


@dataclass(frozen=True)
class LaunchTerminal:
    task: TerminalTask


@dataclass(frozen=True)
class OpenBrowser:
    browser: BrowserTask


Action = StopTask | StopContainers | StartContainer | WaitHealthy | LaunchTerminal | OpenBrowser


@dataclass
class ShutdownPlan:
    containers: list[ContainerSnapshot]
    tasks: list[TaskRecord]
    protected_tasks: list[tuple[TaskRecord, str]]


def shutdown_actions(plan: ShutdownPlan) -> tuple[Action, ...]:
    actions: list[Action] = [StopTask(deepcopy(record)) for record in plan.tasks]
    if plan.containers:
        actions.append(StopContainers(tuple(ContainerRef.from_snapshot(item) for item in plan.containers)))
    return tuple(actions)


@dataclass(frozen=True)
class ActivationPlan:
    directory: Path
    workspaces: tuple[Workspace, ...]
    inventory: tuple[ContainerSnapshot, ...]
    shutdown: ShutdownPlan
    starts: tuple[StartContainer, ...]
    gates: tuple[WaitHealthy, ...]
    terminals: tuple[LaunchTerminal, ...]
    browsers: tuple[OpenBrowser, ...]
    warnings: tuple[str, ...]

    @property
    def actions(self) -> tuple[Action, ...]:
        return (*shutdown_actions(self.shutdown), *self.starts, *self.gates, *self.terminals, *self.browsers)


class ActionStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    ALREADY_FINISHED = "already_finished"
    SKIPPED = "skipped"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


@dataclass
class ActionResult:
    action: Action
    status: ActionStatus = ActionStatus.PENDING
    error: str | None = None
    supervisor_pid: int | None = None


@dataclass
class ExecutionResult:
    actions: tuple[Action, ...]
    results: list[ActionResult] = field(init=False)
    current: ActionResult | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        self.results = [ActionResult(action) for action in self.actions]

    @property
    def completed(self) -> tuple[ActionResult, ...]:
        return tuple(result for result in self.results if result.status in (
            ActionStatus.COMPLETED, ActionStatus.ALREADY_FINISHED))

    @property
    def pending(self) -> tuple[ActionResult, ...]:
        return tuple(result for result in self.results if result.status not in (
            ActionStatus.COMPLETED, ActionStatus.ALREADY_FINISHED, ActionStatus.SKIPPED))


def build_activation_plan(directory: Path, workspaces: Sequence[Workspace],
                          containers: Sequence[ContainerSnapshot], shutdown: ShutdownPlan,
                          *, preview: bool) -> ActivationPlan:
    """Build from resolved paths and authorized shutdown snapshots, without I/O.

    Copy inputs so assigning task ownership never mutates loaded configuration.
    Registration checks, live controller discovery, consent, and lock rechecks
    remain the orchestration layer's responsibility.
    """
    workspaces = tuple(deepcopy(workspaces))
    inventory = tuple(deepcopy(containers))
    active = {workspace.name: workspace for workspace in workspaces if workspace.enabled}
    starts, warnings = [], []
    for item in inventory:
        labels = item.get("Config", {}).get("Labels") or {}
        project = labels.get("com.docker.compose.project")
        if not project or project not in active:
            continue
        service = labels.get("com.docker.compose.service", "(unknown service)")
        if not active[project].manages(service):
            continue
        identifier, state = item["Id"], item["State"]["Status"]
        if state in ("created", "exited"):
            starts.append(StartContainer(ContainerRef(identifier, project, service)))
        elif state not in ("running", "restarting"):
            warnings.append("Container " + identifier[:12] + " is " + state + "; handle it manually.")

    def service_containers(project: str, service: str) -> list[ContainerSnapshot]:
        return [item for item in inventory if (
            (item.get("Config", {}).get("Labels") or {}).get("com.docker.compose.project") == project
            and (item.get("Config", {}).get("Labels") or {}).get("com.docker.compose.service") == service)]

    gates, terminals, browsers = [], [], []
    for workspace in workspaces:
        browsers.extend(OpenBrowser(browser) for browser in workspace.browsers)
        for service in workspace.services:
            if workspace.manages(service) and not service_containers(workspace.name, service):
                warnings.append("Service " + workspace.name + "/" + service
                                + " has no container; create it manually if needed (it may be profile-specific).")
        for task in workspace.terminals:
            task.workspace = str(directory)
            task.directory = str(workspace.directory)
            task.project = workspace.name
            terminals.append(LaunchTerminal(task))
            ids = []
            for service in task.healthy:
                matches = service_containers(workspace.name, service)
                if not matches:
                    message = "Required healthy service " + workspace.name + "/" + service + " has no existing container."
                    if not preview:
                        raise DworkError(message + " Create it manually; nothing changed.")
                    warnings.append(message + " Terminal launch would be blocked.")
                ids.extend(item["Id"] for item in matches)
            if ids:
                gates.append(WaitHealthy(tuple(ids), task.timeout))
    return ActivationPlan(directory, workspaces, inventory, deepcopy(shutdown), tuple(starts), tuple(gates),
                          tuple(terminals), tuple(browsers), tuple(warnings))
