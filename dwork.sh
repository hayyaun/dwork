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

# Enable completion in interactive source-based setups. Zsh's completion system
# must already be initialized (for example, by Oh My Zsh). Keep loading optional
# so a missing interpreter/runtime cannot break shell startup.
case $- in
    *i*)
        if command -v python3 >/dev/null 2>&1; then
            if [ -n "${BASH_VERSION:-}" ]; then
                . <(dwork completion bash 2>/dev/null)
            elif [ -n "${ZSH_VERSION:-}" ] && (( $+functions[compdef] )); then
                . <(dwork completion zsh 2>/dev/null)
            fi
        fi
        ;;
esac
