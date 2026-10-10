#!/usr/bin/env python3
"""용용이: "용용아" 하고 부르면 듣고, Claude Code 로 생각해서, 말로 대답하는 음성 비서."""
import collections
import json
import math
import os
import queue
import random
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
import blogpost
import genie
import kmong
import youtube
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
3-1. 셀러닥터 허브에서 이 고객의 결제 금액과 계정 현황을 확인해: `python3 {HERE / "hub.py"} search 닉네임` (계정 번호가 있으면 번호로도).
   기억 파일에 "허브 고객 검색 주소"가 있으면 그 주소를 search 뒤에 붙여. 없으면 `python3 {HERE / "hub.py"} links` 로 고객 검색 화면을 찾아 기억 파일에 적어.
   허브에 로그인이 안 돼 있다고 나오면 그 사실만 짧게 말하고 넘어가.
4. 화면에서 새로 알게 된 사실(닉네임, 계정 번호, 회사명, 분류, 요청 내용, 거래 상태, 금액, 마감일, 허브의 결제 금액·계정 현황)을
   그 파일에 닉네임별 항목으로 짧게 추가하거나 고쳐. 파일이 없으면 만들어.
5. 대표님께 말로 보고해. 반드시 분류를 먼저 말하고 그다음 내용을 읽어 줘. 문의가 여러 건이면 한 건씩 같은 형식으로:
   "신규 문의예요. ○○님(회사명)이 이렇게 물어보셨어요: (문의 내용)."
   "기존 문의, 구매확정 전이에요. ○○님이 ... "  /  "기존 문의, 구매확정된 고객이에요. ○○님이 ... "
   문의 내용은 짧으면 손님이 쓴 말 그대로, 길면 핵심만 풀어서 읽어.
   이어서 허브에서 확인한 결제 금액·계정 현황(예: "지금까지 결제 ○원, 계정 활성"), 연관 계정·예전 거래, 대표님이 할 일을 한두 문장으로.
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
        "git pull", "node", "npm", "npx", "python", "python3", "uv", "pip", "curl",
    ]),
]))
DISALLOWED_TOOLS = ",".join([
    "Bash(rm:*)", "Bash(sudo:*)", "Bash(git push:*)", "Bash(git reset:*)",
    # 음악은 지니로만 (애플 뮤직 앱이 대신 열리지 않도록)
    "Bash(open -a Music:*)", "Bash(open -a \"Music\":*)", "Bash(open music:*)", "Bash(open -b com.apple.Music:*)",
])
MIN_RMS = float(os.environ.get("YONGYONG_MIN_RMS", "0.01"))  # 낮출수록 작은 소리에도 반응
KMONG_POLL_SEC = int(os.environ.get("YONGYONG_KMONG_POLL", "600"))  # 새 문의 확인 주기(초), 0 이면 끔
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
PANEL_TAG = re.compile(r"\[\[(날씨|뉴스|크몽|답변|블로그)(?::\s*([^\]]*?))?\s*\]\]")
DRAFT = DATA / "kmong_draft.md"  # 크몽 답변 초안 (용용이가 쓰고, 화면에서 고쳐서 크몽 입력창에 넣음)
KMONG_STATUS_RE = re.compile(r"매출|결제|발송|현황|주문|정산|브리핑|상담|답변|답장|초안")  # 이런 요청엔 열린 화면 요약을 붙이지 않음
REPORTS = {"크몽": ("크몽 현황", DATA / "kmong_report.md")}
BRIEFING_TIME = os.environ.get("YONGYONG_BRIEFING_TIME", "09:00")  # 매일 아침 브리핑 (비우면 끔)
BRIEFING_PROMPT = ("아침 브리핑을 해 줘. 순서: 기본 지역 날씨, 주요 뉴스, 크몽 현황(신규 결제·발송 안 한 주문·최근 문의·이번 주/이번 달 매출). "
                   "전체 1분 안에 들을 수 있게. 화면에는 크몽 현황 보고서를 띄워.")

SHOW_FACE = os.environ.get("YONGYONG_FACE", "1") != "0"

FACE = face.Face()
SETTINGS = DATA / "settings.json"
# input: voice(음성) | text(글자로 입력), speak: 대답을 소리로도, alarm: 기상 음악 시각("" 이면 끔)
MODE = {"input": "voice", "speak": True, "alarm": os.environ.get("YONGYONG_ALARM_TIME", "07:00"), "region": "",
        "music": "genie",  # music: 기본 음악 서비스 genie | youtube
        "blog": "mon 10:00", "tistory": ""}  # blog: 매주 블로그 초안 쓰는 요일·시각 ("" 이면 끔)
MUSIC = threading.Event()  # 지니 음악이 나오는 중 → 마이크 대신 텍스트로만 입력 받음


def input_mode():
    """실제로 쓰는 입력 방식. 음악이 나오는 동안은 노래 소리를 말로 착각하지 않도록 텍스트만."""
    return "text" if MUSIC.is_set() else MODE["input"]


def publish_mode():
    FACE.mode({**MODE, "input": input_mode(), "music": MUSIC.is_set()})


