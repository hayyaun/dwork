"""CLI routing, shell completion, diagnostics, and friendly exit handling."""

from pathlib import Path
import json
import sys

from dwork_common import DworkError, LAUNCHERS, color, colored_name
from dwork_version import __version__
import dwork_browsers
import dwork_config
import dwork_docker
import dwork_registry
import dwork_scan
import dwork_status
import dwork_terminals
import dwork_workspaces


COMMANDS = (
    "init",
    "validate",
    "register",
    "scan",
    "list",
    "switch",
    "rename",
    "forget",
    "lock",
    "unlock",
    "down",
    "status",
    "doctor",
    "completion",
)
ALIASES = {
    "reg": "register",
    "ls": "list",
    "sw": "switch",
    "rm": "forget",
    "up": "up",
    "ps": "status",
}


def completion_script(shell):
    """Generate portable shell integrations; dynamic names use the public names API."""
    commands = " ".join((*COMMANDS, *ALIASES))
    if shell == "bash":
        script = r"""# Bash completion for dwork. Source this file from ~/.bashrc.
_dwork_complete() {
    local cur="${COMP_WORDS[COMP_CWORD]}" prev="${COMP_WORDS[COMP_CWORD-1]}"
    local cmd="${COMP_WORDS[1]}" choices candidate
    COMPREPLY=()
    if (( COMP_CWORD == 1 )); then
        choices='@COMMANDS@ --help --version --dry-run'
    elif [[ "$prev" == -f || "$prev" == --file || "$prev" == --env-file ]]; then
        while IFS= read -r candidate; do COMPREPLY+=("$candidate"); done < <(compgen -f -- "$cur")
        return
    elif [[ "$prev" == --project-directory ]]; then
        while IFS= read -r candidate; do COMPREPLY+=("$candidate"); done < <(compgen -d -- "$cur")
        return
    elif [[ "$cmd" == lock || "$cmd" == unlock ]]; then
        if [[ "$cur" != -* ]]; then
            while IFS= read -r candidate; do
                [[ "$candidate" == "$cur"* ]] && COMPREPLY+=("$candidate")
            done < <(dwork list --names 2>/dev/null)
            return
        fi
        choices='--dry-run --help'
    elif [[ "$cmd" == switch || "$cmd" == sw || "$cmd" == forget || "$cmd" == rm || "$cmd" == rename ]]; then
        if (( COMP_CWORD == 2 )) && [[ "$cur" != -* ]]; then
            while IFS= read -r candidate; do
                [[ "$candidate" == "$cur"* ]] && COMPREPLY+=("$candidate")
            done < <(dwork list --names 2>/dev/null)
            return
        fi
        choices='--help'
        [[ "$cmd" == switch || "$cmd" == sw ]] && choices+=' --dry-run'
    elif [[ "$cmd" == completion ]] && (( COMP_CWORD == 2 )); then
        choices='bash zsh'
    else
        case "$cmd" in
            list|ls) choices='--names --json --help' ;;
            init|scan|down) choices='--dry-run --help' ;;
            completion) choices='--help' ;;
            status|ps) choices='--json --help -f --file -p --project-name --project-directory --env-file --profile' ;;
            validate|register|reg|doctor) choices='--help -f --file -p --project-name --project-directory --env-file --profile' ;;
            *) choices='--dry-run --help -f --file -p --project-name --project-directory --env-file --profile' ;;
        esac
    fi
    COMPREPLY=( $(compgen -W "$choices" -- "$cur") )
}
complete -o bashdefault -o default -F _dwork_complete dwork
"""
    elif shell == "zsh":
        script = r"""#compdef dwork
# Source this file after compinit in ~/.zshrc.
_dwork() {
    local cmd="${words[2]}" prev="${words[CURRENT-1]}"
    local -a names choices
    if (( CURRENT == 2 )); then
        choices=(@COMMANDS@ --help --version --dry-run)
    elif [[ "$prev" == -f || "$prev" == --file || "$prev" == --env-file ]]; then
        _files
        return
    elif [[ "$prev" == --project-directory ]]; then
        _files -/
        return
    elif [[ "$cmd" == lock || "$cmd" == unlock ]]; then
        if [[ "$PREFIX" != -* ]]; then
            names=("${(@f)$(dwork list --names 2>/dev/null)}")
            (( ${#names} )) && compadd -- "${names[@]}"
            return
        fi
        choices=(--dry-run --help)
    elif [[ "$cmd" == switch || "$cmd" == sw || "$cmd" == forget || "$cmd" == rm || "$cmd" == rename ]]; then
        if (( CURRENT == 3 )) && [[ "$PREFIX" != -* ]]; then
            names=("${(@f)$(dwork list --names 2>/dev/null)}")
            (( ${#names} )) && compadd -- "${names[@]}"
            return
        fi
        choices=(--help)
        [[ "$cmd" == switch || "$cmd" == sw ]] && choices+=(--dry-run)
    elif [[ "$cmd" == completion ]] && (( CURRENT == 3 )); then
        choices=(bash zsh)
    else
        case "$cmd" in
            list|ls) choices=(--names --json --help) ;;
            init|scan|down) choices=(--dry-run --help) ;;
            completion) choices=(--help) ;;
            status|ps) choices=(--json --help -f --file -p --project-name --project-directory --env-file --profile) ;;
            validate|register|reg|doctor) choices=(--help -f --file -p --project-name --project-directory --env-file --profile) ;;
            *) choices=(--dry-run --help -f --file -p --project-name --project-directory --env-file --profile) ;;
        esac
    fi
    compadd -- "${choices[@]}"
}
if (( $+functions[compdef] )); then
    compdef _dwork dwork
fi
"""
    else:
        raise DworkError("Usage: dwork completion bash|zsh")
    return script.replace("@COMMANDS@", commands)


