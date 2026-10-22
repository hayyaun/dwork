# dwork AUR packaging

Prepared upstream version: [0.5.0](https://github.com/hayyaun/dwork/tree/v0.5.0).

This directory prepares the stable `dwork` AUR package. It has not been submitted.
AUR new-account registration was temporarily closed on 2026-10-20.

On Arch Linux, build as an ordinary user:

```sh
makepkg --printsrcinfo > .SRCINFO
makepkg -s
sudo pacman -U dwork-0.5.0-1-any.pkg.tar.zst
dwork --help
```

Inspect `PKGBUILD` and the generated package before installing. Never run makepkg
as root. The recipe uses distribution Python/YAML, downloads no pip dependencies,
and includes the MIT license in `/usr/share/licenses/dwork/LICENSE`.

The prepared recipe uses the checksum-verified v0.5.0 source archive and installs
native Bash/Zsh completion entries. Bash files go into
`/usr/share/bash-completion/completions`, and the Zsh autoload entry goes into
`/usr/share/zsh/site-functions`. Existing shell completion setup discovers them
without a dwork-specific rc line. Git is a check dependency for the local-repository
source tests; it is not a runtime dependency.

Once you have an AUR account, add your SSH public key in its settings, then clone
`ssh://aur@aur.archlinux.org/dwork.git` into a separate empty directory. Recheck
that the name is available. Copy only PKGBUILD and .SRCINFO into that checkout,
commit them, and push the master branch. Do not commit build artifacts or the
verification script. See https://wiki.archlinux.org/title/AUR_submission_guidelines.

`verify-in-arch.sh` is an optional disposable-container verification script:
run it only inside the official Arch base-devel Docker image. It installs build
and test dependencies in the container, builds as an ordinary user, generates
.SRCINFO, runs namcap, installs the package inside the container and smoke-tests
it. It is not intended to run on your host system.

## Submit when an account is available

1. Register at https://aur.archlinux.org/register and verify your email.
2. Add an SSH **public** key in your AUR account settings. Keep the private key
   on your machine. If you use a dedicated key, select it in your SSH client.
3. Recheck that no `dwork` package has appeared since preparation. If somebody
   has submitted the same project, coordinate with that maintainer instead.
4. Clone the AUR repository and copy the two submission files:

```sh
mkdir -p "$HOME/projects/aur"
cd "$HOME/projects/aur"
git -c init.defaultBranch=master clone ssh://aur@aur.archlinux.org/dwork.git
cd dwork
cp "$HOME/projects/foss/dwork/packaging/aur/PKGBUILD" .
cp "$HOME/projects/foss/dwork/packaging/aur/.SRCINFO" .
```

The source paths above match this developer's checkout; adjust them if yours
is elsewhere. On first SSH connection, compare the host fingerprint with the
fingerprints published at https://aur.archlinux.org/ before accepting it.

5. On Arch, rerun `makepkg -s` and review the contents. Regenerate `.SRCINFO`
   with `makepkg --printsrcinfo > .SRCINFO` whenever PKGBUILD changes.
6. Publish only the recipe and generated metadata:

```sh
git add PKGBUILD .SRCINFO
git commit -m "Add dwork 0.5.0"
git push origin master
```

7. Open https://aur.archlinux.org/packages/dwork and verify the version,
   maintainer, source, dependencies, and upstream link. Only then advertise
   `yay -S dwork` or `paru -S dwork` to users.

## Updating the package later

Create a new upstream release before changing the package version. Set `pkgver`
to that release (without `v`), reset `pkgrel=1`, download its archive and replace
the SHA-256 checksum. For recipe-only changes to the same upstream release,
increment `pkgrel` instead. Regenerate `.SRCINFO`, rebuild/test on Arch, then
commit and push PKGBUILD and .SRCINFO together.

To reproduce validation from this directory (Docker required):

```sh
docker run --rm --mount type=bind,source="$(pwd)",target=/recipe \
  archlinux:base-devel bash /recipe/verify-in-arch.sh
```

The script writes `.SRCINFO` and the built package into this directory. It uses
`makepkg --force` only inside its disposable container copy, allowing repeated
validation when a previous build artifact is present.

## Verification scope for this update

The prepared 0.5.0 recipe pins the verified immutable v0.5.0 tag archive. Its
`.SRCINFO` was generated with `makepkg --printsrcinfo` as an ordinary builder in
the official `archlinux:base-devel` container. Full recipe verification was
attempted, but normal pacman dependency downloads from `geo.mirror.pkgbuild.com`
timed out before source tests or a build could run. Current AUR build, lint,
installation, and smoke verification therefore remain pending; the previous
0.4.1 result below does not establish coverage for 0.5.0. GitHub v0.5.0 release
assets are published separately; AUR submission remains pending.

### Previous recipe verification (0.4.1)

The prepared 0.4.1 AUR recipe was verified on 2026-10-22 in the official
`archlinux:base-devel` container using the exact v0.4.1 tagged source archive.
Its SHA-256 was checked, and `.SRCINFO` was regenerated with
`makepkg --printsrcinfo` as an ordinary user and matched the prepared metadata.

`makepkg` ran all 409 source tests (6 skipped) and built `dwork-0.4.1-1-any.pkg.tar.zst`.
The updated verification helper selected that built package, ran namcap on the
recipe and package, and installed it with pacman inside the container. Bash/Zsh
completion entries, Zsh discovery, `dwork --help`, and a host-only `--dry-run`
outside the source tree all passed. The build, source tests, completion discovery,
and dry-run used the ordinary builder account; no package was installed on the host.

Namcap completed without errors but warned about the non-world-readable installer
ownership marker, references to the bundled private Python modules, and detection
of the launcher's `sh` dependency. These warnings remain recorded in the verification
log and were not suppressed. Installed help and dry-run checks passed with the
bundled modules. This validates the prepared AUR recipe; submission remains pending.
Native desktop GUI behavior still requires testing in a real desktop session.

## Validation recorded on 2026-10-20

Built release 0.1.0-1 using `makepkg` in the official `archlinux:base-devel`
container, with Python 3.14 and PyYAML 6.0.3. All 60 tests passed. The package
installed with pacman, `dwork --help` succeeded, and a host-only `--dry-run`
completed as an ordinary user. The source checksum and license locations were
verified. `.SRCINFO` was generated by makepkg from the final PKGBUILD.

Namcap reported no errors, but emitted two shell-detection warnings for the
launcher's `#!/bin/sh`: it could not identify `sh` as installed and also marked
its explicit dependency as possibly unused. The package declares the standard
`sh` dependency; pacman resolved it and the installed launcher ran successfully.
These warnings are recorded, not suppressed. Recheck them on your Arch system
before submission. Native desktop GUI behavior still needs real desktop testing;
automated terminal-adapter tests use fake launchers.
