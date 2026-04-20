/* Sidebar drawer toggle for narrow viewports.
 *
 * PR-2 QA Issue F:
 *   - Hamburger opens the drawer (transform: translateX).
 *   - A dim backdrop intercepts taps on the main area; tapping it closes.
 *   - The ✕ button inside the drawer closes it.
 *   - ESC closes the drawer while it is open.
 *   - Desktop (≥768px) keeps the sidebar fixed and renders neither
 *     backdrop nor close button (see responsive.css).
 */
(function () {
  var hamburger = document.querySelector('.mb-hamburger');
  var sidebar = document.getElementById('mb-sidebar');
  var backdrop = document.querySelector('.mb-backdrop');
  var closeBtn = sidebar ? sidebar.querySelector('.mb-sidebar-close') : null;
  if (!hamburger || !sidebar) return;

  var mobileMedia = window.matchMedia('(max-width: 768px)');

  function isMobile() {
    return mobileMedia.matches;
  }

  function openDrawer() {
    sidebar.classList.add('is-open');
    hamburger.setAttribute('aria-expanded', 'true');
    if (backdrop && isMobile()) {
      backdrop.hidden = false;
    }
  }

  function closeDrawer() {
    sidebar.classList.remove('is-open');
    hamburger.setAttribute('aria-expanded', 'false');
    if (backdrop) {
      backdrop.hidden = true;
    }
  }

  hamburger.addEventListener('click', function () {
    if (sidebar.classList.contains('is-open')) {
      closeDrawer();
    } else {
      openDrawer();
    }
  });

  if (closeBtn) {
    closeBtn.addEventListener('click', closeDrawer);
  }

  if (backdrop) {
    backdrop.addEventListener('click', closeDrawer);
  }

  document.addEventListener('keydown', function (evt) {
    if (evt.key === 'Escape' && sidebar.classList.contains('is-open')) {
      closeDrawer();
    }
  });

  // Close drawer when a date link is clicked on narrow viewports.
  sidebar.addEventListener('click', function (evt) {
    if (evt.target.tagName === 'A' && isMobile()) {
      closeDrawer();
    }
  });

  // If the viewport grows past the mobile breakpoint while the drawer is
  // open, ensure the backdrop is cleaned up and state stays coherent.
  if (mobileMedia.addEventListener) {
    mobileMedia.addEventListener('change', function (evt) {
      if (!evt.matches && backdrop) {
        backdrop.hidden = true;
      }
    });
  }
})();
