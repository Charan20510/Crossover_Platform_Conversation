
'use strict';

(function () {
  var root = document.documentElement;
  var stored = localStorage.getItem('theme');
  if (stored) root.setAttribute('data-theme', stored);
  else if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches)
    root.setAttribute('data-theme', 'dark');
  else root.setAttribute('data-theme', 'light');

  function updateIcon() {
    var icon = document.getElementById('themeIcon');
    if (icon) icon.textContent = root.getAttribute('data-theme') === 'light' ? 'N' : 'D';
  }
  updateIcon();
  document.addEventListener('DOMContentLoaded', function () {
    updateIcon();
    var btn = document.getElementById('themeToggle');
    if (btn) btn.addEventListener('click', function () {
      var next = root.getAttribute('data-theme') === 'light' ? 'dark' : 'light';
      root.setAttribute('data-theme', next);
      localStorage.setItem('theme', next);
      updateIcon();
    });
  });
})();
