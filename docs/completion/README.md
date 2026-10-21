# Shell completion

[Project home](../../README.md) · [Usage](../usage/README.md) · [Installation](../installation/README.md)

Completion is available for Bash and Zsh. It suggests commands, aliases, relevant
flags, registered workspace names after `switch`/`sw`, `forget`/`rm`, and `rename`, and file
or directory paths after Compose options such as `-f` and `--project-directory`.
This includes `--version`, `init --dry-run`, and Compose-selection flags for `validate`.

## Enable it

For Bash, add this to `~/.bashrc`:

```sh
source <(dwork completion bash)
```

For Zsh, add this to `~/.zshrc` after your existing `compinit` setup:

```sh
source <(dwork completion zsh)
```

If you have no Zsh completion setup yet, initialize it first:

```sh
autoload -Uz compinit
compinit
source <(dwork completion zsh)
```

Do not duplicate an existing `compinit` call provided by your shell configuration
or framework. Reopen the shell, or run the appropriate `source <(...)` line in the
current shell after initialization. The `dwork` command must be on PATH or available
as the sourced dwork function before these lines run.

The Make installer also generates owned scripts at
`PREFIX/share/dwork/completions/dwork.bash` and `PREFIX/share/dwork/completions/_dwork`.
It prints shell-specific source instructions, with your actual prefix. These can
be sourced instead of generating a script during shell startup. Install/uninstall
never edits `.bashrc` or `.zshrc`; uninstall removes the owned scripts along with
the installation. Remove any corresponding startup line yourself when uninstalling.
The Zsh script is intended to be sourced after `compinit`.

Python package installations support the same `dwork completion bash|zsh` commands
without needing the Make-generated scripts.

## Examples

```text
dwork <Tab>              commands and aliases
dwork sw<Tab>            switch or sw, according to your shell's matching rules
dwork switch <Tab>       registered workspace names
dwork sw my<Tab>         matching workspace names
dwork rm <Tab>           registered names to forget
dwork scan --d<Tab>      --dry-run
dwork -f <Tab>           file paths
```

Shell settings determine whether one Tab completes immediately or another Tab
shows multiple matches. Names are queried each time, so registrations, scans, and
forget operations are reflected without regenerating the script.

## Names-only API

```sh
dwork list --names
dwork ls --names
```

Outputs sorted registered names, one per line, without colors or status text.
It only reads the registry: no Docker calls, project-config reads, lock refresh,
directory scans, prompts, or state writes. Locked and unavailable registered names
are included. Completion suppresses registry errors rather than interrupting shell
input; run `dwork list --names` manually to inspect an error.

References: [Bash programmable completion](https://www.gnu.org/s/bash/manual/html_node/Programmable-Completion.html),
[Zsh completion system](https://zsh.sourceforge.io/Doc/Release/Completion-System.html).
