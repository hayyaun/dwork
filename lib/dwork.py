"""Workspace switching, optional YAML config, health gates, and WSL terminals."""
import base64
from contextlib import contextmanager
from dataclasses import dataclass, field
import json
import math
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time

LINUX_TERMINALS = ("gnome-terminal", "konsole", "xfce4-terminal", "xterm")
LAUNCHERS = ("auto", "windows-terminal", *LINUX_TERMINALS)

FILENAMES = ("compose.yaml", "compose.yml", "docker-compose.yaml", "docker-compose.yml")

class DworkError(Exception):
    pass


COMPOSE_ENV = ("COMPOSE_FILE", "COMPOSE_PROJECT_NAME", "COMPOSE_PROFILES",
               "COMPOSE_ENV_FILES", "COMPOSE_PATH_SEPARATOR", "COMPOSE_DISABLE_ENV_FILE")


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
        if type(data["version"]) is not int or data["version"] != 1 or not isinstance(data["workspaces"], list):
            raise ValueError()
        names, paths = set(), set()
        for entry in data["workspaces"]:
            if (not isinstance(entry["name"], str) or not entry["name"]
                    or not isinstance(entry["path"], str) or not Path(entry["path"]).is_absolute()
                    or entry["name"] in names or entry["path"] in paths
                    or not isinstance(entry["options"], list)
                    or any(not isinstance(v, str) for v in entry["options"])
                    or not isinstance(entry["environment"], dict)
                    or any(k not in COMPOSE_ENV or not isinstance(v, str)
                           for k, v in entry["environment"].items())
                    or not isinstance(entry["members"], list) or not entry["members"]):
                raise ValueError()
            target = entry["target"]
            if target is not None and (not isinstance(target, dict) or set(target) != {"context", "daemon"}
                    or any(not isinstance(v, str) or not v for v in target.values())):
                raise ValueError()
            for member in entry["members"]:
                if (not isinstance(member["project"], str) or not member["project"]
                        or not isinstance(member["directory"], str)
                        or not Path(member["directory"]).is_absolute()
                        or type(member["enabled"]) is not bool
                        or (member["services"] is not None and
                            (not isinstance(member["services"], list) or
                             any(not isinstance(s, str) for s in member["services"])))):
                    raise ValueError()
            if (target is not None) != any(m["enabled"] for m in entry["members"]):
                raise ValueError()
            names.add(entry["name"])
            paths.add(entry["path"])
        return data["workspaces"]
    except (ValueError, KeyError, TypeError):
        raise DworkError("Invalid workspace registry: " + str(path)
                         + ". Restore or repair it before switching; nothing changed.")


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
            raise DworkError("Another dwork registration or switch is in progress; try again when it finishes.")
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


def docker_target():
    target = {"context": docker("context", "show").strip(),
              "daemon": docker("info", "--format", "{{.ID}}").strip()}
    if not all(target.values()):
        raise DworkError("Cannot identify the Docker target; nothing changed.")
    return target


def registration_directory(directory, options, discovered):
    # Preserve the invocation directory for relative CLI/environment file paths.
    if options or os.environ.get("COMPOSE_FILE") or os.environ.get("COMPOSE_ENV_FILES") or discovered:
        return directory
    ancestors = (directory, *directory.parents)
    for parent in ancestors:
        if (parent / "dwork.yml").is_file():
            return parent
    for parent in ancestors:
        if any((parent / f).is_file() for f in FILENAMES):
            return parent
    return directory


def registration(directory, options, workspaces, target, name):
    return {"name": name, "path": str(directory.resolve()), "options": list(options),
            "environment": {key: os.environ[key] for key in COMPOSE_ENV if key in os.environ},
            "target": target,
            "members": [{"project": w.name, "directory": str(w.directory.resolve()),
                         "enabled": w.enabled, "services": w.selected} for w in workspaces]}


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
    managed = {}
    for entry in entries:
        if entry["target"] != target or not Path(entry["path"]).is_dir():
            continue
        for member in entry["members"]:
            if member["enabled"] and Path(member["directory"]).is_dir():
                project = member["project"]
                if project in managed:
                    raise DworkError("Ambiguous registered Compose project: " + project + "; nothing changed.")
                managed[project] = member["services"]
    return managed


def confirm_registration(entry):
    print("Register workspace " + repr(entry["name"]) + " at " + entry["path"] + "?")
    print("Future switches may stop its managed containers. Unregistered projects stay running.")
    try:
        return input("Register and switch? (y/N) ").strip().lower() == "y"
    except EOFError:
        return False


