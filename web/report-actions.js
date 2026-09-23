/* Printable views complement the canonical Markdown download. */
(() => {
  'use strict';
  const download = document.getElementById('reviewDownload');
  if (!download || document.getElementById('reviewPreview')) return;
  const preview = document.createElement('a');
  preview.id = 'reviewPreview';
  preview.className = 'button primary report-preview';
  preview.target = '_blank';
  preview.rel = 'noopener noreferrer';
  preview.textContent = 'Открыть отчёт / PDF ↗';
  preview.title = 'Открыть готовый документ в новой вкладке; сохранить в PDF через печать браузера';
  download.before(preview);

  function refresh() {
    const gids = window.reviewList?.read().filter(gid => typeof gid === 'string' && /^\d{18}$/.test(gid)) || [];
    preview.setAttribute('aria-disabled', String(!gids.length));
    preview.classList.toggle('is-disabled', !gids.length);
    if (gids.length) {
      preview.href = '/api/report/view?gids=' + encodeURIComponent(gids.join(','));
      preview.removeAttribute('tabindex');
    } else {
      preview.removeAttribute('href');
      preview.tabIndex = -1;
    }
  }

  function cardPreview(gid) {
    if (typeof gid !== 'string' || !/^\d{18}$/.test(gid)) return;
    const markdown = document.querySelector('#nodeCard .node-report');
    if (!markdown) return;
    let link = document.getElementById('nodeReportPreview');
    if (!link) {
      link = document.createElement('a');
      link.id = 'nodeReportPreview';
      link.className = 'button node-report node-report-preview';
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
      link.textContent = 'Открыть карточку / PDF ↗';
      link.title = 'Готовая карточка в новой вкладке; PDF — через печать браузера';
      markdown.before(link);
    }
    link.href = '/api/report/view?gids=' + encodeURIComponent(gid);
  }

  preview.addEventListener('click', event => {
    refresh();
    if (preview.getAttribute('aria-disabled') === 'true') event.preventDefault();
  });
  window.addEventListener('aml:review', refresh);
  window.addEventListener('aml:node', event => cardPreview(event.detail?.gid));
  refresh();
  if (typeof state !== 'undefined') cardPreview(state.selected);
})();
