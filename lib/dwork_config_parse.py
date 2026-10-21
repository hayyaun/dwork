"""Decode and normalize configuration data without filesystem or Compose access."""

from dataclasses import dataclass
import math

from dwork_common import DworkError, LAUNCHERS
import dwork_browser_launch


COMPOSE_ENV = (
    "COMPOSE_FILE",
    "COMPOSE_PROJECT_NAME",
    "COMPOSE_PROFILES",
    "COMPOSE_ENV_FILES",
    "COMPOSE_PATH_SEPARATOR",
    "COMPOSE_DISABLE_ENV_FILE",
)


@dataclass(frozen=True)
class TerminalConfig:
    title: str | None
    command: tuple[str, ...]
    cwd: str
    healthy: tuple[str, ...]
    timeout: float
    window: str
    launcher: str
    confirm: bool


@dataclass(frozen=True)
class BrowserConfig:
    url: str
    wait_url: str | None
    timeout: float
    confirm: bool
    browser: str


@dataclass(frozen=True)
class WorkspaceConfig:
    enabled: bool
    files: tuple[str, ...]
    selected: tuple[str, ...] | None
    locked: bool
    confirm: bool
    terminals: tuple[TerminalConfig, ...]
    browsers: tuple[BrowserConfig, ...]


def lock_value(config):
    locked = config.get("locked", False)
    if type(locked) is not bool:
        raise DworkError("dwork.yml: locked must be true or false.")
    return locked


def mapping(value, allowed, where):
    if not isinstance(value, dict) or any(not isinstance(k, str) for k in value):
        raise DworkError(where + " must be a mapping with string keys.")
    unknown = set(value) - set(allowed)
    if unknown:
        raise DworkError(where + ": unknown keys: " + ", ".join(sorted(unknown)))
    return value


def strings(value, where, nonempty=True):
    if (
        not isinstance(value, list)
        or (nonempty and not value)
        or any(not isinstance(s, str) or not s or "\0" in s for s in value)
    ):
        raise DworkError(where + " must be a list of nonempty strings.")
    return value


def decode_config(text):
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
        config = yaml.load(text, Loader=UniqueLoader)
    except yaml.YAMLError as error:
        mark = getattr(error, "problem_mark", None)
        location = " at line " + str(mark.line + 1) if mark else ""
        raise DworkError("Invalid dwork.yml" + location + "; nothing changed.")
    return mapping(
        config, ("version", "locked", "confirm", "compose", "terminals", "browsers"), "dwork.yml"
    )


def timeout_value(value, where):
    # Bound integers before isfinite converts them to floats (which can overflow).
    if type(value) not in (int, float) or not 0 < value <= 3600 or not math.isfinite(value):
        raise DworkError(where + " must be greater than 0 and at most 3600 seconds.")
    return value


def parse_config(cfg) -> WorkspaceConfig:
    """Validate YAML values; paths and Compose references are resolved separately."""
    cfg = mapping(
        cfg, ("version", "locked", "confirm", "compose", "terminals", "browsers"), "dwork.yml"
    )
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
    if not enabled and (files or selected):
        raise DworkError(
            "compose.enabled is false; Compose files, services, and CLI options are not allowed."
        )
    tasks = cfg.get("terminals", [])
    if not isinstance(tasks, list):
        raise DworkError("terminals must be a list.")
    terminals = []
    for index, raw in enumerate(tasks):
        task = mapping(
            raw,
            ("title", "command", "cwd", "wait_for", "window", "launcher", "confirm"),
            "terminals[" + str(index) + "]",
        )
        command = strings(task.get("command"), "terminal.command")
        title = task.get("title")
        if "title" in task and title is None:
            raise DworkError("terminal.title and terminal.cwd must be nonempty strings.")
        cwd = task.get("cwd", ".")
        window = task.get("window", "new")
        confirm = task.get("confirm", True)
        if type(confirm) is not bool:
            raise DworkError("terminal.confirm must be true or false.")
        launcher = task.get("launcher", "auto")
        if not isinstance(launcher, str) or launcher not in LAUNCHERS:
            raise DworkError("terminal.launcher must be one of: " + ", ".join(LAUNCHERS))
        if (
            (title is not None and (not isinstance(title, str) or not title))
            or not isinstance(cwd, str)
            or not cwd
        ):
            raise DworkError("terminal.title and terminal.cwd must be nonempty strings.")
        if window not in ("new", "current", "none"):
            raise DworkError("terminal.window must be new, current, or none.")
        wait = mapping(task.get("wait_for", {}), ("healthy", "timeout"), "terminal.wait_for")
        healthy = strings(wait["healthy"], "wait_for.healthy") if "healthy" in wait else []
        timeout = timeout_value(wait.get("timeout", 180), "wait_for.timeout")
        terminals.append(
            TerminalConfig(
                title, tuple(command), cwd, tuple(healthy), timeout, window, launcher, confirm
            )
        )
    browsers = []
    raw_browsers = cfg.get("browsers", [])
    if not isinstance(raw_browsers, list):
        raise DworkError("browsers must be a list.")
    for index, raw in enumerate(raw_browsers):
        where = "browsers[" + str(index) + "]"
        browser = mapping(raw, ("url", "browser", "wait_for", "confirm"), where)
        url = dwork_browser_launch.validate_url(browser.get("url"), where + ".url")
        selected_browser = dwork_browser_launch.validate_browser(browser.get("browser", "default"))
        confirm = browser.get("confirm", True)
        if type(confirm) is not bool:
            raise DworkError("browser.confirm must be true or false.")
        wait = browser.get("wait_for", {})
        wait_url, timeout = None, 60
        if wait is not False:
            wait = mapping(wait, ("url", "timeout"), "browser.wait_for")
            wait_url = dwork_browser_launch.validate_url(
                wait.get("url", url), "browser.wait_for.url"
            )
            timeout = timeout_value(wait.get("timeout", 60), "browser.wait_for.timeout")
        browsers.append(BrowserConfig(url, wait_url, timeout, confirm, selected_browser))
    return WorkspaceConfig(
        enabled,
        tuple(files),
        None if selected is None else tuple(selected),
        locked,
        workspace_confirm,
        tuple(terminals),
        tuple(browsers),
    )
