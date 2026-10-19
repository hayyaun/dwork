# Function modules

[Project home](../README.md) · [Shell setup](../docs/shell/README.md)

Each function lives in its own sourceable file. The repository entry point,
[`.shell_functions`](../.shell_functions), sources the modules using paths relative
to itself, so loading works from any working directory.

## Available modules

- [`dwork.sh`](dwork.sh): defines `dwork` for switching existing Docker Compose
  containers between projects. See the [dwork guide](../docs/shell/dwork/README.md)
  for requirements, examples, confirmation, and limits.

- [`got.sh`](got.sh): defines `got` to stage, commit, and push. See the
  [got guide](../docs/shell/got/README.md) for messages and failure behavior.

## Add a function

1. Create `functions/<name>.sh` containing the function definition.
2. Add an explicit sourcing entry inside the loading block in `.shell_functions`,
   using `"$_shellfunx_dir/functions/<name>.sh"`. Join entries with `&&` so a
   failure stops loading and returns a nonzero status.
3. Document the function in its own guide and link it from this index and the
   project README.
4. Verify loading and behavior in both Bash and Zsh.

Keep module loading free of task side effects: define functions at load time and
perform work when the user invokes them. Module files do not need executable
permissions.

Users only need to source `.shell_functions` in their shell startup files.
