/* A directed, readable projection of real counterparties. No inferred transfers. */
(() => {
  'use strict';
  const stage = document.querySelector('.graph-stage');
  const canvas = document.getElementById('network');
  const host = document.createElement('div');
  host.id = 'flowView';
  host.hidden = true;
  host.setAttribute('aria-label', 'Плательщики, выбранный клиент и получатели');
  stage.append(host);
  const switcher = document.createElement('div');
  switcher.className = 'view-switch';
  switcher.innerHTML = '<span>Представление</span><div role="group" aria-label="Представление связей"><button id="viewFlows" type="button" disabled>Потоки →</button><button id="viewNetwork" type="button" aria-pressed="true">Сеть</button></div><small>Направление реальных переводов</small>';
  document.getElementById('searchForm').after(switcher);
  let card = null, preferFlow = true, frame = 0;
  const isFlow = () => preferFlow && state.view === 'neighborhood' && state.nodeMap.has(state.selected);

  function sync() {
    const active = isFlow();
    document.body.classList.toggle('client-focus', state.nodeMap.has(state.selected));
    host.hidden = !active;
    canvas.hidden = active;
    stage.classList.toggle('flow-mode', active);
    if (active) {
      document.getElementById('legend').innerHTML = '<span><i class="dot" style="background:#2580ac"></i>Плательщики → клиент</span><span><i class="dot" style="background:#158871"></i>Клиент → получатели</span>';
      document.querySelector('.graph-help').textContent = 'Показаны крупнейшие контрагенты. Полный gid — при наведении; роль — в карточке.';
    } else {
      renderLegend();
      document.querySelector('.graph-help').textContent = 'Стрелки показывают движение денег. Нажмите на узел, чтобы изучить клиента.';
    }
    document.getElementById('viewFlows').disabled = !state.nodeMap.has(state.selected);
    for (const [id, on] of [['viewFlows', active], ['viewNetwork', !active]]) {
      document.getElementById(id).classList.toggle('active', on);
      document.getElementById(id).setAttribute('aria-pressed', String(on));
    }
    if (!active) {
      requestAnimationFrame(() => {state.network?.redraw(); if (state.graphReady) state.network?.fit({animation:false});});
    } else render();
  }

  function party(row, direction) {
    return '<button type="button" class="flow-party" data-flow-gid="'+esc(row.gid)+'" data-direction="'+direction+'" title="'+esc(row.gid)+' · '+esc(role(row.role).name)+'">'+
      '<span class="flow-party-id">'+esc(shortGid(row.gid))+'</span><strong>'+money(row.sum_kzt)+'</strong><span class="flow-party-meta">'+fmt(row.n_tx)+' переводов</span></button>';
  }

  function render() {
    if (!isFlow()) return;
    if (!card || card.gid !== state.selected) {
      host.innerHTML = '<div class="flow-placeholder">Загружаю переводы выбранного клиента…</div>';
      return;
    }
    const daily = Boolean(window.moneyTimeline?.active);
    const day = daily ? window.moneyTimeline.day : null;
    if (daily && !day) {
      host.innerHTML = '<div class="flow-placeholder">Ожидаю данные выбранного дня</div>';
      return;
    }
    if (daily) document.getElementById('timelineDayNote').textContent = day.edges.length
      ? 'Синие стрелки — входящие, зелёные — исходящие. Показаны переводы выбранного дня.'
      : 'В этот день видимых переводов нет.';
    const m = card.metrics || {};
    const incoming = daily ? day.edges.filter(e => e.to === card.gid).map(e => ({gid:e.from,role:state.nodeMap.get(e.from)?.role,...e})) : [...(card.in || [])];
    const outgoing = daily ? day.edges.filter(e => e.from === card.gid).map(e => ({gid:e.to,role:state.nodeMap.get(e.to)?.role,...e})) : [...(card.out || [])];
    incoming.sort((a,b) => b.sum_kzt-a.sum_kzt || String(a.gid).localeCompare(String(b.gid)));
    outgoing.sort((a,b) => b.sum_kzt-a.sum_kzt || String(a.gid).localeCompare(String(b.gid)));
    const received = daily ? day.in_kzt : m.in_kzt;
    const sent = daily ? day.out_kzt : m.out_kzt;
    const inCount = daily ? incoming.length : m.in_deg;
    const outCount = daily ? outgoing.length : m.out_deg;
    host.innerHTML = '<div class="flow-summary"><div><span>Входящие · '+fmt(inCount)+' плательщиков</span><strong>'+money(received)+'</strong></div><span class="flow-period">'+esc(daily ? day.label : 'Июль 2026')+'</span><div><span>'+(m.truncated?'Исходящие неизвестны':'Исходящие · '+fmt(outCount)+' получателей')+'</span><strong>'+(m.truncated?'Обрыв данных':money(sent))+'</strong></div></div>'+
      '<div class="flow-columns"><svg class="flow-lanes" aria-hidden="true"></svg><section class="flow-side flow-in" aria-label="Крупнейшие плательщики">'+(incoming.slice(0,5).map(r => party(r,'in')).join('')||'<p class="flow-empty">Видимых входящих нет</p>')+'</section>'+
      '<div class="flow-center"><span class="flow-center-kicker">Клиент</span><span class="flow-center-mark" aria-hidden="true">◎</span><strong title="'+esc(card.gid)+'">'+esc(shortGid(card.gid))+'</strong><span>'+esc(role(card.role).name)+'</span><small>В списке #'+esc(card.rank)+'</small></div>'+
      '<section class="flow-side flow-out" aria-label="Крупнейшие получатели">'+(outgoing.slice(0,5).map(r => party(r,'out')).join('')||'<p class="flow-empty">'+(m.truncated?'4-й шаг. Продолжение не выгружено.':'Видимых исходящих нет')+'</p>')+'</section></div>'+
      '<p class="flow-footnote">До 5 крупнейших контрагентов с каждой стороны; суммы сверху — по всем. Нажмите на клиента, чтобы продолжить проверку.'+(daily?' Совпадение дат не доказывает движение тех же средств.':'')+'</p>';
    scheduleLines();
  }

  function scheduleLines() {
    cancelAnimationFrame(frame);
    frame = requestAnimationFrame(drawLines);
  }

  function drawLines() {
    if (host.hidden) return;
    const area = host.querySelector('.flow-columns');
    const center = host.querySelector('.flow-center');
    if (!area || !center) return;
    const box = area.getBoundingClientRect(), c = center.getBoundingClientRect();
    const svg = host.querySelector('.flow-lanes');
    svg.setAttribute('viewBox', `0 0 ${box.width} ${box.height}`);
    const yCenter = c.top-box.top+c.height/2;
    const lines = [...host.querySelectorAll('.flow-party')].map(button => {
      const r = button.getBoundingClientRect(), incoming = button.dataset.direction === 'in';
      const x1 = incoming ? r.right-box.left : c.right-box.left;
      const x2 = incoming ? c.left-box.left : r.left-box.left;
      const y1 = incoming ? r.top-box.top+r.height/2 : yCenter;
      const y2 = incoming ? yCenter : r.top-box.top+r.height/2;
      const mid = (x1+x2)/2;
      return `<path d="M ${x1} ${y1} C ${mid} ${y1}, ${mid} ${y2}, ${x2-5} ${y2}" class="${incoming?'flow-in-line':'flow-out-line'}" marker-end="url(#flow-arrow-${incoming?'in':'out'})"/>`;
    });
    svg.innerHTML = '<defs><marker id="flow-arrow-in" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" markerHeight="5" orient="auto"><path d="M 0 0 L 10 5 L 0 10 z" fill="#70c9f4"/></marker><marker id="flow-arrow-out" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" markerHeight="5" orient="auto"><path d="M 0 0 L 10 5 L 0 10 z" fill="#53dcbb"/></marker></defs>'+lines.join('');
  }

  document.getElementById('viewFlows').addEventListener('click', () => {
    preferFlow = true;
    if (state.view !== 'neighborhood') showNeighborhood(state.selected);
    sync();
  });
  document.getElementById('viewNetwork').addEventListener('click', () => {
    preferFlow = false;sync();
    if (window.moneyTimeline?.active && window.moneyTimeline.day) window.moneyTimeline.setDay(Number(document.getElementById('timelineRange').value));
  });
  host.addEventListener('click', event => {
    const button = event.target.closest('[data-flow-gid]');
    if (button) openNode(button.dataset.flowGid);
  });
  window.addEventListener('aml:node-loading', () => {card = null;render();});
  window.addEventListener('aml:node', event => {card = event.detail;sync();});
  window.addEventListener('aml:node-error', () => {
    card = null;
    if (isFlow()) host.innerHTML = '<div class="flow-placeholder">Переводы недоступны. Повторите поиск после восстановления соединения.</div>';
  });
  window.addEventListener('aml:graph', sync);
  window.addEventListener('aml:day', render);
  window.addEventListener('aml:timeline-mode', render);
  new ResizeObserver(scheduleLines).observe(host);
  window.flowView = Object.freeze({get active(){return isFlow();}});
})();
