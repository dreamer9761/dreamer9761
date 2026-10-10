#!/usr/bin/env python3
"""블로그 글쓰기 화면 자동 채우기: 사파리(대표님 로그인)로 네이버 블로그·티스토리 글쓰기를 열고 제목과 본문을 붙여넣는다.
발행 버튼은 누르지 않는다 — 대표님이 확인하고 직접 발행.
  python3 blogpost.py naver   (또는 tistory)   가장 최근 초안(data/blog/*.md)으로 채우기"""
import html
import json
import re
import subprocess
import sys
import time
from pathlib import Path

from kmong import _NEW_WINDOW, _RUN_JS, SafariError, _osa, _wait

BLOG_DIR = Path(__file__).resolve().parent / "data" / "blog"
EDITORS = {"naver": "https://blog.naver.com/GoBlogWrite.naver"}  # 티스토리는 블로그 주소가 필요

# 페이지와 그 안의 iframe 들까지 뒤져서 편집기 요소를 찾고, '붙여넣기' 이벤트로 내용을 넣는다
_JS_EDITOR = r"""((cmd, title, html, text) => {
  const docs = [];
  const walk = (d) => { docs.push(d); d.querySelectorAll('iframe').forEach(f => { try { if (f.contentDocument) walk(f.contentDocument); } catch (e) {} }); };
  walk(document);
  const find = (sels) => { for (const s of sels) for (const d of docs) { const e = d.querySelector(s); if (e) return e; } return null; };
  const titleEl = find(['.se-documentTitle .se-text-paragraph', '.se-title-text .se-text-paragraph', '#post-title-inp', 'textarea.textarea_tit', 'input[placeholder*="제목"]', 'textarea[placeholder*="제목"]']);
  const bodyEl = find(['.se-component.se-text .se-text-paragraph', '.se-section-text .se-text-paragraph', '#tinymce', '.mce-content-body', '[contenteditable=true].editor', '.ProseMirror']);
  if (cmd === 'ready') {
    const all = docs.map(d => d.body ? d.body.innerText : '').join('\n');
    if (/작성\s*중인\s*글이\s*있|이어서\s*작성/.test(all)) {   // '임시 저장 글 이어쓰기' 안내는 새로 쓰기로
      for (const d of docs) { const b = Array.from(d.querySelectorAll('button')).find(x => /^(취소|새로\s*쓰기)$/.test(x.innerText.trim())); if (b) { b.click(); return 'dismissed'; } }
    }
    if (/로그인/.test(all.slice(0, 400)) && !titleEl) return 'login';
    return titleEl && bodyEl ? 'ready' : 'wait';
  }
  const paste = (el, h, t) => {
    el.focus();
    const dt = new DataTransfer();
    if (h) dt.setData('text/html', h);
    dt.setData('text/plain', t);
    el.dispatchEvent(new ClipboardEvent('paste', { clipboardData: dt, bubbles: true, cancelable: true }));
  };
  const put = (el, h, t) => {
    if (el.tagName === 'TEXTAREA' || el.tagName === 'INPUT') {
      const proto = el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
      Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, t);
      el.dispatchEvent(new Event('input', { bubbles: true }));
      return;
    }
    const before = el.innerText.length;
    paste(el, h, t);
    if (el.innerText.length === before) {          // 붙여넣기를 안 받는 편집기면 직접 넣기
      if (h) el.innerHTML = h; else el.innerText = t;
      el.dispatchEvent(new Event('input', { bubbles: true }));
    }
  };
  if (cmd === 'fill') {
    if (!titleEl || !bodyEl) return 'noeditor';
    put(titleEl, '', title);
    put(bodyEl, html, text);
    return 'filled';
  }
  return 'bad';
})(%s, %s, %s, %s)"""