def set_music(on):
    if on == MUSIC.is_set():
        return
    MUSIC.set() if on else MUSIC.clear()
    log("🎵 음악 재생 중 → 텍스트로만 입력" if on else "🎵 음악 끝 → 원래 입력 방식(%s)" % ("음성" if MODE["input"] == "voice" else "텍스트"))
    publish_mode()


MUSIC_QUEUE = []  # 이어서 틀 곡 ("가수 곡제목"). 지니 '선택 듣기'가 안 될 때 한 곡씩 이어 틀기용


def play_next():
    """대기열의 다음 곡을 튼다. 틀었으면 True."""
    while MUSIC_QUEUE:
        song = MUSIC_QUEUE.pop(0)
        try:
            result = genie.play(song)
        except Exception as e:
            result = f"지니를 열지 못했어요: {e}"
        log(f"🎵 다음 곡 ({len(MUSIC_QUEUE)}곡 남음): {result.split(' 플레이어 창이 안 뜨')[0]}")
        if "재생을 시작" in result:
            return True
    return False


def music_watch():
    """곡이 끝나면(플레이어가 멈추거나 닫힘) 대기열의 다음 곡을 틀고, 다 끝나면 입력 방식을 되돌린다."""
    quiet = 0
    while True:
        time.sleep(8)
        if not MUSIC.is_set():
            quiet = 0
            continue
        try:
            playing = "playing" in (genie.player_state(), youtube.state())
        except Exception:  # 사파리를 못 읽으면 다음에 다시
            continue
        quiet = 0 if playing else quiet + 1
        if quiet >= 2:  # 16초 넘게 조용하면 곡이 끝난 것으로 봄
            quiet = 0
            if not play_next():
                set_music(False)


WAKE_SONGS = [  # 기상 음악 (지니에서 검색할 걸그룹 노래, 매일 다른 곡)
    "아이브 LOVE DIVE", "아이브 해야", "뉴진스 Hype Boy", "뉴진스 Super Shy", "르세라핌 ANTIFRAGILE",
    "에스파 Supernova", "에스파 Whiplash", "트와이스 TT", "트와이스 FANCY", "레드벨벳 빨간 맛", "있지 달라달라",
    "(여자)아이들 퀸카", "블랙핑크 뚜두뚜두", "소녀시대 다시 만난 세계", "아일릿 Magnetic", "키스오브라이프 Midas Touch",
    "베이비몬스터 SHEESH", "오마이걸 살짝 설렜어", "마마무 HIP", "스테이씨 ASAP",
]
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


def speak(text, then="idle", chat=True):
    """말하면서 캐릭터 입을 소리 크기에 맞춰 움직인다. 끝나면 캐릭터를 `then` 상태로.
    대답 소리를 꺼 두었으면(텍스트 대화용) 화면 대화창에만 보여 준다."""
    print(f"\n🐉 용용이: {text}\n", flush=True)
    if then == "listening" and input_mode() == "text":
        then = "idle"
    if chat:
        FACE.chat("yongyong", text)
    if not MODE["speak"]:
        FACE.show(then if then != "listening" else "idle")
        return
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
               .replace("{KMONG}", str(HERE / "kmong.py")).replace("{KMONG_REPORT}", str(REPORTS["크몽"][1])).replace("{SALES}", str(DATA / "sales.md")).replace("{GENIE}", str(HERE / "genie.py")).replace("{HUB}", str(HERE / "hub.py"))
               .replace("{DRAFT}", str(DRAFT)).replace("{BLOG_DIR}", str(BLOG_DIR)).replace("{TEMPLATES}", str(DATA / "kmong_templates.md"))
               .replace("{TODAY}", time.strftime("%Y-%m-%d (%a)")))
    return f"{persona}\n\n기억 (파일: {MEMO})\n{memo}\n"


class Brain:
    """Claude Code(`claude -p`)를 두뇌로 사용. Claude Pro 로그인 그대로 사용한다."""

    def __init__(self, workdir=WORKDIR, remember=True):
        self.workdir = workdir
        self.remember = remember
        self.session_id = None

    def ask(self, text, tools=True):
        cmd = [
            "claude", "-p", text,
            "--output-format", "json",
            "--append-system-prompt", system_prompt(),
            "--permission-mode", "acceptEdits",
            "--add-dir", str(DATA),
        ]
        if tools:
            cmd += ["--allowedTools", ALLOWED_TOOLS, "--disallowedTools", DISALLOWED_TOOLS]
        else:  # 생각만 하고 아무 도구도 쓰지 않음
            cmd += ["--disallowedTools", "Bash,WebSearch,WebFetch,Read,Edit,Write,Glob,Grep,Task,TodoWrite"]
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


BRAIN = Brain()  # 대화를 이어 가는 두뇌 (음성·텍스트 공용)


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
            if MODE.get("region") != arg:
                MODE["region"] = arg
                mode_route({})
        elif kind == "뉴스":
            FACE.panel("news", topic=arg)
        elif kind == "크몽":
            FACE.panel("report", name="크몽")
        elif kind == "답변":
            FACE.panel("draft")
        elif kind == "블로그":
            FACE.panel("blog")
    return PANEL_TAG.sub("", answer).strip()


