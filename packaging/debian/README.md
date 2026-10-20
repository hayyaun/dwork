# Debian / Ubuntu

Debhelper source-package files live here. The build helper copies them into the
required top-level `debian/` directory in a temporary source tree; it does not
change the checkout or install packages on your host. Version 0.2.0-1 is prepared
for the next release; no apt repository or PPA is published by this build.

## Build

On Debian/Ubuntu, install build dependencies through your package manager:

```sh
sudo apt install build-essential debhelper python3 python3-yaml zsh lintian
python3 scripts/build-deb.py
lintian dist/debian/*.deb
```

The helper runs `dpkg-buildpackage -us -uc -b`; the tests run as part of the
build. The package uses system Python and PyYAML and downloads no pip dependencies.
Packages and build metadata are copied to `dist/debian/`. Build on each Debian or
Ubuntu release you plan to support; Ubuntu 24.04 is the initial validation target.

Inspect with `dpkg-deb --info` and `dpkg-deb --contents`. Install inside a test
system with `sudo apt install ./dist/debian/dwork_0.2.0-1_all.deb`, then run
`dwork --help` and a host-only dry-run. Remove with `sudo apt remove dwork`.
Use apt rather than make uninstall for package-managed installations.

## Publish

Attach the verified .deb and checksum to the matching GitHub release for direct
installation. For `apt install dwork` without a file path, maintain a signed apt
repository or publish source packages to an Ubuntu Launchpad PPA. A PPA requires
an account, signing key and separate source uploads for supported Ubuntu series;
it does not accept a binary .deb as the source submission.

Before public distribution, replace the GitHub noreply maintainer contact in
`control` and `changelog` with your preferred monitored public email. For a source
upload, create the original release tarball and run `dpkg-buildpackage -S` with
appropriate signing configuration in the prepared source tree. Follow Debian's
maintainer guide and Launchpad's PPA guide; this helper builds unsigned binaries.
