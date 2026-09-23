/* Entry points derived from observed graph data, without fixed client IDs. */
(() => {
  'use strict';
  const workspace = document.querySelector('.workspace');
  if (!workspace || document.getElementById('quickScenarios')) return;

  const scenarios = [
    {key: 'coordinator', label: 'Кандидат в организаторы', test: node => node.role === 'coordinator',
      hint: 'Клиент с наивысшим приоритетом среди тех, кто собирает и распределяет деньги. Роль — гипотеза.'},
    {key: 'anomalies', label: 'Необычные переводы', test: node => Number(node.anomalies) > 0,
      hint: 'Клиент с наивысшим приоритетом среди отмеченных правилами аномалий. Изучите факты, затем решите, нужна ли проверка.'},
    {key: 'truncated', label: 'Граница данных', test: node => node.truncated === true,
      hint: 'Клиент на границе выгрузки: исходящие неизвестны. Отсутствие переводов не означает, что деньги остались у него.'},
  ];
  const panel = document.createElement('section');
  panel.id = 'quickScenarios';
  panel.className = 'quick-scenarios';
  panel.setAttribute('aria-label', 'Быстрый вход в анализ');
  panel.innerHTML = '<div class="scenario-row"><span class="scenario-heading">Начните с вопроса</span><div class="scenario-options"></div></div><p class="scenario-hint" id="scenarioHint" role="status">Выбираю примеры из сети…</p>';
  workspace.before(panel);
  const options = panel.querySelector('.scenario-options');
  const hint = panel.querySelector('.scenario-hint');
  let selectedKey = '', opening = false, failedGid = '';

  for (const item of scenarios) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'scenario-button';
    button.dataset.scenario = item.key;
    button.textContent = item.label;
    button.title = item.hint;
    button.setAttribute('aria-describedby', 'scenarioHint');
    button.setAttribute('aria-pressed', 'false');
    button.disabled = true;
    options.append(button);
    item.button = button;
  }

  function updateSelection() {
    for (const item of scenarios) {
      const active = selectedKey === item.key && typeof state !== 'undefined' && state.selected === item.gid;
      item.button.classList.toggle('active', active);
      item.button.setAttribute('aria-pressed', String(active));
    }
  }

  function explanation(item) {
    if (!item) return '';
    if (item.key !== 'truncated' && item.gid && scenarios[0].gid === scenarios[1].gid) {
      return 'Один клиент подходит для двух сценариев: кандидат в организаторы и признаки необычных переводов. Изучите основания в карточке — оба вывода остаются гипотезами.';
    }
    return item.hint;
  }

  function refresh(settled = true) {
    const nodes = typeof state !== 'undefined' ? state.graph?.nodes : null;
    panel.classList.toggle('scenario-error', settled && !Array.isArray(nodes));
    for (const item of scenarios) {
      const candidates = Array.isArray(nodes) ? nodes.filter(node => /^\d{18}$/.test(String(node.id)) && item.test(node)) : [];
      candidates.sort((a, b) => Number(b.priority) - Number(a.priority) || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
      item.gid = candidates[0] ? String(candidates[0].id) : '';
      item.button.disabled = !item.gid;
      item.button.title = item.gid ? item.hint : Array.isArray(nodes) ? 'В текущей сети нет подходящего клиента.' : 'Дождитесь загрузки сети.';
    }
    if (!Array.isArray(nodes)) {
      hint.textContent = settled ? 'Не удалось загрузить сеть. Повторите загрузку данных, чтобы открыть примеры.' : 'Выбираю примеры из сети…';
    } else if (!scenarios.some(item => item.gid)) {
      hint.textContent = 'В текущей сети нет клиентов для этих сценариев. Можно начать со списка приоритетов.';
    } else {
      hint.textContent = explanation(scenarios.find(item => item.key === selectedKey && item.gid === state.selected)) || 'Три отправные точки: роль клиента, необычные переводы и граница доступных данных.';
    }
    updateSelection();
  }

  options.addEventListener('click', async event => {
    const button = event.target.closest('[data-scenario]');
    const item = scenarios.find(candidate => candidate.key === button?.dataset.scenario);
    if (!item?.gid || opening || typeof openNode !== 'function') return;
    const gid = item.gid;
    selectedKey = item.key;
    failedGid = '';
    opening = true;
    panel.setAttribute('aria-busy', 'true');
    hint.textContent = 'Открываю клиента…';
    try {
      if (window.moneyTimeline?.active) window.moneyTimeline.close(false);
      await openNode(gid);
      if (typeof state === 'undefined' || state.selected !== gid) return;
      if (failedGid === gid) {
        hint.textContent = 'Карточка недоступна. Нажмите сценарий ещё раз, чтобы повторить загрузку.';
        return;
      }
      hint.textContent = explanation(item);
      if (item.key === 'anomalies') document.getElementById('showAnomaly')?.click();
    } catch {
      hint.textContent = 'Карточка недоступна. Нажмите сценарий ещё раз, чтобы повторить загрузку.';
    } finally {
      opening = false;
      panel.setAttribute('aria-busy', 'false');
      updateSelection();
    }
  });

  window.addEventListener('aml:ready', () => refresh());
  window.addEventListener('aml:node', () => {
    updateSelection();
    if (!opening && !scenarios.some(item => item.key === selectedKey && item.gid === state.selected)) {
      selectedKey = '';
      refresh();
    }
  });
  window.addEventListener('aml:node-error', event => { failedGid = event.detail?.gid || ''; });
  window.addEventListener('popstate', updateSelection);
  refresh(Boolean(typeof state !== 'undefined' && state.graph));
})();
