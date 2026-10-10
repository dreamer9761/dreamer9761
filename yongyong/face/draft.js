// 크몽 답변 초안 패널: 용용이가 쓴 초안을 보여 주고, 고쳐서 크몽 입력창에 넣는다 (보내기는 대표님이 크몽에서 직접)
(() => {
  const $ = (id) => document.getElementById(id);
  const post = (path, data) => fetch(path, {
    method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Yongyong': '1' }, body: JSON.stringify(data || {}),
  }).then((r) => r.json());

  function close() {
    $('draft').hidden = true;
    if (['weather', 'news', 'report', 'tpl', 'blog'].every((id) => $(id).hidden)) document.documentElement.classList.remove('has-side');
  }

  async function show() {
    for (const id of ['weather', 'news', 'report', 'tpl', 'blog']) $(id).hidden = true;
    $('draft').hidden = false;
    document.documentElement.classList.add('has-side');
    $('draft-msg').textContent = '';
    try {
      const r = await post('/draft');
      if (!r.ok) throw new Error(r.error);
      $('draft-info').innerHTML = window.YongReport.markdown(r.info || '');
      $('draft-text').value = r.reply || '';
      $('draft-updated').textContent = r.updated || '';
    } catch (e) { $('draft-info').textContent = '초안을 불러오지 못했어요: ' + e.message; }
  }

  async function insert() {
    const r = await post('/draft/insert', { text: $('draft-text').value });
    $('draft-msg').textContent = r.ok ? '크몽 입력창에 넣었어요. 크몽에서 확인하고 보내기를 눌러 주세요.' : (r.error || '넣지 못했어요.');
  }

  async function copy() {
    try { await navigator.clipboard.writeText($('draft-text').value); $('draft-msg').textContent = '복사했어요. 크몽 입력창에 붙여넣기(⌘V) 하세요.'; }
    catch (e) { $('draft-text').select(); document.execCommand('copy'); $('draft-msg').textContent = '복사했어요.'; }
  }

  document.addEventListener('DOMContentLoaded', () => {
    $('draft-close').onclick = close;
    $('draft-insert').onclick = insert;
    $('draft-copy').onclick = copy;
  });
  window.YongDraft = { show, close };
})();
