#!/usr/bin/env python3
"""용용이: "용용아" 하고 부르면 듣고, Claude Code 로 생각해서, 말로 대답하는 음성 비서."""
import collections
import json
import math
import os
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from contextlib import contextmanager
from pathlib import Path

import face
import kmong
import news
import mlx_whisper
import numpy as np
import sounddevice as sd
from scipy.signal import resample_poly

HERE = Path(__file__).resolve().parent
PERSONA = (HERE / "persona.md").read_text(encoding="utf-8")
DATA = HERE / "data"  # 고객 메모 등 (git 에 올라가지 않음)
CUSTOMERS = DATA / "customers.md"
MEMO = DATA / "memo.md"  # 대표님 선호 등 오래 기억할 것

KMONG_INSTRUCTIONS = f"""아래는 대표님 사파리에 떠 있는 크몽 화면의 글자야.

크몽 메시지 화면 읽는 법
- 왼쪽 대화 목록은 대화 하나가 이런 순서로 나와: [메모] → [주문자 닉네임] → [거래중 표시(있을 때)] → [마지막 메시지] → [시간].
- [메모]는 대표님이 직접 붙인 것으로 "A01093894 케어상사일레븐" 처럼 A로 시작하는 번호(우리 쪽 고객·계정 번호)와 회사명이 들어 있어.
  한 메모에 번호가 여러 개면 (예: "A01393691 데비쓰마켓A01554358") 그 주문자와 연결된 연관 계정들이야.
- 맨 위에 있을수록, 시간이 "방금 전"에 가까울수록 최근 대화야. 오른쪽에 대화창이 열려 있으면 그 대화 내용이 전부 보여.

할 일
1. 지금 상담 중인(또는 새로 메시지를 보낸) 주문자 닉네임과 메모(계정 번호, 회사명)를 찾아.
2. {CUSTOMERS} 파일에서 그 주문자나 같은 계정 번호의 예전 기록(연관 계정, 이전 주문, 진행 상황)을 찾아봐.
3. 문의를 아래 셋 중 하나로 분류해.
   - 신규 문의: 이 주문자(연관 계정 포함)의 결제 이력이 없음.
   - 기존 문의, 구매확정 전: 결제한 주문이 아직 진행 중이거나 구매확정이 안 됨 (목록에 "거래중" 표시가 있으면 보통 여기).
   - 기존 문의, 구매확정 완료: 결제 이력은 있지만 그 주문들이 모두 구매확정(완료)됨.
   화면과 고객 기록만으로 확실하지 않으면 기억 파일의 크몽 주문관리 주소를 `python3 {HERE / "kmong.py"} read 주소` 로 읽어
   그 닉네임의 주문 상태를 확인해 (주소를 모르면 `python3 {HERE / "kmong.py"} links` 로 찾아). 그래도 모르면 "확인 필요"라고 해.
4. 화면에서 새로 알게 된 사실(닉네임, 계정 번호, 회사명, 분류, 요청 내용, 거래 상태, 금액, 마감일)을
   그 파일에 닉네임별 항목으로 짧게 추가하거나 고쳐. 파일이 없으면 만들어.
5. 대표님께 말로 보고해. 반드시 분류를 먼저 말하고 그다음 내용을 읽어 줘. 문의가 여러 건이면 한 건씩 같은 형식으로:
   "신규 문의예요. ○○님(회사명)이 이렇게 물어보셨어요: (문의 내용)."
   "기존 문의, 구매확정 전이에요. ○○님이 ... "  /  "기존 문의, 구매확정된 고객이에요. ○○님이 ... "
   문의 내용은 짧으면 손님이 쓴 말 그대로, 길면 핵심만 풀어서 읽어. 이어서 연관 계정·예전 거래와 대표님이 할 일을 한 문장으로.
   계정 번호는 길게 다 읽지 말고 "연관 계정 두 개" 처럼 요약해.
화면은 읽기만 하고 크몽에 메시지를 보내거나 클릭하지 마."""

