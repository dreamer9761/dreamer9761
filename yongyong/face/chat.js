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

  async function copyText(text, btn) {
    try { await navigator.clipboard.writeText(text); }
    catch (e) {  // http 등에서 clipboard API 가 막히면 예전 방식으로
      const t = document.createElement('textarea'); t.value = text; document.body.appendChild(t);
      t.select(); document.execCommand('copy'); t.remove();
    }
    btn.textContent = '복사됨'; setTimeout(() => { btn.textContent = '복사'; }, 1500);
  }

  function add(who, text) {
    const log = $('chat-log');
    const div = document.createElement('div');
    div.className = 'msg ' + who;
    const body = document.createElement('span');
    body.textContent = text;
    div.appendChild(body);
    if (who === 'yongyong') {  // 용용이 대답마다 복사 버튼
      const b = document.createElement('button');
      b.className = 'msg-copy'; b.textContent = '복사';
      b.onclick = () => copyText(text, b);
      div.appendChild(b);
    }
    log.appendChild(div);
    while (log.children.length > 40) log.removeChild(log.firstChild);
    log.scrollTop = log.scrollHeight;
  }

  // 용용이가 만든 파일: [엑셀][워드][PDF] 버튼 (누르면 그 형식으로 바꿔서 내려받음)
  const FMT = { xlsx: '엑셀', docx: '워드', pdf: 'PDF', csv: 'CSV', md: '텍스트', txt: '텍스트', pptx: '파워포인트', hwp: '한글', zip: '압축', png: '그림', jpg: '그림' };
  function addFile(f) {
    const log = $('chat-log');
    const div = document.createElement('div');
    div.className = 'msg yongyong file';
    const name = document.createElement('div');
    name.className = 'file-name';
    name.textContent = '📄 ' + f.name;
    div.appendChild(name);
    const row = document.createElement('div');
    row.className = 'file-btns';
    for (const fmt of f.formats) {
      const a = document.createElement('a');
      a.href = `/download/${encodeURIComponent(f.id)}/${fmt}`;
      a.textContent = (FMT[fmt] || fmt.toUpperCase()) + ' 받기';
      a.setAttribute('download', f.name.replace(/\.\w+$/, '') + '.' + fmt);
      row.appendChild(a);
    }
    div.appendChild(row);
    log.appendChild(div);
    log.scrollTop = log.scrollHeight;
  }

  // 첨부 파일: 사진은 휴대폰 원본이 커서 긴 쪽 2000px JPEG 로 줄여서 보낸다
  let files = [];
  const toB64 = (blob) => new Promise((ok, bad) => {
    const r = new FileReader(); r.onload = () => ok(String(r.result).split(',')[1]); r.onerror = bad; r.readAsDataURL(blob);
  });
  async function shrink(file) {
    if (!/^image\/(jpeg|png|webp|heic|heif)/.test(file.type) || file.size < 700000) return { name: file.name, blob: file };
    try {
      const bmp = await createImageBitmap(file);
      const k = Math.min(1, 2000 / Math.max(bmp.width, bmp.height));
      const c = document.createElement('canvas'); c.width = Math.round(bmp.width * k); c.height = Math.round(bmp.height * k);
      c.getContext('2d').drawImage(bmp, 0, 0, c.width, c.height);
      const blob = await new Promise((r) => c.toBlob(r, 'image/jpeg', 0.85));
      return { name: file.name.replace(/\.\w+$/, '') + '.jpg', blob };
    } catch (e) { return { name: file.name, blob: file }; }
  }
  function chips() {
    $('chat-files').innerHTML = files.map((f, i) => `<span class="chip">📎 ${f.name.replace(/[<>&]/g, '')} <b data-i="${i}">✕</b></span>`).join('');
    $('chat-files').querySelectorAll('b').forEach((b) => b.onclick = () => { files.splice(+b.dataset.i, 1); chips(); });
  }

  async function send() {
    const input = $('chat-input');
    const text = input.value.trim();
    if (!text && !files.length) return;
    const sending = files; files = []; chips();
    input.value = '';
    add('me', text + (sending.length ? (text ? '\n' : '') + sending.map((f) => '📎 ' + f.name).join('\n') : ''));
    try {
      const ids = [];
      for (const f of sending) {
        const one = await shrink(f);
        const r = await post('/upload', { name: one.name, data: await toB64(one.blob) });
        if (!r.ok) { add('yongyong', r.error || `${f.name} 을(를) 올리지 못했어요.`); continue; }
        ids.push(r.id);
      }
      if (sending.length && !ids.length && !text) return;
      const r = await post('/ask', { text, files: ids });
      if (!r.ok) add('yongyong', r.error || '보내지 못했어요.');
    } catch (e) { add('yongyong', '보내지 못했어요. 파일이 너무 크면(40MB 넘으면) 줄여서 올려 주세요.'); }
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
    $('chat-attach').onclick = () => $('chat-file').click();
    $('chat-file').onchange = (e) => { files.push(...e.target.files); e.target.value = ''; chips(); };
    // 맥에서는 파일을 대화창에 끌어다 놓아도 첨부
    const box = document.querySelector('.chat');
    box.addEventListener('dragover', (e) => { e.preventDefault(); box.classList.add('drop'); });
    box.addEventListener('dragleave', () => box.classList.remove('drop'));
    box.addEventListener('drop', (e) => { e.preventDefault(); box.classList.remove('drop'); files.push(...e.dataTransfer.files); chips(); });
    $('chat-input').addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); send(); }
    });
    apply(mode);
  });
  window.YongChat = { addFile, apply, add };
})();
