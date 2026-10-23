"""Repository scanning, interactive Compose selection, and bulk registration."""

from pathlib import Path
import os
import re
import shutil
import sys
import time

from dwork_common import DworkError, color, colored_name
import dwork_config
import dwork_docker
import dwork_registry


SCAN_IGNORED_DIRS = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        "node_modules",
        "bower_components",
        "vendor",
        ".venv",
        "venv",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".tox",
        ".nox",
        ".cache",
        ".npm",
        ".pnpm-store",
        ".yarn",
        ".next",
        ".nuxt",
        ".svelte-kit",
        ".angular",
        ".gradle",
        "build",
        "dist",
        "out",
        "target",
        "coverage",
        "htmlcov",
    }
)


SCAN_REPO_MARKERS = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        "dwork.yml",
        "package.json",
        "pyproject.toml",
        "setup.py",
        "Cargo.toml",
        "go.mod",
        "composer.json",
        "Gemfile",
        "pom.xml",
        "build.gradle",
        "build.gradle.kts",
        "settings.gradle",
        "settings.gradle.kts",
        "mix.exs",
        "pubspec.yaml",
    }
) | frozenset(dwork_config.FILENAMES)


def scan_directories(root):
    configured, compose = [], []
    errors = []
    interactive = sys.stdout.isatty() and os.environ.get("TERM") != "dumb"
    latest, last_update, rendered_rows = None, None, 0

    def progress(path, force=False):
        nonlocal last_update, rendered_rows
        now = time.monotonic()
        if interactive and (force or last_update is None or now - last_update >= 0.1):
            size = shutil.get_terminal_size()
            width, height = max(1, size.columns - 1), max(1, size.lines - 2)
            parts = path.relative_to(root).parts
            if len(parts) > height:
                parts = ("...", *parts[-(height - 1) :]) if height > 1 else parts[-1:]
            lines = ["  " * level + part for level, part in enumerate(parts)] or [
                "Searching: " + str(root)
            ]
            clipped = []
            for text in lines:
                if len(text) > width:
                    text = "..." + text[-(width - 3) :] if width > 3 else text[:width]
                clipped.append(color(text, "grey"))
            # Redraw only the current branch; remove stale rows when moving up.
            previous = "\033[" + str(rendered_rows - 1) + "A" if rendered_rows > 1 else ""
            print(previous + "\r\033[J" + "\n".join(clipped), end="", flush=True)
            rendered_rows = len(lines)
            last_update = now

    def unreadable(error):
        errors.append(str(error))

    try:
        for directory, children, files in os.walk(root, followlinks=False, onerror=unreadable):
            path = Path(directory)
            latest = path
            progress(path)
            boundary = bool(
                SCAN_REPO_MARKERS.intersection(files)
                or {".git", ".hg", ".svn"}.intersection(children)
            )
            children[:] = (
                []
                if boundary
                else sorted(
                    name
                    for name in children
                    if name not in SCAN_IGNORED_DIRS and not (path / name).is_symlink()
                )
            )
            if "dwork.yml" in files:
                configured.append(path)
            elif any(name in files for name in dwork_config.FILENAMES):
                compose.append(path)
    finally:
        if interactive and latest is not None:
            progress(latest, force=True)
            print(flush=True)
    return configured, compose, errors


def checkbox_screen(screen, choices, curses):
    """Small scrollable picker using the public curses input/window APIs."""
    selected, cursor = set(), 0
    screen.keypad(True)
    try:
        curses.curs_set(0)
    except curses.error:
        pass
    while True:
        screen.erase()
        rows, columns = screen.getmaxyx()
        visible = max(1, rows - 5)
        offset = max(0, min(cursor - visible + 1, max(0, len(choices) - visible)))
        lines = [
            (0, "Select Compose workspaces to register", curses.A_BOLD),
            (1, "Up/Down: move  Space: toggle  Enter: done  Esc: cancel", curses.A_NORMAL),
        ]
        for index in range(offset, min(len(choices), offset + visible)):
            label = (
                ("> " if index == cursor else "  ")
                + ("[x] " if index in selected else "[ ] ")
                + choices[index]
            )
            lines.append(
                (
                    index - offset + 3,
                    label,
                    curses.A_REVERSE if index == cursor else curses.A_NORMAL,
                )
            )
        lines.append((rows - 1, str(len(selected)) + " selected", curses.A_NORMAL))
        for row, label, attributes in lines:
            if 0 <= row < rows and columns > 1:
                try:
                    screen.addnstr(row, 0, label, columns - 1, attributes)
                except curses.error:
                    pass  # A resize or a wide Unicode character can fill the last cell.
        screen.refresh()
        key = screen.get_wch()
        if key in ("\n", "\r", curses.KEY_ENTER):
            return sorted(selected)
        if key in ("\x1b", "q"):
            return None
        if key == "\x03":
            raise KeyboardInterrupt
        if key in (curses.KEY_DOWN, "j"):
            cursor = min(len(choices) - 1, cursor + 1)
        elif key in (curses.KEY_UP, "k"):
            cursor = max(0, cursor - 1)
        elif key == " ":
            if cursor in selected:
                selected.remove(cursor)
            else:
                selected.add(cursor)


