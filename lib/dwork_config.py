"""Resolve parsed configuration, Compose selection, and workspace discovery."""

from contextlib import contextmanager
from pathlib import Path
import os

from dwork_common import BrowserTask, DworkError, TerminalTask, Workspace
from dwork_config_parse import (
    COMPOSE_ENV,
    WorkspaceConfig,
    decode_config,
    lock_value as lock_value,
    parse_config,
)
import dwork_docker


FILENAMES = ("compose.yaml", "compose.yml", "docker-compose.yaml", "docker-compose.yml")


def init_workspace(directory, preview=False):
    """Create a predictable local starter without inspecting or running workloads."""
    path = directory / "dwork.yml"
    if path.exists() or path.is_symlink():
        raise DworkError("dwork.yml already exists; edit it or run dwork validate.")
    enabled = any((directory / name).is_file() for name in FILENAMES)
    text = (
        "# yaml-language-server: $schema=https://raw.githubusercontent.com/hayyaun/dwork/main/schemas/dwork.schema.json\n"
        + "version: 1\ncompose:\n  enabled: "
        + ("true" if enabled else "false")
        + "\nterminals: []\nbrowsers: []\n"
    )
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
    if (
        options
        or os.environ.get("COMPOSE_FILE")
        or os.environ.get("COMPOSE_ENV_FILES")
        or discovered
    ):
        return directory
    ancestors = (directory, *directory.parents)
    for parent in ancestors:
        if (parent / "dwork.yml").is_file():
            return parent
    for parent in ancestors:
        if any((parent / f).is_file() for f in FILENAMES):
            return parent
    return directory


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


def read_config(path):
    return decode_config(path.read_text())


def load_workspace(directory, options=(), *, compose_directory=None):
    path = directory / "dwork.yml"
    if not path.is_file():
        name, services = dwork_docker.read_model(directory, options)
        return Workspace(name, directory, services)
    return resolve_workspace(
        parse_config(read_config(path)), directory, options, compose_directory=compose_directory
    )


def resolve_workspace(
    config: WorkspaceConfig, directory: Path, options=(), *, compose_directory=None
):
    """Resolve external paths and Compose references after data-only validation."""
    enabled, files = config.enabled, config.files
    selected = None if config.selected is None else list(config.selected)
    if not enabled and (files or selected or options):
        raise DworkError(
            "compose.enabled is false; Compose files, services, and CLI options are not allowed."
        )
    if enabled:
        explicit_files = any(a in ("-f", "--file") or a.startswith("--file=") for a in options)
        file_options = (
            []
            if explicit_files or os.environ.get("COMPOSE_FILE")
            else [arg for file in files for arg in ("-f", str((directory / file).resolve()))]
        )
        name, services = dwork_docker.read_model(
            compose_directory or directory, [*file_options, *options]
        )
        if selected is not None and set(selected) - set(services):
            raise DworkError("compose.services contains an unknown service.")
    else:
        name, services = directory.name, {}
    terminals = []
    for task in config.terminals:
        title = task.title if task.title is not None else "dwork: " + name
        cwd = (directory / task.cwd).resolve()
        if not cwd.is_dir():
            raise DworkError("Terminal working directory does not exist: " + str(cwd))
        if task.healthy and (not enabled or set(task.healthy) - set(services)):
            raise DworkError(
                "Health prerequisites must name services in this workspace Compose model."
            )
        if selected is not None and set(task.healthy) - set(selected):
            raise DworkError("Health prerequisites must be included in compose.services.")
        for value in [title, str(cwd), *task.command]:
            if any(c in value for c in ("\0", "\r", "\n", ";")):
                raise DworkError(
                    "Terminal values cannot contain NUL, newlines, or Windows Terminal semicolon separators; use a script file."
                )
        terminals.append(
            TerminalTask(
                title,
                list(task.command),
                cwd,
                list(task.healthy),
                task.timeout,
                task.window,
                task.launcher,
                task.confirm,
            )
        )
    browsers = [
        BrowserTask(task.url, task.wait_url, task.timeout, task.confirm, task.browser)
        for task in config.browsers
    ]
    return Workspace(
        name,
        directory,
        services,
        enabled,
        selected,
        terminals,
        True,
        config.locked,
        browsers,
        confirm=config.confirm,
        registration_name=config.name,
    )


def config_directory(directory, options):
    """Use explicit Compose directory/file selection as the config search origin."""
    for index, arg in enumerate(options):
        if arg == "--project-directory" and index + 1 < len(options):
            return (directory / options[index + 1]).resolve()
        if arg.startswith("--project-directory="):
            return (directory / arg.split("=", 1)[1]).resolve()
    for index, arg in enumerate(options):
        if arg in ("-f", "--file") and index + 1 < len(options) and options[index + 1] != "-":
            return (directory / options[index + 1]).resolve().parent
        if arg.startswith("--file=") and arg != "--file=-":
            return (directory / arg.split("=", 1)[1]).resolve().parent
    return directory


def discover(directory, options):
    origin = config_directory(directory, options)
    cfg_dir = next((p for p in (origin, *origin.parents) if (p / "dwork.yml").is_file()), None)
    if cfg_dir is not None:
        # YAML-owned paths use cfg_dir; explicit Compose selections retain the
        # caller's cwd, including when the configuration is found in a parent.
        explicit = options or os.environ.get("COMPOSE_FILE") or os.environ.get("COMPOSE_ENV_FILES")
        return [
            load_workspace(cfg_dir, options, compose_directory=directory if explicit else None)
        ], False
    try:
        return [load_workspace(directory, options)], False
    except DworkError:
        ancestors = (directory, *directory.parents)
        configured = (
            bool(options)
            or bool(os.environ.get("COMPOSE_FILE"))
            or bool(os.environ.get("COMPOSE_ENV_FILES"))
            or any((p / f).is_file() for p in ancestors for f in FILENAMES)
            or any((p / ".env").is_file() for p in ancestors)
        )
        if configured:
            raise
        children = [
            child
            for child in sorted(directory.iterdir())
            if child.name != ".git"
            and not child.is_symlink()
            and child.is_dir()
            and (
                (child / "dwork.yml").is_file()
                or any((child / file).is_file() for file in FILENAMES)
            )
        ]
        if not children:
            raise DworkError(
                "No dwork.yml or Compose config here, in parents, or in immediate subdirectories; nothing changed."
            )
        return [load_workspace(child) for child in children], True
