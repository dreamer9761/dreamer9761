"""용용이 캐릭터 창: 작은 웹서버가 face/index.html 을 띄우고, 상태(듣기·생각·말하기)를 실시간으로 보낸다."""
import json
import os
import queue
import subprocess
import threading
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import numpy as np

PAGE = Path(__file__).resolve().parent / "face" / "index.html"
PORT = int(os.environ.get("YONGYONG_FACE_PORT", "8765"))
FRAME_SEC = 0.04  # 입 모양을 바꾸는 간격


class Face:
    def __init__(self):
        self._clients: list[queue.Queue] = []
        self._lock = threading.Lock()
        self._last = json.dumps({"state": "idle"})

    def show(self, state, **extra):
        """state: idle | listening | thinking | speaking"""
        msg = json.dumps({"state": state, **extra}, ensure_ascii=False)
        with self._lock:
            self._last = msg
            for q in self._clients:
                q.put(msg)

    def start(self, open_window=True):
        face = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                if self.path == "/events":
                    return self._events()
                body = PAGE.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _events(self):
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                q: queue.Queue = queue.Queue()
                with face._lock:
                    face._clients.append(q)
                    q.put(face._last)
                try:
                    while True:
                        try:
                            self.wfile.write(f"data: {q.get(timeout=15)}\n\n".encode())
                        except queue.Empty:
                            self.wfile.write(b": ping\n\n")
                        self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    pass
                finally:
                    with face._lock:
                        face._clients.remove(q)

        server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        if open_window:
            url = f"http://127.0.0.1:{PORT}/"
            if Path("/Applications/Google Chrome.app").exists():
                # 주소창 없는 깔끔한 창
                subprocess.Popen(["open", "-na", "Google Chrome", "--args", f"--app={url}",
                                  "--window-size=460,620"])
            else:
                subprocess.Popen(["open", url])


def envelope(wav_path):
    """음성 파일의 크기 변화(0~1)를 FRAME_SEC 간격으로. 캐릭터 입 모양에 사용."""
    with wave.open(str(wav_path)) as w:
        rate = w.getframerate()
        x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32)
    n = max(1, int(rate * FRAME_SEC))
    frames = x[: len(x) // n * n].reshape(-1, n)
    if not len(frames):
        return []
    rms = np.sqrt(np.mean(frames**2, axis=1))
    rms = np.sqrt(rms / max(rms.max(), 1.0))  # 작은 소리도 입이 보이게
    return [round(float(v), 2) for v in rms]
