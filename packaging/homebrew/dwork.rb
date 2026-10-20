class Dwork < Formula
  include Language::Python::Virtualenv

  desc "Switch development workspaces and resume existing containers"
  homepage "https://github.com/hayyaun/dwork"
  url "https://github.com/hayyaun/dwork/archive/refs/tags/v0.1.0.tar.gz"
  sha256 "31762d6eb3e57ba9637cc955af01c519c55ef9ac3c2320a6109c712ba47a36f0"
  license "MIT"

  depends_on "make" => :build
  depends_on :linux
  depends_on "libyaml"
  depends_on "python@3.14"

  resource "pyyaml" do
    url "https://files.pythonhosted.org/packages/05/8e/961c0007c59b8dd7729d542c61a4d537767a59645b82a0b521206e1e25c2/pyyaml-6.0.3.tar.gz"
    sha256 "d76623373421df22fb4cf8817020cbb7ef15c725b9d5e45f17e189bfc384190f"
  end

  def install
    # v0.1.0 predates Python package metadata; use its supported Make installer.
    venv = virtualenv_create(libexec, "python3.14")
    venv.pip_install resource("pyyaml")
    system "gmake", "install", "VENV=0", "PREFIX=#{prefix}", "PYTHON=#{libexec}/bin/python"
  end

  def caveats
    <<~EOS
      Docker and Docker Compose are required for container workspaces.
      Install a supported desktop terminal for Linux terminal tasks, or use
      Windows Terminal and PowerShell from WSL2. Each terminal asks by default.
    EOS
  end

  test do
    assert_match "Usage: dwork", shell_output("#{bin}/dwork --help")
    (testpath/"dwork.yml").write <<~YAML
      version: 1
      compose:
        enabled: false
    YAML
    assert_match "No container changes needed", shell_output("#{bin}/dwork --dry-run")
  end
end
