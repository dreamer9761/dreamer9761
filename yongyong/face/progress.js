// 캐릭터 머리 위 말풍선: 오래 걸리는 작업(메일 색인·증빙 색인)은 % 와 막대로, Claude 가 생각 중일 때는 걸린 시간으로 보여 준다.
(function () {
  let jobs = {}, thinkingSince = 0, timer = null;
  const $ = (id) => document.getElementById(id);

  function render() {
    const box = $('progress');
    if (!box) return;
    const rows = Object.values(jobs).map((j) =>
      `<div class="pg-row"><div class="pg-label">${esc(j.label)}${j.pct == null ? '' : ` <b>${j.pct}%</b>`}</div>` +
      `<div class="pg-bar${j.pct == null ? ' busy' : ''}"><i style="width:${j.pct == null ? 100 : j.pct}%"></i></div></div>`);
    if (!rows.length && thinkingSince) {
      rows.push('<div class="pg-row"><div class="pg-label">생각하는 중… <b id="pg-sec">0초</b></div><div class="pg-bar busy"><i></i></div></div>');
    }
    const html = rows.join('');
    if (html !== last) { box.innerHTML = html; last = html; }  // 같으면 다시 그리지 않아야 막대 애니메이션이 끊기지 않음
    tickSec();
    box.classList.toggle('show', rows.length > 0);
    const stage = box.parentElement;
    stage.classList.toggle('has-pg', rows.length > 0);
    // 말풍선 윗부분이 화면 밖으로 나가면 그만큼 용용이를 내린다 (화면이 가운데 정렬이라 2배)
    stage.style.setProperty('--pg-h', '0px');
    const over = rows.length ? 8 - box.getBoundingClientRect().top : 0;
    stage.style.setProperty('--pg-h', Math.max(0, Math.ceil(over * 2)) + 'px');
  }
  let last = '';
  function tickSec() {
    const el = document.getElementById('pg-sec');
    if (el && thinkingSince) el.textContent = Math.floor((Date.now() - thinkingSince) / 1000) + '초';
  }
  const esc = (t) => String(t).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

  window.YongProgress = {
    jobs(j) { jobs = j || {}; render(); },
    state(s) {  // 용용이 상태가 바뀔 때마다 (thinking 이면 초 세기 시작)
      if (s === 'thinking') {
        if (!thinkingSince) thinkingSince = Date.now();
        if (!timer) timer = setInterval(tickSec, 1000);
      } else {
        thinkingSince = 0;
        clearInterval(timer); timer = null;
      }
      render();
    },
  };
})();
