// 뉴스 패널: 용용이(파이썬)가 Google 뉴스 RSS 를 대신 받아 와서 건네준다 (브라우저에서 직접 받으면 막힘)
(() => {
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);
  let closeTimer;

  function close() {
    clearTimeout(closeTimer);
    $('news').hidden = true;
    if ($('weather').hidden && $('report').hidden && $('draft').hidden && $('tpl').hidden && $('blog').hidden && $('notices').hidden) document.documentElement.classList.remove('has-side');
  }

  async function show(topic) {
    $('weather').hidden = true;
    $('report').hidden = true;
    $('draft').hidden = true;
    $('tpl').hidden = true;
    $('blog').hidden = true;
    $('notices').hidden = true;
    $('news').hidden = false;
    document.documentElement.classList.add('has-side');
    try { if (window.innerWidth < 900) window.resizeTo(1120, Math.max(window.outerHeight, 820)); } catch (e) {}
    $('news-title').textContent = '📰 뉴스 불러오는 중…';
    $('news-updated').textContent = '';
    $('news-list').innerHTML = '';
    clearTimeout(closeTimer);
    closeTimer = setTimeout(close, 5 * 60 * 1000);
    try {
      const r = await fetch('/news', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Yongyong': '1' },
        body: JSON.stringify({ topic: topic || '' }),
      }).then((x) => x.json());
      if (!r.ok) throw new Error(r.error || '뉴스를 불러오지 못했어요.');
      $('news-title').textContent = `📰 ${r.label}`;
      $('news-updated').textContent = `${new Date().toTimeString().slice(0, 5)} 기준 · Google 뉴스 · 제목을 누르면 기사가 열려요`;
      $('news-list').innerHTML = r.items.map((n, i) => `<li><a href="${esc(n.link)}" target="_blank" rel="noopener">
        <span class="no">${i + 1}</span><span><div class="tt">${esc(n.title)}</div>
        <div class="meta">${esc(n.source)}${n.ago ? ' · ' + esc(n.ago) : ''}</div></span></a></li>`).join('')
        || '<li class="meta">관련 기사가 없어요.</li>';
    } catch (e) {
      $('news-title').textContent = '📰 뉴스';
      $('news-list').innerHTML = `<li class="wx-err">${esc(e.message)}</li>`;
    }
  }

  document.addEventListener('DOMContentLoaded', () => { $('news-close').onclick = close; });
  window.YongNews = { show, close };
})();
