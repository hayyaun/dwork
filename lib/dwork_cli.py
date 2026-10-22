"""CLI routing, shell completion, diagnostics, and friendly exit handling."""

from pathlib import Path
import json
import sys

from dwork_common import DworkError, LAUNCHERS, color, colored_name
from dwork_version import __version__
import dwork_browsers
import dwork_config
import dwork_docker
import dwork_groups
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
    "group",
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
    local cmd="${COMP_WORDS[1]}" choices candidate index compose_mode=0 named_mode=0 literal=0
    local group_mode=0 selector_available=1 group_action="" member_count=0 group_dry=0
    COMPREPLY=()
    if [[ "$cmd" == up || "$cmd" == down || "$cmd" == switch || "$cmd" == sw ]]; then
        for (( index=2; index<COMP_CWORD; index++ )); do
            case "${COMP_WORDS[index]}" in
                --dry-run) group_dry=1 ;;
                --group) group_mode=1 ;;
                *) [[ "$group_mode" == 0 ]] && selector_available=0 ;;
            esac
        done
    fi
    if [[ "$cmd" == scan ]]; then
        for (( index=2; index<COMP_CWORD; index++ )); do
            [[ "${COMP_WORDS[index]}" == -- ]] && literal=1
        done
    fi
    if (( COMP_CWORD == 1 )); then
        choices='@COMMANDS@ --help --version --dry-run'
    elif [[ "$group_mode" == 1 ]]; then
        if [[ "$prev" == --group && "$selector_available" == 1 ]]; then
            while IFS= read -r candidate; do
                [[ "$candidate" == "$cur"* ]] && COMPREPLY+=("$candidate")
            done < <(dwork group list --names 2>/dev/null)
            return
        fi
        choices='--help'
        [[ "$group_dry" == 0 ]] && choices+=' --dry-run'
    elif [[ "$cmd" == group ]]; then
        for (( index=2; index<COMP_CWORD; index++ )); do
            if [[ "${COMP_WORDS[index]}" == --dry-run ]]; then
                group_dry=1
                continue
            fi
            if [[ -z "$group_action" ]]; then
                group_action="${COMP_WORDS[index]}"
            elif [[ "${COMP_WORDS[index]}" != -* ]]; then
                member_count=$((member_count + 1))
            fi
        done
        if [[ -z "$group_action" ]]; then
            choices='create add remove delete --help'
            [[ "$group_dry" == 0 ]] && choices+=' list show --dry-run'
        else
            choices='--help'
            case "$group_action" in
                list) choices+=' --names' ;;
                create|add|remove|delete) [[ "$group_dry" == 0 ]] && choices+=' --dry-run' ;;
            esac
            if [[ "$cur" != -* ]]; then
                if (( member_count == 0 )) && [[ "$group_action" == show || "$group_action" == add || "$group_action" == remove || "$group_action" == delete ]]; then
                    while IFS= read -r candidate; do
                        [[ "$candidate" == "$cur"* ]] && COMPREPLY+=("$candidate")
                    done < <(dwork group list --names 2>/dev/null)
                elif (( member_count > 0 )) && [[ "$group_action" == create || "$group_action" == add || "$group_action" == remove ]]; then
                    while IFS= read -r candidate; do
                        [[ "$candidate" == "$cur"* ]] && COMPREPLY+=("$candidate")
                    done < <(dwork ls --names 2>/dev/null)
                fi
                return
            fi
        fi
    elif [[ "$literal" == 0 && ( "$prev" == -f || "$prev" == --file || "$prev" == --env-file ) ]]; then
        while IFS= read -r candidate; do COMPREPLY+=("$candidate"); done < <(compgen -f -- "$cur")
        return
    elif [[ "$literal" == 0 && "$prev" == --project-directory ]]; then
        while IFS= read -r candidate; do COMPREPLY+=("$candidate"); done < <(compgen -d -- "$cur")
        return
    elif [[ "$cmd" == scan ]]; then
        if [[ "$cur" != -* || "$literal" == 1 ]]; then
            while IFS= read -r candidate; do COMPREPLY+=("$candidate"); done < <(compgen -d -- "$cur")
            return
        fi
        choices='--dry-run --help'
    elif [[ "$cmd" == lock || "$cmd" == unlock || "$cmd" == up || "$cmd" == down ]]; then
        if [[ "$cmd" == up ]]; then
            for (( index=2; index<COMP_CWORD; index++ )); do
                [[ "${COMP_WORDS[index]}" == --dry-run ]] && continue
                if [[ "${COMP_WORDS[index]}" == -* && "${COMP_WORDS[index]}" != -- ]]; then
                    compose_mode=1
                else
                    named_mode=1
                fi
                break
            done
        fi
        if [[ "$cur" != -* && "$compose_mode" == 0 ]]; then
            while IFS= read -r candidate; do
                [[ "$candidate" == "$cur"* ]] && COMPREPLY+=("$candidate")
            done < <(dwork list --names 2>/dev/null)
            return
        fi
        choices='--dry-run --help'
        [[ ( "$cmd" == up || "$cmd" == down ) && "$selector_available" == 1 ]] && choices+=' --group'
        [[ "$cmd" == up && "$named_mode" == 0 ]] && choices+=' -f --file -p --project-name --project-directory --env-file --profile'
    elif [[ "$cmd" == switch || "$cmd" == sw || "$cmd" == forget || "$cmd" == rm || "$cmd" == rename ]]; then
        if [[ "$cur" != -* ]] && { (( COMP_CWORD == 2 )) || [[ ( "$cmd" == switch || "$cmd" == sw ) && "$selector_available" == 1 ]]; }; then
            while IFS= read -r candidate; do
                [[ "$candidate" == "$cur"* ]] && COMPREPLY+=("$candidate")
            done < <(dwork list --names 2>/dev/null)
            return
        fi
        choices='--help'
        [[ "$cmd" == switch || "$cmd" == sw ]] && choices+=' --dry-run'
        [[ ( "$cmd" == switch || "$cmd" == sw ) && "$selector_available" == 1 ]] && choices+=' --group'
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
    local cmd="${words[2]}" prev="${words[CURRENT-1]}" index compose_mode=0 named_mode=0 literal=0
    local group_mode=0 selector_available=1 group_action="" member_count=0 group_dry=0
    local -a names choices
    if [[ "$cmd" == up || "$cmd" == down || "$cmd" == switch || "$cmd" == sw ]]; then
        for (( index=3; index<CURRENT; index++ )); do
            case "${words[index]}" in
                --dry-run) group_dry=1 ;;
                --group) group_mode=1 ;;
                *) [[ "$group_mode" == 0 ]] && selector_available=0 ;;
            esac
        done
    fi
    if [[ "$cmd" == scan ]]; then
        for (( index=3; index<CURRENT; index++ )); do
            [[ "${words[index]}" == -- ]] && literal=1
        done
    fi
    if (( CURRENT == 2 )); then
        choices=(@COMMANDS@ --help --version --dry-run)
    elif [[ "$group_mode" == 1 ]]; then
        if [[ "$prev" == --group && "$selector_available" == 1 ]]; then
            names=("${(@f)$(dwork group list --names 2>/dev/null)}")
            (( ${#names} )) && compadd -- "${names[@]}"
            return
        fi
        choices=(--help)
        [[ "$group_dry" == 0 ]] && choices+=(--dry-run)
    elif [[ "$cmd" == group ]]; then
        for (( index=3; index<CURRENT; index++ )); do
            if [[ "${words[index]}" == --dry-run ]]; then
                group_dry=1
                continue
            fi
            if [[ -z "$group_action" ]]; then
                group_action="${words[index]}"
            elif [[ "${words[index]}" != -* ]]; then
                member_count=$((member_count + 1))
            fi
        done
        if [[ -z "$group_action" ]]; then
            choices=(create add remove delete --help)
            [[ "$group_dry" == 0 ]] && choices+=(list show --dry-run)
        else
            choices=(--help)
            case "$group_action" in
                list) choices+=(--names) ;;
                create|add|remove|delete) [[ "$group_dry" == 0 ]] && choices+=(--dry-run) ;;
            esac
            if [[ "$PREFIX" != -* ]]; then
                if (( member_count == 0 )) && [[ "$group_action" == show || "$group_action" == add || "$group_action" == remove || "$group_action" == delete ]]; then
                    names=("${(@f)$(dwork group list --names 2>/dev/null)}")
                    (( ${#names} )) && compadd -- "${names[@]}"
                elif (( member_count > 0 )) && [[ "$group_action" == create || "$group_action" == add || "$group_action" == remove ]]; then
                    names=("${(@f)$(dwork ls --names 2>/dev/null)}")
                    (( ${#names} )) && compadd -- "${names[@]}"
                fi
                return
            fi
        fi
    elif [[ "$literal" == 0 && ( "$prev" == -f || "$prev" == --file || "$prev" == --env-file ) ]]; then
        _files
        return
    elif [[ "$literal" == 0 && "$prev" == --project-directory ]]; then
        _files -/
        return
    elif [[ "$cmd" == scan ]]; then
        if [[ "$PREFIX" != -* || "$literal" == 1 ]]; then
            _files -/
            return
        fi
        choices=(--dry-run --help)
    elif [[ "$cmd" == lock || "$cmd" == unlock || "$cmd" == up || "$cmd" == down ]]; then
        if [[ "$cmd" == up ]]; then
            for (( index=3; index<CURRENT; index++ )); do
                [[ "${words[index]}" == --dry-run ]] && continue
                if [[ "${words[index]}" == -* && "${words[index]}" != -- ]]; then
                    compose_mode=1
                else
                    named_mode=1
                fi
                break
            done
        fi
        if [[ "$PREFIX" != -* && "$compose_mode" == 0 ]]; then
            names=("${(@f)$(dwork list --names 2>/dev/null)}")
            (( ${#names} )) && compadd -- "${names[@]}"
            return
        fi
        choices=(--dry-run --help)
        [[ ( "$cmd" == up || "$cmd" == down ) && "$selector_available" == 1 ]] && choices+=(--group)
        [[ "$cmd" == up && "$named_mode" == 0 ]] && choices+=(-f --file -p --project-name --project-directory --env-file --profile)
    elif [[ "$cmd" == switch || "$cmd" == sw || "$cmd" == forget || "$cmd" == rm || "$cmd" == rename ]]; then
        if [[ "$PREFIX" != -* ]] && { (( CURRENT == 3 )) || [[ ( "$cmd" == switch || "$cmd" == sw ) && "$selector_available" == 1 ]]; }; then
            names=("${(@f)$(dwork list --names 2>/dev/null)}")
            (( ${#names} )) && compadd -- "${names[@]}"
            return
        fi
        choices=(--help)
        [[ "$cmd" == switch || "$cmd" == sw ]] && choices+=(--dry-run)
        [[ ( "$cmd" == switch || "$cmd" == sw ) && "$selector_available" == 1 ]] && choices+=(--group)
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


def positional_arguments(options, preview, usage):
    """Parse selectors/roots without treating their values as Compose options."""
    values = []
    literal = False
    for value in options:
        if not literal and value == "--":
            literal = True
        elif not literal and value == "--dry-run":
            if preview:
                raise DworkError(usage)
            preview = True
        elif not literal and value.startswith("-"):
            raise DworkError(usage)
        else:
            values.append(value)
    return values, preview


def group_management(options, preview):
    """Validate the full management request before taking the mutation lock."""
    usage = "Usage: dwork group list [--names] | show NAME | create/add/remove NAME WORKSPACE... | delete NAME [--dry-run]"
    if options == ["list", "--names"] and not preview:
        for name in dwork_groups.group_names():
            print(name)
        return 0
    values, preview = positional_arguments(options, preview, usage)
    if not values:
        raise DworkError(usage)
    action, *arguments = values
    valid = (
        (action == "list" and not arguments)
        or (action in ("show", "delete") and len(arguments) == 1)
        or (action in ("create", "add", "remove") and len(arguments) >= 2)
    )
    if not valid or (preview and action in ("list", "show")):
        raise DworkError(usage)
    name = arguments[0] if arguments else None
    members = arguments[1:]

    def run():
        return dwork_groups.group_command(
            dwork_registry.read_registry(), action, name, members, preview
        )

    if preview or action in ("list", "show"):
        return run()
    with dwork_registry.registry_lock():
        return run()


def group_lifecycle(mode, options, preview):
    """An explicit group selector never changes the meaning of a bare name."""
    usage = "Usage: dwork " + mode + " --group NAME [--dry-run]"
    if options.count("--group") != 1 or "--" in options:
        raise DworkError(usage)
    index = options.index("--group")
    if index + 1 >= len(options) or options[index + 1].startswith("-"):
        raise DworkError(usage)
    name = options[index + 1]
    extra, preview = positional_arguments(options[:index] + options[index + 2 :], preview, usage)
    if extra:
        raise DworkError(usage)

    def run():
        entries = dwork_registry.read_registry()
        selected = dwork_groups.select_group(entries, name)
        names = [entry["name"] for entry in selected]
        print("Named group: " + colored_name(name) + " -> " + ", ".join(names))
        if mode == "up":
            return dwork_workspaces.up_registered_workspaces(entries, names, preview)
        if mode == "down":
            return dwork_workspaces.down_workspaces(entries, preview, names)
        return dwork_workspaces.switch_registered_group(entries, names, name, preview)

    if preview:
        return run()
    with dwork_registry.registry_lock():
        return run()


def main():
    options = list(sys.argv[1:])
    version_options = (
        options[: options.index("--")] if options[:1] == ["scan"] and "--" in options else options
    )
    if "--version" in version_options:
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
        print("       dwork scan [PATH...] [--dry-run]")
        print("       dwork list | forget NAME")
        print("       dwork switch NAME [--dry-run]")
        print("       dwork rename NAME NEW_NAME")
        print("       dwork lock NAME... [--dry-run]")
        print("       dwork unlock NAME... [--dry-run]")
        print("       dwork up [NAME...] [--dry-run]")
        print("       dwork down [NAME...] [--dry-run]")
        print("       dwork up|switch|down --group NAME [--dry-run]")
        print("       dwork group list [--names] | show NAME")
        print("       dwork group create|add|remove NAME WORKSPACE... [--dry-run]")
        print("       dwork group delete NAME [--dry-run]")
        print("       dwork status | doctor [Docker Compose global options]")
        print("       dwork list --names | completion bash|zsh")
        print("       dwork list --json | status --json [Docker Compose global options]")
        print(
            "Aliases: ls=list, sw=switch, reg=register, rm=forget, up=current workspace or start named workspaces, ps=status."
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
        print("up NAME...: start named registered workspaces together; leave all others running.")
        print(
            "group: save reusable local selections of registered workspaces; editing never launches workloads."
        )
        print(
            "switch --group: switch once to every member; down --group also stops shared eligible members."
        )
        print(
            "down NAME...: stop only the named registrations; no names keeps the existing all-workspace scope."
        )
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
    if mode == "group":
        return group_management(options, preview)
    if mode in ("up", "switch", "down") and "--group" in options:
        return group_lifecycle(mode, options, preview)
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
        paths, preview = positional_arguments(
            options, preview, "Usage: dwork scan [PATH...] [--dry-run]"
        )
        roots = list(dict.fromkeys(Path(path).expanduser().resolve() for path in paths))
        roots = roots or [directory]
        for root in roots:
            if not root.is_dir():
                raise DworkError(
                    "Scan root is not an available directory: " + str(root) + "; nothing changed."
                )

        def scan():
            entries = dwork_registry.read_registry()
            result = 0
            for root in roots:
                result = dwork_scan.scan_workspaces(root, entries, preview) or result
            return result

        if preview:
            return scan()
        with dwork_registry.registry_lock():
            return scan()
    if mode == "down":
        names, preview = positional_arguments(
            options, preview, "Usage: dwork down [NAME...] [--dry-run]"
        )
        if preview:
            return dwork_workspaces.down_workspaces(dwork_registry.read_registry(), True, names)
        with dwork_registry.registry_lock():
            return dwork_workspaces.down_workspaces(dwork_registry.read_registry(), False, names)
    if mode == "up" and options and (not options[0].startswith("-") or options[0] == "--"):
        names, preview = positional_arguments(
            options, preview, "Usage: dwork up [NAME...] [--dry-run]"
        )
        if not names:
            raise DworkError("Usage: dwork up [NAME...] [--dry-run]")
        if preview:
            return dwork_workspaces.up_registered_workspaces(
                dwork_registry.read_registry(), names, True
            )
        with dwork_registry.registry_lock():
            return dwork_workspaces.up_registered_workspaces(
                dwork_registry.read_registry(), names, False
            )
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
