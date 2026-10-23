# Landing website

[Project home](../../README.md) · [Documentation](../README.md) · [Site source](../../site/)

The landing page introduces dwork, its installation, and the scan/list/switch
workflow. Its source is in `site/`; the reference guides remain GitHub Markdown
under `docs/`. Adding the source and workflow does not publish a live website.

## Preview locally

The site is plain HTML, CSS, and JavaScript. It has no build step or package
dependencies. From the repository root, start a local server manually:

```sh
make serve
```

This runs `python3 -m http.server 8000 --directory site` by default;
use `make serve PYTHON=/path/to/python3` to select another interpreter.

Open [http://localhost:8000](http://localhost:8000). Stop the server with Ctrl+C.
Before publishing, check the page at desktop and mobile widths, keyboard navigation,
copy buttons, and links. Check that the content remains usable with JavaScript
disabled. JavaScript enhances clipboard copying and keyboard focus for code blocks;
the page content and navigation do not require it.

## Publish with GitHub Pages

The [Pages workflow](../../.github/workflows/pages.yml) uploads only `site/` and
deploys that artifact with GitHub's Pages actions. It does not build or publish
the repository's Markdown guides.

1. In the repository's **Settings → Pages**, set **Source** to **GitHub Actions**.
2. Push the site and workflow to `main`.
3. Check the **GitHub Pages** workflow run and its deployment result.

The workflow runs for pushes to `main` that change `site/` or the workflow itself.
It can also be started manually from the **Actions** tab, selecting `main`.
Other branches do not deploy. Enabling Pages, pushing, and publishing are separate
actions; they are not performed by a local preview.

After a successful deployment, the expected project URL is
[https://hayyaun.github.io/dwork/](https://hayyaun.github.io/dwork/).
Verify that deployment before adding the URL as a live website in project links.

## Maintain the page

Navigation arrows use decorative inline SVGs with `currentColor`, explicit sizing,
and `aria-hidden`. Keep them as vectors rather than Unicode arrow characters,
which some platforms render as emoji.

- [`site/index.html`](../../site/index.html): content, navigation, installation
  command, examples, and links to the GitHub reference guides.
- [`site/styles.css`](../../site/styles.css): colors, typography, responsive layout,
  focus states, and reduced-motion behavior.
- [`site/script.js`](../../site/script.js): clipboard copying and code focus
  enhancement only.
- [`site/logo.svg`](../../site/logo.svg): the original tray artwork reused for
  the app logo.
- [`site/favicon.svg`](../../site/favicon.svg): the same tray artwork with a
  transparent background.
- [`.github/workflows/pages.yml`](../../.github/workflows/pages.yml): deployment
  triggers, Pages permissions, and the uploaded directory.

The app logo comes from the companion's editable
[`tray.svg`](../../companion/src/dwork_tray/assets/tray.svg), copied unchanged to
`site/logo.svg`. Its two light perspective window frames are also used in the
favicon. The companion itself loads the exported
[`tray.png`](../../companion/src/dwork_tray/assets/tray.png); see the
[tray icon guide](../companion/README.md#tray-icon). Maintain the shared design at
the original SVG source and refresh the site's copies when it changes. This
artwork is part of the project under its [MIT license](../../LICENSE).

Keep the landing page aligned with the [README](../../README.md),
[installation guide](../installation/README.md), and
[workspace guide](../workspaces/README.md). The curl installer uses current `main`
source; tagged release packages may have fewer features. Keep those installation
paths distinct. Requirements include Git, Make, curl, Python with venv support
(3.10+ on Linux/WSL2; 3.13+ on macOS), and Docker/Compose for container workspaces.
Link detailed platform and terminal prerequisites rather than omitting them.

Keep the existing-container-only promise and the limits of registration, locks,
and confirmations clear. Avoid advertising an unpublished package channel or a
source-only configuration field as a released feature. Use relative paths for
site assets so the page works under GitHub Pages' `/dwork/` project path, and use
GitHub links for Markdown documentation.
