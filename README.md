# shellfunx

Reusable shell functions for Bash and Zsh. Each function adds a focused command
for everyday development tasks.

## Quick start

Clone the repository somewhere permanent:

```sh
git clone https://github.com/hayyaun/shellfunx.git "$HOME/projects/foss/shellfunx"
```

Add this line to `~/.bashrc` for Bash and/or `~/.zshrc` for Zsh:

```sh
[ -r "$HOME/projects/foss/shellfunx/.shell_functions" ] && . "$HOME/projects/foss/shellfunx/.shell_functions"
```

Adjust the path if you cloned elsewhere. Open a new terminal, or load it now:

```sh
. "$HOME/projects/foss/shellfunx/.shell_functions"
```

Each function lives in its own file under [`functions/`](functions/README.md).
[`.shell_functions`](.shell_functions) loads the function modules for both shells.

## Documentation

- [Shell functions](docs/shell/README.md): setup, how sourcing works, updates,
  and removal.
- [dwork](docs/shell/dwork/README.md): switch existing Docker Compose containers
  between projects, with previews, options, shared-project exclusions, and limits.

When no default Compose config exists, `dwork` can discover projects in immediate
subdirectories and ask for confirmation before switching them together.

`dwork` stops other Compose projects and starts only existing stopped containers
for the current project. It warns about missing containers; it never creates them.
