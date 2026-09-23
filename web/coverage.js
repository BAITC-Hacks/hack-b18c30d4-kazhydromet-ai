/* Marginal review coverage, calculated from observed transactions on the server. */
(() => {
  'use strict';
  const dialog = document.getElementById('reviewDialog');
  const panel = document.createElement('section');
  panel.className = 'review-coverage';
  panel.id = 'reviewCoverage';
  panel.setAttribute('aria-label', 'Охват выбранной проверки');
  dialog.querySelector('.review-content').prepend(panel);
  let version = 0, controller = null;

  async function load() {
    controller?.abort();
    const current = ++version;
    if (!dialog.open) return;
    controller = new AbortController();
    const request = controller;
    const timeout = setTimeout(() => request.abort(), 15000);
    panel.setAttribute('aria-busy', 'true');
    panel.innerHTML = '<p class="coverage-loading">Считаю уникальные переводы выбранных клиентов…</p>';
    try {
      const response = await fetch('/api/review-coverage?gids='+encodeURIComponent(window.reviewList.read().join(',')), {signal:request.signal});
      if (!response.ok) throw new Error('unavailable');
      const data = await response.json();
      if (current !== version || !dialog.open) return;
      const next = data.next_candidate;
      const share = Math.min(100,Math.max(0,Number(data.transactions_share)*100));
      panel.innerHTML = '<div class="coverage-heading"><div><span class="eyebrow">Обоснованный план проверки</span><h3>Что даёт этот перечень</h3></div><span class="coverage-chip">Без двойного счёта</span></div>'+
        '<div class="coverage-numbers"><div><strong id="coverageTransactions">'+fmt(data.n_transactions)+'</strong><span>из '+fmt(data.total_transactions)+' видимых переводов</span></div><div><strong>'+money(data.sum_kzt)+'</strong><span>сумма охваченных операций</span></div></div>'+
        '<div class="coverage-meter" role="meter" aria-label="Доля охваченных переводов" aria-valuemin="0" aria-valuemax="100" aria-valuenow="'+share.toFixed(1)+'"><span style="width:'+share.toFixed(3)+'%"></span></div>'+
        '<p class="coverage-caption">'+share.toLocaleString('ru-RU',{maximumFractionDigits:1})+'% переводов · '+fmt(data.n_counterparties)+' других клиентов · операция между двумя выбранными учитывается один раз.</p>'+
        (next ? '<div class="coverage-next"><div><span class="coverage-next-label">'+(data.n_selected?'Что даст следующая проверка':'С чего начать')+'</span><button class="coverage-client" data-coverage-open="'+esc(next.gid)+'" title="Открыть карточку">#'+esc(next.rank)+' · '+esc(next.gid)+'</button><p>'+esc(next.why)+'</p></div><button class="button primary" data-coverage-add="'+esc(next.gid)+'">Добавить: +'+fmt(next.new_transactions)+' переводов</button></div>' : '<p class="coverage-complete">'+(data.n_selected>=100?'Достигнут лимит перечня — 100 клиентов.':'В оставшемся топ-50 нет клиентов, добавляющих видимые операции.')+'</p>')+
        (data.unknown_gids?.length?'<p class="coverage-caption">Не найдены и не учтены: '+data.unknown_gids.map(esc).join(', ')+'.</p>':'')+
        '<details class="coverage-method"><summary>Как выбирается следующий клиент</summary><p>Среди ещё не выбранных клиентов топ-50, кроме исходных seed, выбираем того, кто добавит больше неохваченных переводов. При равенстве — выше приоритет. Пустой перечень начинаем с первого по приоритету. Это последовательная эвристика, не гарантия лучшего набора.</p><p>'+esc(data.note||'Только видимые операции. Охват не означает преступный оборот или эффект блокировки.')+'</p></details>';
    } catch (error) {
      if (current !== version || !dialog.open) return;
      panel.innerHTML = '<p class="coverage-loading">Охват сейчас недоступен. Выбранные клиенты сохранены; отчёт можно скачать.</p><button class="button small-button" data-coverage-retry>Повторить расчёт</button>';
    } finally {
      clearTimeout(timeout);
      if (current === version) panel.setAttribute('aria-busy','false');
    }
  }

  panel.addEventListener('click', event => {
    const add = event.target.closest('[data-coverage-add]');
    const open = event.target.closest('[data-coverage-open]');
    if (add) {
      add.disabled = true;
      if (!window.reviewList.toggle(add.dataset.coverageAdd)) load();
    } else if (open) {
      dialog.close();
      openNode(open.dataset.coverageOpen);
    } else if (event.target.closest('[data-coverage-retry]')) load();
  });
  new MutationObserver(load).observe(dialog,{attributes:true,attributeFilter:['open']});
  window.addEventListener('aml:review', () => {if (dialog.open) load();});
})();