def list_registrations(entries):
    if not entries:
        print("No registered workspaces. Run dwork register in a project to remember it.")
        return 0
    containers, target = [], None
    if any(e["target"] is not None for e in entries):
        try:
            target = docker_target()
            containers = inventory()
        except (DworkError, OSError, ValueError, KeyError, TypeError) as error:
            print("Warning: Docker status unavailable: " + str(error), file=sys.stderr)
    for entry in sorted(entries, key=lambda e: e["name"]):
        if not Path(entry["path"]).is_dir() or any(
                not Path(m["directory"]).is_dir() for m in entry["members"]):
            state = "unavailable directory"
        elif entry["target"] is None:
            state = "host-only; sessions not tracked"
        elif target is None:
            state = "Docker status unavailable"
        elif entry["target"] != target:
            state = "different Docker target (" + entry["target"]["context"] + ")"
        else:
            selected = [c for c in containers for m in entry["members"] if m["enabled"]
                        and (c.get("Config", {}).get("Labels") or {}).get("com.docker.compose.project") == m["project"]
                        and (m["services"] is None or (c.get("Config", {}).get("Labels") or {}).get("com.docker.compose.service") in m["services"])]
            running = sum(c["State"]["Status"] in ("running", "restarting") for c in selected)
            state = str(running) + "/" + str(len(selected)) + " containers running"
        print(entry["name"] + "  " + entry["path"] + "  [" + state + "]")
    return 0

@dataclass
class TerminalTask:
    title: str
    command: list
    cwd: Path
    healthy: list = field(default_factory=list)
    timeout: float = 180
    window: str = "new"
    launcher: str = "auto"
    confirm: bool = True

@dataclass
class Workspace:
    name: str
    directory: Path
    services: dict
    enabled: bool = True
    selected: object = None
    terminals: list = field(default_factory=list)
    configured: bool = False

    def manages(self, service):
        return self.selected is None or service in self.selected

def run_command(args, cwd=None):
    result = subprocess.run(args, cwd=cwd, text=True, capture_output=True)
    if result.returncode:
        raise DworkError(result.stderr.strip() or "Command failed: " + shlex.join(args))
    return result.stdout

def docker(*args, cwd=None):
    return run_command(["docker", *args], cwd)

def read_model(directory, options):
    raw = docker("compose", *options, "config", "--no-interpolate",
                 "--no-env-resolution", "--format", "json", cwd=directory)
    model = json.loads(raw)
    name = model.get("name", "")
    if not isinstance(name, str) or not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", name):
        raise DworkError("Cannot identify a valid Compose project; nothing changed.")
    services = model.get("services", {})
    if not isinstance(services, dict):
        raise DworkError("Invalid Compose service definitions; nothing changed.")
    return name, services

def mapping(value, allowed, where):
    if not isinstance(value, dict) or any(not isinstance(k, str) for k in value):
        raise DworkError(where + " must be a mapping with string keys.")
    unknown = set(value) - set(allowed)
    if unknown:
        raise DworkError(where + ": unknown keys: " + ", ".join(sorted(unknown)))
    return value

def strings(value, where, nonempty=True):
    if (not isinstance(value, list) or (nonempty and not value)
            or any(not isinstance(s, str) or not s or "\0" in s for s in value)):
        raise DworkError(where + " must be a list of nonempty strings.")
    return value

def read_config(path):
    try:
        import yaml
    except ImportError:
        raise DworkError("dwork.yml requires PyYAML (Ubuntu: sudo apt install python3-yaml).")
    # SafeLoader reads data only. Reject duplicate keys rather than hide typos.
    class UniqueLoader(yaml.SafeLoader):
        pass
    def unique_mapping(loader, node):
        loader.flatten_mapping(node)
        result = {}
        for key_node, value_node in node.value:
            key = loader.construct_object(key_node)
            if not isinstance(key, str) or key in result:
                raise DworkError("dwork.yml contains a duplicate or non-string key.")
            result[key] = loader.construct_object(value_node)
        return result
    UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, unique_mapping)
    try:
        config = yaml.load(path.read_text(), Loader=UniqueLoader)
    except yaml.YAMLError as error:
        mark = getattr(error, "problem_mark", None)
        location = " at line " + str(mark.line + 1) if mark else ""
        raise DworkError("Invalid dwork.yml" + location + "; nothing changed.")
    return mapping(config, ("version", "compose", "terminals"), "dwork.yml")

