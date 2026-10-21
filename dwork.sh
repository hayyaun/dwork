# Switch development workspaces. Source this module; invoke dwork to do work.
# Capture the location while sourcing: a relative BASH_SOURCE/%x must not be
# reinterpreted after the caller changes directories. Use shell builtins only.
if [ -n "${BASH_VERSION:-}" ]; then
    _DWORK_SOURCE_DIRECTORY="${BASH_SOURCE[0]}"
elif [ -n "${ZSH_VERSION:-}" ]; then
    _DWORK_SOURCE_DIRECTORY="${(%):-%x}"
fi
case "${_DWORK_SOURCE_DIRECTORY:-}" in
    */*) _DWORK_SOURCE_DIRECTORY="${_DWORK_SOURCE_DIRECTORY%/*}/" ;;
    *) _DWORK_SOURCE_DIRECTORY=. ;;
esac
_DWORK_SOURCE_DIRECTORY=$(CDPATH= cd -- "$_DWORK_SOURCE_DIRECTORY" && pwd -P) || return

dwork() (
    command -v python3 >/dev/null 2>&1 || {
        printf "%s\n" "dwork: python3 is required." >&2
        return 1
    }
    if [ -z "${BASH_VERSION:-}${ZSH_VERSION:-}" ]; then
        printf "%s\n" "dwork: Bash or Zsh is required." >&2
        return 1
    fi
    python3 "$_DWORK_SOURCE_DIRECTORY/lib/dwork.py" "$@"
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
