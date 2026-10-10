#!/usr/bin/env python3
"""용용이: "용용아" 하고 부르면 듣고, Claude Code 로 생각해서, 말로 대답하는 음성 비서."""
import collections
import json
import os
import queue
import re
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path

import kmong
import mlx_whisper
import numpy as np
import sounddevice as sd

HERE = Path(__file__).resolve().parent
PERSONA = (HERE / "persona.md").read_text(encoding="utf-8")
DATA = HERE / "data"  # 고객 메모 등 (git 에 올라가지 않음)
CUSTOMERS = DATA / "customers.md"

KMONG_INSTRUCTIONS = f"""아래는 대표님 사파리에 떠 있는 크몽 화면의 글자야.
1. 지금 상담 중인(또는 새로 문의한) 주문자 닉네임을 찾아.
2. {CUSTOMERS} 파일에서 그 주문자의 예전 기록(연관 계정, 이전 주문, 진행 상황)을 찾아봐.
3. 화면에서 새로 알게 된 사실(주문자, 요청 내용, 주문·진행 상태, 금액, 마감일, 같은 사람으로 보이는 다른 계정)을
   그 파일의 해당 주문자 항목에 짧게 추가하거나 고쳐. 파일이 없으면 만들어.
4. 대표님께 말로 보고해: 누가, 무엇을 원하는지, 예전 거래나 연관 계정, 지금 상황, 대표님이 할 일. 2~4문장.
화면은 읽기만 하고 크몽에 메시지를 보내거나 클릭하지 마."""

WHISPER_MODEL = os.environ.get("YONGYONG_WHISPER", "mlx-community/whisper-large-v3-turbo")
VOICE = os.environ.get("YONGYONG_VOICE", "Yuna")
MIC_NAME = os.environ.get("YONGYONG_MIC", "Studio Display")
WORKDIR = Path(os.environ.get("YONGYONG_WORKDIR", Path.home() / "projects")).expanduser()
MIN_RMS = float(os.environ.get("YONGYONG_MIN_RMS", "0.006"))  # 낮출수록 작은 소리에도 반응
KMONG_POLL_SEC = int(os.environ.get("YONGYONG_KMONG_POLL", "30"))  # 0 이면 자동 감시 끔
FOLLOW_UP_SEC = 8  # 대답 후 이 시간 안에는 "용용아" 없이 바로 말해도 됨

SAMPLE_RATE = 16000  # Whisper 입력
BLOCK_SEC = 0.03
END_SILENCE_SEC = 0.8
MAX_UTTERANCE_SEC = 30
MIN_SPEECH_SEC = 0.3

# Whisper 가 "용용아"를 다르게 받아 적는 경우까지 포함
WAKE_RE = re.compile(r"(용\s?용|용\s?룡|영\s?용|용\s?영|룡\s?용)\s*(아|이|야)?[\s,.!?~]*")
RESET_RE = re.compile(r"새\s?대화|처음부터")

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
    n = int(len(x) * SAMPLE_RATE / rate)
    return np.interp(np.linspace(0, len(x), n, endpoint=False), np.arange(len(x)), x).astype(np.float32)


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
    )
    return result["text"].strip()


def for_speech(text):
    text = re.sub(r"```.*?```", " 코드는 화면에 띄워 뒀어요. ", text, flags=re.S)
    text = re.sub(r"https?://\S+", " 링크 ", text)
    text = re.sub(r"[`*#>|_\[\]]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def speak(text):
    print(f"\n🐉 용용이: {text}\n", flush=True)
    subprocess.run(["say", "-v", VOICE, "-r", "200", for_speech(text)], check=False)


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
            "--append-system-prompt", PERSONA,
            "--permission-mode", "acceptEdits",
            "--add-dir", str(DATA),
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
        return data.get("result") or "처리했어요."


def kmong_prompt(page, new_lines=None):
    prompt = KMONG_INSTRUCTIONS
    if new_lines is not None:
        prompt += ("\n\n이번에 화면에서 새로 생긴 줄은 아래와 같아. 주문자가 보낸 새 메시지나 새 주문이 아니면"
                   " (광고, 내가 보낸 메시지, 화면 이동 등) 파일만 정리하고 정확히 '없음' 이라고만 대답해.\n"
                   + new_lines)
    return prompt + "\n\n=== 크몽 화면 ===\n" + page


def kmong_watch(busy):
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
        report = brain.ask(kmong_prompt(page, new_lines)).strip()
        if report and report.strip(" .'\"") != "없음":
            with busy, deaf():
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

    log("음성인식 모델 준비 중... (처음 한 번은 다운로드 때문에 몇 분 걸려요)")
    transcribe(np.zeros(SAMPLE_RATE, dtype=np.float32))

    brain = Brain()
    busy = threading.Lock()  # 용용이가 한 번에 한 가지만 말하도록
    if KMONG_POLL_SEC > 0:
        threading.Thread(target=kmong_watch, args=(busy,), daemon=True).start()
        log(f"크몽 감시 시작 ({KMONG_POLL_SEC}초마다 사파리 크몽 탭 확인)")

    def on_audio(indata, frames, t, status):
        if not muted.is_set():
            audio_q.put(indata[:, 0].copy())

    with sd.InputStream(device=dev, channels=1, samplerate=rate, dtype="float32",
                        blocksize=int(rate * BLOCK_SEC), callback=on_audio):
        with deaf():
            speak("용용이 준비됐어요. 용용아 하고 불러 주세요.")
        awake_until = 0.0
        for audio in utterances(rate):
            with busy, deaf():
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
                    speak("네.")
                    awake_until = time.time() + FOLLOW_UP_SEC
                    continue
                if RESET_RE.search(command) and len(command) < 15:
                    brain.session_id = None
                    speak("새 대화를 시작할게요.")
                    awake_until = time.time() + FOLLOW_UP_SEC
                    continue

                subprocess.Popen(["say", "-v", VOICE, "네, 잠시만요."])
                if "크몽" in command:
                    try:
                        page = kmong.snapshot()
                        if page:
                            command = f"{command}\n\n{kmong_prompt(page)}"
                    except kmong.SafariError as e:
                        speak(str(e))
                        continue
                speak(brain.ask(command))
                awake_until = time.time() + FOLLOW_UP_SEC


if __name__ == "__main__":
    try:
        kmong_once() if "--kmong" in sys.argv else main()
    except KeyboardInterrupt:
        print("\n용용이를 종료합니다.")
        sys.exit(0)