def md_to_html(md):
    out, in_list = [], False
    for line in md.splitlines():
        line = line.rstrip()
        item = re.match(r"\s*[-*]\s+(.*)", line)
        if not item and in_list:
            out.append("</ul>")
            in_list = False
        text = html.escape(item.group(1) if item else re.sub(r"^#+\s*", "", line))
        text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
        if item:
            out.append(("<ul>" if not in_list else "") + "<li>%s</li>" % text)
            in_list = True
        elif re.match(r"#{1,4}\s", line):
            out.append("<h3>%s</h3>" % text)
        elif line.strip():
            out.append("<p>%s</p>" % text)
        else:
            out.append("<p><br></p>")
    if in_list:
        out.append("</ul>")
    return "".join(out)


def md_to_text(md):
    return re.sub(r"\*\*(.+?)\*\*", r"\1", re.sub(r"^#+\s*", "", md, flags=re.M))


def fill(site, title, body_md, tags, tistory=""):
    """글쓰기 화면을 열어 제목·본문을 채운다. 태그는 클립보드에 넣어 둔다 (발행 창의 태그 칸에 붙여넣기)."""
    url = EDITORS.get(site) or ("https://%s.tistory.com/manage/newpost" % tistory if tistory else "")
    if not url:
        return "티스토리 블로그 주소를 먼저 알려 주세요 (블로그 화면의 티스토리 탭)."
    win = _osa(_NEW_WINDOW, url)
    _wait(win, 25, lambda ready, logged_in, host: True)
    state = "wait"
    for _ in range(30):  # 편집기가 뜰 때까지
        state = _osa(_RUN_JS, win, _JS_EDITOR % (json.dumps("ready"), '""', '""', '""'))
        if state in ("ready", "login"):
            break
        time.sleep(1)
    if state == "login":
        return "%s에 로그인이 안 돼 있어요. 열린 사파리 창에서 로그인한 뒤 다시 말씀해 주세요." % ("네이버" if site == "naver" else "티스토리")
    if state != "ready":
        return "글쓰기 화면의 입력 칸을 찾지 못했어요. 열린 창에 [본문 복사]로 붙여넣어 주세요."
    r = _osa(_RUN_JS, win, _JS_EDITOR % (json.dumps("fill"), json.dumps(title), json.dumps(md_to_html(body_md)),
                                          json.dumps(md_to_text(body_md))))
    if r != "filled":
        return "제목·본문 칸을 찾지 못했어요. 열린 창에 [본문 복사]로 붙여넣어 주세요."
    subprocess.run(["pbcopy"], input=tags.encode("utf-8"), check=False)
    return ("%s 글쓰기 화면에 제목과 본문을 넣었어요. [이미지 N] 자리에 이미지를 넣고, 발행 창의 태그 칸에 붙여넣기(⌘V) 한 뒤 "
            "확인하고 발행해 주세요." % ("네이버 블로그" if site == "naver" else "티스토리"))


def latest(site):
    files = sorted(BLOG_DIR.glob("*.md"))
    if not files:
        raise SafariError("아직 블로그 초안이 없어요.")
    text = files[-1].read_text(encoding="utf-8")
    name = "네이버" if site == "naver" else "티스토리"
    m = re.search(r"^##\s*" + name + r"\s*\n(.*?)(?=^##\s|\Z)", text, re.S | re.M)
    part = m.group(1) if m else ""
    title = re.search(r"^제목\s*[:：]\s*(.+)$", part, re.M)
    tags = re.search(r"^태그\s*[:：]\s*(.+)$", part, re.M)
    body = part.split("\n---", 1)[1] if "\n---" in part else part
    return (title.group(1).strip() if title else ""), body.strip(), (tags.group(1).strip() if tags else "")


if __name__ == "__main__":
    try:
        site = (sys.argv[1:] or ["naver"])[0]
        t, b, g = latest(site)
        print(fill(site, t, b, g, sys.argv[2] if len(sys.argv) > 2 else ""))
    except SafariError as e:
        print(e)
        sys.exit(1)
