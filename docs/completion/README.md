# Shell completion

[Project home](../../README.md) · [Usage](../usage/README.md) · [Installation](../installation/README.md)

Completion is available for Bash and Zsh. It suggests commands, aliases, relevant
flags, registered workspace names after `switch`/`sw`, `forget`/`rm`, `rename`,
`lock`, and `unlock`, and file
or directory paths after Compose options such as `-f` and `--project-directory`.
This includes `--version`, `init --dry-run`, and Compose-selection flags for `validate`.
CLI 0.5.0+ completion scripts also suggest registered names for each
`up NAME...` / `down NAME...` argument and directories for each `scan PATH...`
root. These additions are currently available from source; release publication
is pending. Published v0.4.1 completion scripts do not include these new forms.

## Package and Make installations

Current Make installs generate native completion files as well as the existing
sourceable scripts. Package recipes select their platform's standard directories:

- Debian/Ubuntu: `/usr/share/bash-completion/completions/dwork` and
  `/usr/share/zsh/vendor-completions/_dwork`.
- Fedora/Arch: `/usr/share/bash-completion/completions/dwork` and
  `/usr/share/zsh/site-functions/_dwork`.
- Homebrew: its `bash_completion` directory (`etc/bash_completion.d/dwork`) and
  `zsh_completion` directory (`share/zsh/site-functions/_dwork`) under the formula
  prefix, linked by Homebrew into its shared prefix.
- Other Make installs: `PREFIX/share/bash-completion/completions/dwork` and
  `PREFIX/share/zsh/site-functions/_dwork`.

When the shell's completion framework already searches those directories, no
dwork-specific sourcing line is needed. Reopen the shell after installation.
Bash needs `bash-completion` installed and loaded; the default `~/.local` install
is discoverable through its usual user-data directory. Zsh needs the directory
in `fpath` before `compinit` runs. Oh My Zsh already calls `compinit`. With
Homebrew, run `brew shellenv` before Oh My Zsh/`compinit` so Homebrew's completion
directory is included. See [Homebrew's shell setup](https://docs.brew.sh/Shell-Completion).
Installation does not configure these shell-wide prerequisites or edit rc files.
If Zsh reports insecure completion directories, inspect them with `compaudit` and
review their ownership/permissions. Do not disable the audit. Noninteractive package
verification uses the documented `compinit -i -D` to exclude insecure entries and
checks that dwork remains available; it does not change shell configuration.

For package staging, Make accepts `BASH_COMPLETION_DIR` and `ZSH_COMPLETION_DIR`.
They are final absolute paths under `PREFIX`, without `DESTDIR`; the installer
applies staging itself. Supported directories are `share/bash-completion/completions`
or `etc/bash_completion.d` for Bash, and `share/zsh/site-functions` or
`share/zsh/vendor-completions` for Zsh. Debian's recipe explicitly chooses the
vendor directory. Custom prefixes and the default user prefix may need the
manual setup below, particularly for Zsh.

The native Zsh file is an autoload function body that sources the shared
completion definition and calls it on the first Tab request. The public
`dwork completion zsh` output remains sourceable. Make records ownership and
hashes for native files, refuses unrelated or modified files, and removes owned
files on uninstall without removing shared completion directories. Existing
sourceable paths remain available for users who already configured them.

These paths apply to new builds from this source. Previously published release
assets are unchanged and may still require explicit sourcing.

## Source-based installations

Sourcing the current `dwork.sh` automatically enables completion in an interactive
Bash shell. In an interactive Zsh shell, it does so when `compinit` has already
defined `compdef`. Keep the dwork sourcing line after Oh My Zsh or your existing
completion initialization. No additional `source <(dwork completion zsh)` line is
needed in that setup.

If dwork was sourced before `compinit`, source `dwork.sh` again afterward, or use
the explicit completion command below. dwork does not initialize `compinit` for
you. Re-sourcing is supported. Noninteractive shells define the command without
generating or registering completion. Interactive loading uses one Python
invocation; if Python or the runtime is unavailable, optional completion loading
is quietly skipped. Invoke `dwork completion bash|zsh` directly to diagnose a
generation error. The dwork command retains its normal error reporting.

This behavior is in the current source; older checkouts may still need manual
completion setup. Shell startup files are not edited by the loader.

## Manual setup: Python packages and custom prefixes

For Bash, including macOS system Bash 3.2, add this to `~/.bashrc`:

```sh
eval "$(dwork completion bash)"
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

The Make installer keeps sourceable scripts at
`PREFIX/share/dwork/completions/dwork.bash` and `PREFIX/share/dwork/completions/_dwork`.
It prints native paths and fallback source instructions with your actual prefix. These can
be sourced instead of generating a script during shell startup. Install/uninstall
never edits `.bashrc` or `.zshrc`; uninstall removes the owned scripts along with
the installation. Remove any corresponding startup line yourself when uninstalling.
The Zsh script is intended to be sourced after `compinit`.

Python package installations support the same `dwork completion bash|zsh` commands
but do not install native completion files. These commands also remain available
for older source checkouts and for explicitly reloading completion.

## Examples

```text
dwork <Tab>              commands and aliases
dwork sw<Tab>            switch or sw, according to your shell's matching rules
dwork switch <Tab>       registered workspace names
dwork sw my<Tab>         matching workspace names
dwork rm <Tab>           registered names to forget
dwork lock <Tab>         registered names to protect temporarily
dwork unlock api <Tab>   another registered name to unlock
dwork lock --d<Tab>      --dry-run
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
