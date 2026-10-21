# Agent skill

[Project home](../../README.md) · [Install dwork](../installation/README.md) ·
[Configuration](../configuration/README.md)

Install the **dwork** skill so your coding agent can inspect your project's
Compose services and development commands, then create or update `dwork.yml`
with terminal/background tasks and optional browser pages that wait for HTTP
readiness. It accounts for macOS Apple Terminal, Linux desktops, and WSL's
Windows terminal/browser routing.
The skill includes configuration rules and examples; your agent does not need
to work inside the dwork source repository or download its docs on each use.

Installing the skill and installing the `dwork` command are separate steps.
Install the command using the [normal installation](../installation/README.md)
to preview and run the generated configuration.

## Install for your agents

With Node.js 22.20 or newer and npm/npx, run:

```sh
npx skills add hayyaun/dwork --skill dwork -g
```

The [open skills CLI](https://github.com/vercel-labs/skills) lets you choose your
agents, including Codex, Claude Code, Cursor, GitHub Copilot, Gemini CLI,
OpenCode, and its [other supported agents](https://github.com/vercel-labs/skills/blob/main/docs/agents.md).
`-g` installs for your user across projects. Omit it and run the command in your
own project to install a project-scoped skill you can share with teammates.

To target **all agents supported by that installer**, use:

```sh
npx skills add hayyaun/dwork --skill dwork -g --agent '*'
```

To target only Codex, Claude Code, and Cursor:

```sh
npx skills add hayyaun/dwork --skill dwork -g -a codex claude-code cursor
```

The quoted `'*'` is literal, not a shell wildcard. These commands install agent
instructions, not the dwork executable. Use the installer's `--copy` option if
you prefer independent copies over symlinks. Support depends on the agent's
version and skill capabilities; this is not a promise that every AI product
can load skills.

### From a local checkout

To install from a clone, including changes not yet published to GitHub, run
this from the dwork repository root:

```sh
npx skills add ./skills/dwork --skill dwork -g
```

You can add `--agent '*'` here as well. The GitHub commands above become
available after the skill files are published in the repository.

## Manual installation without Node.js

Copy the complete [`skills/dwork/`](../../skills/dwork/) directory, including
`references/`, into your agent's supported skills location. For example:

- **Codex:** `~/.agents/skills/dwork/` for your user, or
  `<your-project>/.agents/skills/dwork/` for one project.
- **Claude Code:** `~/.claude/skills/dwork/` or
  `<your-project>/.claude/skills/dwork/`.
- **Cursor:** `~/.cursor/skills/dwork/` or
  `<your-project>/.cursor/skills/dwork/`.
- **Other agents:** use the agent's documented Agent Skills directory or import
  UI. The installed directory must contain `SKILL.md` and its `references/`
  together. Use the CLI's supported-agent list for known installation paths.

If a dwork skill already exists there, review it before replacing it; preserve
local customizations. Avoid installing multiple copies visible to the same
agent. Install in the environment where the agent runs (for example, inside WSL
for an agent running in WSL). Local user skills do not automatically reach
remote or cloud agents; use their supported sync or project-skill mechanism.

Codex users with `$skill-installer` can also ask it:

```text
Install the dwork skill from https://github.com/hayyaun/dwork/tree/main/skills/dwork
```

Agent-specific documentation:
[Codex](https://learn.chatgpt.com/docs/build-skills),
[Claude Code](https://code.claude.com/docs/en/skills),
[Cursor](https://cursor.com/help/customization/skills).

## Use it in your project

Open your own project in your agent and ask:

```text
Use the dwork skill to inspect this project and create dwork.yml for its
development workflow. Use its existing commands and Compose services.
```

You can explicitly select `$dwork` in Codex or invoke `/dwork` in Claude Code.
For other agents, use their skill picker or mention the skill by name. If a
newly installed skill is missing, start a new session or reload the agent as
its documentation recommends.

The agent checks commands, directories, services, health prerequisites, and any
requested browser URLs. When dwork is available, it runs `dwork --dry-run` and
reports missing prerequisites
instead of installing dependencies or starting the workspace. Review its YAML
and dry-run warnings, then run `dwork` yourself when ready. A normal invocation
asks before registering a new directory and can stop other registered workspaces
on the same Docker target before asking about terminal launches. Browser entries
ask separately after terminal tasks dispatch. Unregistered projects stay running;
use `DWORK_KEEP_PROJECTS` or `locked: true` for workspaces you want to keep running.

The skill also considers whether `dwork.yml` is personal workspace configuration.
It suggests ignoring personal configs with a scoped `.gitignore` entry and asks
before changing ignore rules unless that change was already authorized. Shared
team configs and tracked examples stay tracked. `.git/info/exclude` is an option
for an ignore preference local to one clone; adding an ignore rule never untracks
an existing file.

Use a runtime containing these features: macOS tracked tasks need Python 3.13+
(Linux/WSL need 3.10+). Older dwork releases may reject newer fields; update the
runtime rather than bypassing schema validation. See the
[Homebrew version notes](../../packaging/homebrew/README.md) for stable versus HEAD.

## Update or remove

For CLI installations, use `npx skills check` to check for updates,
`npx skills update dwork` to update, or `npx skills remove dwork -g` to remove a
user installation (omit `-g` for project installations). Follow its scope/agent
prompts. For manual installations, replace the complete skill folder after
reviewing local changes, or remove that folder to uninstall. These actions do
not remove dwork or any project's `dwork.yml`.
