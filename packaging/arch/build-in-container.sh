#!/usr/bin/env bash
# Run only inside the disposable Arch base-devel container.
set -euo pipefail
version=${1:?Usage: build-in-container.sh VERSION}
[[ $version =~ ^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$ ]]

pacman -Syu --noconfirm --needed python python-yaml zsh docker
useradd --create-home builder
install -d -o builder -g builder /home/builder/package
install -m644 /checkout/packaging/arch/PKGBUILD \
  "/checkout/dist/source/dwork-$version.tar.gz" /home/builder/package/
chown builder:builder /home/builder/package/*
cd /home/builder/package
checksum=$(sha256sum "dwork-$version.tar.gz")
runuser -u builder -- env DWORK_VERSION="$version" \
  DWORK_SOURCE_SHA256="${checksum%% *}" makepkg --cleanbuild --noconfirm

packages=(dwork-"$version"-1-any.pkg.tar.zst)
[[ ${#packages[@]} -eq 1 && -f ${packages[0]} ]]
package_path="$PWD/${packages[0]}"
pacman -U --noconfirm "$package_path"
pacman -Qk dwork
runuser -u builder -- /usr/bin/dwork --help
workspace=$(mktemp -d)
chmod 755 "$workspace"
printf 'version: 1\ncompose:\n  enabled: false\n' > "$workspace/dwork.yml"
cd "$workspace"
runuser -u builder -- /usr/bin/dwork --dry-run
install -m644 "$package_path" /output/