def load_workspace(directory, options=()):
    path = directory / "dwork.yml"
    if not path.is_file():
        name, services = read_model(directory, options)
        return Workspace(name, directory, services)
    cfg = read_config(path)
    if type(cfg.get("version")) is not int or cfg["version"] != 1:
        raise DworkError("dwork.yml: version must be 1.")
    compose = mapping(cfg.get("compose", {}), ("enabled", "files", "services"), "compose")
    enabled = compose.get("enabled", True)
    if type(enabled) is not bool:
        raise DworkError("compose.enabled must be true or false.")
    files = strings(compose["files"], "compose.files") if "files" in compose else []
    selected = strings(compose["services"], "compose.services") if "services" in compose else None
    if not enabled and (files or selected or options):
        raise DworkError("compose.enabled is false; Compose files, services, and CLI options are not allowed.")
    if enabled:
        # Explicit CLI/environment file selection takes precedence over configured files.
        explicit_files = any(a in ("-f", "--file") or a.startswith("--file=") for a in options)
        file_options = [] if explicit_files or os.environ.get("COMPOSE_FILE") else [
            arg for file in files for arg in ("-f", str((directory / file).resolve()))]
        name, services = read_model(directory, [*file_options, *options])
        if selected is not None and set(selected) - set(services):
            raise DworkError("compose.services contains an unknown service.")
    else:
        name, services = directory.name, {}
    tasks = cfg.get("terminals", [])
    if not isinstance(tasks, list):
        raise DworkError("terminals must be a list.")
    terminals = []
    for index, raw in enumerate(tasks):
        task = mapping(raw, ("title", "command", "cwd", "wait_for", "window", "launcher", "confirm"),
                       "terminals[" + str(index) + "]")
        command = strings(task.get("command"), "terminal.command")
        title = task.get("title", "dwork: " + name)
        cwd = task.get("cwd", ".")
        window = task.get("window", "new")
        confirm = task.get("confirm", True)
        if type(confirm) is not bool:
            raise DworkError("terminal.confirm must be true or false.")
        launcher = task.get("launcher", "auto")
        if not isinstance(launcher, str) or launcher not in LAUNCHERS:
            raise DworkError("terminal.launcher must be one of: " + ", ".join(LAUNCHERS))
        if not isinstance(title, str) or not title or not isinstance(cwd, str) or not cwd:
            raise DworkError("terminal.title and terminal.cwd must be nonempty strings.")
        cwd = (directory / cwd).resolve()
        if not cwd.is_dir():
            raise DworkError("Terminal working directory does not exist: " + str(cwd))
        if window not in ("new", "current"):
            raise DworkError("terminal.window must be new or current.")
        wait = mapping(task.get("wait_for", {}), ("healthy", "timeout"), "terminal.wait_for")
        healthy = strings(wait["healthy"], "wait_for.healthy") if "healthy" in wait else []
        timeout = wait.get("timeout", 180)
        if type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0 < timeout <= 3600:
            raise DworkError("wait_for.timeout must be greater than 0 and at most 3600 seconds.")
        if healthy and (not enabled or set(healthy) - set(services)):
            raise DworkError("Health prerequisites must name services in this workspace Compose model.")
        if selected is not None and set(healthy) - set(selected):
            raise DworkError("Health prerequisites must be included in compose.services.")
        for value in [title, str(cwd), *command]:
            if any(c in value for c in ("\0", "\r", "\n", ";")):
                raise DworkError("Terminal values cannot contain NUL, newlines, or Windows Terminal semicolon separators; use a script file.")
        terminals.append(TerminalTask(title, command, cwd, healthy, timeout, window, launcher, confirm))
    return Workspace(name, directory, services, enabled, selected, terminals, True)

def config_directory(directory, options):
    """Use explicit Compose directory/file selection as the config search origin."""
    for index, arg in enumerate(options):
        if arg == "--project-directory" and index + 1 < len(options):
            return Path(options[index + 1]).resolve()
        if arg.startswith("--project-directory="):
            return Path(arg.split("=", 1)[1]).resolve()
    for index, arg in enumerate(options):
        if arg in ("-f", "--file") and index + 1 < len(options) and options[index + 1] != "-":
            return Path(options[index + 1]).resolve().parent
        if arg.startswith("--file=") and arg != "--file=-":
            return Path(arg.split("=", 1)[1]).resolve().parent
    return directory

def discover(directory, options):
    origin = config_directory(directory, options)
    cfg_dir = next((p for p in (origin, *origin.parents) if (p / "dwork.yml").is_file()), None)
    if cfg_dir is not None:
        return [load_workspace(cfg_dir, options)], False
    try:
        return [load_workspace(directory, options)], False
    except DworkError:
        ancestors = (directory, *directory.parents)
        configured = (bool(options) or bool(os.environ.get("COMPOSE_FILE"))
                      or bool(os.environ.get("COMPOSE_ENV_FILES"))
                      or any((p / f).is_file() for p in ancestors for f in FILENAMES)
                      or any((p / ".env").is_file() for p in ancestors))
        if configured:
            raise
        children = [
            child for child in sorted(directory.iterdir())
            if child.name != ".git" and not child.is_symlink() and child.is_dir()
            and ((child / "dwork.yml").is_file()
                 or any((child / file).is_file() for file in FILENAMES))
        ]
        if not children:
            raise DworkError("No dwork.yml or Compose config here, in parents, or in immediate subdirectories; nothing changed.")
        return [load_workspace(child) for child in children], True

