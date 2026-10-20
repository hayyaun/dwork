# Introducing dwork

[Project home](../../README.md) · [Examples](../../examples/README.md)

## One-line introduction

Switch development projects with one command: resume existing Docker containers,
wait for healthy dependencies, and open the commands your workspace needs.

## Short caption

Switching projects usually means remembering which containers and terminals to
start. With **dwork**, describe that workspace once in `dwork.yml`, then run:

```sh
dwork --dry-run
dwork
```

Start the existing database container. Wait until it is healthy. Confirm each session, then open the backend
and frontend commands in their own terminals.

No config? dwork uses your existing Compose project.

Bash and Zsh function. Optional YAML configuration. Terminal launching supports native Linux desktops
and WSL2 + Windows Terminal. Containers must already be created.

Code and examples: [github.com/hayyaun/dwork](https://github.com/hayyaun/dwork)

## Suggested demonstration

1. Show a backend/database example config.
2. Run `dwork --dry-run` and explain the plan.
3. Invoke `dwork` and show the database becoming healthy before the backend opens.
4. Show the full-stack and host-only examples.

Use a prepared demo project. Keep credentials out of recordings. A demonstration
does not require showing private dotenv files.
