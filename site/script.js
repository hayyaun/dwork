// Copy controls are an enhancement; the commands remain selectable without JS.
if (window.isSecureContext && navigator.clipboard?.writeText) {
  const status = document.getElementById("copy-status");
  document.querySelectorAll("[data-copy]").forEach((button) => {
    const target = document.getElementById(button.dataset.copy);
    if (!target) return;
    button.hidden = false;
    let resetTimer;
    button.addEventListener("click", async () => {
      clearTimeout(resetTimer);
      try {
        await navigator.clipboard.writeText(target.textContent);
        button.textContent = "Copied!";
        status.textContent = "Copied to clipboard.";
      } catch {
        button.textContent = "Select text";
        status.textContent = "Clipboard access is unavailable. Select the command text to copy it.";
      }
      resetTimer = setTimeout(() => {
        button.textContent = "Copy";
        status.textContent = "";
      }, 3000);
    });
  });
}

// Scrollable code samples can also be reached with the keyboard when they overflow.
function updateCodeFocus() {
  document.querySelectorAll("pre").forEach((block) => {
    if (block.scrollWidth > block.clientWidth) {
      block.tabIndex = 0;
      block.setAttribute("aria-label", "Code sample; scroll horizontally to read more");
    } else {
      block.removeAttribute("tabindex");
      block.removeAttribute("aria-label");
    }
  });
}
updateCodeFocus();
window.addEventListener("resize", updateCodeFocus);
