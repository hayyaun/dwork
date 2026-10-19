# got

[Project home](../../../README.md) · [Shell setup](../README.md)

Stage changes, commit, and push with one command.

Implementation: [`functions/got.sh`](../../../functions/got.sh).

## Requirements

- Bash or Zsh.
- Git, with your repository, commit identity, remote, and push destination already
  configured.

Follow the [shell setup instructions](../README.md#install) to load the function.

## Usage

Provide a required commit subject and an optional commit body:

```sh
got "Fix checkout validation"
got "Fix checkout validation" "Reject empty addresses before submitting the order."
```

With one argument, this runs:

```sh
git add .
git commit -m "Fix checkout validation"
git push
```

With two arguments, the commit step uses both:

```sh
git commit -m "Fix checkout validation" -m "Reject empty addresses before submitting the order."
```

Git makes the second message a separate paragraph in the commit message.
Quote each argument so spaces and shell metacharacters remain part of the message.

## Behavior

- Each command runs only if the previous command succeeds.
- Missing or empty subjects, or more than two arguments, produce usage information
  and exit with status 2 before running Git.
- `git add .` stages changes under the current directory, including deletions.
  Any changes already staged elsewhere in the repository are also included in
  the commit.
- If there is nothing to commit, Git returns an error and `got` does not push.
- `git push` uses your existing Git configuration. It does not set an upstream,
  force-push, or change remotes.
- A failed push leaves the successful local commit in place. Resolve the push
  issue and run `git push` yourself.
- Normal Git hooks and authentication prompts still apply.

Loading the function does not run Git; invoking it performs the three actions.
