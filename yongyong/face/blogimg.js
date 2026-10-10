// 블로그용 이미지 카드 그리기 (1080×1080 PNG). 용용이가 초안의 "## 이미지" 줄로 내용을 정하면 여기서 그린다.
(() => {
  const W = 1080, H = 1080;
  const FONT = '-apple-system, "Apple SD Gothic Neo", "Noto Sans KR", sans-serif';
  const THEMES = [
    ['#0f1e4a', '#1d6b74', '#7ef0c0'], ['#1b1340', '#5b2a86', '#ffd166'], ['#0b2a2a', '#1f7a5a', '#b8f2a0'],
    ['#2a1430', '#b23a48', '#ffd6a5'], ['#10243e', '#2f5d8a', '#9ad1ff'],
  ];

  function wrap(ctx, text, maxW) {
    const lines = [];
    for (const para of String(text).split('\n')) {
      let line = '';
      for (const ch of para) {
        if (ctx.measureText(line + ch).width > maxW && line) { lines.push(line); line = ch.trim() ? ch : ''; }
        else line += ch;
      }
      lines.push(line);
    }
    return lines;
  }

  function block(ctx, text, x, y, maxW, size, weight, color, lh = 1.3) {
    ctx.font = `${weight} ${size}px ${FONT}`;
    ctx.fillStyle = color;
    const lines = wrap(ctx, text, maxW);
    lines.forEach((l, i) => ctx.fillText(l, x, y + i * size * lh));
    return y + lines.length * size * lh;
  }

  function frame(ctx, t) {
    const g = ctx.createLinearGradient(0, 0, W, H);
    g.addColorStop(0, t[0]); g.addColorStop(1, t[1]);
    ctx.fillStyle = g; ctx.fillRect(0, 0, W, H);
    ctx.globalAlpha = 0.08; ctx.fillStyle = '#fff';
    ctx.beginPath(); ctx.arc(W * 0.9, H * 0.12, 260, 0, Math.PI * 2); ctx.fill();
    ctx.beginPath(); ctx.arc(W * 0.05, H * 0.95, 200, 0, Math.PI * 2); ctx.fill();
    ctx.globalAlpha = 1;
    ctx.fillStyle = t[2]; ctx.fillRect(90, 90, 120, 12);
    ctx.font = `600 30px ${FONT}`; ctx.fillStyle = 'rgba(255,255,255,.75)';
    ctx.fillText('스마트로보코리아 · 크몽', 90, H - 90);
  }

  function draw(spec, i) {
    const c = document.createElement('canvas'); c.width = W; c.height = H;
    const ctx = c.getContext('2d'); ctx.textBaseline = 'top';
    const t = THEMES[i % THEMES.length], [head, ...rest] = spec.parts;
    frame(ctx, t);
    const k = spec.kind;
    if (/표지|커버|cover/i.test(k)) {
      let y = block(ctx, head || '', 90, 300, W - 180, 92, 800, '#fff', 1.25);
      if (rest[0]) block(ctx, rest[0], 90, y + 40, W - 180, 44, 500, t[2]);
    } else if (/단계|순서|step/i.test(k)) {
      let y = block(ctx, head || '', 90, 150, W - 180, 64, 800, '#fff');
      rest.slice(0, 4).forEach((s, n) => {
        y += 40;
        ctx.fillStyle = t[2]; ctx.beginPath(); ctx.arc(130, y + 32, 40, 0, Math.PI * 2); ctx.fill();
        ctx.font = `800 40px ${FONT}`; ctx.fillStyle = t[0]; ctx.textAlign = 'center'; ctx.fillText(String(n + 1), 130, y + 12); ctx.textAlign = 'left';
        y = Math.max(y + 80, block(ctx, s.replace(/^\d+\s*단계\s*[:：]?\s*/, ''), 200, y + 8, W - 290, 42, 600, '#fff'));
      });
    } else if (/체크|목록|check/i.test(k)) {
      let y = block(ctx, head || '', 90, 150, W - 180, 64, 800, '#fff');
      rest.slice(0, 5).forEach((s) => {
        y += 34;
        block(ctx, '✓', 90, y, 60, 46, 800, t[2]);
        y = block(ctx, s, 160, y + 2, W - 250, 42, 600, '#fff');
      });
    } else if (/안내|상담|cta/i.test(k)) {
      let y = block(ctx, head || '', 90, 330, W - 180, 66, 800, '#fff', 1.3);
      ctx.fillStyle = t[2]; ctx.fillRect(90, y + 50, 560, 96);
      block(ctx, rest[0] || '크몽에서 상담하기 →', 120, y + 74, 520, 44, 800, t[0]);
    } else {  // 강조 (한 문장)
      block(ctx, '“', 90, 160, 200, 200, 800, t[2]);
      block(ctx, spec.parts.join(' '), 90, 380, W - 180, 62, 700, '#fff', 1.4);
    }
    return c;
  }

  async function copy(canvas) {
    const blob = await new Promise((r) => canvas.toBlob(r, 'image/png'));
    await navigator.clipboard.write([new ClipboardItem({ 'image/png': blob })]);
  }

  function save(canvas, name) {
    const a = document.createElement('a');
    a.href = canvas.toDataURL('image/png'); a.download = name; a.click();
  }

  window.YongBlogImages = { draw, copy, save };
})();