def briefing():
    log("아침 브리핑 시작")
    answer = Brain().ask(BRIEFING_PROMPT)
    with BUSY, deaf():
        speak("좋은 아침이에요, 대표님. " + show_panels(answer))


def wake_up():
    """기상 음악: 지니에서 걸그룹 노래를 작은 소리로 틀고 점점 키운다."""
    state_file = DATA / "alarm.json"
    try:
        last = json.loads(state_file.read_text()).get("song")
    except (OSError, ValueError):
        last = None
    songs = random.sample([x for x in WAKE_SONGS if x != last], 10)  # 10곡 연속, 어제 첫 곡은 빼고
    song = songs[0]
    state_file.write_text(json.dumps({"song": song, "date": time.strftime("%Y-%m-%d")}, ensure_ascii=False))
    log(f"⏰ 기상 음악: {song}")
    with BUSY, deaf():
        genie.volume(35)
        speak("좋은 아침이에요, 대표님! 일어날 시간이에요.")
    try:
        if MODE.get("music") == "youtube":
            ok, _, msg = youtube.play("걸그룹 히트곡", 10, views=True)
            result = "재생을 시작" if ok else msg
        else:
            MUSIC_QUEUE[:] = songs
            result = "재생을 시작" if play_next() else "지니에서 재생하지 못했어요."
    except (kmong.SafariError, subprocess.TimeoutExpired, ValueError) as e:
        result = f"지니를 열지 못했어요: {e}"
    if "재생을 시작" not in result:
        with BUSY, deaf():
            speak("기상 음악을 틀지 못했어요. " + result.split(" 플레이어 창이 안 뜨")[0])
        return
    set_music(True)
    for level in (45, 55, 65):  # 1분 30초에 걸쳐 소리를 조금씩 키움
        time.sleep(30)
        genie.volume(level)


IDLE_MIN = int(os.environ.get("YONGYONG_IDLE_MIN", "10"))  # 맥을 이만큼 안 쓰면 대기 화면 (0 이면 끔)


def system_idle_seconds():
    """맥 전체에서 마지막으로 키보드·마우스를 쓴 뒤 지난 시간(초). 다른 앱에서 일하는 것도 포함."""
    out = subprocess.run(["ioreg", "-c", "IOHIDSystem", "-d", "4"], capture_output=True, text=True).stdout
    m = re.search(r'"HIDIdleTime"\s*=\s*(\d+)', out)
    return int(m.group(1)) / 1e9 if m else 0.0


def idle_watch():
    """대기 화면은 맥을 정말 아무도 안 쓸 때만. 용용이가 일하는 중이거나 키보드·마우스를 쓰면 바로 닫음."""
    shown = False
    while True:
        time.sleep(15)
        try:
            idle = system_idle_seconds()
        except OSError:
            continue
        working = BUSY.locked() or _refreshing.locked()
        if not shown and idle >= IDLE_MIN * 60 and not working:
            FACE.panel("dash", on=True)
            shown = True
        elif shown and (idle < 20 or BUSY.locked()):
            FACE.panel("dash", on=False)
            shown = False


BLOG_DIR = DATA / "blog"
WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
BLOG_PROMPT = "이번 주 블로그 글 초안을 써 줘. 화면에 띄울 수 있게 대답 끝에 [[블로그]] 를 붙여."


def blog_week():
    """매주 정해진 요일·시각에 블로그 초안을 만들고 알려 준다 (올리기는 대표님이 직접)."""
    log("📝 이번 주 블로그 초안 쓰는 중")
    answer = Brain(remember=False).ask(BLOG_PROMPT)
    with BUSY, deaf():
        speak(show_panels(answer))
        speak("네이버 글쓰기 화면에 미리 채워 둘게요.", then="thinking")
        msg = blog_fill("naver")  # 발행 직전까지 준비해 두고, 발행은 대표님이 확인 후
        log(f"📝 {msg}")
        speak(msg)


def blog_route(_body):
    files = sorted(BLOG_DIR.glob("*.md")) if BLOG_DIR.exists() else []
    if not files:
        return {"ok": False, "tistory": MODE.get("tistory", "")}
    text = files[-1].read_text(encoding="utf-8")
    out = {"ok": True, "tistory": MODE.get("tistory", ""),
           "updated": files[-1].stem + " 초안 · 확인하고 직접 올려 주세요"}
    for key, name in (("naver", "네이버"), ("tistory", "티스토리")):
        m = re.search(r"^##\s*" + name + r"\s*\n(.*?)(?=^##\s|\Z)", text, re.S | re.M)  # '## 이미지' 앞에서 끝남
        part = m.group(1) if m else ""
        title = re.search(r"^제목\s*[:：]\s*(.+)$", part, re.M)
        tags = re.search(r"^태그\s*[:：]\s*(.+)$", part, re.M)
        body = part.split("\n---", 1)[1] if "\n---" in part else part
        out[key] = {"title": title.group(1).strip() if title else "", "tags": tags.group(1).strip() if tags else "",
                    "body": body.strip()}
    m = re.search(r"^##\s*이미지\s*\n(.*?)(?=^##\s|\Z)", text, re.S | re.M)
    out["images"] = [{"kind": k.strip(), "parts": [x.strip() for x in v.split("|") if x.strip()]}
                     for k, v in re.findall(r"^\s*-\s*([^:：\n]+)[:：]\s*(.+)$", m.group(1) if m else "", re.M)]
    return out


