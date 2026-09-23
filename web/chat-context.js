/* Contextual questions use current API-backed selections, never invented identifiers. */
(() => {
  'use strict';
  const container = document.createElement('div');
  container.className = 'chat-hints';
  container.setAttribute('aria-label', 'Вопросы по текущему выбору');
  const day = document.createElement('button');
  const scope = document.createElement('button');
  for (const button of [day, scope]) { button.type = 'button'; button.className = 'hint'; }
  day.textContent = 'Разобрать этот день';
  scope.textContent = 'Оценить мой перечень';
  container.append(day, scope);
  document.getElementById('chatForm').before(container);
  day.addEventListener('click', () => sendChat('Что произошло в этот день у выбранного клиента?'));
  scope.addEventListener('click', () => sendChat('Какой охват даёт мой перечень и кого добавить следующим?', false));
  function refresh() {
    const selected = typeof state !== 'undefined' && state.chatContext;
    const date = selected && window.moneyTimeline?.active && window.moneyTimeline.day?.date;
    day.hidden = !date;
    scope.hidden = !(window.reviewList?.size > 0);
    container.hidden = day.hidden && scope.hidden;
    const context = document.getElementById('chatContext');
    if (selected) {
      context.textContent = 'Контекст следующего вопроса: клиент ' + selected +
        (date ? ' · ' + date.split('-').reverse().join('.') : ' · весь июль');
    }
  }
  for (const event of ['aml:node', 'aml:node-loading', 'aml:node-error', 'aml:day', 'aml:timeline-mode', 'aml:review', 'hashchange']) {
    window.addEventListener(event, () => queueMicrotask(refresh));
  }
  refresh();
})();