def inventory():
    ids = docker("ps", "--all", "--quiet", "--filter", "label=com.docker.compose.project").split()
    items = json.loads(docker("inspect", "--type", "container", *ids)) if ids else []
    if not isinstance(items, list):
        raise DworkError("Invalid container inventory; nothing changed.")
    return items

def service_containers(containers, project, service):
    return [c for c in containers
            if (c.get("Config", {}).get("Labels") or {}).get("com.docker.compose.project") == project
            and (c.get("Config", {}).get("Labels") or {}).get("com.docker.compose.service") == service]

def wait_healthy(ids, timeout):
    deadline = time.monotonic() + timeout
    while True:
        items = json.loads(docker("inspect", "--type", "container", *ids))
        if {c["Id"] for c in items} != set(ids):
            raise DworkError("A required container disappeared; terminals were not opened.")
        ready = True
        for item in items:
            state = item["State"]
            if state["Status"] in ("exited", "dead", "paused", "removing"):
                raise DworkError("A required container is " + state["Status"] + "; terminals were not opened.")
            health = state.get("Health", {}).get("Status")
            if health is None:
                raise DworkError("A required container has no Docker health check; terminals were not opened.")
            if health == "unhealthy":
                raise DworkError("A required container is unhealthy; terminals were not opened.")
            ready = ready and state["Status"] == "running" and health == "healthy"
        if ready:
            return
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise DworkError("Timed out waiting for healthy containers; terminals were not opened.")
        time.sleep(min(1, remaining))

def terminal_arguments(task):
    distro = os.environ.get("WSL_DISTRO_NAME")
    shell = shutil.which(os.environ.get("SHELL", "bash"))
    if not distro or not shell:
        raise DworkError("Terminal tasks currently require WSL2 and an available Bash or Zsh shell.")
    if Path(shell).name not in ("bash", "zsh"):
        raise DworkError("Terminal tasks require Bash or Zsh as SHELL.")
    if any(c in value for value in (distro, shell) for c in ("\0", "\r", "\n", ";")):
        raise DworkError("WSL distribution and shell cannot contain terminal command separators.")
    # Shell startup loads the normal user PATH; shlex.join preserves command argv.
    return ["-w", "new" if task.window == "new" else "0", "new-tab", "--title", task.title,
            "wsl.exe", "--distribution", distro, "--cd", str(task.cwd),
            "--exec", shell, "-lic", "exec " + shlex.join(task.command)]

def powershell_script(task):
    arguments = subprocess.list2cmdline(terminal_arguments(task)).replace("'", "''")
    # Start-Process receives one explicitly quoted ArgumentList, per Microsoft docs.
    return ("$ErrorActionPreference = 'Stop'; "
            "$process = Start-Process -FilePath wt.exe -ArgumentList '" + arguments
            + "' -PassThru; $process.WaitForExit(); exit $process.ExitCode")

def command_shell():
    shell = shutil.which(os.environ.get("SHELL", "bash"))
    if not shell or Path(shell).name not in ("bash", "zsh"):
        raise DworkError("Terminal tasks require an available Bash or Zsh as SHELL.")
    return shell

def choose_launcher(task):
    selected = task.launcher
    if selected == "auto":
        selected = os.environ.get("DWORK_TERMINAL", "auto") or "auto"
    if selected not in LAUNCHERS:
        raise DworkError("DWORK_TERMINAL must be one of: " + ", ".join(LAUNCHERS))
    if selected != "auto":
        return selected
    if os.environ.get("WSL_DISTRO_NAME"):
        return "windows-terminal"
    if not sys.platform.startswith("linux"):
        raise DworkError("Terminal launching supports native Linux and WSL; Compose-only mode is still available.")
    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
    preferred = ("konsole" if "kde" in desktop else
                 "xfce4-terminal" if "xfce" in desktop else
                 "gnome-terminal" if "gnome" in desktop else None)
    order = ([preferred] if preferred else []) + [p for p in LINUX_TERMINALS if p != preferred]
    for launcher in order:
        if launcher == "xterm" and task.window == "current":
            continue
        if shutil.which(launcher):
            return launcher
    raise DworkError("No supported Linux terminal is installed for this window mode. Install GNOME Terminal, Konsole, Xfce Terminal, or xterm (new windows only), or set DWORK_TERMINAL.")