def blog_fill(site):
    """최근 초안으로 글쓰기 화면을 열어 채운다 (발행은 대표님이 직접)."""
    try:
        title, body, tags = blogpost.latest(site)
        return blogpost.fill(site, title, body, tags, MODE.get("tistory", ""))
    except (kmong.SafariError, subprocess.TimeoutExpired) as e:
        return str(e)


def blog_fill_route(body):
    site = "tistory" if body.get("site") == "tistory" else "naver"
    msg = blog_fill(site)
    log(f"📝 {msg}")
    return {"ok": "넣었어요" in msg, "message": msg}


BLOG_POST_RE = re.compile(r"블로그.{0,10}(올려|채워|붙여|발행|업로드)|(네이버|티스토리).{0,8}(올려|채워)")


def handle_blog_post(command):
    if not BLOG_POST_RE.search(command):
        return False
    sites = ["tistory"] if "티스토리" in command else ["naver"] if "네이버" in command else ["naver", "tistory"]
    if "tistory" in sites and not MODE.get("tistory"):
        sites = [x for x in sites if x != "tistory"] or sites
    speak("블로그 글쓰기 화면을 열어서 초안을 채울게요.", then="thinking")
    for site in sites:
        msg = blog_fill(site)
        log(f"📝 {msg}")
        speak(msg)
    return True


def schedule_loop():
    """정해진 시각에 기상 음악, 아침 브리핑, 주간 블로그 초안."""
    done = set()
    while True:
        time.sleep(15)
        now, today = time.strftime("%H:%M"), time.strftime("%Y-%m-%d")
        blog_day, _, blog_at = (MODE.get("blog") or "").partition(" ")
        jobs = [("alarm", MODE.get("alarm"), wake_up), ("briefing", BRIEFING_TIME, briefing),
                ("blog", blog_at if WEEKDAYS[time.localtime().tm_wday] == blog_day else "", blog_week)]
        for name, at, job in jobs:
            if at and now == at and (name, today) not in done:
                done.add((name, today))
                threading.Thread(target=job, daemon=True).start()


_TIME = r"(오전|아침|오후|저녁)?\s*(\d{1,2})\s*시\s*(반|(\d{1,2})\s*분)?"
ALARM_RE = re.compile(r"(?:알람|기상|깨워).{0,12}?" + _TIME + r"|" + _TIME + r".{0,8}(?:깨워|알람|기상)")
ALARM_OFF_RE = re.compile(r"(알람|기상\s*음악).{0,6}(꺼|끄|취소|없애|그만)")


def handle_alarm(command):
    """'알람 6시 반으로 바꿔 줘', '알람 꺼 줘' 같은 요청이면 처리하고 True."""
    if ALARM_OFF_RE.search(command):
        MODE["alarm"] = ""
        mode_route({})
        speak("기상 음악을 껐어요.")
        return True
    m = ALARM_RE.search(command)
    if not m:
        return False
    ampm, h, half, mins = m.groups()[:4] if m.group(2) else m.groups()[4:8]
    hour = int(h) % 24
    if ampm in ("오후", "저녁") and hour < 12:
        hour += 12
    minute = 30 if half == "반" else int(mins or 0)
    MODE["alarm"] = f"{hour:02d}:{minute:02d}"
    mode_route({})
    speak(f"매일 {hour}시{f' {minute}분' if minute else ''}에 지니 걸그룹 노래로 깨워 드릴게요.")
    return True


def load_mode():
    try:
        MODE.update({k: v for k, v in json.loads(SETTINGS.read_text()).items() if k in MODE})
    except (OSError, ValueError):
        pass


def mode_route(body):
    """화면에서 [음성 / 텍스트] 와 [대답 소리] 를 바꿀 때. 빈 요청이면 지금 설정만 돌려준다."""
    if body.get("input") in ("voice", "text"):
        MODE["input"] = body["input"]
        log("입력 방식: " + ("음성" if MODE["input"] == "voice" else "텍스트"))
    if "speak" in body:
        MODE["speak"] = bool(body["speak"])
    if "tistory" in body:
        MODE["tistory"] = re.sub(r"[^a-z0-9-]", "", str(body["tistory"]).lower())[:40]
    SETTINGS.write_text(json.dumps(MODE))
    publish_mode()
    return {"ok": True, **MODE, "input": input_mode(), "music": MUSIC.is_set()}


def ask_route(body):
    """화면 대화창에 글자로 입력한 질문."""
    text = str(body.get("text", "")).strip()
    if not text:
        return {"ok": False, "error": "내용을 입력해 주세요."}

    def run():
        with BUSY, deaf():
            log(f"⌨️ {text}")
            handle_command(text)
    threading.Thread(target=run, daemon=True).start()
    return {"ok": True}


