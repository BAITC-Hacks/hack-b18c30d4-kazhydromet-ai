/* Analyst shortlist. Only identifiers persist; cards always come from the current API. */
(() => {
  'use strict';

  const STORAGE_KEY = 'kazhydromet.review-list.v1';
  const LIMIT = 100;
  const GID = /^\d{18}$/;
  const ROLES = {
    coordinator: 'Кандидат в организаторы',
    consolidator: 'Признаки консолидации',
    distributor: 'Признаки распределения',
    transit: 'Признаки транзита',
    terminal: 'Конечный получатель в выборке',
    peripheral: 'Явных признаков нет',
  };

  let storageAvailable = true;
  let selected = [];
  let currentGid = null;
  let request = null;
  let requestVersion = 0;
  let undo = null;
  const byId = id => document.getElementById(id);
  const valid = gid => typeof gid === 'string' && GID.test(gid);

  function normalize(value) {
    if (!Array.isArray(value)) return [];
    const result = new Set();
    for (const gid of value) {
      if (valid(gid)) result.add(gid);
      if (result.size === LIMIT) break;
    }
    return [...result];
  }

  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) {
      try { selected = normalize(JSON.parse(stored)); }
      catch { selected = []; }
    }
  } catch { storageAvailable = false; }

  function persist() {
    if (!storageAvailable) return;
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(selected)); }
    catch { storageAvailable = false; }
  }

  function storageNote() {
    return storageAvailable
      ? 'Перечень хранится только в этом браузере. Скачайте его перед завершением работы.'
      : 'Хранилище браузера недоступно. Перечень сохранится только до перезагрузки страницы — скачайте его.';
  }

  function notice(message = '', allowUndo = false) {
    const target = byId('reviewNotice');
    if (!target) return;
    target.replaceChildren();
    const text = document.createElement('span');
    text.textContent = (message ? `${message} ` : '') + storageNote();
    target.append(text);
    if (allowUndo && undo) {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'button small';
      button.dataset.reviewUndo = '';
      button.textContent = 'Вернуть';
      target.append(' ', button);
    }
  }

  function refreshCard(card) {
    const id = typeof card === 'string' ? card : card && card.gid;
    if (valid(id)) currentGid = id;
    const button = byId('reviewToggle');
    if (!button) return;
    const gid = button.dataset.reviewGid || currentGid;
    const exists = selected.includes(gid);
    button.disabled = !valid(gid);
    button.setAttribute('aria-pressed', String(exists));
    button.classList.toggle('is-selected', exists);
    button.textContent = exists ? '✓ В перечне на проверку' : '+ В перечень на проверку';
    button.title = exists ? 'Убрать клиента из перечня' : 'Добавить клиента в перечень';
  }

  function refresh() {
    const count = byId('reviewCount');
    const total = byId('reviewTotal');
    const open = byId('reviewOpen');
    const empty = byId('reviewEmpty');
    const clear = byId('reviewClear');
    const download = byId('reviewDownload');
    if (count) count.textContent = String(selected.length);
    if (total) total.textContent = String(selected.length);
    if (open) open.setAttribute('aria-label', `Перечень на проверку: ${selected.length} клиентов`);
    if (empty) {
      empty.hidden = selected.length !== 0;
      empty.textContent = 'Пока никого не выбрали. Откройте карточку клиента и нажмите «В перечень на проверку».';
    }
    if (clear) clear.disabled = selected.length === 0;
    if (download) {
      download.setAttribute('aria-disabled', String(selected.length === 0));
      download.classList.toggle('is-disabled', selected.length === 0);
      if (selected.length) {
        download.href = '/api/report?gids=' + encodeURIComponent(selected.join(','));
        download.setAttribute('download', 'aml_report.md');
        download.removeAttribute('tabindex');
      } else {
        download.removeAttribute('href');
        download.setAttribute('tabindex', '-1');
      }
    }
    refreshCard();
    window.dispatchEvent(new CustomEvent('aml:review', { detail: { gids: [...selected] } }));
  }

  function change(next, message, reversible = true) {
    const previous = [...selected];
    selected = normalize(next);
    undo = reversible ? previous : null;
    persist();
    refresh();
    notice(message, reversible);
    const dialog = byId('reviewDialog');
    if (dialog && dialog.open) loadCards();
  }

  function toggle(gid) {
    if (!valid(gid)) return false;
    if (selected.includes(gid)) {
      change(selected.filter(item => item !== gid), 'Клиент убран из перечня.');
      return true;
    }
    if (selected.length >= LIMIT) {
      notice(`В перечне уже ${LIMIT} клиентов. Уберите одного, чтобы добавить нового.`, Boolean(undo));
      const button = byId('reviewToggle');
      if (button) {
        button.textContent = 'Достигнут лимит: 100 клиентов';
        button.title = 'Откройте перечень и уберите одного клиента, чтобы добавить нового.';
      }
      return false;
    }
    change([...selected, gid], 'Клиент добавлен в перечень.', false);
    return true;
  }

  function makeRow(gid) {
    const item = document.createElement('article');
    item.className = 'review-item';
    const main = document.createElement('div');
    main.className = 'review-item-main';
    const open = document.createElement('button');
    open.type = 'button';
    open.className = 'review-open full-gid';
    open.dataset.reviewOpen = gid;
    open.textContent = gid;
    open.title = `Открыть карточку ${gid}`;
    const role = document.createElement('p');
    role.className = 'review-item-role';
    role.textContent = 'Загружаю актуальную карточку…';
    const meta = document.createElement('p');
    meta.className = 'review-meta small';
    const remove = document.createElement('button');
    remove.type = 'button';
    remove.className = 'button small review-remove';
    remove.dataset.reviewRemove = gid;
    remove.textContent = 'Убрать';
    remove.setAttribute('aria-label', `Убрать ${gid} из перечня`);
    main.append(open, role, meta);
    item.append(main, remove);
    return { item, role, meta };
  }

  async function loadCards() {
    const container = byId('reviewItems');
    if (!container) return;
    if (request) request.abort();
    request = new AbortController();
    const controller = request;
    const version = ++requestVersion;
    const gids = [...selected];
    container.replaceChildren();
    const rows = gids.map(gid => {
      const row = makeRow(gid);
      container.append(row.item);
      return row;
    });
    container.setAttribute('aria-busy', String(gids.length > 0));
    let cursor = 0;
    const timeout = setTimeout(() => controller.abort(), 20000);
    async function worker() {
      while (cursor < gids.length && version === requestVersion) {
        const index = cursor++;
        const row = rows[index];
        try {
          const response = await fetch('/api/node/' + encodeURIComponent(gids[index]), {
            signal: controller.signal,
            headers: { Accept: 'application/json' },
          });
          if (!response.ok) throw new Error(response.status === 404 ? 'missing' : 'unavailable');
          const data = await response.json();
          if (version !== requestVersion) return;
          if (data.error || data.gid !== gids[index]) throw new Error('missing');
          const role = ROLES[data.role] || 'Роль требует уточнения';
          const rank = Number.isInteger(data.rank) && data.rank > 0 ? `#${data.rank} · ` : '';
          row.role.textContent = rank + role;
          row.meta.textContent = typeof data.plain === 'string' ? data.plain : 'Откройте карточку для подробностей.';
        } catch (error) {
          if (version !== requestVersion) return;
          row.role.textContent = error.message === 'missing'
            ? 'Не найден в текущем расчёте'
            : 'Карточка временно недоступна';
          row.meta.textContent = 'Идентификатор сохранён. Можно повторно открыть перечень или убрать клиента.';
        }
      }
    }
    try { await Promise.all(Array.from({ length: Math.min(4, gids.length) }, worker)); }
    finally {
      clearTimeout(timeout);
      if (version === requestVersion) container.setAttribute('aria-busy', 'false');
    }
  }

  function close() {
    const dialog = byId('reviewDialog');
    if (dialog && dialog.open) dialog.close();
  }

  function open() {
    const dialog = byId('reviewDialog');
    if (!dialog) return;
    refresh();
    notice(undo ? 'Можно вернуть удалённых клиентов.' : '', Boolean(undo));
    if (!dialog.open) dialog.showModal();
    loadCards();
  }

  document.addEventListener('click', event => {
    if (!(event.target instanceof Element)) return;
    const target = event.target.closest('button, a');
    if (!target) return;
    if (target.id === 'reviewOpen') open();
    else if (target.id === 'reviewClose') close();
    else if (target.id === 'reviewToggle') toggle(target.dataset.reviewGid || currentGid);
    else if (target.id === 'reviewClear' && selected.length) change([], 'Перечень очищен.');
    else if (target.hasAttribute('data-review-undo') && undo) change(undo, 'Перечень восстановлен.', false);
    else if (target.hasAttribute('data-review-remove')) {
      change(selected.filter(gid => gid !== target.dataset.reviewRemove), 'Клиент убран из перечня.');
    } else if (target.hasAttribute('data-review-open')) {
      const gid = target.dataset.reviewOpen;
      if (!valid(gid)) return;
      close();
      if (typeof window.openNode === 'function') window.openNode(gid);
      else location.hash = gid;
    } else if (target.id === 'reviewDownload' && !selected.length) event.preventDefault();
  });

  // Both dispatch targets are accepted; refreshCard is deliberately idempotent.
  document.addEventListener('aml:node', event => refreshCard(event.detail));
  window.addEventListener('aml:node', event => refreshCard(event.detail));
  window.addEventListener('storage', event => {
    if (event.key !== STORAGE_KEY && event.key !== null) return;
    try { selected = normalize(event.newValue ? JSON.parse(event.newValue) : []); }
    catch { return; }
    undo = null;
    refresh();
    notice('Перечень обновлён в другой вкладке.');
    if (byId('reviewDialog')?.open) loadCards();
  });

  window.reviewList = Object.freeze({
    has: gid => valid(gid) && selected.includes(gid),
    get size() { return selected.length; },
    read: () => [...selected],
    refreshCard,
    open,
    toggle,
  });
  refresh();
  notice();
})();
