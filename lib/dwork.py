"""Workspace switching, optional YAML config, health gates, and WSL terminals."""
import base64
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
import time

LINUX_TERMINALS = ("gnome-terminal", "konsole", "xfce4-terminal", "xterm")
LAUNCHERS = ("auto", "windows-terminal", *LINUX_TERMINALS)

FILENAMES = ("compose.yaml", "compose.yml", "docker-compose.yaml", "docker-compose.yml")

class DworkError(Exception):
    pass

@dataclass
class TerminalTask:
    title: str
    command: list
    cwd: Path
    healthy: list = field(default_factory=list)
    timeout: float = 180
    window: str = "new"
    launcher: str = "auto"

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
        task = mapping(raw, ("title", "command", "cwd", "wait_for", "window", "launcher"),
                       "terminals[" + str(index) + "]")
        command = strings(task.get("command"), "terminal.command")
        title = task.get("title", "dwork: " + name)
        cwd = task.get("cwd", ".")
        window = task.get("window", "new")
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
        terminals.append(TerminalTask(title, command, cwd, healthy, timeout, window, launcher))
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

def main():
    options = sys.argv[1:]
    preview = bool(options and options[0] == "--dry-run")
    if preview:
        options = options[1:]
    if options and options[0] in ("--help", "-h"):
        print("Usage: dwork [--dry-run] [Docker Compose global options]")
        print("Read dwork.yml when present; otherwise use existing Compose containers.")
        print("With no default config, discover immediate child directories only.")
        print("Child-project switching requires confirmation (y/N).")
        print("Dry-run previews containers, health prerequisites, and terminals without mutation.")
        print("Never creates, rebuilds, recreates, or removes containers.")
        print("DWORK_KEEP_PROJECTS: comma-separated projects to leave running.")
        print("DWORK_TERMINAL: auto, windows-terminal, gnome-terminal, konsole, xfce4-terminal, xterm.")
        return 0
    directory = Path.cwd()
    workspaces, discovered = discover(directory, options)
    active = {w.name: w for w in workspaces if w.enabled}
    if len(active) != sum(w.enabled for w in workspaces):
        raise DworkError("Child directories resolve to the same Compose project; use explicit Compose options.")
    if active and not shutil.which("docker"):
        raise DworkError("docker is not available.")
    containers = inventory() if active else []
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
        elif project not in keep and state in ("running", "restarting"):
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
    if discovered or preview:
        for identifier, project in stops:
            print("Would stop: " + identifier[:12] + " (" + project + ")")
        for identifier, project, service in starts:
            print("Would start existing: " + identifier[:12] + " (" + project + "/" + service + ")")
        for task in tasks:
            if task.healthy:
                print("Would wait for healthy: " + ", ".join(task.healthy) + " (timeout " + str(task.timeout) + "s)")
            print("Would open terminal: " + task.title + " -> " + shlex.join(task.command) + " in " + str(task.cwd))
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
    for identifier, project in stops:
        print("Stopping: " + identifier[:12] + " (" + project + ")", flush=True)
        docker("stop", identifier)
    for identifier, project, service in starts:
        print("Starting existing: " + identifier[:12] + " (" + project + "/" + service + ")", flush=True)
        docker("start", identifier)
    # All health gates pass before any terminal launches.
    for ids, timeout in gates:
        print("Waiting for Docker health checks...", flush=True)
        wait_healthy(ids, timeout)
    for task in tasks:
        print("Opening terminal: " + task.title, flush=True)
        open_terminal(task)
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except (DworkError, OSError, ValueError, KeyError, TypeError) as error:
        print("dwork: " + str(error), file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\ndwork: cancelled.", file=sys.stderr)
        sys.exit(130)
