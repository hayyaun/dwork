# Introducing dwork

[Project home](../../README.md) · [Examples](../../examples/README.md)

## Social preview image

Use [github-social-card-v2.png](../assets/github-social-card-v2.png) for the repository's
social preview. The opaque PNG is 1280 × 640 pixels and 729,086 bytes, below GitHub's
1 MB limit, with generous margins around the title and supporting copy.

Upload it in the repository's **Settings → General → Social preview → Edit →
Upload an image**. See [GitHub's social preview guide](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/customizing-your-repositorys-social-media-preview)
for supported formats and sizing.

The card uses the existing README hero's dark terminal artwork and green accents.
Small OS logos sit beside the platform names, and the project's
[tray glyph](../../companion/src/dwork_tray/assets/tray.png) appears discreetly
beside the repository URL.
It was created with the built-in image generator and exported to the upload size.
The [generation and refinement prompts](../assets/github-social-card-prompt.md)
record the exact copy, visual references, and crop constraints.

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

The [Get started section](../../README.md#get-started) includes a 42-second video
demo, hosted as a GitHub attachment for inline playback in the README.

1. Show a backend/database example config.
2. Run `dwork --dry-run` and explain the plan.
3. Invoke `dwork` and show the database becoming healthy before the backend opens.
4. Show the full-stack and host-only examples.

Use a prepared demo project. Keep credentials out of recordings. A demonstration
does not require showing private dotenv files.
