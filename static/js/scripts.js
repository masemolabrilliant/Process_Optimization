(function () {
  var body = document.body;
  var sidebarToggle = document.getElementById('sidebarToggle');     // hamburger
  var sidebarCollapse = document.getElementById('sidebarCollapse'); // desktop collapse
  var sidebarDock = document.getElementById('sidebarDock');         // left/right dock
  var backdrop = document.querySelector('.sidebar-backdrop');

  // Mobile open/close (adds/removes .sidebar-open)
  if (sidebarToggle) {
    sidebarToggle.addEventListener('click', function () {
      if (window.matchMedia('(max-width: 767.98px)').matches) {
        body.classList.toggle('sidebar-open');
      } else {
        // On desktop, treat the same button as collapse toggle if you like
        body.classList.toggle('sidebar-collapsed');
      }
    });
  }

  // Desktop collapse
  if (sidebarCollapse) {
    sidebarCollapse.addEventListener('click', function () {
      body.classList.toggle('sidebar-collapsed');
    });
  }

  // Clicking backdrop closes mobile off-canvas
  if (backdrop) {
    backdrop.addEventListener('click', function () {
      body.classList.remove('sidebar-open');
    });
  }

  // Keep aria-expanded in sync for caret color/rotation when Bootstrap toggles collapse
  document.querySelectorAll('[data-toggle="collapse"]').forEach(function (el) {
    var target = document.querySelector(el.getAttribute('href'));
    if (!target) return;
    target.addEventListener('shown.bs.collapse', function(){ el.setAttribute('aria-expanded', 'true'); });
    target.addEventListener('hidden.bs.collapse', function(){ el.setAttribute('aria-expanded', 'false'); });
  });
})();