def doctor(directory, options):
    failures = []

    def check(label, operation, hint):
        try:
            value = operation()
            print(color("OK: ", "start") + label)
            return value
        except (DworkError, OSError, ValueError, KeyError, TypeError) as error:
            failures.append(label)
            print(color("FAIL: " + label + ": " + str(error), "stop", sys.stderr), file=sys.stderr)
            print("  Fix: " + hint, file=sys.stderr)
            return None

    workspaces = check(
        "Workspace configuration and Compose compatibility",
        lambda: dwork_config.discover(directory, options)[0],
        "Check dwork.yml and Compose options; Compose must support config --no-interpolate --no-env-resolution --format json.",
    )
    if workspaces is None:
        print("Run dwork --dry-run after fixing configuration to inspect the switch plan.")
        return 1
    if any(w.enabled for w in workspaces):
        check(
            "Docker target",
            dwork_docker.show_target,
            "Install Docker CLI and check docker context show, DOCKER_CONTEXT, and DOCKER_HOST.",
        )
        containers = check(
            "Docker access and container inventory",
            dwork_docker.inventory,
            "Check docker info, daemon availability, and permissions for the selected Docker target.",
        )
        if containers is not None:
            dwork_docker.show_status(workspaces, containers)
            for workspace in workspaces:
                for task in workspace.terminals:
                    for service in task.healthy:
                        matches = dwork_docker.service_containers(
                            containers, workspace.name, service
                        )
                        if not matches or any(not c["State"].get("Health") for c in matches):
                            failures.append("health prerequisite")
                            print(
                                "FAIL: "
                                + workspace.name
                                + "/"
                                + service
                                + " requires existing containers with Docker health checks."
                                + " Complete project setup and configure healthcheck manually.",
                                file=sys.stderr,
                            )
    else:
        print("Docker checks skipped: Compose is disabled.")
    for workspace in workspaces:
        for task in workspace.terminals:
            check(
                "Shell, command, and terminal for " + task.title,
                lambda task=task: dwork_terminals.preflight_terminals([task]),
                "Check SHELL (Bash/Zsh), command PATH, graphical session, and configured launcher or DWORK_TERMINAL.",
            )
        for browser in workspace.browsers:
            check(
                "Browser opener for " + browser.url,
                lambda browser=browser: dwork_browsers.preflight_browsers([browser]),
                "Check the selected browser, graphical session, and xdg-open on Linux, or Windows PowerShell interop on WSL.",
            )
    print(
        "Doctor: "
        + (str(len(failures)) + " check(s) failed." if failures else "all checks passed.")
        + " No containers, terminals, or browser URLs changed."
    )
    return 1 if failures else 0


