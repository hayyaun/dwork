# dwork AUR packaging

Upstream release: https://github.com/hayyaun/dwork/releases/tag/v0.1.0

This directory prepares the stable `dwork` AUR package. It has not been submitted.
AUR new-account registration was temporarily closed on 2026-10-20.

On Arch Linux, build as an ordinary user:

```sh
makepkg --printsrcinfo > .SRCINFO
makepkg -s
sudo pacman -U dwork-0.1.0-1-any.pkg.tar.zst
dwork --help
```

Inspect `PKGBUILD` and the generated package before installing. Never run makepkg
as root. The recipe uses distribution Python/YAML, downloads no pip dependencies,
and includes the MIT license in `/usr/share/licenses/dwork/LICENSE`.

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
