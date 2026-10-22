dwork-tray portable Windows host application

Keep this entire folder together, including _internal and dwork-tray-terminal.exe.
No Windows Python, pip, virtual environment, compiler, or installation is required.
The core dwork CLI and all workspace execution stay in WSL.

Extract the ZIP to a location of your choice. It may remain in your Linux home;
Windows can run it through \\wsl.localhost\Ubuntu\home\YOUR_USER\... .
From Windows PowerShell, run (substitute your matching Linux CLI interpreter):

  .\dwork-tray.exe --wsl-distribution Ubuntu --wsl-python /home/YOUR_USER/dwork-env/bin/python --check
  .\dwork-tray.exe --wsl-distribution Ubuntu --wsl-python /home/YOUR_USER/dwork-env/bin/python

Start the selected distribution deliberately before checking/launching the tray.
Optionally add --wsl-user USER; otherwise its configured default account is used.
Windows Terminal and Windows PowerShell are OS/application prerequisites.
Do not invoke dwork-tray-terminal.exe directly; the tray hands it validated actions.
The CLI inside WSL retains all confirmations, locking, and ownership checks.
Quit closes only the tray. Windows login startup is not implemented.

This experimental portable build is unsigned. Verify its SHA256SUMS.windows and
source revision against the CI/release you selected. Do not disable Windows
security protections to run an untrusted download.

Included licenses/ contains notices for the bundled runtime/dependencies.
See https://github.com/hayyaun/dwork/tree/main/docs/companion for usage and limits.