WHISPER_MODEL = os.environ.get("YONGYONG_WHISPER", "mlx-community/whisper-large-v3-turbo")
VOICE = os.environ.get("YONGYONG_VOICE", "Yuna")
MIC_NAME = os.environ.get("YONGYONG_MIC", "Studio Display")
WORKDIR = Path(os.environ.get("YONGYONG_WORKDIR", Path.home() / "projects")).expanduser()

# 음성으로는 "허용" 버튼을 누를 수 없으니, 용용이가 묻지 않고 써도 되는 도구를 미리 정해 둔다.
# 지우기·푸시·관리자 권한처럼 되돌리기 어려운 명령은 넣지 않았다. 필요하면 .env 에서 YONGYONG_ALLOWED_TOOLS 로 바꾸기.
ALLOWED_TOOLS = os.environ.get("YONGYONG_ALLOWED_TOOLS", ",".join([
    "WebSearch", "WebFetch", "Read", "Edit", "Write", "Glob", "Grep", "TodoWrite",
    *(f"Bash({c}:*)" for c in [
        "ls", "cat", "head", "tail", "wc", "pwd", "date", "cal", "mkdir", "cp", "mv", "touch", "find", "grep",
        "git status", "git diff", "git log", "git add", "git commit", "git checkout", "git branch", "git clone",
        "git pull", "node", "npm", "npx", "python", "python3", "uv", "pip", "open", "curl",
    ]),
]))
DISALLOWED_TOOLS = "Bash(rm:*),Bash(sudo:*),Bash(git push:*),Bash(git reset:*)"
MIN_RMS = float(os.environ.get("YONGYONG_MIN_RMS", "0.01"))  # 낮출수록 작은 소리에도 반응
KMONG_POLL_SEC = int(os.environ.get("YONGYONG_KMONG_POLL", "30"))  # 0 이면 자동 감시 끔
FOLLOW_UP_SEC = 8  # 대답 후 이 시간 안에는 "용용아" 없이 바로 말해도 됨

SAMPLE_RATE = 16000  # Whisper 입력
BLOCK_SEC = 0.03
END_SILENCE_SEC = 0.8
MAX_UTTERANCE_SEC = 30
MIN_SPEECH_SEC = 0.4

# Whisper 가 "용용아"를 다르게 받아 적는 경우까지 포함
WAKE_RE = re.compile(r"(용\s?용|용\s?룡|영\s?용|용\s?영|룡\s?용)\s*(아|이|야)?[\s,.!?~]*")
RESET_RE = re.compile(r"새\s?대화|처음부터")
LOGIN_RE = re.compile(r"계정\s?연결|(클로드|클라우드|claude)\s*로그인", re.I)  # "크몽 로그인" 은 해당 없음
PANEL_TAG = re.compile(r"\[\[(날씨|뉴스|크몽)(?::\s*([^\]]*?))?\s*\]\]")
KMONG_STATUS_RE = re.compile(r"매출|결제|발송|현황|주문|정산|브리핑")
REPORTS = {"크몽": ("크몽 현황", DATA / "kmong_report.md")}
BRIEFING_TIME = os.environ.get("YONGYONG_BRIEFING_TIME", "09:00")  # 매일 아침 브리핑 (비우면 끔)
BRIEFING_PROMPT = ("아침 브리핑을 해 줘. 순서: 기본 지역 날씨, 주요 뉴스, 크몽 현황(신규 결제·발송 안 한 주문·최근 문의·이번 주/이번 달 매출). "
                   "전체 1분 안에 들을 수 있게. 화면에는 크몽 현황 보고서를 띄워.")

SHOW_FACE = os.environ.get("YONGYONG_FACE", "1") != "0"

FACE = face.Face()
BUSY = threading.Lock()  # 용용이가 한 번에 한 가지만 말하도록
ENV_FILE = HERE / ".env"
audio_q: "queue.Queue[np.ndarray]" = queue.Queue()
muted = threading.Event()


def log(msg):
    print(time.strftime("[%H:%M:%S]"), msg, flush=True)


def pick_mic():
    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] > 0 and MIC_NAME.lower() in d["name"].lower():
            return i, d
    i = sd.default.device[0]
    return i, sd.query_devices(i)


