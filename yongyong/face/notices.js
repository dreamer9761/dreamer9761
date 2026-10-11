// 메일 발송 알림 패널: 고객에게 메일을 보낸 뒤 크몽 대화창에 남길 알림 (넣기만 하고, 보내기는 대표님이 크몽에서)
(() => {
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);
  const post = (path, data) => fetch(path, {
    method: 'POST', credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json', 'X-Yongyong': '1' }, body: JSON.stringify(data || {}),
  }).then((r) => r.json());
  const OTHERS = ['weather', 'news', 'report', 'draft', 'tpl', 'blog'];

  function render(items) {
    $('notices-list').innerHTML = items.length ? items.map((n, i) => `
      <div class="notice">
        <div class="notice-head"><b>${esc(n.nickname)}</b>님 · ${esc(n.subject || '')} <span>${esc(n.sent || '')}</span></div>
        <textarea class="draft-text notice-text" data-i="${i}">${esc(n.text)}</textarea>
        <div class="draft-actions">
          <button data-act="insert" data-i="${i}">크몽 대화창에 넣기</button>
          <button data-act="dismiss" data-i="${i}" class="ghost">지우기</button>
        </div>
      </div>`).join('') : '<p class="dash-muted">남길 메일 발송 알림이 없어요.</p>';
    $('notices-list').querySelectorAll('button').forEach((b) => b.onclick = async () => {
      const i = +b.dataset.i;
      b.disabled = true;
      $('notices-msg').textContent = b.dataset.act === 'insert' ? '크몽 대화를 여는 중…' : '';
      const text = $('notices-list').querySelector(`textarea[data-i="${i}"]`).value;
      const r = await post('/notices/act', { index: i, action: b.dataset.act, text });
      if (!r.ok) { $('notices-msg').textContent = r.error; b.disabled = false; return; }
      $('notices-msg').textContent = b.dataset.act === 'insert' ? '크몽 입력창에 넣었어요. 크몽에서 확인하고 전송을 눌러 주세요.' : '지웠어요.';
      render(r.items);
    });
  }

  function close() {
    $('notices').hidden = true;
    if (OTHERS.every((id) => $(id).hidden)) document.documentElement.classList.remove('has-side');
  }

  async function show() {
    OTHERS.forEach((id) => { $(id).hidden = true; });
    $('notices').hidden = false;
    document.documentElement.classList.add('has-side');
    $('notices-msg').textContent = '';
    try { render((await post('/notices')).items || []); } catch (e) { $('notices-msg').textContent = '불러오지 못했어요.'; }
  }

  document.addEventListener('DOMContentLoaded', () => { $('notices-close').onclick = close; });
  window.YongNotices = { show, close };
})();
