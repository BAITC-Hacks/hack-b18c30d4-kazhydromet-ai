/* Calendar playback uses observed transfers, never inferred movement of identical funds. */
(() => {
  'use strict';
  const el = id => document.getElementById(id);
  const reduceMotion = () => matchMedia('(prefers-reduced-motion: reduce)').matches;
  let active = false, data = null, index = 0, timer = null, version = 0;
  let loading = false, graphChanging = false;
  let overviewCopy = '';
  const overviewTitle = document.querySelector('.intro h1').textContent;

  function stop() {
    clearInterval(timer);
    timer = null;
    el('timelinePlay').textContent = '▶ Воспроизвести';
    el('timelinePlay').setAttribute('aria-pressed', 'false');
  }

  function visible(value) {
    if (value && !active) overviewCopy = el('introLine').textContent;
    active = value;
    document.body.classList.toggle('timeline-focus', value);
    document.querySelector('.intro h1').textContent = value ? 'Переводы. День за днём.' : overviewTitle;
    if (value) el('introLine').textContent = 'Исследуйте реальные входящие и исходящие. Близкие даты не доказывают движение одних и тех же средств.';
    else if (overviewCopy) el('introLine').textContent = overviewCopy;
    el('timelinePanel').hidden = !value;
    document.querySelector('.graph-panel').classList.toggle('timeline-active', value);
    el('timelineToggle').classList.toggle('active', value);
    el('timelineToggle').setAttribute('aria-pressed', String(value));
    el('timelineToggle').textContent = value ? 'Весь период' : 'Потоки по дням';
  }

  function close(restore = true) {
    ++version;
    stop();
    visible(false);
    data = null;
    loading = false;
    if (restore && state.graph && state.nodeMap.has(state.selected)) showNeighborhood(state.selected);
  }

  function controlsDisabled(disabled) {
    for (const id of ['timelinePlay', 'timelinePrev', 'timelineNext', 'timelineRange']) el(id).disabled = disabled;
  }

  function setDay(next) {
    if (!active || !data || data.gid !== state.selected) return;
    index = Math.min(Math.max(0, next), data.days.length - 1);
    const day = data.days[index];
    el('timelineDate').textContent = day.label;
    el('timelineRange').value = String(index);
    el('timelineRange').setAttribute('aria-valuetext', day.label);
    el('timelineIn').textContent = money(day.in_kzt);
    el('timelineOut').textContent = data.truncated ? 'Не наблюдаются' : money(day.out_kzt);
    el('timelineInCount').textContent = fmt(day.in_n_tx) + ' переводов';
    el('timelineOutCount').textContent = data.truncated ? 'Обрыв на 4-м шаге' : fmt(day.out_n_tx) + ' переводов';
    el('timelinePrev').disabled = index === 0;
    el('timelineNext').disabled = index === data.days.length - 1;
    el('timelineDayNote').textContent = day.edges.length
      ? 'Синие стрелки — входящие, зелёные — исходящие. Бледные узлы — связи в другие дни.'
      : 'В этот день видимых переводов нет. Связи за другие дни показаны бледным цветом.';
    document.querySelectorAll('.day-column').forEach((bar, i) => bar.classList.toggle('selected', i === index));
    if (!state.network || !state.graphReady || state.view !== 'neighborhood') return;

    const ids = new Set([data.gid]);
    day.edges.forEach(edge => { ids.add(edge.from); ids.add(edge.to); });
    const nodes = state.network.body.data.nodes;
    const patches = nodes.getIds().map(id => {
      const original = graphNode(state.nodeMap.get(id));
      if (ids.has(id)) return original;
      return {...original, color: {background: '#e7ecdf', border: '#d5ddcd',
        highlight: {background: '#e7ecdf', border: '#9bb48a'}}, borderWidth: 1,
        font: {...original.font, color: '#a9b5a0'}};
    });
    nodes.update(patches);
    const edges = state.network.body.data.edges;
    edges.clear();
    edges.add(day.edges.map(edge => ({...graphEdge(edge),
      color: {color: edge.to === data.gid ? '#3e7898' : '#2c855c',
        highlight: edge.to === data.gid ? '#3e7898' : '#2c855c', opacity: .95},
      width: Math.max(1.6, Math.log10(Math.max(1, edge.sum_kzt)) - 2.8)})));
    state.network.selectNodes([data.gid], false);
    state.network.redraw();
    el('graphCount').textContent = fmt(day.edges.length ? ids.size : 0) + ' клиентов с переводами · ' + fmt(day.edges.length) + ' связей за день';
    status('graphStatus', 'Переводы за ' + day.label + ' · выбранный клиент ' + data.gid);
  }

  function renderCalendar() {
    const max = Math.max(1, ...data.days.map(day => day.in_kzt + day.out_kzt));
    const fragment = document.createDocumentFragment();
    data.days.forEach((day, dayIndex) => {
      const bar = document.createElement('button');
      bar.type = 'button';
      bar.className = 'day-column';
      bar.dataset.day = String(dayIndex);
      bar.setAttribute('aria-label', day.label + ', входящие ' + money(day.in_kzt) +
        (data.truncated ? ', исходящие не наблюдаются' : ', исходящие ' + money(day.out_kzt)));
      bar.title = day.label + ' · ' + fmt(day.in_n_tx + day.out_n_tx) + ' переводов';
      const incoming = document.createElement('i');
      incoming.className = 'day-in';
      incoming.style.height = Math.max(0, 24 * day.in_kzt / max) + 'px';
      const outgoing = document.createElement('i');
      outgoing.className = 'day-out';
      outgoing.style.height = Math.max(0, 24 * day.out_kzt / max) + 'px';
      bar.append(outgoing, incoming);
      fragment.append(bar);
    });
    el('timelineBars').replaceChildren(fragment);
    el('timelineRange').max = String(data.days.length - 1);
    el('timelineStart').textContent = data.days[0].label;
    el('timelineEnd').textContent = data.days.at(-1).label;
    el('timelineCaveat').textContent = data.note;
    controlsDisabled(false);
  }

  async function load(gid, autoplay = false) {
    const current = ++version;
    stop();
    data = null;
    loading = true;
    controlsDisabled(true);
    visible(true);
    el('timelineDate').textContent = 'Загружаю даты…';
    el('timelineDayNote').textContent = 'Читаю исходные транзакции выбранного клиента.';
    el('timelineBars').replaceChildren();
    el('timelineIn').textContent = '—';el('timelineOut').textContent = '—';
    el('timelineInCount').textContent = '';el('timelineOutCount').textContent = '';
    try {
      const result = await getJSON('/api/timeline/' + encodeURIComponent(gid));
      if (current !== version || !active || state.selected !== gid) return;
      if (!Array.isArray(result.days) || !result.days.length) throw new Error('Нет дат для отображения');
      data = result;
      index = Math.max(0, data.days.findIndex(day => day.edges.length));
      renderCalendar();
      setDay(index);
      if (state.graphReady) state.network?.fit({animation: false});
      if (autoplay && !reduceMotion()) play();
    } catch (error) {
      if (current !== version) return;
      el('timelineDate').textContent = 'Даты недоступны';
      el('timelineDayNote').textContent = error.message + '. Можно вернуться ко всему периоду.';
    } finally {
      if (current === version) loading = false;
    }
  }

  function play() {
    if (timer) { stop(); return; }
    if (!data || !active) return;
    if (index >= data.days.length - 1) setDay(0);
    el('timelinePlay').textContent = 'Ⅱ Пауза';
    el('timelinePlay').setAttribute('aria-pressed', 'true');
    timer = setInterval(() => {
      if (!active || !data || document.hidden) { stop(); return; }
      if (!state.graphReady) return;
      if (index >= data.days.length - 1) { stop(); return; }
      setDay(index + 1);
    }, 1400);
  }

  el('timelineToggle').addEventListener('click', () => {
    if (active) close();
    else if (state.selected && state.nodeMap.has(state.selected)) {
      if (state.view !== 'neighborhood') showNeighborhood(state.selected);
      load(state.selected);
    }
  });
  el('timelinePlay').addEventListener('click', play);
  el('timelinePrev').addEventListener('click', () => { stop(); setDay(index - 1); });
  el('timelineNext').addEventListener('click', () => { stop(); setDay(index + 1); });
  el('timelineRange').addEventListener('input', event => { stop(); setDay(Number(event.target.value)); });
  el('timelineBars').addEventListener('click', event => {
    const bar = event.target.closest('[data-day]');
    if (bar) { stop(); setDay(Number(bar.dataset.day)); }
  });
  document.addEventListener('visibilitychange', () => { if (document.hidden) stop(); });

  window.addEventListener('aml:node', event => {
    el('timelineToggle').disabled = false;
    if (active && (!data || data.gid !== event.detail.gid || graphChanging)) load(event.detail.gid);
    graphChanging = false;
  });
  window.addEventListener('aml:graph', event => {
    graphChanging = true;
    ready();
    if (!active) return;
    stop();
    if (event.detail.view !== 'neighborhood') close(false);
  });
  window.addEventListener('aml:graph-ready', () => {
    if (active && data && data.gid === state.selected) setDay(index);
  });
  function ready() {
    el('startInvestigation').disabled = !(state.graph && state.topRows.length);
    el('timelineToggle').disabled = !(state.selected && state.nodeMap.has(state.selected));
  }
  window.addEventListener('aml:ready', ready);
  el('startInvestigation').addEventListener('click', async () => {
    const gid = state.selected && state.nodeMap.has(state.selected) ? state.selected : state.topRows[0]?.gid;
    if (!gid) return;
    el('startInvestigation').disabled = true;
    try {
      close(false);
      await openNode(gid);
      await load(gid, true);
      document.querySelector('.graph-panel').scrollIntoView({block: 'nearest', behavior: reduceMotion() ? 'instant' : 'smooth'});
    } finally { ready(); }
  });
  ready();
  window.moneyTimeline = Object.freeze({get active() {return active;}, get day() {return data?.days[index];},
    get playing() {return Boolean(timer);}, close, setDay, stop});
})();