def to_16k(x, rate):
    if rate == SAMPLE_RATE:
        return x
    g = math.gcd(SAMPLE_RATE, rate)  # 저역 통과 필터를 포함한 리샘플링 (단순 보간보다 인식률이 좋음)
    return resample_poly(x, SAMPLE_RATE // g, rate // g).astype(np.float32)


def utterances(rate):
    """마이크 소리를 말 한 덩어리씩 잘라서 돌려준다 (간단한 음량 기반 감지)."""
    block_sec = BLOCK_SEC
    pre_roll = collections.deque(maxlen=int(0.3 / block_sec))
    floor = MIN_RMS / 3
    speaking, voiced, silent = False, [], 0
    while True:
        block = audio_q.get()
        rms = float(np.sqrt(np.mean(block**2)))
        threshold = max(floor * 3, MIN_RMS)
        if not speaking:
            if rms > threshold:
                speaking, voiced, silent = True, [*pre_roll, block], 0
            else:
                floor = 0.95 * floor + 0.05 * rms
                pre_roll.append(block)
            continue
        voiced.append(block)
        silent = silent + 1 if rms < threshold else 0
        if silent * block_sec >= END_SILENCE_SEC or len(voiced) * block_sec >= MAX_UTTERANCE_SEC:
            speaking = False
            pre_roll.clear()
            if (len(voiced) - silent) * block_sec >= MIN_SPEECH_SEC:
                yield to_16k(np.concatenate(voiced), rate)


def transcribe(audio):
    result = mlx_whisper.transcribe(
        audio,
        path_or_hf_repo=WHISPER_MODEL,
        language="ko",
        initial_prompt="용용아,",
        condition_on_previous_text=False,
        temperature=0.0,  # 기본값은 실패 시 무작위성을 올려 다시 시도해서 엉뚱한 외국어가 나옴
    )
    # 잡음을 억지로 받아 적은 구간은 버림
    text = "".join(
        seg["text"] for seg in result.get("segments", [])
        if seg.get("no_speech_prob", 0) < 0.6 and seg.get("avg_logprob", 0) > -1.0
    ).strip()
    letters = [c for c in text if c.isalpha()]
    hangul = sum("가" <= c <= "힣" for c in letters)
    if letters and hangul / len(letters) < 0.5:
        return ""
    return text


def for_speech(text):
    text = re.sub(r"```.*?```", " 코드는 화면에 띄워 뒀어요. ", text, flags=re.S)
    text = re.sub(r"https?://\S+", " 링크 ", text)
    text = re.sub(r"[`*#>|_\[\]]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def speak(text, then="idle"):
    """말하면서 캐릭터 입을 소리 크기에 맞춰 움직인다. 끝나면 캐릭터를 `then` 상태로."""
    print(f"\n🐉 용용이: {text}\n", flush=True)
    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "say.wav"
        subprocess.run(["say", "-v", VOICE, "-r", "200", "-o", str(wav), "--file-format=WAVE",
                        "--data-format=LEI16@22050", for_speech(text)], check=False)
        if not wav.exists():
            return
        FACE.show("speaking", text=text, env=face.envelope(wav), frame=face.FRAME_SEC)
        subprocess.run(["afplay", str(wav)], check=False)
    FACE.show(then, **({"seconds": FOLLOW_UP_SEC} if then == "listening" else {}))


@contextmanager
def deaf():
    """용용이가 말하거나 생각하는 동안에는 마이크를 무시 (자기 목소리에 반응하지 않도록)."""
    muted.set()
    try:
        yield
    finally:
        time.sleep(0.3)
        while not audio_q.empty():
            audio_q.get_nowait()
        muted.clear()


def system_prompt():
    memo = MEMO.read_text(encoding="utf-8").strip() if MEMO.exists() else "(아직 없음)"
    persona = (PERSONA.replace("{WEATHER}", str(HERE / "weather.py")).replace("{NEWS}", str(HERE / "news.py"))
               .replace("{KMONG}", str(HERE / "kmong.py")).replace("{KMONG_REPORT}", str(REPORTS["크몽"][1]))
               .replace("{TODAY}", time.strftime("%Y-%m-%d (%a)")))
    return f"{persona}\n\n기억 (파일: {MEMO})\n{memo}\n"


class Brain:
    """Claude Code(`claude -p`)를 두뇌로 사용. Claude Pro 로그인 그대로 사용한다."""

    def __init__(self, workdir=WORKDIR, remember=True):
        self.workdir = workdir
        self.remember = remember
        self.session_id = None

    def ask(self, text):
        cmd = [
            "claude", "-p", text,
            "--output-format", "json",
            "--append-system-prompt", system_prompt(),
            "--permission-mode", "acceptEdits",
            "--add-dir", str(DATA),
            "--allowedTools", ALLOWED_TOOLS,
            "--disallowedTools", DISALLOWED_TOOLS,
        ]
        if self.remember and self.session_id:
            cmd += ["--resume", self.session_id]
        try:
            p = subprocess.run(cmd, cwd=self.workdir, capture_output=True, text=True, timeout=1800)
            data = json.loads(p.stdout)
        except subprocess.TimeoutExpired:
            return "작업이 너무 오래 걸려서 멈췄어요."
        except json.JSONDecodeError:
            log(f"claude 오류: {p.stderr.strip() or p.stdout.strip()}")
            return "죄송해요, 처리하다가 문제가 생겼어요. 터미널을 확인해 주세요."
        self.session_id = data.get("session_id", self.session_id)
        for d in data.get("permission_denials") or []:
            log(f"(권한 막힘) {d.get('tool_name')} {json.dumps(d.get('tool_input', {}), ensure_ascii=False)[:120]}")
        result = data.get("result") or "처리했어요."
        if needs_login(result):
            FACE.show("login")
            return "Claude 로그인이 필요해요. 화면의 로그인 버튼을 눌러 주세요."
        return result


def needs_login(output):
    return "Not logged in" in output or "Please run /login" in output or "Invalid API key" in output


def check_login():
    """Claude Code 가 로그인돼 있는지 아주 짧은 질문으로 확인."""
    try:
        p = subprocess.run(["claude", "-p", "ok", "--max-turns", "1"], cwd=DATA,
                           capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired):
        return True  # 확인 자체가 안 되면 일단 진행하고, 실제 질문 때 다시 판단
    return not needs_login(p.stdout + p.stderr)


def login_start(_body):
    """터미널 창을 열어 `claude setup-token` 실행 → 브라우저에서 승인하면 토큰이 나온다."""
    claude = shutil.which("claude") or str(Path.home() / ".local/bin/claude")
    subprocess.run(["osascript",
                    "-e", 'tell application "Terminal" to activate',
                    "-e", f'tell application "Terminal" to do script "\\"{claude}\\" setup-token"'],
                   check=False, capture_output=True)
    return {"ok": True}


def login_token(body):
    """로그인 화면에 붙여넣은 토큰을 저장하고 바로 적용."""
    token = re.sub(r"\s+", "", str(body.get("token", "")))
    if not token.startswith("sk-ant-"):
        return {"ok": False, "error": "sk-ant- 로 시작하는 토큰을 붙여넣어 주세요."}
    old = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")
    os.environ["CLAUDE_CODE_OAUTH_TOKEN"] = token
    if not check_login():
        if old is None:
            os.environ.pop("CLAUDE_CODE_OAUTH_TOKEN")
        else:
            os.environ["CLAUDE_CODE_OAUTH_TOKEN"] = old
        return {"ok": False, "error": "이 토큰으로 로그인되지 않았어요. 다시 시도해 주세요."}
    lines = ENV_FILE.read_text().splitlines() if ENV_FILE.exists() else []
    lines = [ln for ln in lines if not ln.startswith("export CLAUDE_CODE_OAUTH_TOKEN=")]
    lines.append(f'export CLAUDE_CODE_OAUTH_TOKEN="{token}"')
    ENV_FILE.write_text("\n".join(lines) + "\n")
    ENV_FILE.chmod(0o600)

    def greet():
        with BUSY, deaf():
            speak("로그인됐어요! 이제 용용아 하고 불러 주세요.")
    threading.Thread(target=greet, daemon=True).start()
    return {"ok": True}


def report_route(body):
    title, path = REPORTS.get(str(body.get("name", "")), (None, None))
    if not path or not path.exists():
        return {"ok": False, "error": "아직 보고서가 없어요."}
    updated = time.strftime("%m월 %d일 %H:%M 작성", time.localtime(path.stat().st_mtime))
    return {"ok": True, "title": f"🧾 {title}", "updated": updated, "text": path.read_text(encoding="utf-8")}


def show_panels(answer):
    """대답 속 [[날씨:강릉]] [[뉴스:경제]] [[크몽]] 표시대로 화면 패널을 띄우고, 소리로 읽을 글만 돌려준다."""
    tags = PANEL_TAG.findall(answer)
    if tags:
        kind, arg = tags[-1]
        if kind == "날씨" and arg:
            FACE.panel("weather", place=arg)
        elif kind == "뉴스":
            FACE.panel("news", topic=arg)
        elif kind == "크몽":
            FACE.panel("report", name="크몽")
    return PANEL_TAG.sub("", answer).strip()


def briefing_loop():
    """매일 BRIEFING_TIME 에 아침 브리핑."""
    last_day = None
    while True:
        time.sleep(20)
        now = time.strftime("%H:%M")
        today = time.strftime("%Y-%m-%d")
        if now != BRIEFING_TIME or last_day == today:
            continue
        last_day = today
        log("아침 브리핑 시작")
        answer = Brain().ask(BRIEFING_PROMPT)
        with BUSY, deaf():
            speak("좋은 아침이에요, 대표님. " + show_panels(answer))


def news_route(body):
    label, items = news.fetch_news(str(body.get("topic", "")), limit=15)
    return {"ok": True, "label": label, "items": items}


def kmong_prompt(page, new_lines=None):
    prompt = KMONG_INSTRUCTIONS
    if new_lines is not None:
        prompt += ("\n\n이번에 화면에서 새로 생긴 줄은 아래와 같아. 주문자가 보낸 새 메시지나 새 주문이 아니면"
                   " (광고, 내가 보낸 메시지, 화면 이동 등) 파일만 정리하고 정확히 '없음' 이라고만 대답해.\n"
                   + new_lines)
    return prompt + "\n\n=== 크몽 화면 ===\n" + page


def kmong_watch():
    """크몽 탭을 주기적으로 읽다가 새 문의가 보이면 먼저 알려 준다."""
    brain = Brain(workdir=DATA, remember=False)
    last = None
    while True:
        time.sleep(KMONG_POLL_SEC)
        try:
            page = kmong.snapshot()
        except Exception as e:  # 사파리가 닫혀 있거나 권한이 없을 때는 조용히 다시 시도
            log(f"(크몽 읽기 실패) {e}")
            continue
        if not page:
            continue
        if last is None or kmong.fingerprint(page) == kmong.fingerprint(last):
            last = page
            continue
        new_lines = kmong.changes(last, page)
        last = page
        if not new_lines:
            continue
        log("크몽 화면 변화 감지 → 확인 중")
        report = brain.ask(kmong_prompt(page, new_lines)).strip()  # 캐릭터 상태는 건드리지 않음
        if report and report.strip(" .'\"") != "없음":
            with BUSY, deaf():
                speak("크몽 알림이에요. " + report)


def kmong_once():
    """음성 없이 지금 크몽 화면을 한 번 요약 (테스트용: ./run.sh --kmong)."""
    DATA.mkdir(exist_ok=True)
    try:
        page = kmong.snapshot()
    except kmong.SafariError as e:
        print(e)
        return
    if not page:
        print("사파리에 크몽(kmong.com) 탭이 보이지 않아요.")
        return
    print(f"크몽 화면 {len(page)}자 읽음. 요약 중...")
    speak(Brain(workdir=DATA, remember=False).ask(kmong_prompt(page)))


def main():
    WORKDIR.mkdir(parents=True, exist_ok=True)
    DATA.mkdir(exist_ok=True)
    dev, info = pick_mic()
    rate = int(info["default_samplerate"])
    log(f"마이크: {info['name']} ({rate}Hz) / 음성인식: {WHISPER_MODEL} / 작업 폴더: {WORKDIR}")
    if SHOW_FACE:
        FACE.routes["/login/start"] = login_start
        FACE.routes["/login/token"] = login_token
        FACE.routes["/news"] = news_route
        FACE.routes["/report"] = report_route
        try:
            FACE.start()
        except OSError:  # 이미 다른 창에서 용용이가 켜져 있음 → 캐릭터 창만 다시 열고 끝냄
            print("용용이가 이미 켜져 있어요. 캐릭터 창을 다시 열게요.")
            subprocess.run(["open", f"http://127.0.0.1:{face.PORT}/"], check=False)
            return
    FACE.show("thinking")
    log("음성인식 모델 준비 중... (처음 한 번은 다운로드 때문에 몇 분 걸려요)")
    transcribe(np.zeros(SAMPLE_RATE, dtype=np.float32))

    brain = Brain()

    log("Claude 로그인 확인 중...")
    logged_in = check_login()
    log("Claude 로그인 " + ("확인됨" if logged_in else "필요"))
    if not logged_in:
        log("Claude 로그인이 필요해요 → 캐릭터 창의 [로그인] 버튼을 눌러 주세요.")
    if KMONG_POLL_SEC > 0:
        threading.Thread(target=kmong_watch, daemon=True).start()
    if re.fullmatch(r"\d{2}:\d{2}", BRIEFING_TIME):
        threading.Thread(target=briefing_loop, daemon=True).start()
        log(f"아침 브리핑: 매일 {BRIEFING_TIME}")
        log(f"크몽 감시 시작 ({KMONG_POLL_SEC}초마다 사파리 크몽 탭 확인)")

    def on_audio(indata, frames, t, status):
        if not muted.is_set():
            audio_q.put(indata[:, 0].copy())

    with sd.InputStream(device=dev, channels=1, samplerate=rate, dtype="float32",
                        blocksize=int(rate * BLOCK_SEC), callback=on_audio):
        with deaf():
            time.sleep(2 if SHOW_FACE else 0)  # 캐릭터 창이 뜰 시간
            if logged_in:
                speak("용용이 준비됐어요. 용용아 하고 불러 주세요.")
            else:
                speak("Claude 계정 연결이 필요해요. 화면의 로그인 버튼을 눌러 주세요.", then="login")
        awake_until = 0.0
        for audio in utterances(rate):
            with BUSY, deaf():
                text = transcribe(audio)
                if not text:
                    continue
                m = WAKE_RE.search(text)
                if m:
                    command = text[m.end():].strip()
                elif time.time() < awake_until:
                    command = text
                else:
                    log(f"(무시) {text}")
                    continue

                log(f"🎤 {text}")
                if not command:
                    speak("네.", then="listening")
                    awake_until = time.time() + FOLLOW_UP_SEC
                    continue
                if LOGIN_RE.search(command):
                    speak("화면에 Claude 계정 연결 창을 띄웠어요. 로그인 시작 버튼을 눌러 주세요.", then="login")
                    continue
                if RESET_RE.search(command) and len(command) < 15:
                    brain.session_id = None
                    speak("새 대화를 시작할게요.", then="listening")
                    awake_until = time.time() + FOLLOW_UP_SEC
                    continue

                speak("네, 잠시만요.", then="thinking")
                if "크몽" in command and not KMONG_STATUS_RE.search(command):  # 상담창 질문일 때만 지금 화면을 붙임
                    try:
                        page = kmong.snapshot()
                        if page:
                            command = f"{command}\n\n{kmong_prompt(page)}"
                    except kmong.SafariError as e:
                        speak(str(e))
                        continue
                speak(show_panels(brain.ask(command)), then="listening")
                awake_until = time.time() + FOLLOW_UP_SEC


if __name__ == "__main__":
    try:
        kmong_once() if "--kmong" in sys.argv else main()
    except KeyboardInterrupt:
        print("\n용용이를 종료합니다.")
        sys.exit(0)
