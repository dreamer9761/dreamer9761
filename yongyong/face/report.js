// 보고서 패널: 용용이가 data/ 에 써 둔 요약(간단한 마크다운)을 보여 준다 (예: 크몽 현황)
(() => {
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);
  const inline = (s) => esc(s).replace(/\*\*(.+?)\*\*/g, '<b>$1</b>');
  let closeTimer;

  function markdown(md) {
    let html = '', list = false;
    for (const raw of md.split('\n')) {
      const line = raw.trimEnd();
      const li = line.match(/^\s*[-*]\s+(.*)/);
      if (!li && list) { html += '</ul>'; list = false; }
      if (li) { if (!list) { html += '<ul>'; list = true; } html += `<li>${inline(li[1])}</li>`; }
      else if (/^#{1,2}\s/.test(line)) html += `<h3>${inline(line.replace(/^#+\s*/, ''))}</h3>`;
      else if (/^#{3,}\s/.test(line)) html += `<h4>${inline(line.replace(/^#+\s*/, ''))}</h4>`;
      else if (line.trim()) html += `<p>${inline(line)}</p>`;
    }
    return html + (list ? '</ul>' : '');
  }

  function close() {
    clearTimeout(closeTimer);
    $('report').hidden = true;
    if ($('weather').hidden && $('news').hidden && $('draft').hidden && $('tpl').hidden && $('blog').hidden && $('notices').hidden) document.documentElement.classList.remove('has-side');
  }

  async function show(name) {
    for (const id of ['weather', 'news', 'draft', 'tpl', 'blog', 'notices']) $(id).hidden = true;
    $('report').hidden = false;
    document.documentElement.classList.add('has-side');
    try { if (window.innerWidth < 900) window.resizeTo(1120, Math.max(window.outerHeight, 820)); } catch (e) {}
    clearTimeout(closeTimer);
    closeTimer = setTimeout(close, 10 * 60 * 1000);
    try {
      const r = await fetch('/report', {
        method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Yongyong': '1' },
        body: JSON.stringify({ name }),
      }).then((x) => x.json());
      if (!r.ok) throw new Error(r.error || '보고서를 불러오지 못했어요.');
      $('report-title').textContent = r.title;
      $('report-updated').textContent = r.updated;
      $('report-body').innerHTML = markdown(r.text);
    } catch (e) {
      $('report-body').innerHTML = `<p class="wx-err">${esc(e.message)}</p>`;
    }
  }

  document.addEventListener('DOMContentLoaded', () => { $('report-close').onclick = close; });
  window.YongReport = { show, close, markdown };
})();
