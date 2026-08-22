
'use strict';

(() => {
  const U = window.MAIL_URLS || {};
  const $ = (sel, root = document) => root.querySelector(sel);

  function getCookie(name) {
    const match = document.cookie.match(new RegExp('(^|;\\s*)' + name + '=([^;]*)'));
    return match ? decodeURIComponent(match[2]) : '';
  }
  async function post(url, body) {
    try {
      const res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
        credentials: 'same-origin',
        body: JSON.stringify(body || {}),
      });
      return await res.json();
    } catch (e) {
      return { status: false, reason: 'network error' };
    }
  }
  async function getJSON(url) {
    try {
      const res = await fetch(url, { credentials: 'same-origin' });
      return await res.json();
    } catch (e) {
      return { status: false, reason: 'network error' };
    }
  }

  const esc = (s) => String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');

  function fmtDate(iso) {
    const d = new Date(iso);
    if (isNaN(d)) return '';
    const now = new Date();
    const sameDay = d.toDateString() === now.toDateString();
    return sameDay
      ? d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
      : d.toLocaleDateString([], { year: 'numeric', month: 'short', day: '2-digit' });
  }

  function applyThemeLabel() {
    const dark = document.documentElement.getAttribute('data-theme') !== 'light';
    document.querySelectorAll('[data-theme-label]').forEach(el => {
      el.textContent = dark ? 'Light mode' : 'Dark mode';
    });
  }
  function toggleTheme() {
    const next = document.documentElement.getAttribute('data-theme') === 'light' ? 'dark' : 'light';
    document.documentElement.setAttribute('data-theme', next);
    try { localStorage.setItem('mailTheme', next); } catch (e) {}
    applyThemeLabel();
  }
  applyThemeLabel();

  const composeModal = $('#rc-compose');
  const composeForm = $('#rc-compose-form');

  function openCompose(opts = {}) {
    if (!composeForm) return;
    const f = composeForm;
    f.mode.value = opts.mode || 'new';
    f.reply_to.value = opts.replyTo || '';
    f.draft_id.value = opts.draftId || '';
    f.to.value = opts.to || '';
    f.cc.value = opts.cc || '';
    f.bcc.value = '';
    f.subject.value = opts.subject || '';
    f.text.value = opts.text || '';
    if (f.attachments) f.attachments.value = '';
    $('#rc-compose-title').textContent = opts.title || 'New message';
    composeModal.classList.remove('hidden');
    f.to.focus();
  }
  const closeCompose = () => composeModal && composeModal.classList.add('hidden');

  contactSearch($('#rc-compose-to'), (c) => {
    if (c.email && composeForm) composeForm.to.value = c.email;
  });

  const MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024;
  const MAX_ATTACHMENTS_TOTAL_BYTES = 25 * 1024 * 1024;

  function readFileAsBase64(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result).split(',')[1] || '');
      reader.onerror = () => reject(reader.error);
      reader.readAsDataURL(file);
    });
  }

  async function composePayload() {
    const f = composeForm;
    const files = f.attachments ? Array.from(f.attachments.files || []) : [];
    let total = 0;
    for (const file of files) {
      if (file.size > MAX_ATTACHMENT_BYTES) {
        Toast.err(`"${file.name}" is larger than ${MAX_ATTACHMENT_BYTES / 1024 / 1024} MB.`);
        return null;
      }
      total += file.size;
    }
    if (total > MAX_ATTACHMENTS_TOTAL_BYTES) {
      Toast.err(`Attachments exceed the ${MAX_ATTACHMENTS_TOTAL_BYTES / 1024 / 1024} MB total limit.`);
      return null;
    }
    const attachments = [];
    for (const file of files) {
      attachments.push({
        filename: file.name,
        contentType: file.type || 'application/octet-stream',
        content_b64: await readFileAsBase64(file),
      });
    }
    return {
      mail_account: f.mail_account ? f.mail_account.value : '',
      mode: f.mode.value,
      reply_to: f.reply_to.value,
      draft_id: f.draft_id.value,
      to: f.to.value, cc: f.cc.value, bcc: f.bcc.value,
      subject: f.subject.value, text: f.text.value,
      quote: false,
      attachments,
    };
  }

  if (composeForm) {
    composeForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const payload = await composePayload();
      if (!payload) return;
      const btn = composeForm.querySelector('button[type=submit]');
      btn.disabled = true; btn.textContent = 'Sending…';
      const data = await post(U.send, payload);
      btn.disabled = false; btn.textContent = 'Send';
      if (data.status) {
        Toast.ok('Message sent.');
        closeCompose();
      } else {
        Toast.err(data.reason || 'Send failed.');
      }
    });
  }

  const listEl = $('#rc-list');
  const rowsEl = $('#rc-rows');
  const paneBody = $('#rc-pane-body');

  const state = {
    folder: ($('#rc-folders') && $('#rc-folders').dataset.folder) || 'INBOX',
    page: 1, pages: 1, q: '', threads: false, unreadOnly: false,
    selectMode: false, selected: new Set(),
    messages: [], open: null,
    draftsPath: null,
    expandedThreads: new Set(),
  };

  function rowHTML(m, child, parentId) {
    return `<li class="rc-row ${m.is_read ? '' : 'unread'} ${child ? 'rc-thread-child' : ''}"
        data-id="${m.id}" ${parentId ? `data-parent="${parentId}"` : ''}>
      <input type="checkbox" class="rc-row-check ${state.selectMode ? '' : 'hidden'}"
             ${state.selected.has(m.id) ? 'checked' : ''} aria-label="Select message">
      <span class="rc-row-sender">${esc(m.sender_name)}</span>
      <span class="rc-row-date">${fmtDate(m.date)}</span>
      <span class="rc-row-subject">${esc(m.subject)}</span>
      <span class="rc-row-flags">
        ${!child && m.thread_count > 1
          ? `<span class="rc-thread-count" data-thread="${m.id}" title="Show thread">${m.thread_count}</span>` : ''}
        ${m.has_attachments ? '<span title="Has attachments">&#128206;</span>' : ''}
        ${m.is_answered ? '<span title="Answered">&#8617;</span>' : ''}
        <span class="rc-star ${m.is_starred ? 'on' : ''}" data-star="${m.id}" title="Flag">&#9733;</span>
      </span>
    </li>`;
  }

  function renderFolders(folders) {
    const ul = $('#rc-folder-list');
    if (!folders) return;
    const drafts = folders.find(f => f.kind === 'drafts');
    state.draftsPath = drafts ? drafts.path : null;
    if (!ul) return;
    ul.innerHTML = folders.map(f => `<li><a class="rc-folder ${f.path === state.folder ? 'active' : ''}"
        href="?folder=${encodeURIComponent(f.path)}" data-folder="${esc(f.path)}" data-kind="${esc(f.kind)}">
        <span class="rc-folder-name">${esc(f.name)}</span>
        ${f.unread ? `<span class="rc-badge">${f.unread}</span>` : ''}</a></li>`).join('');
  }

  async function loadList(keepOpen) {
    if (!rowsEl) return;
    const params = new URLSearchParams({
      folder: state.folder, page: state.page,
      q: state.q, threads: state.threads ? '1' : '0',
      unread: state.unreadOnly ? '1' : '0',
    });
    rowsEl.innerHTML = '<li class="rc-loading">Loading…</li>';
    const data = await getJSON(`${U.list}?${params}`);
    if (!data.status) {
      rowsEl.innerHTML = `<li class="rc-loading">${esc(data.reason || 'Could not load messages.')}</li>`;
      return;
    }
    state.page = data.page; state.pages = data.pages;
    state.messages = data.messages;
    state.expandedThreads.clear();
    rowsEl.innerHTML = data.messages.length
      ? data.messages.map(m => rowHTML(m)).join('')
      : '<li class="rc-loading">This folder is empty.</li>';
    $('#rc-summary').textContent = data.summary;
    renderFolders(data.folders);
    if (keepOpen && state.open) markActiveRow(state.open);
  }

  async function toggleThread(id) {
    const li = rowsEl && rowsEl.querySelector(`.rc-row[data-id="${id}"]`);
    if (!li) return;
    if (state.expandedThreads.has(id)) {
      state.expandedThreads.delete(id);
      rowsEl.querySelectorAll(`.rc-thread-child[data-parent="${id}"]`).forEach(el => el.remove());
      return;
    }
    const data = await getJSON(`${U.messageBase}${id}/thread/`);
    if (!data.status) return Toast.err(data.reason || 'Could not load thread.');
    state.expandedThreads.add(id);
    const html = data.messages
      .filter(m => m.id !== id)
      .map(m => rowHTML(m, true, id))
      .join('');
    li.insertAdjacentHTML('afterend', html);
  }

  function markActiveRow(id) {
    rowsEl.querySelectorAll('.rc-row').forEach(li => li.classList.toggle('active', li.dataset.id === id));
  }

  function setToolbarEnabled(on) {
    document.querySelectorAll('#rc-pane-toolbar .rc-tool').forEach(b => { b.disabled = !on; });
  }

  async function openDraftInCompose(id) {
    const data = await getJSON(`${U.messageBase}${id}/`);
    if (!data.status) return Toast.err(data.reason || 'Could not open draft.');
    const m = data.message;
    openCompose({
      mode: 'new', draftId: m.id, title: 'Edit draft',
      to: m.to, cc: m.cc, subject: m.subject, text: m.body_text,
    });
  }

  async function openMessage(id) {
    if (!paneBody) return;
    if (state.draftsPath && state.folder === state.draftsPath) {
      return openDraftInCompose(id);
    }
    paneBody.innerHTML = '<div class="rc-splash"><p>Loading…</p></div>';
    document.querySelector('.rc-shell').classList.add('reading');
    const data = await getJSON(`${U.messageBase}${id}/`);
    if (!data.status) {
      paneBody.innerHTML = `<div class="rc-splash"><p>${esc(data.reason || 'Could not open message.')}</p></div>`;
      return;
    }
    const m = data.message;
    state.open = m.id;
    state.openMessage = m;
    markActiveRow(m.id);
    setToolbarEnabled(true);

    const attachments = (m.attachments || []).map((a, i) =>
      `<a class="rc-attach" href="${U.messageBase}${m.id}/attachment/${i}/" download="${esc(a.filename)}">
        &#128206; ${esc(a.filename)}
        <span class="rc-muted">${Math.max(1, Math.round((a.size || 0) / 1024))} KB</span></a>`).join('');

    const body = m.body_html
      ? `<iframe class="rc-msg-frame" sandbox referrerpolicy="no-referrer"
           srcdoc="${esc(m.body_html)}"></iframe>`
      : `<pre>${esc(m.body_text || '(empty message)')}</pre>`;

    paneBody.innerHTML = `
      <div class="rc-msg-head">
        <div class="rc-msg-subject">${esc(m.subject)}</div>
        <div class="rc-msg-meta">
          <span class="rc-avatar-sm">${esc((m.sender_name || '?').slice(0, 1).toUpperCase())}</span>
          <div><b>${esc(m.sender_name)}</b> &lt;${esc(m.sender)}&gt;<br>
            to ${esc(m.to || 'me')}${m.cc ? ' · cc ' + esc(m.cc) : ''}</div>
          <span class="rc-spacer"></span>
          <span>${fmtDate(m.date)}</span>
        </div>
      </div>
      ${attachments ? `<div class="rc-attachments">${attachments}</div>` : ''}
      <div class="rc-msg-body">${body}</div>`;

    const row = rowsEl && rowsEl.querySelector(`.rc-row[data-id="${m.id}"]`);
    if (row) row.classList.remove('unread');
  }

  function targetIds() {
    if (state.selected.size) return Array.from(state.selected);
    return state.open ? [state.open] : [];
  }
  function refreshSelectionUI() {
    const count = state.selected.size;
    const label = $('#rc-selected-count');
    if (label) label.textContent = `${count} selected`;
  }

  async function doFlag(flag, value, ids) {
    ids = ids || targetIds();
    if (!ids.length) return Toast.err('Nothing selected.');
    const data = await post(U.flag, { ids, flag, value });
    if (!data.status) return Toast.err(data.reason || 'Failed.');
    await loadList(true);
  }

  async function doDelete(ids) {
    ids = ids || targetIds();
    if (!ids.length) return Toast.err('Nothing selected.');
    const trash = (state.folder || '').toLowerCase().includes('trash');
    if (trash && !confirm(`Permanently delete ${ids.length} message(s)?`)) return;
    const data = await post(U.del, { ids });
    if (!data.status) return Toast.err(data.reason || 'Delete failed.');
    Toast.ok(data.expunged ? `${data.expunged} deleted permanently.` : `${data.moved} moved to Trash.`);
    state.selected.clear();
    if (ids.includes(state.open)) { state.open = null; setToolbarEnabled(false); }
    await loadList();
  }

  async function doMove(dest, ids) {
    ids = ids || targetIds();
    if (!ids.length) return Toast.err('Nothing selected.');
    const data = await post(U.move, { ids, destination: dest });
    if (!data.status) return Toast.err(data.reason || 'Move failed.');
    Toast.ok(`Moved ${data.moved} message(s).`);
    state.selected.clear();
    await loadList();
  }

  function replyContext(mode) {
    const m = state.openMessage;
    if (!m) { Toast.err('Open a message first.'); return null; }
    const titles = { reply: 'Reply', reply_all: 'Reply all', forward: 'Forward' };
    const quoted = mode === 'forward'
      ? `\n\n-------- Forwarded message --------\nSubject: ${m.subject}\nFrom: ${m.sender}\nTo: ${m.to}\n\n${m.body_text || ''}`
      : `\n\nOn ${fmtDate(m.date)}, ${m.sender_name} wrote:\n` +
        (m.body_text || '').split('\n').map(l => '> ' + l).join('\n');
    return {
      mode, replyTo: m.id, title: titles[mode],
      to: mode === 'forward' ? '' : m.sender,
      cc: mode === 'reply_all' ? m.cc : '',
      subject: mode === 'forward'
        ? (/^fwd?:/i.test(m.subject) ? m.subject : `Fwd: ${m.subject}`)
        : (/^re:/i.test(m.subject) ? m.subject : `Re: ${m.subject}`),
      text: quoted,
    };
  }

  document.addEventListener('click', async (e) => {
    const star = e.target.closest('[data-star]');
    if (star) {
      e.stopPropagation();
      const on = star.classList.contains('on');
      star.classList.toggle('on', !on);
      await doFlag('flagged', !on, [star.dataset.star]);
      return;
    }

    const check = e.target.closest('.rc-row-check');
    if (check) {
      e.stopPropagation();
      const id = check.closest('.rc-row').dataset.id;
      check.checked ? state.selected.add(id) : state.selected.delete(id);
      refreshSelectionUI();
      return;
    }

    const contactRow = e.target.closest('[data-action="compose-to"]');
    if (contactRow) { openCompose({ to: contactRow.dataset.to }); return; }

    const threadBadge = e.target.closest('[data-thread]');
    if (threadBadge) { e.stopPropagation(); await toggleThread(threadBadge.dataset.thread); return; }

    const row = e.target.closest('.rc-row[data-id]');
    if (row && rowsEl && rowsEl.contains(row)) { openMessage(row.dataset.id); return; }

    const folderLink = e.target.closest('.rc-folder[data-folder]');
    if (folderLink) {
      e.preventDefault();
      state.folder = folderLink.dataset.folder;
      state.page = 1; state.selected.clear(); state.open = null;
      setToolbarEnabled(false);
      if (paneBody) paneBody.innerHTML = '<div class="rc-splash"><p>Select a message to read it.</p></div>';
      history.replaceState(null, '', `?folder=${encodeURIComponent(state.folder)}`);
      await loadList();
      syncFolder();
      return;
    }

    const menuBtn = e.target.closest('[data-action$="-menu"]');
    if (menuBtn) {
      const menu = menuBtn.parentElement.querySelector('.rc-menu');
      document.querySelectorAll('.rc-menu').forEach(m => { if (m !== menu) m.classList.add('hidden'); });
      menu.classList.toggle('hidden');
      return;
    }
    if (!e.target.closest('.rc-menu')) {
      document.querySelectorAll('.rc-menu').forEach(m => m.classList.add('hidden'));
    }

    const btn = e.target.closest('[data-action]');
    if (!btn) return;
    const action = btn.dataset.action;

    switch (action) {
      case 'theme-toggle': toggleTheme(); break;
      case 'about': $('#rc-about').classList.remove('hidden'); break;
      case 'about-close': $('#rc-about').classList.add('hidden'); break;
      case 'compose': openCompose(); break;
      case 'compose-close': closeCompose(); break;

      case 'save-draft': {
        const payload = await composePayload();
        if (!payload) break;
        const data = await post(U.draft, payload);
        data.status ? Toast.ok('Draft saved to the server.') : Toast.err(data.reason || 'Could not save draft.');
        break;
      }

      case 'select-toggle': {
        state.selectMode = !state.selectMode;
        btn.classList.toggle('active', state.selectMode);
        $('#rc-bulkbar').classList.toggle('hidden', !state.selectMode);
        rowsEl.querySelectorAll('.rc-row-check').forEach(c => c.classList.toggle('hidden', !state.selectMode));
        if (!state.selectMode) { state.selected.clear(); refreshSelectionUI(); }
        break;
      }
      case 'threads-toggle':
        state.threads = !state.threads;
        btn.classList.toggle('active', state.threads);
        state.page = 1;
        await loadList();
        break;
      case 'options-toggle':
        $('#rc-options').classList.toggle('hidden');
        btn.classList.toggle('active');
        break;
      case 'refresh':
        btn.disabled = true;
        await syncFolder();
        btn.disabled = false;
        break;
      case 'sync-folders': {
        const data = await post(U.syncFolders, {});
        if (!data.status) { Toast.err(data.reason || 'Could not list folders.'); break; }
        renderFolders(data.folders);
        Toast.ok('Folder list updated.');
        break;
      }

      case 'page-prev':
        if (state.page > 1) { state.page--; await loadList(); }
        break;
      case 'page-next':
        if (state.page < state.pages) { state.page++; await loadList(); }
        break;

      case 'bulk-read':   await doFlag('seen', true); break;
      case 'bulk-unread': await doFlag('seen', false); break;
      case 'bulk-delete': await doDelete(); break;
      case 'delete':      await doDelete(); break;
      case 'mark':
        await doFlag(btn.dataset.flag, btn.dataset.value === '1');
        break;
      case 'move':        await doMove(btn.dataset.dest); break;
      case 'print':       window.print(); break;

      case 'reply': case 'reply-all': case 'forward': {
        const mode = action === 'reply-all' ? 'reply_all' : action;
        const ctx = replyContext(mode);
        if (ctx) openCompose(ctx);
        break;
      }

      case 'mailbox-select': {
        const data = await post(U.settings, { action: 'select', mail_account: btn.dataset.id });
        data.status ? location.reload() : Toast.err(data.reason || 'Failed.');
        break;
      }
      case 'mailbox-connect': {
        btn.disabled = true;
        const data = await post(U.settings, { action: 'connect', mail_account: btn.dataset.id });
        btn.disabled = false;
        data.status ? location.reload() : Toast.err(data.reason || 'Connection failed.');
        break;
      }
      case 'mailbox-delete': {
        if (!confirm(`Delete mailbox "${btn.dataset.name}" and its stored mail?`)) break;
        const data = await post(U.settings, { action: 'delete', mail_account: btn.dataset.id });
        data.status ? location.reload() : Toast.err(data.reason || 'Failed.');
        break;
      }
      default: break;
    }
  });

  const search = $('#rc-search');
  if (search) {
    let timer;
    search.addEventListener('input', () => {
      clearTimeout(timer);
      timer = setTimeout(() => {
        state.q = search.value.trim();
        state.page = 1;
        loadList();
      }, 300);
    });
  }

  const pageSize = $('#rc-page-size');
  if (pageSize) {
    pageSize.addEventListener('change', async () => {
      await post(U.settings, { action: 'page_size', page_size: Number(pageSize.value) });
      state.page = 1;
      loadList();
    });
  }
  const settingsPageSize = $('#rc-settings-page-size');
  if (settingsPageSize) {
    settingsPageSize.addEventListener('change', async () => {
      const data = await post(U.settings, { action: 'page_size', page_size: Number(settingsPageSize.value) });
      data.status ? Toast.ok('Preference saved.') : Toast.err(data.reason || 'Failed.');
    });
  }
  const unreadOnly = $('#rc-unread-only');
  if (unreadOnly) unreadOnly.addEventListener('change', () => {
    state.unreadOnly = unreadOnly.checked;
    state.page = 1;
    loadList();
  });
  const selectAll = $('#rc-select-all');
  if (selectAll) selectAll.addEventListener('change', () => {
    state.selected.clear();
    rowsEl.querySelectorAll('.rc-row').forEach(li => {
      const box = li.querySelector('.rc-row-check');
      box.checked = selectAll.checked;
      if (selectAll.checked) state.selected.add(li.dataset.id);
    });
    refreshSelectionUI();
  });
  const mailboxSelect = $('#rc-mailbox-select');
  if (mailboxSelect) mailboxSelect.addEventListener('change', async () => {
    await post(U.settings, { action: 'select', mail_account: mailboxSelect.value });
    location.reload();
  });

  const mailboxForm = $('#rc-mailbox-form');
  if (mailboxForm) {
    mailboxForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const body = { action: 'add' };
      new FormData(mailboxForm).forEach((v, k) => { body[k] = v; });
      const btn = mailboxForm.querySelector('button[type=submit]');
      btn.disabled = true;
      const data = await post(U.settings, body);
      btn.disabled = false;
      data.status ? location.reload() : Toast.err(data.reason || 'Could not add mailbox.');
    });
  }

  async function syncFolder(limit) {
    const data = await post(U.sync, { folder: state.folder, limit: limit || undefined });
    if (!data.status) { Toast.err(data.reason || 'Sync failed.'); return data; }
    await loadList(true);
    return data;
  }

  if (listEl) {
    (async () => {
      await loadList();
      await post(U.syncFolders, {});
      await syncFolder();
      setInterval(async () => {
        if (document.hidden) return;
        const data = await getJSON(`${U.poll}?folder=${encodeURIComponent(state.folder)}`);
        if (data.status && data.new) {
          Toast.ok(`${data.new} new message(s).`);
          await loadList(true);
        }
      }, 30000);
    })();
  }
})();
