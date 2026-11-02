"""Проверка HTTP-движка tts.py на имитаторе TTS-сервера (127.0.0.1). Реальный сервер 192.168.206.206 не используется."""
import io, json, math, shutil, struct, subprocess, sys, tempfile, threading, wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

SRC = Path(sys.argv[1])  # путь к video/engine/tts.py
calls, mode = [], {"busy_once": False, "not_wav": False}


def tone_wav(sec=0.6, sr=24000):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        sil = b"\0\0" * int(sr * 0.2)
        w.writeframes(sil + b"".join(struct.pack("<h", int(8000 * math.sin(2 * math.pi * 440 * i / sr)))
                                     for i in range(int(sr * sec))) + sil)
    return buf.getvalue()


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        calls.append((self.path, body))
        if mode["busy_once"]:
            mode["busy_once"] = False
            self.send_response(503); self.end_headers(); self.wfile.write(b'{"detail":"queue full"}'); return
        data = b'{"detail":"bad"}' if mode["not_wav"] else tone_wav()
        self.send_response(200)
        self.send_header("Content-Type", "audio/wav"); self.send_header("Content-Length", str(len(data)))
        self.end_headers(); self.wfile.write(data)


srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
port = srv.server_address[1]

root = Path(tempfile.mkdtemp())
eng = root / "engine"; eng.mkdir()
shutil.copy(SRC, eng / "tts.py")
(eng / "config.json").write_text(json.dumps({
    "piper_voices": "/nonexistent",
    "tts_servers": {"silero": {"url": f"http://127.0.0.1:{port}", "max_chars": 1000, "retries": 1},
                    "outside": {"url": "http://8.8.8.8:8014"},
                    "short": {"url": f"http://127.0.0.1:{port}", "max_chars": 10}}}))
theme = root / "themes" / "t"; theme.mkdir(parents=True)


def story(engine, **voice):
    (theme / "story.json").write_text(json.dumps({
        "voice": {"engine": engine, "request": {"model": "v5_cis_base", "speaker": "ru_alexandr"}, **voice},
        "scenes": [{"id": "s1", "beats": [{"id": "a", "say": "РИВЦ представляет ГОЛОЛЁД.", "tts": "Р+ИВЦ представляет ГОЛОЛЁД."},
                                          {"id": "b", "say": "Новый SNOWTAM."}]}]}, ensure_ascii=False))


def run(*extra):
    return subprocess.run([sys.executable, str(eng / "tts.py"), str(theme), *extra], capture_output=True, text=True)


fails = 0
def check(name, cond, info=""):
    global fails
    print(("OK  " if cond else "FAIL") + " " + name + ("" if cond else f"  {info}"))
    fails += not cond

# 1. Обычный выпуск: две реплики, повтор после 503, 48 кГц моно, manifest
story("silero"); mode["busy_once"] = True
r = run()
check("выпуск silero", r.returncode == 0, r.stderr)
check("POST /v1/tts, тело = voice.request + text",
      calls[-1] == ("/v1/tts", {"model": "v5_cis_base", "speaker": "ru_alexandr", "text": "Новый SNOWTAM."}), calls[-1])
check("в запрос ушло поле tts, а не say", any(b.get("text") == "Р+ИВЦ представляет ГОЛОЛЁД." for _, b in calls))
check("повтор после 503", len(calls) == 3, calls)
m = json.loads((theme / "audio/beats/manifest.json").read_text())
check("manifest engine/model/credit", (m["engine"], m["model"], m["credit"]) == ("silero", "v5_cis_base", "Голос: v5_cis_base, ru_alexandr"), m)
check("manifest beats", set(m["beats"]) == {"s1.a", "s1.b"}, m["beats"])
with wave.open(str(theme / "audio/beats/s1__a.wav")) as w:
    dur = w.getnframes() / w.getframerate()
    check("48 кГц моно 16 бит", (w.getframerate(), w.getnchannels(), w.getsampwidth()) == (48000, 1, 2))
check("тишина по краям срезана", 0.5 < dur < 0.7, dur)

# 2. Внешний адрес отвергается до запроса
n = len(calls); story("outside"); r = run()
check("внешний адрес отвергнут", r.returncode != 0 and "не внутренняя сеть" in r.stderr and len(calls) == n, r.stderr)

# 3. Длинная реплика
story("short"); r = run()
check("предел символов", r.returncode != 0 and "предел short" in r.stderr, r.stderr)

# 4. Неизвестный движок
story("nope"); r = run()
check("неизвестный движок", r.returncode != 0 and "tts_servers" in r.stderr, r.stderr)

# 5. Ответ не WAV
story("silero"); mode["not_wav"] = True; r = run(); mode["not_wav"] = False
check("ответ не WAV", r.returncode != 0 and "не WAV" in r.stderr, r.stderr)

# 6. Сервер не отвечает
cfg = json.loads((eng / "config.json").read_text()); cfg["tts_servers"]["down"] = {"url": "http://127.0.0.1:9"}
(eng / "config.json").write_text(json.dumps(cfg)); story("down"); r = run()
check("нет связи", r.returncode != 0 and "нет связи" in r.stderr, r.stderr)

# 7. Piper остаётся движком по умолчанию (piper-tts здесь не установлен — ждём ImportError piper, а не ошибку HTTP)
(theme / "story.json").write_text(json.dumps({"voice": {"model": "ru_RU-dmitri-medium", "length_scale": 1.1},
                                              "scenes": []}))
r = run()
check("без voice.engine — Piper", "piper" in r.stderr and "tts_servers" not in r.stderr, r.stderr[-300:])

srv.shutdown()
print("итого ошибок:", fails)
sys.exit(fails)
