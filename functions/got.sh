# Stage changes, commit with a required subject and optional body, then push.
# Usage: got "Commit subject" ["Commit body"]
got() {
    if [ "$#" -lt 1 ] || [ "$#" -gt 2 ] || [ -z "${1:-}" ]; then
        printf "%s\n" "Usage: got \"Commit subject\" [\"Commit body\"]" >&2
        return 2
    fi

    git add . || return
    if [ "$#" -eq 2 ]; then
        git commit -m "$1" -m "$2" || return
    else
        git commit -m "$1" || return
    fi
    git push
}
