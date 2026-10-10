// 대화 방식 선택: 🎤 음성(용용아 하고 부르기) / ⌨️ 텍스트(글자로 입력), 🔊 대답 소리 켜기·끄기
(() => {
  const $ = (id) => document.getElementById(id);
  const post = (path, data) => fetch(path, {
    method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Yongyong': '1' }, body: JSON.stringify(data || {}),
  }).then((r) => r.json());
  let mode = { input: 'voice', speak: true };

  function apply(m) {
    mode = { ...mode, ...m };
    if (document.documentElement.classList.contains('remote')) mode = { ...mode, input: 'text' };  // 밖에서는 항상 글자로
    document.documentElement.classList.toggle('text-mode', mode.input === 'text');
    document.documentElement.classList.toggle('music-on', !!mode.music);
    $('mode-voice').disabled = !!mode.music;
    $('mode-voice').title = mode.music ? '음악이 나오는 동안은 텍스트로만 입력할 수 있어요' : '';
    $('mode-voice').classList.toggle('on', mode.input === 'voice');
    $('mode-text').classList.toggle('on', mode.input === 'text');
    $('mode-speak').textContent = mode.speak ? '🔊 소리 켬' : '🔇 소리 끔';
    $('mode-speak').classList.toggle('on', mode.speak);
    if (mode.input === 'text') setTimeout(() => $('chat-input').focus(), 50);
  }

  function add(who, text) {
    const log = $('chat-log');
    const div = document.createElement('div');
    div.className = 'msg ' + who;
    div.textContent = text;
    log.appendChild(div);
    while (log.children.length > 40) log.removeChild(log.firstChild);
    log.scrollTop = log.scrollHeight;
  }

  async function send() {
    const input = $('chat-input');
    const text = input.value.trim();
    if (!text) return;
    input.value = '';
    add('me', text);
    try {
      const r = await post('/ask', { text });
      if (!r.ok) add('yongyong', r.error || '보내지 못했어요.');
    } catch (e) { add('yongyong', '용용이가 꺼져 있는 것 같아요.'); }
  }

  async function setMode(change) {
    apply(change);
    try { apply(await post('/mode', change)); } catch (e) {}
  }

  document.addEventListener('DOMContentLoaded', () => {
    $('mode-voice').onclick = () => setMode({ input: 'voice' });
    $('mode-text').onclick = () => setMode({ input: 'text' });
    $('mode-speak').onclick = () => setMode({ speak: !mode.speak });
    $('chat-send').onclick = send;
    $('chat-input').addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); send(); }
    });
    apply(mode);
  });
  window.YongChat = { apply, add };
})();