# 음악은 Claude 에게 맡기지 않고 여기서 바로 지니로 튼다 (다른 앱이 열리지 않도록)
MUSIC_STOP_RE = re.compile(r"(음악|노래|지니|플레이어)\S*\s*(좀\s*)?(꺼|멈춰|정지|그만|중지)")
MUSIC_PLAY_RE = re.compile(r"틀어|들려|(노래|음악|곡|지니).{0,10}(재생|켜|플레이|듣고\s*싶|들을래|찾아)"
                           r"|(재생|플레이).{0,6}(노래|음악|곡)|듣고\s*싶(어|다)|들을래")
YT = r"(?:유\s?튜\s?브|유\s?투\s?브|유튭|you\s?tube)"  # 음성인식이 "유투브", "YouTube" 로도 받아 적음
YT_RE = re.compile(YT, re.I)
GENIE_RE = re.compile(r"지니|genie", re.I)
MUSIC_SOURCE_RE = re.compile(r"(기본|앞으로|이제부터).{0,12}(" + YT + r"|지니)|(" + YT + r"|지니).{0,6}(기본으로|로\s*(바꿔|할게|해\s*줘))", re.I)
MUSIC_NEXT_RE = re.compile(r"다음\s*곡|넘겨|스킵|skip", re.I)
NOT_MUSIC_RE = re.compile(r"뉴스|날씨|브리핑|크몽|매출|요약|문의|보고|일정|메일")  # "뉴스 들려줘" 는 음악이 아님
VOLUME_RE = re.compile(r"(소리|볼륨|음량)\D{0,6}(\d{1,3})\s*(으로|로|%|퍼센트)")


def handle_music(command):
    """음악 요청이면 처리하고 True. 아니면 False."""
    m = VOLUME_RE.search(command)
    if m:
        speak(genie.volume(m.group(2)))
        return True
    m = MUSIC_SOURCE_RE.search(command)
    if m:
        MODE["music"] = "youtube" if YT_RE.search(m.group(0)) else "genie"
        mode_route({})
        speak("앞으로 음악은 " + ("유튜브" if MODE["music"] == "youtube" else "지니") + "로 틀게요.")
        return True
    if MUSIC_STOP_RE.search(command):
        MUSIC_QUEUE.clear()
        results = [genie.stop(), youtube.stop()]
        speak(next((r for r in results if "껐어요" in r), results[0]))
        set_music(False)
        return True
    if MUSIC.is_set() and MUSIC_NEXT_RE.search(command):
        if MUSIC_QUEUE:
            speak("다음 곡 틀게요.") if play_next() else speak("다음 곡을 틀지 못했어요.")
        else:
            speak("지니 플레이어 창에서 다음 곡 버튼을 눌러 주세요. 지금은 지니 재생목록으로 이어서 나오고 있어요.")
        return True
    if not MUSIC_PLAY_RE.search(command) or NOT_MUSIC_RE.search(command):
        return False
    source = "youtube" if YT_RE.search(command) else "genie" if GENIE_RE.search(command) else MODE.get("music", "genie")
    log(f"🎵 음악 서비스: {'유튜브' if source == 'youtube' else '지니'}")
    n = int(m.group(1)) if (m := re.search(r"(\d{1,2})\s*(곡|개)", command)) else 10
    n = max(1, min(n, 30))
    if source == "youtube":
        return play_youtube(command, n)
    speak("지니에서 찾아볼게요.", then="thinking", chat=False)
    plan = Brain(workdir=DATA, remember=False).ask(
        f"다음 음악 요청을 지니뮤직에서 {n}곡 이어서 틀 계획으로 바꿔 줘. JSON 한 줄만 쓰고 다른 말은 쓰지 마.\n"
        '- 가수나 장르 하나만 말했으면(예: "아이유 노래", "걸그룹 노래"): {"search": "검색어"}  (검색 결과 위에서부터 틀어)\n'
        f'- 특정 곡을 말했거나 분위기만 말했으면: {{"songs": ["가수 곡제목", ...]}}  ({n}곡, 말한 곡이 있으면 첫 곡으로, 나머지는 어울리는 실제 곡)\n'
        "요청: " + command, tools=False)
    try:
        plan = json.loads(plan[plan.index("{"): plan.rindex("}") + 1])
    except ValueError:
        plan = {"songs": [plan.strip().splitlines()[0][:60]]}
    MUSIC_QUEUE.clear()
    try:
        if plan.get("search"):
            log(f"🎵 지니 검색 후 {n}곡 연속: {plan['search']}")
            ok, titles, msg = genie.play_top(plan["search"], n)
            if not ok and not msg:  # '선택 듣기'를 못 하면 찾은 곡들을 한 곡씩 이어 틀기
                MUSIC_QUEUE.extend(titles or [plan["search"]])
                ok = play_next()
                msg = f"지니에서 {len(titles) or 1}곡을 한 곡씩 이어서 틀어요." if ok else "지니에서 재생하지 못했어요."
        else:
            songs = [x for x in plan.get("songs", []) if isinstance(x, str)][:n] or [command]
            log(f"🎵 지니 {len(songs)}곡 연속: {', '.join(songs)}")
            MUSIC_QUEUE.extend(songs)
            ok = play_next()
            msg = f"지니에서 {len(songs)}곡을 이어서 틀어요. 첫 곡은 {songs[0]}." if ok else "지니에서 재생하지 못했어요."
    except (kmong.SafariError, subprocess.TimeoutExpired, ValueError) as e:
        ok, msg = False, f"지니를 열지 못했어요: {e}"
    log(f"🎵 {msg}")
    if ok:
        set_music(True)
        msg += " 음악이 나오는 동안은 화면 아래 칸에 글자로 말씀해 주세요. 다음 곡은 '다음 곡'이라고 입력하세요."
    speak(msg)
    return True


