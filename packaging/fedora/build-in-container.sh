#!/usr/bin/env bash
# Run only inside the disposable Fedora container; /checkout is read-only.
set -euo pipefail
version=${1:?Usage: build-in-container.sh VERSION}
[[ $version =~ ^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$ ]]

dnf install -y --setopt=install_weak_deps=False \
  rpm-build redhat-rpm-config make python3-devel python3-pyyaml zsh docker-cli \
  tar gzip shadow-utils util-linux
useradd --create-home builder
install -d -o builder -g builder /home/builder/rpmbuild /home/builder/rpmbuild/SOURCES
install -m644 "/checkout/dist/source/dwork-$version.tar.gz" \
  /home/builder/rpmbuild/SOURCES/
runuser -u builder -- rpmbuild -bb /checkout/packaging/fedora/dwork.spec \
  --define '_topdir /home/builder/rpmbuild' --define "dwork_version $version"

packages=(/home/builder/rpmbuild/RPMS/noarch/dwork-"$version"-*.noarch.rpm)
[[ ${#packages[@]} -eq 1 && -f ${packages[0]} ]]
dnf install -y "${packages[0]}"
rpm -V dwork
runuser -u builder -- /usr/bin/dwork --help
workspace=$(mktemp -d)
chmod 755 "$workspace"
printf 'version: 1\ncompose:\n  enabled: false\n' > "$workspace/dwork.yml"
cd "$workspace"
runuser -u builder -- /usr/bin/dwork --dry-run
install -m644 "${packages[0]}" /output/