def main():
    options = list(sys.argv[1:])
    if "--version" in options:
        if options != ["--version"]:
            raise DworkError("Usage: dwork --version")
        print("dwork " + __version__)
        return 0
    command = options.pop(0) if options and options[0] in (*COMMANDS, *ALIASES) else "activate"
    mode = ALIASES.get(command, command)
    preview = bool(options and options[0] == "--dry-run")
    if preview:
        options = options[1:]
    if options and options[0] in ("--help", "-h"):
        print("Usage: dwork [--dry-run] [Docker Compose global options]")
        print("       dwork --version")
        print("       dwork init [--dry-run]")
        print("       dwork validate [Docker Compose global options]")
        print("       dwork register [NAME] [Docker Compose global options]")
        print("       dwork scan [--dry-run]")
        print("       dwork list | forget NAME")
        print("       dwork switch NAME [--dry-run]")
        print("       dwork rename NAME NEW_NAME")
        print("       dwork lock NAME... [--dry-run]")
        print("       dwork unlock NAME... [--dry-run]")
        print("       dwork down [--dry-run]")
        print("       dwork status | doctor [Docker Compose global options]")
        print("       dwork list --names | completion bash|zsh")
        print("       dwork list --json | status --json [Docker Compose global options]")
        print(
            "Aliases: ls=list, sw=switch, reg=register, rm=forget, up=current workspace, ps=status."
        )
        print("register: remember without switching; list: show remembered directories and status.")
        print("init: create a minimal local dwork.yml without overwriting; --dry-run previews it.")
        print(
            "validate: check configuration and Compose references without inspecting running workloads."
        )
        print(
            "scan: recursively register dwork.yml workspaces, then optionally select Compose-only directories."
        )
        print("switch: activate a remembered workspace; forget: remove only its registration.")
        print(
            "lock/unlock: add/remove local temporary protection until explicitly unlocked; preserve dwork.yml locks."
        )
        print(
            "down: stop registered containers on this Docker target and locally tracked commands; respect exclusions."
        )
        print(
            "status: read-only workspace/container state; doctor: read-only dependency diagnostics."
        )
        print("Read dwork.yml when present; otherwise use existing Compose containers.")
        print("With no default config, discover immediate child directories only.")
        print("Child-project switching requires confirmation (y/N).")
        print(
            "dwork and up confirm the plan (y/N); root confirm: false skips that activation prompt."
        )
        print(
            "Registration, group, task, and down confirmations are separate; --dry-run never prompts."
        )
        print(
            "Each terminal and browser URL asks (y/N) unless that task sets confirm: false in dwork.yml."
        )
        print(
            "Browser URLs use the default or configured browser; WSL uses Windows browsers. Set wait_for: false to skip readiness."
        )
        print(
            "Dry-run previews containers, health prerequisites, terminals, and browser URLs without mutation."
        )
        print("Only other registered workspaces on this Docker target may be stopped.")
        print(
            "Workspaces with locked: true or temporary CLI locks never stop during a switch or down."
        )
        print("Never creates, rebuilds, recreates, or removes containers.")
        print("DWORK_KEEP_PROJECTS: comma-separated projects to leave running.")
        print("DWORK_TERMINAL: " + ", ".join(LAUNCHERS) + ".")
        print("Color is automatic in terminals; NO_COLOR disables it. Pipes and logs stay plain.")
        return 0
    directory = Path.cwd()
    if mode in ("lock", "unlock"):
        if options[-1:] == ["--dry-run"] and not preview:
            preview, options = True, options[:-1]
        if not options or any(value.startswith("-") for value in options):
            raise DworkError("Usage: dwork " + mode + " NAME... [--dry-run]")
        if preview:
            return dwork_registry.set_temporary_locks(
                dwork_registry.read_registry(), options, mode == "lock", True
            )
        with dwork_registry.registry_lock():
            return dwork_registry.set_temporary_locks(
                dwork_registry.read_registry(), options, mode == "lock"
            )
    if mode == "init":
        if options:
            raise DworkError("Usage: dwork init [--dry-run]")
        return dwork_config.init_workspace(directory, preview)
    if mode == "validate":
        if preview:
            raise DworkError(
                "Usage: dwork validate [Docker Compose global options]; validation is already read-only."
            )
        workspaces, _ = dwork_config.discover(directory, options)
        for workspace in workspaces:
            print("Valid workspace configuration: " + str(workspace.directory))
        return 0
    if mode == "completion":
        if preview or len(options) != 1:
            raise DworkError("Usage: dwork completion bash|zsh")
        print(completion_script(options[0]), end="")
        return 0
    if mode == "doctor":
        return doctor(directory, options)
    if mode == "list":
        if options == ["--json"] and not preview:
            print(json.dumps(dwork_status.registered_snapshot(), ensure_ascii=True))
            return 0
        if options == ["--names"] and not preview:
            for entry in sorted(dwork_registry.read_registry(), key=lambda e: e["name"]):
                print(entry["name"])
            return 0
        if options or preview:
            raise DworkError("Usage: dwork list [--names | --json]")
        return dwork_registry.list_registrations(dwork_registry.read_registry())
    if mode == "status" and "--json" in options:
        if preview or options.count("--json") != 1:
            raise DworkError("Usage: dwork status --json [Docker Compose global options]")
        options.remove("--json")
        print(json.dumps(dwork_status.current_snapshot(directory, options), ensure_ascii=True))
        return 0
    if mode == "status":
        return dwork_workspaces.switch_workspace(directory, options, mode, preview, [])
    if mode == "rename":
        if preview or len(options) != 2 or any(value.startswith("-") for value in options):
            raise DworkError("Usage: dwork rename NAME NEW_NAME")
        name, new_name = options
        dwork_registry.validate_workspace_name(new_name)
        with dwork_registry.registry_lock():
            entries = dwork_registry.read_registry()
            entry = next((e for e in entries if e["name"] == name), None)
            if entry is None:
                raise DworkError("Unknown workspace: " + name + ". Run dwork list.")
            if any(e["name"] == new_name for e in entries):
                raise DworkError(
                    "Workspace name already registered: " + new_name + ". Choose an available name."
                )
            entry["name"] = new_name
            dwork_registry.save_registry(entries)
        print("Renamed " + colored_name(name) + " to " + colored_name(new_name) + ".")
        return 0
    if mode == "scan":
        if options:
            raise DworkError("Usage: dwork scan [--dry-run]")
        if preview:
            return dwork_scan.scan_workspaces(directory, dwork_registry.read_registry(), True)
        with dwork_registry.registry_lock():
            return dwork_scan.scan_workspaces(directory, dwork_registry.read_registry(), False)
    if mode == "down":
        if options:
            raise DworkError("Usage: dwork down [--dry-run]")
        if preview:
            return dwork_workspaces.down_workspaces(dwork_registry.read_registry(), True)
        with dwork_registry.registry_lock():
            return dwork_workspaces.down_workspaces(dwork_registry.read_registry(), False)
    name = None
    if mode in ("switch", "forget"):
        if not options or options[0].startswith("-"):
            raise DworkError(
                "Usage: dwork " + mode + " NAME" + (" [--dry-run]" if mode == "switch" else "")
            )
        name = options.pop(0)
        if mode == "switch" and options == ["--dry-run"]:
            preview, options = True, []
        if options or (mode == "forget" and preview):
            raise DworkError(
                "Usage: dwork " + mode + " NAME" + (" [--dry-run]" if mode == "switch" else "")
            )
    elif mode == "register":
        if preview:
            raise DworkError("Use dwork --dry-run to preview; register only saves a workspace.")
        if options and not options[0].startswith("-"):
            name = options.pop(0)
    if mode in ("activate", "up") and options and not options[0].startswith("-"):
        raise DworkError("Unknown command: " + options[0] + ". See dwork --help.")
    if preview:
        return dwork_workspaces.registry_command(
            directory, options, mode, preview, name, dwork_registry.read_registry()
        )
    with dwork_registry.registry_lock():
        return dwork_workspaces.registry_command(
            directory, options, mode, preview, name, dwork_registry.read_registry()
        )


def cli():
    """Shared console entry point for source and packaged installations."""
    try:
        return main()
    except (DworkError, OSError, ValueError, KeyError, TypeError) as error:
        print(color("dwork: " + str(error), "stop", sys.stderr), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\ndwork: cancelled.", file=sys.stderr)
        return 130
