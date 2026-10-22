#!/usr/bin/env bash
set -euo pipefail
pacman -Syu --noconfirm --needed git python python-yaml python-jsonschema bash-completion zsh namcap
useradd --create-home builder
cp -a /recipe /home/builder/package
chown -R builder:builder /home/builder/package
cd /home/builder/package
runuser -u builder -- makepkg --printsrcinfo > /recipe/.SRCINFO
runuser -u builder -- makepkg --force --cleanbuild --noconfirm
namcap PKGBUILD
package_candidates=$(runuser -u builder -- makepkg --packagelist)
package=
while IFS= read -r candidate; do
  test -f "$candidate" || continue
  test "$(pacman -Qpq "$candidate")" = dwork || continue
  test -z "$package"
  package=$candidate
done <<< "$package_candidates"
test -n "$package"
namcap "$package"
pacman -U --noconfirm "$package"
test -f /usr/share/bash-completion/completions/dwork
test -f /usr/share/zsh/site-functions/_dwork
runuser -u builder -- zsh -fc 'autoload -Uz compinit; compinit -D; [[ ${_comps[dwork]} == _dwork ]]'
/usr/bin/dwork --help
mkdir -p /tmp/dwork-smoke
printf 'version: 1\ncompose:\n  enabled: false\n' > /tmp/dwork-smoke/dwork.yml
cd /tmp/dwork-smoke
runuser -u builder -- /usr/bin/dwork --dry-run
pacman -Ql dwork
cp "$package" /recipe/
