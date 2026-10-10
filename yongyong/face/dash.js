// 대기 화면: 맥을 10분 동안 아무도 쓰지 않으면 시계·날씨·크몽 현황을 창 가득 보여 준다. 움직이거나 말을 걸면 사라짐.
(() => {
  const $ = (id) => document.getElementById(id);
  const DAYS = ['일', '월', '화', '수', '목', '금', '토'];
  const post = (path, data) => fetch(path, {
    method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Yongyong': '1' }, body: JSON.stringify(data || {}),
  }).then((r) => r.json());
  let last = Date.now(), on = false, shownAt = 0, timers = [], mouse = null;

  function tick() {
    const d = new Date(), pad = (n) => String(n).padStart(2, '0');
    $('dash-time').innerHTML = `${pad(d.getHours())}:${pad(d.getMinutes())}<span>${pad(d.getSeconds())}</span>`;
    $('dash-date').textContent = `${d.getMonth() + 1}월 ${d.getDate()}일 ${DAYS[d.getDay()]}요일`;
  }

  async function weather(place) {
    if (!place) { $('dash-wx').innerHTML = '<p class="dash-muted">"용용아, 내 기본 지역은 ○○이야" 라고 알려 주시면 날씨가 나와요.</p>'; return; }
    try {
      const { loc, f } = await window.YongWeather.data(place);
      const W = window.YongWeather.WMO, c = f.current, d = f.daily;
      const [icon, desc] = W(c.weather_code);
      $('dash-wx').innerHTML = `
        <div class="dash-now"><span class="i">${icon}</span><span class="t">${Math.round(c.temperature_2m)}°</span>
          <span class="d"><b>${loc.name} · ${desc}</b><br>최고 ${Math.round(d.temperature_2m_max[0])}° 최저 ${Math.round(d.temperature_2m_min[0])}°
          · 강수 ${d.precipitation_probability_max[0] || 0}%</span></div>
        <div class="dash-days">${d.time.slice(1, 6).map((t, i) => {
          const day = new Date(t + 'T00:00:00'), k = i + 1, p = d.precipitation_probability_max[k] || 0;
          return `<div><div class="l">${DAYS[day.getDay()]}</div><div class="i">${W(d.weather_code[k])[0]}</div>
            <div>${Math.round(d.temperature_2m_max[k])}° <span class="dash-muted">${Math.round(d.temperature_2m_min[k])}°</span></div>
            <div class="r">${p >= 20 ? '💧' + p + '%' : ''}</div></div>`;
        }).join('')}</div>`;
    } catch (e) { $('dash-wx').innerHTML = `<p class="dash-muted">날씨를 불러오지 못했어요 (${e.message})</p>`; }
  }

  async function kmong() {
    try {
      const r = await post('/dashboard');
      weather(r.region);
      if (!r.report) { $('dash-kmong').innerHTML = '<p class="dash-muted">아직 크몽 현황 보고서가 없어요. "용용아, 크몽 현황 알려 줘" 라고 해 보세요.</p>'; return; }
      $('dash-kmong-updated').textContent = r.updated;
      $('dash-kmong').innerHTML = window.YongReport.markdown(r.report);
    } catch (e) { $('dash-kmong').innerHTML = '<p class="dash-muted">용용이와 연결되지 않았어요.</p>'; }
  }

  function show() {
    if (on) return;
    on = true;
    shownAt = Date.now();
    mouse = null;
    document.documentElement.classList.add('dash-on');
    post('/window', { full: true }).catch(() => {});
    tick(); kmong();
    timers = [setInterval(tick, 1000), setInterval(kmong, 15 * 60 * 1000)];
  }

  function hide() {
    if (!on) return;
    on = false;
    timers.forEach(clearInterval);
    document.documentElement.classList.remove('dash-on');
    post('/window', { full: false }).catch(() => {});
  }

  function activity() {
    last = Date.now();
    if (Date.now() - shownAt > 2000) hide();  // 창이 커지는 순간 생기는 가짜 움직임은 무시
  }

  // 마우스는 실제로 조금이라도 움직였을 때만 (창 크기가 바뀌며 생기는 이벤트 제외)
  window.addEventListener('mousemove', (e) => {
    if (mouse && Math.hypot(e.screenX - mouse[0], e.screenY - mouse[1]) > 8) activity();
    mouse = [e.screenX, e.screenY];
  }, { passive: true });
  ['mousedown', 'keydown', 'touchstart', 'wheel'].forEach((ev) => window.addEventListener(ev, activity, { passive: true }));
  // 언제 띄울지는 용용이(파이썬)가 맥 전체의 키보드·마우스 사용 시간을 보고 정한다 (다른 앱에서 작업 중이면 안 뜸)
  window.YongDash = { activity, show, hide };
})();
