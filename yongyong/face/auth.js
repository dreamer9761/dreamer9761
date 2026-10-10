// 밖(휴대폰·사무실)에서 접속하면 아이디·비밀번호 로그인 화면을 먼저 보여 준다. 맥미니 안에서는 바로 통과.
(() => {
  const $ = (id) => document.getElementById(id);
  const post = (path, data) => fetch(path, {
    method: 'POST', credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json', 'X-Yongyong': '1' }, body: JSON.stringify(data || {}),
  }).then((r) => r.json());

  async function start(connect) {
    let r;
    try { r = await post('/auth/check'); } catch (e) { return connect(); }
    if (r.remote) {
      document.documentElement.classList.add('remote', 'text-mode');
      $('remote-logout').hidden = false;
    }
    if (r.ok) return connect();
    if (!r.enabled) {
      $('auth-msg').textContent = '아직 원격 접속이 설정되지 않았어요. 맥미니에서 remote_setup.sh 를 먼저 실행해 주세요.';
    }
    document.documentElement.classList.add('auth-on');
    $('auth-form').onsubmit = async (e) => {
      e.preventDefault();
      $('auth-msg').textContent = '확인 중…';
      const res = await post('/auth/login', { id: $('auth-id').value.trim(), pw: $('auth-pw').value });
      if (!res.ok) { $('auth-msg').textContent = res.error || '로그인하지 못했어요.'; return; }
      $('auth-pw').value = '';
      document.documentElement.classList.remove('auth-on');
      connect();
    };
  }

  document.addEventListener('DOMContentLoaded', () => {
    $('remote-logout').onclick = async () => { await post('/auth/logout'); location.reload(); };
  });
  if ('serviceWorker' in navigator && location.protocol === 'https:') navigator.serviceWorker.register('sw.js').catch(() => {});
  window.YongAuth = { start };
})();
