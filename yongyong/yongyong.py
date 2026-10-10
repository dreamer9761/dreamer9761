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

import mlx_whisper
import numpy as np
import sounddevice as sd

HERE = Path(__file__).resolve().parent
PERSONA = (HERE / "persona.md").read_text(encoding="utf-8")

WHISPER_MODEL = os.environ.get("YONGYONG_WHISPER", "mlx-community/whisper-large-v3-turbo")
VOICE = os.environ.get("YONGYONG_VOICE", "Yuna")
MIC_NAME = os.environ.get("YONGYONG_MIC", "Studio Display")
WORKDIR = Path(os.environ.get("YONGYONG_WORKDIR", Path.home() / "projects")).expanduser()
MIN_RMS = float(os.environ.get("YONGYONG_MIN_RMS", "0.006"))  # 낮출수록 작은 소리에도 반응
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

    def __init__(self):
        self.session_id = None

    def ask(self, text):
        cmd = [
            "claude", "-p", text,
            "--output-format", "json",
            "--append-system-prompt", PERSONA,
            "--permission-mode", "acceptEdits",
        ]
        if self.session_id:
            cmd += ["--resume", self.session_id]
        try:
            p = subprocess.run(cmd, cwd=WORKDIR, capture_output=True, text=True, timeout=1800)
            data = json.loads(p.stdout)
        except subprocess.TimeoutExpired:
            return "작업이 너무 오래 걸려서 멈췄어요."
        except json.JSONDecodeError:
            log(f"claude 오류: {p.stderr.strip() or p.stdout.strip()}")
            return "죄송해요, 처리하다가 문제가 생겼어요. 터미널을 확인해 주세요."
        self.session_id = data.get("session_id", self.session_id)
        return data.get("result") or "처리했어요."


def main():
    WORKDIR.mkdir(parents=True, exist_ok=True)
    dev, info = pick_mic()
    rate = int(info["default_samplerate"])
    log(f"마이크: {info['name']} ({rate}Hz) / 음성인식: {WHISPER_MODEL} / 작업 폴더: {WORKDIR}")

    log("음성인식 모델 준비 중... (처음 한 번은 다운로드 때문에 몇 분 걸려요)")
    transcribe(np.zeros(SAMPLE_RATE, dtype=np.float32))

    brain = Brain()

    def on_audio(indata, frames, t, status):
        if not muted.is_set():
            audio_q.put(indata[:, 0].copy())

    with sd.InputStream(device=dev, channels=1, samplerate=rate, dtype="float32",
                        blocksize=int(rate * BLOCK_SEC), callback=on_audio):
        with deaf():
            speak("용용이 준비됐어요. 용용아 하고 불러 주세요.")
        awake_until = 0.0
        for audio in utterances(rate):
            with deaf():
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
                speak(brain.ask(command))
                awake_until = time.time() + FOLLOW_UP_SEC


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n용용이를 종료합니다.")
        sys.exit(0)
