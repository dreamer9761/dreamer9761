// 날씨 패널: Open-Meteo(무료, 키 필요 없음) 예보 + 한반도 지도
(() => {
  // 주요 도시 좌표 (지명 검색이 실패해도 바로 쓰고, 지도에 주변 도시 날씨로도 표시)
  const CITIES = {
    서울: [37.5665, 126.978], 인천: [37.4563, 126.7052], 수원: [37.2636, 127.0286], 춘천: [37.8813, 127.7298],
    원주: [37.3422, 127.9202], 강릉: [37.7519, 128.8761], 속초: [38.207, 128.5918], 청주: [36.6424, 127.489],
    대전: [36.3504, 127.3845], 세종: [36.48, 127.289], 천안: [36.8151, 127.1139], 안동: [36.5684, 128.7294],
    포항: [36.019, 129.3435], 대구: [35.8714, 128.6014], 울산: [35.5384, 129.3114], 부산: [35.1796, 129.0756],
    창원: [35.2281, 128.6811], 전주: [35.8242, 127.148], 광주: [35.1595, 126.8526], 목포: [34.8118, 126.3922],
    여수: [34.7604, 127.6622], 제주: [33.4996, 126.5312], 서귀포: [33.2541, 126.56], 울릉: [37.4845, 130.9057],
  };
  const WMO = (c) =>
    c === 0 ? ['☀️', '맑음'] : c === 1 ? ['🌤️', '대체로 맑음'] : c === 2 ? ['⛅', '구름 조금'] : c === 3 ? ['☁️', '흐림'] :
    c <= 48 ? ['🌫️', '안개'] : c <= 57 ? ['🌦️', '이슬비'] : c <= 67 ? ['🌧️', '비'] : c <= 77 ? ['🌨️', '눈'] :
    c <= 82 ? ['🌦️', '소나기'] : c <= 86 ? ['🌨️', '눈 소나기'] : ['⛈️', '뇌우'];
  const DAYS = ['일', '월', '화', '수', '목', '금', '토'];
  const $ = (id) => document.getElementById(id);
  let closeTimer;

  async function getJSON(url) {
    const r = await fetch(url);
    if (!r.ok) throw new Error(r.status);
    return r.json();
  }

  async function locate(place) {
    const key = place.replace(/\s/g, '').replace(/(특별시|광역시|특별자치시|특별자치도|시|군)$/, '');
    if (CITIES[key]) return { name: key, lat: CITIES[key][0], lon: CITIES[key][1] };
    const g = await getJSON(`https://geocoding-api.open-meteo.com/v1/search?count=1&language=ko&name=${encodeURIComponent(place)}`);
    const r = g.results && g.results[0];
    if (!r) throw new Error(`'${place}' 위치를 찾지 못했어요.`);
    return { name: r.name, lat: r.latitude, lon: r.longitude };
  }

  const forecast = (loc) => getJSON(`https://api.open-meteo.com/v1/forecast?latitude=${loc.lat}&longitude=${loc.lon}` +
    '&current=temperature_2m,apparent_temperature,relative_humidity_2m,precipitation,weather_code,cloud_cover,wind_speed_10m' +
    '&hourly=temperature_2m,weather_code,precipitation_probability' +
    '&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max' +
    '&timezone=Asia%2FSeoul&forecast_days=7');

  function render(loc, f) {
    const c = f.current;
    const [icon, desc] = WMO(c.weather_code);
    $('wx-place').textContent = `📍 ${loc.name}`;
    $('wx-updated').textContent = `${c.time.slice(11, 16)} 기준 · Open-Meteo`;
    $('wx-now').innerHTML = `
      <div class="icon">${icon}</div>
      <div class="temp">${Math.round(c.temperature_2m)}°</div>
      <div class="desc"><b>${desc}</b><br>
        체감 ${Math.round(c.apparent_temperature)}° · 구름 ${c.cloud_cover}% · 습도 ${c.relative_humidity_2m}%<br>
        바람 ${(c.wind_speed_10m / 3.6).toFixed(1)}m/s · 강수 ${c.precipitation}mm</div>`;

    const h = f.hourly, start = Math.max(0, h.time.findIndex((t) => t >= c.time.slice(0, 13)));
    $('wx-hours').innerHTML = [...Array(8)].map((_, k) => {
      const i = start + k * 3;
      if (i >= h.time.length) return '';
      const p = h.precipitation_probability[i];
      return `<div class="wx-cell"><div class="lbl">${k ? h.time[i].slice(11, 13) + '시' : '지금'}</div>
        <div class="i">${WMO(h.weather_code[i])[0]}</div><div class="hi">${Math.round(h.temperature_2m[i])}°</div>
        <div class="rain">${p >= 20 ? '💧' + p + '%' : ''}</div></div>`;
    }).join('');

    const d = f.daily;
    $('wx-days').innerHTML = d.time.map((t, i) => {
      const day = new Date(t + 'T00:00:00');
      const p = d.precipitation_probability_max[i];
      return `<div class="wx-cell ${i ? '' : 'today'}"><div class="lbl">${i ? DAYS[day.getDay()] : '오늘'} ${day.getDate()}일</div>
        <div class="i">${WMO(d.weather_code[i])[0]}</div>
        <div><span class="hi">${Math.round(d.temperature_2m_max[i])}°</span> <span class="lo">${Math.round(d.temperature_2m_min[i])}°</span></div>
        <div class="rain">${p >= 20 ? '💧' + p + '%' : ''}</div></div>`;
    }).join('');
  }

  // 지도: 미리 만들어 둔 한반도 윤곽 위에 도시별 하늘 상태·기온 표시 (외부 지도 서비스·API 키 불필요)
  function project(lat, lon) {
    const M = window.KOREA_MAP, B = M.B;
    const my = (a) => Math.log(Math.tan(Math.PI / 4 + a * Math.PI / 360));
    const k = M.W / ((B.e - B.w) * Math.PI / 180);
    return [((lon - B.w) * Math.PI / 180) * k, (my(B.n) - my(lat)) * k];
  }

  async function drawMap(loc, here) {
    const M = window.KOREA_MAP, box = $('wx-map');
    if (!M) { box.textContent = '지도 데이터를 불러오지 못했어요.'; return; }
    const pin = (lat, lon, icon, temp, name, main) => {
      const [x, y] = project(lat, lon);
      return `<g transform="translate(${x.toFixed(1)} ${y.toFixed(1)})" class="${main ? 'main' : ''}">
        ${main ? '<circle class="pulse" r="26" cy="4"/>' : ''}
        <text class="i" y="${main ? -8 : -4}">${icon}</text><text class="t" y="${main ? 20 : 18}">${temp}°</text><text class="n" y="${main ? 37 : 34}">${name}</text></g>`;
    };
    const [hx, hy] = project(loc.lat, loc.lon);
    const inside = hx >= 0 && hx <= M.W && hy >= 0 && hy <= M.H;
    // 선택한 도시를 먼저 놓고, 이미 놓인 핀과 너무 가까운 도시는 건너뛰어 글자가 겹치지 않게
    const placed = inside ? [[hx, hy]] : [];
    const roomFor = (lat, lon) => {
      const [x, y] = project(lat, lon);
      if (placed.some(([px, py]) => Math.abs(px - x) < 46 && Math.abs(py - y) < 52)) return false;
      placed.push([x, y]);
      return true;
    };
    let pins = '';
    const others = Object.entries(CITIES).filter(([n, [la, lo]]) => n !== loc.name && roomFor(la, lo));
    try {
      const q = await getJSON(`https://api.open-meteo.com/v1/forecast?latitude=${others.map((o) => o[1][0]).join(',')}` +
        `&longitude=${others.map((o) => o[1][1]).join(',')}&current=temperature_2m,weather_code&timezone=Asia%2FSeoul`);
      (Array.isArray(q) ? q : [q]).forEach((r, i) => {
        pins += pin(others[i][1][0], others[i][1][1], WMO(r.current.weather_code)[0], Math.round(r.current.temperature_2m), others[i][0]);
      });
    } catch (e) { /* 주변 도시는 생략 */ }
    if (inside) pins += pin(loc.lat, loc.lon, WMO(here.weather_code)[0], Math.round(here.temperature_2m), loc.name, true);
    box.innerHTML = `<svg viewBox="0 0 ${M.W} ${M.H}" preserveAspectRatio="xMidYMid meet" class="wx-svg">
      <defs><clipPath id="wx-clip"><rect width="${M.W}" height="${M.H}"/></clipPath></defs>
      <g clip-path="url(#wx-clip)"><rect width="${M.W}" height="${M.H}" class="sea"/>
      <path d="${M.other}" class="land other"/><path d="${M.kor}" class="land kor"/></g>
      ${pins}</svg>${inside ? '' : `<div class="wx-note">${loc.name}은(는) 지도 범위 밖이에요.</div>`}`;
  }

  function close() {
    clearTimeout(closeTimer);
    $('weather').hidden = true;
    if ($('news').hidden && $('report').hidden && $('draft').hidden) document.documentElement.classList.remove('has-side');
  }

  async function show(place) {
    $('news').hidden = true;
    $('report').hidden = true;
    $('draft').hidden = true;
    $('weather').hidden = false;
    document.documentElement.classList.add('has-side');
    try { if (window.innerWidth < 900) window.resizeTo(1120, Math.max(window.outerHeight, 820)); } catch (e) {}
    $('wx-err').textContent = '';
    $('wx-place').textContent = `📍 ${place}`;
    $('wx-updated').textContent = '불러오는 중…';
    clearTimeout(closeTimer);
    closeTimer = setTimeout(close, 3 * 60 * 1000); // 3분 뒤 자동으로 닫기
    try {
      const loc = await locate(place);
      const f = await forecast(loc);
      render(loc, f);
      await drawMap(loc, f.current);
    } catch (e) {
      $('wx-err').textContent = `날씨를 불러오지 못했어요: ${e.message}`;
    }
  }

  document.addEventListener('DOMContentLoaded', () => { $('wx-close').onclick = close; });
  // 대시보드 등 다른 화면에서 쓰는 날씨 데이터
  async function data(place) {
    const loc = await locate(place);
    return { loc, f: await forecast(loc) };
  }
  window.YongWeather = { show, close, data, WMO };
})();