def linux_terminal_arguments(task, launcher):
    if not sys.platform.startswith("linux"):
        raise DworkError("Native terminal launchers require Linux.")
    if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
        raise DworkError("Native Linux terminal tasks require a graphical session (DISPLAY or WAYLAND_DISPLAY).")
    if launcher not in LINUX_TERMINALS or not shutil.which(launcher):
        raise DworkError("Linux terminal is unavailable: " + launcher)
    if launcher == "xterm":
        if task.window == "current":
            raise DworkError("xterm does not support window: current; use window: new or a tab-capable launcher.")
        if not os.environ.get("DISPLAY"):
            raise DworkError("xterm requires an X11 DISPLAY (including XWayland).")
    command = [command_shell(), "-lic", "exec " + shlex.join(task.command)]
    if launcher == "gnome-terminal":
        return [launcher, "--window" if task.window == "new" else "--tab",
                "--title", task.title, "--working-directory", str(task.cwd), "--", *command]
    if launcher == "konsole":
        return [launcher, "--separate" if task.window == "new" else "--new-tab",
                "--workdir", str(task.cwd), "-p", "LocalTabTitleFormat=" + task.title, "-e", *command]
    if launcher == "xfce4-terminal":
        return [launcher, "--window" if task.window == "new" else "--tab",
                "--title", task.title, "--working-directory", str(task.cwd), "--execute", *command]
    return [launcher, "-title", task.title, "-e", *command]

def preflight_terminals(tasks):
    windows = False
    for task in tasks:
        launcher = choose_launcher(task)
        if launcher == "windows-terminal":
            terminal_arguments(task)
            if not shutil.which("powershell.exe"):
                raise DworkError("Windows terminal tasks require Windows PowerShell and Windows Terminal.")
            windows = True
        else:
            linux_terminal_arguments(task, launcher)
        program = task.command[0]
        local = (task.cwd / program).resolve()
        available = (local.is_file() and os.access(local, os.X_OK)) if "/" in program else bool(shutil.which(program))
        if not available:
            raise DworkError("Terminal command is unavailable: " + program)
    if windows:
        run_command(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
                     "(Get-Command wt.exe -ErrorAction Stop).Source"])

def confirm_terminal(task):
    if not task.confirm:
        return True
    prompt = ("Open terminal " + repr(task.title) + " running "
              + shlex.join(task.command) + " in " + str(task.cwd) + "? (y/N) ")
    try:
        answer = input(prompt)
    except EOFError:
        answer = ""
    return answer.strip().lower() == "y"

