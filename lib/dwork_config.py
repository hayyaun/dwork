"""Workspace configuration, Compose environment selection, and discovery."""
from contextlib import contextmanager
from pathlib import Path
import math
import os

from dwork_common import BrowserTask, DworkError, LAUNCHERS, TerminalTask, Workspace
import dwork_browsers
import dwork_docker


FILENAMES = ("compose.yaml", "compose.yml", "docker-compose.yaml", "docker-compose.yml")
COMPOSE_ENV = ("COMPOSE_FILE", "COMPOSE_PROJECT_NAME", "COMPOSE_PROFILES",
               "COMPOSE_ENV_FILES", "COMPOSE_PATH_SEPARATOR", "COMPOSE_DISABLE_ENV_FILE")


def init_workspace(directory, preview=False):
    """Create a predictable local starter without inspecting or running workloads."""
    path = directory / "dwork.yml"
    if path.exists() or path.is_symlink():
        raise DworkError("dwork.yml already exists; edit it or run dwork validate.")
    enabled = any((directory / name).is_file() for name in FILENAMES)
    text = ("version: 1\ncompose:\n  enabled: " + ("true" if enabled else "false")
            + "\nterminals: []\nbrowsers: []\n")
    if preview:
        print("Would create " + str(path) + ":\n" + text, end="")
        return 0
    # Exclusive creation also protects existing files and links if another process
    # creates the path after the check above.
    try:
        with path.open("x", encoding="utf-8") as stream:
            stream.write(text)
    except FileExistsError:
        raise DworkError("dwork.yml already exists; edit it or run dwork validate.")
    print("Created " + str(path) + ". Review it, then run dwork validate.")
    return 0


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


def lock_value(config):
    locked = config.get("locked", False)
    if type(locked) is not bool:
        raise DworkError("dwork.yml: locked must be true or false.")
    return locked


@contextmanager
def compose_environment(values):
    previous = {key: os.environ.get(key) for key in COMPOSE_ENV}
    try:
        for key in COMPOSE_ENV:
            os.environ.pop(key, None)
        os.environ.update(values)
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


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
    return mapping(config, ("version", "locked", "confirm", "compose", "terminals", "browsers"), "dwork.yml")


def load_workspace(directory, options=()):
    path = directory / "dwork.yml"
    if not path.is_file():
        name, services = dwork_docker.read_model(directory, options)
        return Workspace(name, directory, services)
    cfg = read_config(path)
    if type(cfg.get("version")) is not int or cfg["version"] != 1:
        raise DworkError("dwork.yml: version must be 1.")
    locked = lock_value(cfg)
    workspace_confirm = cfg.get("confirm", True)
    if type(workspace_confirm) is not bool:
        raise DworkError("dwork.yml: confirm must be true or false.")
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
        name, services = dwork_docker.read_model(directory, [*file_options, *options])
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
        if window not in ("new", "current", "none"):
            raise DworkError("terminal.window must be new, current, or none.")
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
    browsers = []
    raw_browsers = cfg.get("browsers", [])
    if not isinstance(raw_browsers, list):
        raise DworkError("browsers must be a list.")
    for index, raw in enumerate(raw_browsers):
        where = "browsers[" + str(index) + "]"
        browser = mapping(raw, ("url", "browser", "wait_for", "confirm"), where)
        url = dwork_browsers.validate_url(browser.get("url"), where + ".url")
        selected_browser = dwork_browsers.validate_browser(browser.get("browser", "default"))
        confirm = browser.get("confirm", True)
        if type(confirm) is not bool:
            raise DworkError("browser.confirm must be true or false.")
        wait = browser.get("wait_for", {})
        wait_url, timeout = None, 60
        if wait is not False:
            wait = mapping(wait, ("url", "timeout"), "browser.wait_for")
            wait_url = dwork_browsers.validate_url(wait.get("url", url), "browser.wait_for.url")
            timeout = wait.get("timeout", 60)
            if type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0 < timeout <= 3600:
                raise DworkError("browser.wait_for.timeout must be greater than 0 and at most 3600 seconds.")
        browsers.append(BrowserTask(url, wait_url, timeout, confirm, selected_browser))
    return Workspace(name, directory, services, enabled, selected, terminals, True, locked, browsers,
                     confirm=workspace_confirm)


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