def play_youtube(command, n):
    speak("유튜브에서 찾아볼게요.", then="thinking", chat=False)
    plan = Brain(workdir=DATA, remember=False).ask(
        "다음 음악 요청을 유튜브 검색어로 바꿔 줘. JSON 한 줄만 쓰고 다른 말은 쓰지 마. "
        '형식: {"query": "검색어", "views": true 또는 false}. 조회수·인기·많이 본 것을 원하면 views 는 true. '
        "검색어에는 '유튜브', '틀어 줘' 같은 말은 빼고 가수·곡·장르만.\n요청: " + command, tools=False)
    try:
        plan = json.loads(plan[plan.index("{"): plan.rindex("}") + 1])
    except ValueError:
        plan = {"query": re.sub(YT + r"(에서|로)?|틀어\s*줘|들려\s*줘", "", command, flags=re.I).strip(), "views": "조회수" in command}
    log(f"🎵 유튜브 {'조회수 순 ' if plan.get('views') else ''}{n}곡: {plan.get('query')}")
    MUSIC_QUEUE.clear()
    try:
        genie.stop()
        ok, titles, msg = youtube.play(str(plan.get("query") or command), n, bool(plan.get("views")))
    except (kmong.SafariError, subprocess.TimeoutExpired, ValueError) as e:
        ok, msg = False, f"유튜브를 열지 못했어요: {e}"
    log(f"🎵 {msg}")
    if ok:
        set_music(True)
        msg += " 음악이 나오는 동안은 화면 아래 칸에 글자로 말씀해 주세요."
    speak(msg)
    return True


TEMPLATE_EDIT_RE = re.compile(r"자주\s*쓰는\s*문구.{0,10}(추가|편집|수정|관리|열어|보여)")
TEMPLATE_RE = re.compile(r"자주\s*쓰는\s*문구.{0,10}(가져|읽어|불러|업데이트|새로|저장)")


def fetch_templates():
    speak("크몽 자주 쓰는 문구를 하나씩 열어서 읽어 올게요. 끝날 때까지 크몽 화면은 건드리지 말아 주세요.", then="thinking")
    try:
        text = kmong.read_templates(DATA / "kmong_templates.md")
    except kmong.SafariError as e:
        speak(str(e))
        return
    n = text.count("\n### ")
    if n:
        log(f"자주 쓰는 문구 {n}개 저장 → {DATA / 'kmong_templates.md'}")
        speak(f"자주 쓰는 문구 {n}개를 저장했어요. 이제 상담 초안에 참고할게요.")
    else:
        speak(text)


MODE_RE = re.compile(r"(텍스트|글자|채팅|음성|목소리)\s*(모드|로\s*(할게|하자|바꿔|대화))")


def handle_command(command):
    """음성이든 텍스트든 들어온 요청 하나를 처리한다 (BUSY 를 잡은 상태에서 호출)."""
    if LOGIN_RE.search(command):
        speak("화면에 Claude 계정 연결 창을 띄웠어요. 로그인 시작 버튼을 눌러 주세요.", then="login")
        return
    if RESET_RE.search(command) and len(command) < 15:
        BRAIN.session_id = None
        speak("새 대화를 시작할게요.", then="listening")
        return
    m = MODE_RE.search(command)
    if m and len(command) < 20:
        mode_route({"input": "voice" if m.group(1) in ("음성", "목소리") else "text"})
        speak("음성 모드로 바꿨어요. 용용아 하고 불러 주세요." if MODE["input"] == "voice"
              else "텍스트 모드로 바꿨어요. 화면 아래 칸에 입력해 주세요.")
        return

    if TEMPLATE_EDIT_RE.search(command):
        FACE.panel("templates")
        speak("화면에 자주 쓰는 문구 칸을 띄웠어요. 문구를 붙여넣고 저장해 주세요.")
        return
    if handle_blog_post(command):
        return
    if TEMPLATE_RE.search(command):
        fetch_templates()
        return
    if handle_alarm(command) or handle_music(command):
        return
    speak("네, 잠시만요.", then="thinking", chat=False)
    if "크몽" in command and not KMONG_STATUS_RE.search(command):  # 상담창 질문일 때만 지금 화면을 붙임
        try:
            page = kmong.snapshot()
            if page:
                command = f"{command}\n\n{kmong_prompt(page)}"
        except kmong.SafariError as e:
            speak(str(e))
            return
    speak(show_panels(BRAIN.ask(command)), then="listening")


