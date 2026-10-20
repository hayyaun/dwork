# Switch development workspaces. Source this module; invoke dwork to do work.
dwork() (
    command -v python3 >/dev/null 2>&1 || {
        printf "%s\n" "dwork: python3 is required." >&2
        return 1
    }
    if [ -n "${BASH_VERSION:-}" ]; then
        _dwork_file="${BASH_SOURCE[0]}"
    elif [ -n "${ZSH_VERSION:-}" ]; then
        _dwork_file="${(%):-%x}"
    else
        printf "%s\n" "dwork: Bash or Zsh is required." >&2
        return 1
    fi
    _dwork_dir=$(CDPATH= cd -- "$(dirname -- "$_dwork_file")" && pwd -P) || return
    python3 "$_dwork_dir/lib/dwork.py" "$@"
)
