#!/usr/bin/env bash
set -euo pipefail
pacman -Syu --noconfirm --needed python python-yaml zsh namcap
useradd --create-home builder
cp -a /recipe /home/builder/package
chown -R builder:builder /home/builder/package
cd /home/builder/package
runuser -u builder -- makepkg --printsrcinfo > /recipe/.SRCINFO
runuser -u builder -- makepkg --cleanbuild --noconfirm
namcap PKGBUILD
namcap dwork-0.1.0-1-any.pkg.tar.zst
pacman -U --noconfirm dwork-0.1.0-1-any.pkg.tar.zst
/usr/bin/dwork --help
mkdir -p /tmp/dwork-smoke
printf 'version: 1\ncompose:\n  enabled: false\n' > /tmp/dwork-smoke/dwork.yml
cd /tmp/dwork-smoke
runuser -u builder -- /usr/bin/dwork --dry-run
pacman -Ql dwork
cp /home/builder/package/dwork-0.1.0-1-any.pkg.tar.zst /recipe/