def default_region():
    """대기 화면 날씨 지역: 마지막으로 물어본 지역, 없으면 기억 파일의 '기본 지역'."""
    if MODE.get("region"):
        return MODE["region"]
    memo = MEMO.read_text(encoding="utf-8") if MEMO.exists() else ""
    m = re.search(r"기본\s*지역\S*\s*[:：]?\s*([가-힣]{2,})", memo)
    return m.group(1) if m else ""


_refreshing = threading.Lock()


def refresh_kmong_report():
    """대기 화면용: 보고서가 오래됐으면 조용히(말하지 않고) 새로 만든다."""
    if not _refreshing.acquire(blocking=False):
        return
    try:
        log("대기 화면용 크몽 현황 새로 만드는 중")
        Brain(remember=False).ask("크몽 현황 보고서를 새로 만들어 줘. 파일만 정리하고 대답은 '완료' 한 단어로.")
    finally:
        _refreshing.release()


def dashboard_route(_body):
    path = REPORTS["크몽"][1]
    report = path.read_text(encoding="utf-8") if path.exists() else ""
    age = time.time() - path.stat().st_mtime if path.exists() else None
    if (age is None or age > 2 * 3600) and 9 <= time.localtime().tm_hour < 21:
        threading.Thread(target=refresh_kmong_report, daemon=True).start()
    updated = time.strftime("%H:%M 기준", time.localtime(path.stat().st_mtime)) if path.exists() else ""
    return {"ok": True, "region": default_region(), "report": report, "updated": updated}


# 캐릭터 창(사파리)을 화면 가득 키우거나 원래 크기로
_WINDOW_SCRIPT = r"""
on run argv
  set wantFull to (item 1 of argv) is "full"
  set addr to "127.0.0.1:" & (item 2 of argv)
  tell application "Finder" to set sb to bounds of window of desktop
  tell application "Safari"
    repeat with w in windows
      repeat with t in tabs of w
        if URL of t contains addr then
          set old to bounds of w
          if wantFull then
            set current tab of w to t
            set bounds of w to {0, 25, item 3 of sb, item 4 of sb}
            set index of w to 1
          else if (count of argv) > 2 then
            set bounds of w to {(item 3 of argv) as integer, (item 4 of argv) as integer, (item 5 of argv) as integer, (item 6 of argv) as integer}
          end if
          return ((item 1 of old) as text) & " " & (item 2 of old) & " " & (item 3 of old) & " " & (item 4 of old)
        end if
      end repeat
    end repeat
  end tell
  return ""
end run
"""
_saved_bounds = []


def window_route(body):
    full = bool(body.get("full"))
    if full and _saved_bounds:
        return {"ok": True}
    args = ["full" if full else "restore", face.PORT, *(_saved_bounds if not full else [])]
    try:
        out = kmong._osa(_WINDOW_SCRIPT, *args)
    except Exception as e:  # 창 크기 조절은 못 해도 화면은 그대로 보임
        return {"ok": False, "error": str(e)}
    if full and out:
        _saved_bounds[:] = out.split()
    elif not full:
        _saved_bounds.clear()
    return {"ok": True}


TEMPLATES = DATA / "kmong_templates.md"


def templates_route(_body):
    return {"ok": True, "text": TEMPLATES.read_text(encoding="utf-8") if TEMPLATES.exists() else ""}


def templates_save_route(body):
    text = str(body.get("text", "")).strip()
    if not text:
        return {"ok": False, "error": "내용이 비어 있어요."}
    TEMPLATES.write_text(text + "\n", encoding="utf-8")
    return {"ok": True, "count": len(re.findall(r"^###\s", text, re.M))}


def draft_route(_body):
    if not DRAFT.exists():
        return {"ok": False, "error": "아직 답변 초안이 없어요."}
    text = DRAFT.read_text(encoding="utf-8")
    info, _, reply = text.partition("## 답변 초안")
    return {"ok": True, "info": info.strip(), "reply": reply.strip(),
            "updated": time.strftime("%H:%M 작성", time.localtime(DRAFT.stat().st_mtime))}


def draft_insert_route(body):
    """화면에서 고친 초안을 크몽 대화 입력창에 넣는다. 보내기 버튼은 대표님이 크몽에서 직접 누른다."""
    text = str(body.get("text", "")).strip()
    if not text:
        return {"ok": False, "error": "넣을 내용이 없어요."}
    try:
        ok = kmong.insert_draft(text)
    except kmong.SafariError as e:
        return {"ok": False, "error": str(e)}
    return {"ok": ok, "error": "" if ok else "크몽 대화 입력창을 찾지 못했어요. 상담할 대화를 열어 주세요."}


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


def kmong_inbox():
    """크몽 메시지 목록 글자. 사파리에 크몽 탭이 열려 있으면 그걸, 없으면 기억해 둔 메시지 주소를 잠깐 열어 읽는다."""
    page = kmong.snapshot()
    if page and re.search(r"inbox|message|메시지", page[:300], re.I):
        return page
    memo = MEMO.read_text(encoding="utf-8") if MEMO.exists() else ""
    m = re.search(r"크몽 메시지\s*주소\S*\s*[:：]?\s*(https?://\S+)", memo)
    if m:
        return "[탭] " + "\n".join(kmong.open_and_read(m.group(1)))
    return page  # 메시지 주소를 아직 모르면 열려 있는 크몽 탭이라도


