/* Tab switching. Progressive enhancement:
 *   - Before this script runs, only the first panel is visible (hidden attr).
 *   - Clicking a tab shows its panel and hides the others.
 *   - Keyboard: ArrowLeft / ArrowRight navigates between tabs.
 *   - If JS is disabled, no-js CSS rule reveals every panel so content is
 *     still reachable.
 */
(function () {
  var buttons = document.querySelectorAll('[data-tab-target]');
  if (!buttons.length) return;

  function activate(slug) {
    buttons.forEach(function (btn) {
      var isTarget = btn.getAttribute('data-tab-target') === slug;
      btn.classList.toggle('is-active', isTarget);
      btn.setAttribute('aria-selected', isTarget ? 'true' : 'false');
    });
    var panels = document.querySelectorAll('[data-tab]');
    panels.forEach(function (panel) {
      if (panel.getAttribute('data-tab') === slug) {
        panel.removeAttribute('hidden');
      } else {
        panel.setAttribute('hidden', '');
      }
    });
  }

  buttons.forEach(function (btn, idx) {
    btn.addEventListener('click', function () {
      activate(btn.getAttribute('data-tab-target'));
    });
    btn.addEventListener('keydown', function (evt) {
      if (evt.key !== 'ArrowLeft' && evt.key !== 'ArrowRight') return;
      evt.preventDefault();
      var next = evt.key === 'ArrowLeft' ? idx - 1 : idx + 1;
      if (next < 0) next = buttons.length - 1;
      if (next >= buttons.length) next = 0;
      buttons[next].focus();
      activate(buttons[next].getAttribute('data-tab-target'));
    });
  });
})();