def choose_compose_directories(paths, root):
    if (
        not sys.stdin.isatty()
        or not sys.stdout.isatty()
        or os.environ.get("TERM") in (None, "", "dumb")
    ):
        raise DworkError(
            "The Compose checkbox picker requires an interactive terminal. Run dwork scan in a terminal; configured workspaces already registered are kept."
        )
    try:
        import curses
    except ImportError:
        raise DworkError(
            "The Compose picker requires Python curses support from your Python distributor. You can also register individual directories with dwork register."
        )
    choices = [str(path.relative_to(root)) for path in paths]
    try:
        curses.setupterm()  # Validate TERM before initscr, which can terminate on bad terminal data.
        indices = curses.wrapper(checkbox_screen, choices, curses)
    except curses.error as error:
        raise DworkError(
            "Cannot open the Compose picker: "
            + str(error)
            + ". Configured workspaces already registered are kept."
        )
    return [] if indices is None else [paths[index] for index in indices]


def scan_workspaces(root, entries, preview):
    print("Scanning: " + str(root), flush=True)
    configured, compose, errors = scan_directories(root)
    target = None
    failures = len(errors)
    for error in errors:
        print(
            color("Warning: scan could not read a directory: " + error, "warning", sys.stderr),
            file=sys.stderr,
        )

    def add_directories(paths):
        nonlocal target, failures
        added = 0
        for directory in paths:
            existing = next((e for e in entries if e["path"] == str(directory)), None)
            if existing:
                print(
                    "Already registered: "
                    + colored_name(existing["name"])
                    + " -> "
                    + str(directory)
                )
                continue
            try:
                # Each discovered directory owns its own config, even beneath another workspace.
                with dwork_config.compose_environment({}):
                    workspace = dwork_config.load_workspace(directory)
                    if workspace.enabled and target is None:
                        target = dwork_docker.docker_target()
                    base = (
                        workspace.registration_name
                        or re.sub(r"[^A-Za-z0-9_.-]+", "-", workspace.name).strip("-_.")
                        or "workspace"
                    )
                    name, suffix = base, 2
                    while any(e["name"] == name for e in entries):
                        name, suffix = base + "-" + str(suffix), suffix + 1
                    candidate = dwork_registry.registration(
                        directory,
                        [],
                        [workspace],
                        target if workspace.enabled else None,
                        name,
                        direct=True,
                    )
                dwork_registry.check_ownership(entries, candidate)
                entries.append(candidate)
                added += 1
                print(
                    ("Would register: " if preview else "Registering: ")
                    + colored_name(name)
                    + " -> "
                    + str(directory)
                )
            except (DworkError, OSError, ValueError, KeyError, TypeError) as error:
                failures += 1
                print(
                    color("Skipped " + str(directory) + ": " + str(error), "warning", sys.stderr),
                    file=sys.stderr,
                )
        if added and not preview:
            dwork_registry.save_registry(entries)
        return added

    count = add_directories(configured)
    print(
        ("Would add " if preview else "Added ")
        + str(count)
        + " configured workspace(s). No containers or terminals changed."
    )
    candidates = [p for p in compose if not any(e["path"] == str(p) for e in entries)]
    if preview:
        for path in candidates:
            print("Compose candidate (not selected): " + str(path))
    elif candidates:
        try:
            answer = input(
                "Also review "
                + str(len(candidates))
                + " Compose-only directories to register? (y/N) "
            )
        except EOFError:
            answer = ""
        if answer.strip().lower() == "y":
            selected = choose_compose_directories(candidates, root)
            count = add_directories(selected)
            print(
                "Added "
                + str(count)
                + " selected Compose workspace(s). No containers or terminals changed."
            )
    else:
        print("No unregistered Compose-only directories found.")
    return 1 if failures else 0
