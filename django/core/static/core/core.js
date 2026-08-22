/* ============================================================
   Shared UI helpers — toast, fetch wrapper, token-copy, count-up
   stats, and the cross-channel notification bell. Loaded on every
   page; whatsapp.js / mail.js load after this and use Toast/apiPost.
   ============================================================ */

'use strict';

// ── toast ────────────────────────────────────────────────────
const Toast = (() => {
  let container = null;
  function _ensure() {
    if (!container) {
      container = document.getElementById('toast-container');
    }
    if (!container) {
      container = document.createElement('div');
      container.id = 'toast-container';
      document.body.appendChild(container);
    }
  }
  function show(msg, type = 'info', duration = 3500) {
    _ensure();
    const el = document.createElement('div');
    el.className = `toast ${type}`;
    el.innerHTML = `<span>${msg}</span>`;
    container.appendChild(el);
    setTimeout(() => {
      el.style.opacity = '0';
      el.style.transform = 'translateX(40px)';
      el.style.transition = 'opacity .3s, transform .3s';
      setTimeout(() => el.remove(), 320);
    }, duration);
  }
  return { show, ok: (m) => show(m, 'ok'), err: (m) => show(m, 'err', 4500) };
})();

// ── sidebar toggle (collapsed by default on flush pages, e.g. Chats) ──
const appShell = document.getElementById('app-shell');
const sidebarToggle = document.getElementById('sidebar-toggle');
if (appShell) {
  if (document.querySelector('.main-flush')) appShell.classList.add('sidebar-collapsed');
  if (sidebarToggle) {
    sidebarToggle.addEventListener('click', () => appShell.classList.toggle('sidebar-collapsed'));
  }
}

// ── fetch wrapper (attaches device/account/mail token) ────────
async function apiPost(url, body, token) {
  const res = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { 'Authorization': token } : {}),
    },
    body: JSON.stringify(body),
  });
  return res.json();
}

// ── contact type-ahead (used by WhatsApp Chats search + Mail compose "To") ──
// Wires `input` to a debounced /app/contacts/search/?q= lookup, rendering a
// suggestion menu under it. `onPick(contact)` fires on click/Enter.
function contactSearch(input, onPick) {
  if (!input) return;
  const menu = document.createElement('div');
  menu.className = 'ac-menu hidden';
  input.parentElement.style.position = input.parentElement.style.position || 'relative';
  input.parentElement.appendChild(menu);

  let timer = null;
  let items = [];
  let active = -1;

  function hide() { menu.classList.add('hidden'); menu.innerHTML = ''; items = []; active = -1; }

  function render() {
    menu.innerHTML = items.map((c, i) => `
      <button type="button" class="ac-item${i === active ? ' active' : ''}" data-i="${i}">
        <span class="ac-name">${c.name}</span>
        <span class="ac-meta">${c.whatsapp || c.email || c.company || ''}</span>
      </button>`).join('');
    menu.classList.toggle('hidden', items.length === 0);
  }

  menu.addEventListener('click', (e) => {
    const btn = e.target.closest('.ac-item');
    if (!btn) return;
    onPick(items[parseInt(btn.dataset.i, 10)]);
    hide();
  });

  input.addEventListener('input', () => {
    clearTimeout(timer);
    const q = input.value.trim();
    if (q.length < 2) { hide(); return; }
    timer = setTimeout(async () => {
      try {
        const data = await fetch(`/app/contacts/search/?q=${encodeURIComponent(q)}`).then(r => r.json());
        items = data.results || [];
        active = -1;
        render();
      } catch (_) { hide(); }
    }, 200);
  });

  input.addEventListener('keydown', (e) => {
    if (menu.classList.contains('hidden')) return;
    if (e.key === 'ArrowDown') { e.preventDefault(); active = Math.min(active + 1, items.length - 1); render(); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); active = Math.max(active - 1, 0); render(); }
    else if (e.key === 'Enter' && active >= 0) { e.preventDefault(); onPick(items[active]); hide(); }
    else if (e.key === 'Escape') { hide(); }
  });

  document.addEventListener('click', (e) => {
    if (e.target !== input && !menu.contains(e.target)) hide();
  });
}

// ── copy to clipboard ────────────────────────────────────────
function copyText(text) {
  navigator.clipboard.writeText(text).then(() => Toast.ok('Copied!'));
}
document.querySelectorAll('.token-box').forEach(el => {
  el.title = 'Click to copy';
  el.addEventListener('click', () => copyText(el.dataset.full || el.textContent.trim()));
});

// ── count-up animation ───────────────────────────────────────
function countUp(el, target, duration = 800) {
  const start = performance.now();
  const from = parseInt(el.textContent, 10) || 0;
  function step(now) {
    const p = Math.min((now - start) / duration, 1);
    const ease = 1 - Math.pow(1 - p, 3);
    el.textContent = Math.round(from + (target - from) * ease);
    if (p < 1) requestAnimationFrame(step);
  }
  requestAnimationFrame(step);
}
document.querySelectorAll('.stat-value[data-count]').forEach(el => {
  countUp(el, parseInt(el.dataset.count, 10));
});

// ── notification bell polling (cross-channel: whatsapp + mail) ─
const bell = document.getElementById('bell-btn');
const bellBadge = document.getElementById('bell-badge');
let lastCount = 0;

async function pollNotifications() {
  try {
    const data = await fetch('/app/notifications/').then(r => r.json());
    const count = data.count || 0;
    if (bellBadge) {
      if (count > 0) {
        bellBadge.textContent = count > 99 ? '99+' : count;
        bellBadge.classList.add('visible');
      } else {
        bellBadge.classList.remove('visible');
      }
    }
    if (count > lastCount && lastCount !== null) {
      const newest = (data.latest || [])[0];
      if (newest && bell) {
        bell.classList.add('ringing');
        setTimeout(() => bell.classList.remove('ringing'), 600);
        const who = newest.name || newest.sender || 'someone';
        const preview = (newest.message || '').slice(0, 60);
        Toast.show(`💬 New message from <b>${who}</b>: ${preview}`, 'info', 5000);
      }
    }
    lastCount = count;
  } catch (_) { /* silently fail */ }
}

if (bell) {
  pollNotifications();
  setInterval(pollNotifications, 10000);
}
