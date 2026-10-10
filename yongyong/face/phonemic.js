// 휴대폰(원격)에서 🎤 버튼을 누르고 말하기: 소리를 16kHz 로 줄여 맥미니로 보내면, 맥미니가 받아 적고 대답을 소리로 돌려준다.
(() => {
  const $ = (id) => document.getElementById(id);
  let ctx, src, node, stream, chunks = [], rate = 48000, recording = false, startAt = 0;

  function toPcm16k(buffers) {
    const len = buffers.reduce((n, b) => n + b.length, 0), all = new Float32Array(len);
    let o = 0; for (const b of buffers) { all.set(b, o); o += b.length; }
    const ratio = rate / 16000, out = new Int16Array(Math.floor(len / ratio));
    for (let i = 0; i < out.length; i++) {           // 구간 평균으로 줄이기 (간단한 저역 통과)
      const a = Math.floor(i * ratio), z = Math.min(len, Math.floor((i + 1) * ratio));
      let sum = 0; for (let j = a; j < z; j++) sum += all[j];
      const v = Math.max(-1, Math.min(1, sum / Math.max(1, z - a)));
      out[i] = v < 0 ? v * 32768 : v * 32767;
    }
    let bin = ''; const bytes = new Uint8Array(out.buffer);
    for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
    return btoa(bin);
  }

  async function start(e) {
    e.preventDefault();
    if (recording) return;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
    } catch (err) { $('chat-input').placeholder = '마이크 권한을 허용해 주세요'; return; }
    ctx = new (window.AudioContext || window.webkitAudioContext)();
    rate = ctx.sampleRate; chunks = [];
    src = ctx.createMediaStreamSource(stream);
    node = ctx.createScriptProcessor(4096, 1, 1);
    node.onaudioprocess = (ev) => { if (recording) chunks.push(new Float32Array(ev.inputBuffer.getChannelData(0))); };
    src.connect(node); node.connect(ctx.destination);
    recording = true; startAt = Date.now();
    $('chat-mic').classList.add('rec'); $('chat-mic').textContent = '듣는 중…';
    if (navigator.vibrate) navigator.vibrate(30);
  }

  async function stop(e) {
    if (e) e.preventDefault();
    if (!recording) return;
    recording = false;
    $('chat-mic').classList.remove('rec'); $('chat-mic').textContent = '🎤';
    try { node.disconnect(); src.disconnect(); stream.getTracks().forEach((t) => t.stop()); ctx.close(); } catch (err) {}
    if (Date.now() - startAt < 500) { $('chat-input').placeholder = '버튼을 누른 채로 말하고 떼세요'; return; }
    const pcm = toPcm16k(chunks); chunks = [];
    $('chat-input').placeholder = '받아 적는 중…';
    try {
      const r = await fetch('/voice', {
        method: 'POST', credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', 'X-Yongyong': '1' }, body: JSON.stringify({ pcm, reply: true }),
      }).then((x) => x.json());
      $('chat-input').placeholder = r.ok ? '용용이에게 입력 (Enter: 보내기)' : (r.error || '다시 말해 주세요');
    } catch (err) { $('chat-input').placeholder = '보내지 못했어요'; }
  }

  // 맥미니가 보낸 대답 소리 재생 (휴대폰 화면에서만)
  function play(b64) {
    if (!document.documentElement.classList.contains('remote')) return;
    const a = new Audio('data:audio/wav;base64,' + b64);
    a.play().catch(() => {});
  }

  document.addEventListener('DOMContentLoaded', () => {
    const b = $('chat-mic');
    b.addEventListener('pointerdown', start);
    ['pointerup', 'pointerleave', 'pointercancel'].forEach((ev) => b.addEventListener(ev, stop));
    b.addEventListener('contextmenu', (e) => e.preventDefault());
  });
  window.YongPhoneMic = { play };
})();
