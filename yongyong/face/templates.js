// 자주 쓰는 문구 관리: 대표님이 문구를 직접 붙여넣고 고쳐서 저장 (상담 초안이 이 내용을 그대로 참고)
(() => {
  const $ = (id) => document.getElementById(id);
  const post = (path, data) => fetch(path, {
    method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Yongyong': '1' }, body: JSON.stringify(data || {}),
  }).then((r) => r.json());
  const EXAMPLE = '### 신규개정개설가입컨설팅\n(크몽 자주 쓰는 문구 내용을 그대로 붙여넣기)\n\n### 환불이 안되는이유\n(내용)\n';

  function close() {
    $('tpl').hidden = true;
    if (['weather', 'news', 'report', 'draft', 'blog'].every((id) => $(id).hidden)) document.documentElement.classList.remove('has-side');
  }

  async function show() {
    for (const id of ['weather', 'news', 'report', 'draft', 'blog']) $(id).hidden = true;
    $('tpl').hidden = false;
    document.documentElement.classList.add('has-side');
    $('tpl-msg').textContent = '';
    try {
      const r = await post('/templates');
      $('tpl-text').value = r.text || EXAMPLE;
    } catch (e) { $('tpl-msg').textContent = '불러오지 못했어요.'; }
  }

  async function save() {
    const r = await post('/templates/save', { text: $('tpl-text').value });
    $('tpl-msg').textContent = r.ok ? `저장했어요 (문구 ${r.count}개). 상담 초안에 바로 반영돼요.` : (r.error || '저장하지 못했어요.');
  }

  document.addEventListener('DOMContentLoaded', () => {
    $('tpl-close').onclick = close;
    $('tpl-save').onclick = save;
    $('tpl-open').onclick = show;
  });
  window.YongTemplates = { show, close };
})();