def open_terminal(task):
    launcher = choose_launcher(task)
    if launcher == "windows-terminal":
        encoded = base64.b64encode(powershell_script(task).encode("utf-16le")).decode("ascii")
        run_command(["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded])
        return
    arguments = linux_terminal_arguments(task, launcher)
    # GUI emulators can remain alive as long as their command. Detach the
    # launcher without pipes, so dwork returns while the terminal stays open.
    process = subprocess.Popen(arguments, cwd=task.cwd, stdin=subprocess.DEVNULL,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               start_new_session=True)
    try:
        code = process.wait(timeout=0.2)
    except subprocess.TimeoutExpired:
        return
    if code:
        raise DworkError(launcher + " failed to launch (exit " + str(code) + "). Check your graphical session.")

def show_target():
    context = docker("context", "show").strip()
    print("Docker context: " + context)
    # DOCKER_HOST can override the endpoint associated with the displayed context.
    if os.environ.get("DOCKER_HOST") and not os.environ.get("DOCKER_CONTEXT"):
        print("Docker endpoint override: DOCKER_HOST is set (value hidden).")


def show_status(workspaces, containers):
    for workspace in workspaces:
        print("Workspace: " + workspace.name + " (" + str(workspace.directory) + ")")
        if not workspace.enabled:
            print("  Compose disabled; host command state is not tracked.")
            continue
        for item in containers:
            labels = item.get("Config", {}).get("Labels") or {}
            if labels.get("com.docker.compose.project") != workspace.name:
                continue
            service = labels.get("com.docker.compose.service", "(unknown service)")
            state = item["State"]
            health = state.get("Health", {}).get("Status", "no health check")
            managed = "managed" if workspace.manages(service) else "unmanaged"
            print("  " + service + " / " + item["Id"][:12] + ": "
                  + state["Status"] + ", " + health + " (" + managed + ")")
        for service in workspace.services:
            if workspace.manages(service) and not service_containers(containers, workspace.name, service):
                print("  " + service + ": missing container; run the project's initial setup manually.")
    if any(w.terminals for w in workspaces):
        print("Host terminal commands are configured; running sessions are not tracked.")


def doctor(directory, options):
    failures = []

    def check(label, operation, hint):
        try:
            value = operation()
            print("OK: " + label)
            return value
        except (DworkError, OSError, ValueError, KeyError, TypeError) as error:
            failures.append(label)
            print("FAIL: " + label + ": " + str(error), file=sys.stderr)
            print("  Fix: " + hint, file=sys.stderr)
            return None

    workspaces = check("Workspace configuration and Compose compatibility",
                       lambda: discover(directory, options)[0],
                       "Check dwork.yml and Compose options; Compose must support config --no-interpolate --no-env-resolution --format json.")
    if workspaces is None:
        print("Run dwork --dry-run after fixing configuration to inspect the switch plan.")
        return 1
    if any(w.enabled for w in workspaces):
        check("Docker target", show_target,
              "Install Docker CLI and check docker context show, DOCKER_CONTEXT, and DOCKER_HOST.")
        containers = check("Docker access and container inventory", inventory,
                           "Check docker info, daemon availability, and permissions for the selected Docker target.")
        if containers is not None:
            show_status(workspaces, containers)
            for workspace in workspaces:
                for task in workspace.terminals:
                    for service in task.healthy:
                        matches = service_containers(containers, workspace.name, service)
                        if not matches or any(not c["State"].get("Health") for c in matches):
                            failures.append("health prerequisite")
                            print("FAIL: " + workspace.name + "/" + service
                                  + " requires existing containers with Docker health checks."
                                  + " Complete project setup and configure healthcheck manually.", file=sys.stderr)
    else:
        print("Docker checks skipped: Compose is disabled.")
    for workspace in workspaces:
        for task in workspace.terminals:
            check("Shell, command, and terminal for " + task.title,
                  lambda task=task: preflight_terminals([task]),
                  "Check SHELL (Bash/Zsh), command PATH, graphical session, and configured launcher or DWORK_TERMINAL.")
    print("Doctor: " + (str(len(failures)) + " check(s) failed." if failures else "all checks passed.")
          + " No containers or terminals changed.")
    return 1 if failures else 0


def report_failure(completed, pending, step, containers):
    print("Switch incomplete at: " + step, file=sys.stderr)
    print("Completed: " + ("; ".join(completed) or "none"), file=sys.stderr)
    print("Not confirmed complete: " + ("; ".join(pending) or "none"), file=sys.stderr)
    print("The interrupted or failed operation may have changed state; inspect before retrying.", file=sys.stderr)
    print("No automatic rollback was attempted. Host commands are not supervised.", file=sys.stderr)
    try:
        current = inventory() if containers else []
        running = [((c.get("Config", {}).get("Labels") or {}).get("com.docker.compose.project", "?")
                    + "/" + c["Id"][:12]) for c in current
                   if c["State"]["Status"] in ("running", "restarting")]
        print("Still running/restarting: " + (", ".join(running) or "none"), file=sys.stderr)
    except (DworkError, OSError, ValueError, KeyError, TypeError):
        print("Could not refresh container state; check docker ps --all.", file=sys.stderr)
    print("Inspect current state: dwork status; preview a retry: dwork --dry-run (use the same Compose options).", file=sys.stderr)
    for action in completed:
        if action.startswith("stop "):
            identifier = action.split()[1]
            print("To restore the stopped container if appropriate: docker start " + identifier, file=sys.stderr)
    print("For a failed container: docker inspect <container-id> and docker logs --tail 50 <container-id>.", file=sys.stderr)


def main():
    options = list(sys.argv[1:])
    commands = ("register", "list", "switch", "forget", "status", "doctor")
    mode = options.pop(0) if options and options[0] in commands else "activate"
    preview = bool(options and options[0] == "--dry-run")
    if preview:
        options = options[1:]
    if options and options[0] in ("--help", "-h"):
        print("Usage: dwork [--dry-run] [Docker Compose global options]")
        print("       dwork register [NAME] [Docker Compose global options]")
        print("       dwork list | forget NAME")
        print("       dwork switch NAME [--dry-run]")
        print("       dwork status | doctor [Docker Compose global options]")
        print("register: remember without switching; list: show remembered directories and status.")
        print("switch: activate a remembered workspace; forget: remove only its registration.")
        print("status: read-only workspace/container state; doctor: read-only dependency diagnostics.")
        print("Read dwork.yml when present; otherwise use existing Compose containers.")
        print("With no default config, discover immediate child directories only.")
        print("Child-project switching requires confirmation (y/N).")
        print("Each terminal asks (y/N) unless that task sets confirm: false in dwork.yml.")
        print("Dry-run previews containers, health prerequisites, and terminals without mutation.")
        print("Only other registered workspaces on this Docker target may be stopped.")
        print("Never creates, rebuilds, recreates, or removes containers.")
        print("DWORK_KEEP_PROJECTS: comma-separated projects to leave running.")
        print("DWORK_TERMINAL: auto, windows-terminal, gnome-terminal, konsole, xfce4-terminal, xterm.")
        return 0
    directory = Path.cwd()
    if mode == "doctor":
        return doctor(directory, options)
    if mode == "list":
        if options or preview:
            raise DworkError("Usage: dwork list")
        return list_registrations(read_registry())
    if mode == "status":
        return switch_workspace(directory, options, mode, preview, [])
    name = None
    if mode in ("switch", "forget"):
        if not options or options[0].startswith("-"):
            raise DworkError("Usage: dwork " + mode + " NAME" + (" [--dry-run]" if mode == "switch" else ""))
        name = options.pop(0)
        if mode == "switch" and options == ["--dry-run"]:
            preview, options = True, []
        if options or (mode == "forget" and preview):
            raise DworkError("Usage: dwork " + mode + " NAME" + (" [--dry-run]" if mode == "switch" else ""))
    elif mode == "register":
        if preview:
            raise DworkError("Use dwork --dry-run to preview; register only saves a workspace.")
        if options and not options[0].startswith("-"):
            name = options.pop(0)
    if mode == "activate" and options and not options[0].startswith("-"):
        raise DworkError("Unknown command: " + options[0] + ". See dwork --help.")
    if preview:
        return registry_command(directory, options, mode, preview, name, read_registry())
    with registry_lock():
        return registry_command(directory, options, mode, preview, name, read_registry())


def registry_command(directory, options, mode, preview, name, entries):
    if mode in ("switch", "forget"):
        entry = next((e for e in entries if e["name"] == name), None)
        if entry is None:
            raise DworkError("Unknown workspace: " + str(name) + ". Run dwork list.")
        if mode == "forget":
            save_registry([e for e in entries if e is not entry])
            print("Forgot " + name + ". Containers, terminals, and project files were left alone.")
            return 0
        directory = Path(entry["path"])
        if not directory.is_dir():
            raise DworkError("Workspace directory unavailable: " + str(directory)
                             + ". Forget it and register the new location after a move.")
        old_environment = {key: os.environ.get(key) for key in COMPOSE_ENV}
        original = Path.cwd()
        try:
            os.chdir(directory)
            for key in COMPOSE_ENV:
                os.environ.pop(key, None)
            os.environ.update(entry["environment"])
            return switch_workspace(directory, entry["options"], mode, preview, entries, name)
        finally:
            os.chdir(original)
            for key, value in old_environment.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
    return switch_workspace(directory, options, mode, preview, entries, name)


def switch_workspace(directory, options, mode, preview, entries, name=None):
    workspaces, discovered = discover(directory, options)
    root = registration_directory(directory, options, discovered)
    if root != directory:
        directory = root
        workspaces, discovered = discover(directory, options)
    active = {w.name: w for w in workspaces if w.enabled}
    if len(active) != sum(w.enabled for w in workspaces):
        raise DworkError("Child directories resolve to the same Compose project; use explicit Compose options.")
    if active and not shutil.which("docker"):
        raise DworkError("docker is not available.")
    if mode == "status":
        containers = inventory() if active else []
        if active:
            show_target()
        show_status(workspaces, containers)
        return 0
    target = docker_target() if active else None
    existing = next((e for e in entries if e["path"] == str(directory)), None)
    default_name = workspaces[0].name if len(workspaces) == 1 else directory.name
    name = name or (existing["name"] if existing else default_name)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", name):
        raise DworkError("Workspace name must contain letters, digits, dots, underscores, or hyphens"
                         + " and start with a letter or digit. Use dwork register NAME.")
    candidate = registration(directory, options, workspaces, target, name)
    if any(e["name"] == name and e["path"] != candidate["path"] for e in entries):
        raise DworkError("Workspace name already registered: " + name + ". Use dwork register NAME with a unique name.")
    check_ownership(entries, candidate)
    if mode == "register":
        save_registry([e for e in entries if e["path"] != candidate["path"]] + [candidate])
        print("Registered " + name + " at " + str(directory) + ". No containers or terminals changed.")
        return 0
    if existing and candidate != existing:
        raise DworkError("Workspace configuration or Docker target changed since registration."
                         + " Review dwork --dry-run after running dwork register " + name
                         + " with the intended Compose options; nothing changed.")
    if mode == "switch" and not existing:
        raise DworkError("Workspace registration no longer matches its directory; register it again.")
    managed = registered_services(entries, target)
    containers = inventory() if active else []
    if active:
        show_target()
    keep = {n.strip() for n in os.environ.get("DWORK_KEEP_PROJECTS", "").split(",") if n.strip()}
    stops, starts, warnings = [], [], []
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
        elif (project in managed and project not in keep and state in ("running", "restarting")
              and (managed[project] is None or service in managed[project])):
            stops.append((identifier, project))
    gates, tasks = [], []
    for w in workspaces:
        for service in w.services:
            if w.manages(service) and not service_containers(containers, w.name, service):
                warnings.append("Service " + w.name + "/" + service + " has no container; create it manually if needed (it may be profile-specific).")
        for task in w.terminals:
            tasks.append(task)
            ids = []
            for service in task.healthy:
                matches = service_containers(containers, w.name, service)
                if not matches:
                    message = "Required healthy service " + w.name + "/" + service + " has no existing container."
                    if not preview:
                        raise DworkError(message + " Create it manually; nothing changed.")
                    warnings.append(message + " Terminal launch would be blocked.")
                ids.extend(c["Id"] for c in matches)
            if ids:
                gates.append((ids, task.timeout))
    if not preview:
        preflight_terminals(tasks)
    if discovered:
        print("Projects found in immediate subdirectories:")
        for w in workspaces:
            print("  " + str(w.directory.relative_to(directory)) + " -> " + w.name)
    else:
        print("Current Compose project: " + workspaces[0].name if active
              else "Current workspace: " + workspaces[0].name + " (Compose disabled)")
    for warning in warnings:
        print("Warning: " + warning, file=sys.stderr)
    print("Switch plan: " + str(len(stops)) + " stop(s), " + str(len(starts))
          + " start(s), " + str(len(tasks)) + " terminal task(s).")
    if active:
        print("Scope: only other registered workspaces on this Docker target may be stopped.")
    if existing is None:
        print("Would register workspace: " + name + " -> " + str(directory))
    print("Protected projects (DWORK_KEEP_PROJECTS): " + (", ".join(sorted(keep)) or "none"))
    for identifier, project in stops:
        print("Would stop: " + identifier[:12] + " (" + project + ")")
    for identifier, project, service in starts:
        print("Would start existing: " + identifier[:12] + " (" + project + "/" + service + ")")
    for task in tasks:
        if task.healthy:
            print("Would wait for healthy: " + ", ".join(task.healthy) + " (timeout " + str(task.timeout) + "s)")
        confirmation = " [confirmation required]" if task.confirm else " [confirm: false]"
        print("Would open terminal: " + task.title + " -> " + shlex.join(task.command) + " in " + str(task.cwd) + confirmation)
    if not stops and not starts and not tasks:
        print("No container changes needed.")
    if preview:
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
        if not confirm_registration(candidate):
            print("Cancelled; no workspace registered and no containers or terminals changed.")
            return 0
        save_registry(entries + [candidate])
        print("Registered " + name + " at " + str(directory) + ".")
    actions = []
    for identifier, project in stops:
        actions.append(("stop " + identifier + " (" + project + ")",
                        lambda identifier=identifier: docker("stop", identifier)))
    for identifier, project, service in starts:
        actions.append(("start " + identifier + " (" + project + "/" + service + ")",
                        lambda identifier=identifier: docker("start", identifier)))
    for ids, timeout in gates:
        actions.append(("wait for healthy " + ", ".join(ids),
                        lambda ids=ids, timeout=timeout: wait_healthy(ids, timeout)))
    completed = []
    pending = [label for label, _ in actions] + ["terminal " + task.title for task in tasks]
    step = "before execution"
    try:
        for label, operation in actions:
            step = label
            print("Executing: " + label, flush=True)
            operation()
            completed.append(label)
            pending.pop(0)
        for task in tasks:
            step = "terminal " + task.title
            if not confirm_terminal(task):
                print("Skipped terminal: " + task.title, flush=True)
                pending.pop(0)
                continue
            print("Opening terminal: " + task.title, flush=True)
            open_terminal(task)
            completed.append("launched terminal " + task.title)
            pending.pop(0)
    except (DworkError, OSError, ValueError, KeyError, TypeError, KeyboardInterrupt):
        report_failure(completed, pending, step, containers)
        raise
    return 0

def cli():
    """Shared console entry point for source and packaged installations."""
    try:
        return main()
    except (DworkError, OSError, ValueError, KeyError, TypeError) as error:
        print("dwork: " + str(error), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\ndwork: cancelled.", file=sys.stderr)
        return 130

if __name__ == "__main__":
    sys.exit(cli())
