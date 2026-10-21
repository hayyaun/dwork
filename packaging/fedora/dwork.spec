# The release build supplies dwork_version from the validated version tag.
Name:           dwork
Version:        %{dwork_version}
Release:        1%{?dist}
Summary:        Switch development workspaces and resume existing containers
License:        MIT
URL:            https://github.com/hayyaun/dwork
Source0:        dwork-%{version}.tar.gz
BuildArch:      noarch
BuildRequires:  make
BuildRequires:  python3-devel >= 3.10
BuildRequires:  python3-pyyaml
BuildRequires:  zsh
BuildRequires:  docker-cli
Requires:       python3 >= 3.10
Requires:       python3-pyyaml

%description
Resume existing Docker Compose containers, stop other projects, wait for
healthy dependencies, and confirm before launching configured terminals.
Supports Linux desktops and WSL2. Containers are never created or rebuilt.

%prep
%setup -q

%build
# Interpreted application; the staged installer downloads no dependencies.

%install
%make_install VENV=0 PREFIX=%{_prefix} PYTHON=%{__python3}

%check
%make_build test PYTHON=%{__python3}

%files
%license LICENSE
%doc README.md
%{_bindir}/dwork
%{_datadir}/dwork/