def kmong_watch():
    """KMONG_POLL_SEC(기본 10분)마다 크몽 메시지를 확인해서, 새 문의가 있으면 분류하고 허브에서 고객 정보를 찾아 읽어 준다."""
    brain = Brain(workdir=DATA, remember=False)
    last = None
    first = True
    while True:
        if not first:
            time.sleep(KMONG_POLL_SEC)
        first = False
        try:
            page = kmong_inbox()
        except Exception as e:  # 사파리가 닫혀 있거나 권한이 없을 때는 조용히 다시 시도
            log(f"(크몽 읽기 실패) {e}")
            continue
        if not page:
            if not re.search(r"크몽 메시지\s*주소", MEMO.read_text(encoding="utf-8") if MEMO.exists() else ""):
                log("크몽 메시지 주소를 찾는 중")
                brain.ask("크몽 메시지(채팅) 목록 페이지 주소를 `python3 " + str(HERE / "kmong.py") + " links` 로 찾아서 "
                          "기억 파일에 '크몽 메시지 주소: URL' 한 줄로 적어 줘. 대답은 '완료' 한 단어로.")
            continue
        if last is None or kmong.fingerprint(page) == kmong.fingerprint(last):
            last = page
            continue
        new_lines = kmong.changes(last, page)
        last = page
        if not new_lines:
            continue
        log("크몽 새 메시지 감지 → 확인 중")
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
    load_mode()
    dev, info = pick_mic()
    rate = int(info["default_samplerate"])
    log(f"마이크: {info['name']} ({rate}Hz) / 음성인식: {WHISPER_MODEL} / 작업 폴더: {WORKDIR}")
    if SHOW_FACE:
        FACE.routes["/login/start"] = login_start
        FACE.routes["/login/token"] = login_token
        FACE.routes["/news"] = news_route
        FACE.routes["/report"] = report_route
        FACE.routes["/mode"] = mode_route
        FACE.routes["/ask"] = ask_route
        FACE.routes["/dashboard"] = dashboard_route
        FACE.routes["/window"] = window_route
        FACE.routes["/draft"] = draft_route
        FACE.routes["/draft/insert"] = draft_insert_route
        FACE.routes["/templates"] = templates_route
        FACE.routes["/templates/save"] = templates_save_route
        FACE.routes["/blog"] = blog_route
        FACE.routes["/blog/fill"] = blog_fill_route
        try:
            FACE.start()
        except OSError:  # 이미 다른 창에서 용용이가 켜져 있음 → 캐릭터 창만 다시 열고 끝냄
            print("용용이가 이미 켜져 있어요. 캐릭터 창을 다시 열게요.")
            subprocess.run(["open", f"http://127.0.0.1:{face.PORT}/"], check=False)
            return
    FACE.show("thinking")
    log("음성인식 모델 준비 중... (처음 한 번은 다운로드 때문에 몇 분 걸려요)")
    transcribe(np.zeros(SAMPLE_RATE, dtype=np.float32))

    log("Claude 로그인 확인 중...")
    logged_in = check_login()
    log("Claude 로그인 " + ("확인됨" if logged_in else "필요"))
    if not logged_in:
        log("Claude 로그인이 필요해요 → 캐릭터 창의 [로그인] 버튼을 눌러 주세요.")
    if KMONG_POLL_SEC > 0:
        threading.Thread(target=kmong_watch, daemon=True).start()
        log(f"크몽 새 문의 확인: {KMONG_POLL_SEC // 60}분마다")
    threading.Thread(target=schedule_loop, daemon=True).start()
    threading.Thread(target=music_watch, daemon=True).start()
    if IDLE_MIN > 0:
        threading.Thread(target=idle_watch, daemon=True).start()
    log(f"기상 음악: {MODE['alarm'] or '꺼짐'} / 아침 브리핑: {BRIEFING_TIME or '꺼짐'} / 블로그 초안: {MODE.get('blog') or '꺼짐'}")

    def on_audio(indata, frames, t, status):
        if not muted.is_set() and input_mode() == "voice":
            audio_q.put(indata[:, 0].copy())

    with sd.InputStream(device=dev, channels=1, samplerate=rate, dtype="float32",
                        blocksize=int(rate * BLOCK_SEC), callback=on_audio):
        with deaf():
            time.sleep(2 if SHOW_FACE else 0)  # 캐릭터 창이 뜰 시간
            publish_mode()
            if logged_in and MODE["input"] == "text":
                speak("용용이 준비됐어요. 화면 아래 칸에 입력해 주세요.")
            elif logged_in:
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
                    speak("네.", then="listening", chat=False)
                else:
                    FACE.chat("me", command)
                    handle_command(command)
                awake_until = time.time() + FOLLOW_UP_SEC


if __name__ == "__main__":
    try:
        kmong_once() if "--kmong" in sys.argv else main()
    except KeyboardInterrupt:
        print("\n용용이를 종료합니다.")
        sys.exit(0)
