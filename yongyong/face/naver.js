// 네이버 메일 다시 연결: 새 애플리케이션 비밀번호를 붙여 넣으면 용용이가 확인하고 맥 키체인에 저장 (휴대폰에서도)
(() => {
  const $ = (id) => document.getElementById(id);
  const post = (path, data) => fetch(path, {
    method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Yongyong': '1' }, body: JSON.stringify(data || {}),
  }).then((r) => r.json());
  const OTHERS = ['weather', 'news', 'report', 'draft', 'tpl', 'blog', 'notices'];

  function close() {
    $('naver').hidden = true;
    $('naver-pw').value = '';
    if (OTHERS.every((id) => $(id).hidden)) document.documentElement.classList.remove('has-side');
  }

  async function show() {
    for (const id of OTHERS) $(id).hidden = true;
    $('naver').hidden = false;
    document.documentElement.classList.add('has-side');
    $('naver-msg').textContent = '';
    try {
      const r = await post('/naver/connect', { check: true });
      if (r.id && !$('naver-id').value) $('naver-id').value = r.id;
      $('naver-state').textContent = r.paused ? '⚠️ 지금 로그인이 안 돼서 자동 연동이 멈춰 있어요.' : (r.id ? '지금 연결돼 있어요. 비밀번호를 바꿨을 때만 다시 넣으세요.' : '아직 연결 전이에요.');
    } catch (e) {}
    setTimeout(() => { $('naver').scrollIntoView({ behavior: 'smooth', block: 'start' }); ($('naver-id').value ? $('naver-pw') : $('naver-id')).focus(); }, 50);
  }

  async function save() {
    const btn = $('naver-save');
    btn.disabled = true;
    $('naver-msg').textContent = '네이버에 확인하는 중…';
    try {
      const r = await post('/naver/connect', { id: $('naver-id').value, password: $('naver-pw').value });
      $('naver-msg').textContent = r.ok ? '✅ ' + r.message : '❌ ' + (r.error || '연결하지 못했어요.');
      if (r.ok) { $('naver-pw').value = ''; $('naver-state').textContent = '지금 연결돼 있어요.'; }
    } catch (e) { $('naver-msg').textContent = '❌ 용용이와 연결되지 않았어요.'; }
    btn.disabled = false;
  }

  document.addEventListener('DOMContentLoaded', () => {
    $('naver-open').onclick = show;
    $('naver-close').onclick = close;
    $('naver-save').onclick = save;
    $('naver-pw').addEventListener('keydown', (e) => { if (e.key === 'Enter') save(); });
  });
  window.YongNaver = { show, close };
})();
