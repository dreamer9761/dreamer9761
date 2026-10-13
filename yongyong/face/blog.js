// 블로그 초안 패널: 용용이가 쓴 이번 주 글을 네이버·티스토리용으로 보여 주고, 복사해서 대표님이 직접 올린다
(() => {
  const $ = (id) => document.getElementById(id);
  const post = (path, data) => fetch(path, {
    method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Yongyong': '1' }, body: JSON.stringify(data || {}),
  }).then((r) => r.json());
  let data = null, site = 'naver';

  function render() {
    const d = data && data[site];
    document.querySelectorAll('.blog-tab').forEach((b) => b.classList.toggle('on', b.dataset.site === site));
    $('blog-title').value = d ? d.title : '';
    $('blog-tags').textContent = d && d.tags ? d.tags : '';
    $('blog-body').innerHTML = d ? window.YongReport.markdown(d.body) : '<p>아직 초안이 없어요. "용용아, 블로그 글 써 줘" 라고 해 보세요.</p>';
    $('blog-tistory').hidden = site !== 'tistory';
    images();
  }

  function images() {
    const box = $('blog-images');
    box.innerHTML = '';
    const list = (data && data.images) || [];
    $('blog-images-wrap').hidden = !list.length;
    list.forEach((spec, i) => {
      const canvas = window.YongBlogImages.draw(spec, i);
      const name = `블로그_${(data.updated || '').slice(0, 10)}_${i + 1}.png`;
      const card = document.createElement('div');
      card.className = 'blog-img';
      const img = new Image(); img.src = canvas.toDataURL('image/png'); img.alt = spec.parts.join(' ');
      const save = document.createElement('button'); save.textContent = `이미지 ${i + 1} 저장`;
      save.onclick = () => { window.YongBlogImages.save(canvas, name); $('blog-msg').textContent = `${name} 을(를) 다운로드 폴더에 저장했어요.`; };
      const copy = document.createElement('button'); copy.textContent = '복사'; copy.className = 'ghost';
      copy.onclick = async () => {
        try { await window.YongBlogImages.copy(canvas); $('blog-msg').textContent = `이미지 ${i + 1} 을(를) 복사했어요. 글쓰기 화면의 [이미지 ${i + 1}] 자리에 붙여넣기(⌘V) 하세요.`; }
        catch (e) { $('blog-msg').textContent = '복사가 안 되면 [저장]을 눌러 다운로드 폴더에서 끌어다 넣어 주세요.'; }
      };
      card.append(img, save, copy);
      box.appendChild(card);
    });
  }

  function close() {
    $('blog').hidden = true;
    if (['weather', 'news', 'report', 'draft', 'tpl', 'notices', 'naver'].every((id) => $(id).hidden)) document.documentElement.classList.remove('has-side');
  }

  async function show() {
    for (const id of ['weather', 'news', 'report', 'draft', 'tpl', 'notices', 'naver']) $(id).hidden = true;
    $('blog').hidden = false;
    document.documentElement.classList.add('has-side');
    $('blog-msg').textContent = '';
    try {
      const r = await post('/blog');
      data = r.ok ? r : null;
      $('blog-updated').textContent = r.ok ? r.updated : '';
      $('blog-tistory-name').value = r.tistory || '';
    } catch (e) { data = null; }
    render();
  }

  async function copy(text, html, what) {
    try {
      if (html && window.ClipboardItem) {
        await navigator.clipboard.write([new ClipboardItem({
          'text/html': new Blob([html], { type: 'text/html' }), 'text/plain': new Blob([text], { type: 'text/plain' }) })]);
      } else await navigator.clipboard.writeText(text);
      $('blog-msg').textContent = `${what} 복사했어요. 글쓰기 화면에 붙여넣기(⌘V) 하세요.`;
    } catch (e) { $('blog-msg').textContent = '복사하지 못했어요: ' + e.message; }
  }

  function openEditor() {
    if (site === 'naver') { window.open('https://blog.naver.com/GoBlogWrite.naver', '_blank'); return; }
    const name = $('blog-tistory-name').value.trim().replace(/^https?:\/\//, '').replace(/\.tistory\.com.*$/, '');
    if (!name) { $('blog-msg').textContent = '티스토리 블로그 주소(○○○.tistory.com 의 ○○○)를 먼저 넣어 주세요.'; return; }
    post('/mode', { tistory: name });
    window.open(`https://${name}.tistory.com/manage/newpost`, '_blank');
  }

  async function autofill() {
    $('blog-msg').textContent = '글쓰기 화면을 열어 채우는 중이에요… (30초 정도)';
    $('blog-fill').disabled = true;
    try { const r = await post('/blog/fill', { site }); $('blog-msg').textContent = r.message; }
    catch (e) { $('blog-msg').textContent = '채우지 못했어요.'; }
    $('blog-fill').disabled = false;
  }

  function saveAll() {
    document.querySelectorAll('#blog-images .blog-img button:not(.ghost)').forEach((b, i) => setTimeout(() => b.click(), i * 400));
  }

  document.addEventListener('DOMContentLoaded', () => {
    $('blog-close').onclick = close;
    $('blog-fill').onclick = autofill;
    $('blog-save-all').onclick = saveAll;
    document.querySelectorAll('.blog-tab').forEach((b) => b.onclick = () => { site = b.dataset.site; render(); });
    $('blog-open').onclick = openEditor;
    $('blog-copy-title').onclick = () => copy($('blog-title').value, '', '제목을');
    $('blog-copy-body').onclick = () => copy($('blog-body').innerText, $('blog-body').innerHTML, '본문을(서식 포함)');
    $('blog-copy-tags').onclick = () => copy($('blog-tags').textContent, '', '태그를');
  });
  window.YongBlog = { show, close };
})();
