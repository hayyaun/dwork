class Dwork < Formula
  include Language::Python::Virtualenv

  desc "Switch development workspaces and resume existing containers"
  homepage "https://github.com/hayyaun/dwork"
  url "https://github.com/hayyaun/dwork/archive/refs/tags/v0.3.0.tar.gz"
  sha256 "67fdb571b2350b998230c551e4b49091667ac1b857706d94de31d65c0226710c"
  license "MIT"
  head "https://github.com/hayyaun/dwork.git", branch: "main"

  depends_on "make" => :build
  depends_on "libyaml"
  depends_on "python@3.14"

  resource "pyyaml" do
    url "https://files.pythonhosted.org/packages/05/8e/961c0007c59b8dd7729d542c61a4d537767a59645b82a0b521206e1e25c2/pyyaml-6.0.3.tar.gz"
    sha256 "d76623373421df22fb4cf8817020cbb7ef15c725b9d5e45f17e189bfc384190f"
  end

  def install
    # Stable releases and HEAD use the shared Make installer.
    venv = virtualenv_create(libexec, "python3.14")
    venv.pip_install resource("pyyaml")
    system "gmake", "install", "VENV=0", "PREFIX=#{prefix}", "PYTHON=#{libexec}/bin/python",
           "BASH_COMPLETION_DIR=#{bash_completion}", "ZSH_COMPLETION_DIR=#{zsh_completion}"
    # Also supports tagged releases whose Make installer only provides sourceable scripts.
    bash_completion.mkpath
    cp pkgshare/"completions/dwork.bash", bash_completion/"dwork" unless (bash_completion/"dwork").exist?
    zsh_completion.mkpath
    unless (zsh_completion/"_dwork").exist?
      (zsh_completion/"_dwork").write <<~ZSH
        #compdef dwork
        source #{(pkgshare/"completions/_dwork").to_s.shellescape}
        _dwork "$@"
      ZSH
    end
  end

  def caveats
    <<~EOS
      Docker and Docker Compose are required for container workspaces.
      Terminal tasks use Apple Terminal on macOS,
      a supported Linux desktop terminal, or Windows Terminal from WSL2.
      Each terminal asks by default. Apple Terminal supports new windows only.
    EOS
  end

  test do
    assert_path_exists bash_completion/"dwork"
    assert_path_exists zsh_completion/"_dwork"
    assert_match "Usage: dwork", shell_output("#{bin}/dwork --help")
    (testpath/"dwork.yml").write <<~YAML
      version: 1
      compose:
        enabled: false
    YAML
    assert_match "No container changes needed", shell_output("#{bin}/dwork --dry-run")
  end
end
