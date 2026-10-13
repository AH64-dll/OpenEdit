/* Optional clipboard enhancement; the page and media work without JavaScript. */
(() => {
  const status = document.getElementById('copy-status');
  let clearStatus;
  document.querySelectorAll('[data-copy]').forEach(button => {
    button.hidden = false;
    button.addEventListener('click', async () => {
      const code = document.getElementById(button.dataset.copy);
      if (!code) return;
      try {
        await navigator.clipboard.writeText(code.textContent.trim());
        status.textContent = 'Commands copied.';
      } catch {
        const selection = window.getSelection();
        const range = document.createRange();
        range.selectNodeContents(code);
        selection.removeAllRanges();
        selection.addRange(range);
        status.textContent = 'Commands selected. Use your browser’s Copy command.';
      }
      clearTimeout(clearStatus);
      clearStatus = setTimeout(() => { status.textContent = ''; }, 4000);
    });
  });
})();
