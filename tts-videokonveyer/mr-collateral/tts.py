#!/usr/bin/env python3
"""Озвучка реплик story.json → audio/beats/<сцена>__<реплика>.wav (48 кГц моно) + manifest.json.

  <python> engine/tts.py ТЕМА [--length-scale 1.1]

Движок — story.json → voice.engine:
  piper (или поле не задано) — локальный Piper. Интерпретатор с piper-tts и папка моделей — engine/config.json
      (piper_python, piper_voices). Модель и MODEL_CARD — huggingface.co/rhasspy/piper-voices (ru/ru_RU/<голос>/medium).
      Темп задаётся length_scale (>1 — медленнее), а не atempo: тембр не искажается. По умолчанию — voice.length_scale.
  любое имя из engine/config.json → tts_servers — синтезатор внутреннего TTS-сервера (POST <url>/v1/tts, JSON → WAV).
      Тело запроса — voice.request из story.json плюс текст реплики; имена полей — из Swagger <url>/docs сервиса.
      Адрес обязан быть во внутренней сети: внешние адреса отвергаются (сборка без внешней сети, решение ГД 22.10.2026).
      Нужен только стандартный Python; системные прокси не используются.
Обычно вызывается через vc.py.
"""
from __future__ import annotations

import argparse
import ipaddress
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import wave
from pathlib import Path

E = Path(__file__).resolve().parent
# 48 кГц моно 16 бит; тишину по краям срезаем — паузы задаёт build.py
TRIM = ("silenceremove=start_periods=1:start_threshold=-50dB,areverse,"
        "silenceremove=start_periods=1:start_threshold=-50dB,areverse")
RETRY_HTTP = {429, 502, 503, 504}  # очередь сервера занята или модель ещё загружается


def piper_engine(voice: dict, cfg: dict, length_scale: float | None):
    from piper import PiperVoice, SynthesisConfig  # нужен только для Piper

    length_scale = length_scale or voice["length_scale"]
    model = Path(os.environ.get("PIPER_VOICES", cfg["piper_voices"])) / f'{voice["model"]}.onnx'
    pv = PiperVoice.load(str(model))
    syn = SynthesisConfig(length_scale=length_scale)

    def synth(text: str, wav_path: str) -> None:
        with wave.open(wav_path, "wb") as w:
            pv.synthesize_wav(text, w, syn_config=syn)

    meta = {"engine": "piper", "model": voice["model"], "length_scale": length_scale,
            "credit": voice.get("credit") or f'Голос: Piper {voice["model"]}'}
    return synth, meta


def check_internal(url: str) -> None:
    """Адрес синтезатора должен разрешаться только во внутренние (частные) адреса."""
    host = urllib.parse.urlsplit(url).hostname
    if not host:
        sys.exit(f"tts: в адресе синтезатора нет хоста: {url}")
    try:
        addrs = {ai[4][0] for ai in socket.getaddrinfo(host, None)}
    except socket.gaierror as e:
        sys.exit(f"tts: не удалось разрешить {host}: {e}. Включён ли VPN / внутренняя сеть?")
    ips = [ipaddress.ip_address(a.split("%")[0]) for a in addrs]
    bad = sorted(str(ip) for ip in ips if not (ip.is_private or ip.is_loopback))
    if bad:
        sys.exit(f"tts: {host} → {', '.join(bad)} — не внутренняя сеть. Синтез только локальный "
                 "(video/README.md, «Обязательное требование»).")


def server_engine(name: str, voice: dict, cfg: dict):
    servers = cfg.get("tts_servers", {})
    if name not in servers:
        sys.exit(f'tts: voice.engine="{name}" нет в engine/config.json → tts_servers ({", ".join(servers) or "пусто"})')
    srv = servers[name]
    url = os.environ.get("VC_TTS_URL", srv["url"]).rstrip("/")
    check_internal(url)
    request = dict(voice.get("request", {}))
    request.pop("text", None)
    max_chars = int(srv.get("max_chars", 1000))
    timeout = float(srv.get("timeout", 600))  # первый запрос после 10 мин простоя ждёт загрузку модели
    retries = int(srv.get("retries", 4))
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # мимо системных прокси

    def synth(text: str, wav_path: str) -> None:
        if len(text) > max_chars:
            sys.exit(f"tts: реплика {len(text)} символов, предел {name} — {max_chars}. Разбейте реплику.")
        body = json.dumps({**request, "text": text}, ensure_ascii=False).encode("utf-8")
        for attempt in range(retries + 1):
            req = urllib.request.Request(f"{url}/v1/tts", data=body, method="POST",
                                         headers={"Content-Type": "application/json"})
            try:
                with opener.open(req, timeout=timeout) as r:
                    data = r.read()
                break
            except urllib.error.HTTPError as e:
                detail = e.read()[:500].decode("utf-8", "replace")
                if e.code in RETRY_HTTP and attempt < retries:
                    time.sleep(5 * 2 ** attempt)
                    continue
                sys.exit(f"tts: {name} ответил {e.code} на «{text[:60]}»: {detail}")
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                sys.exit(f"tts: нет связи с {url} ({e}). Включён ли VPN / внутренняя сеть? Готовность: {url}/health/ready")
        if data[:4] != b"RIFF":
            sys.exit(f"tts: {name} вернул не WAV на «{text[:60]}»: {data[:300].decode('utf-8', 'replace')}")
        Path(wav_path).write_bytes(data)

    model = request.get("model") or name
    who = request.get("speaker") or request.get("voice_id")
    meta = {"engine": name, "server": url, "model": model, "request": request, "length_scale": None,
            "credit": voice.get("credit") or f"Голос: {model}" + (f", {who}" if who else "")}
    return synth, meta


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("theme")
    ap.add_argument("--length-scale", type=float)
    a = ap.parse_args()
    P = Path(a.theme).resolve()
    OUT = P / "audio" / "beats"
    story = json.loads((P / "story.json").read_text(encoding="utf-8"))
    voice = story["voice"]
    cfg = json.loads((E / "config.json").read_text(encoding="utf-8"))
    engine = voice.get("engine", "piper")
    if engine == "piper":
        synth, meta = piper_engine(voice, cfg, a.length_scale)
    else:
        if a.length_scale:
            print(f"  --length-scale действует только для Piper; для {engine} темп — в voice.request")
        synth, meta = server_engine(engine, voice, cfg)
    OUT.mkdir(parents=True, exist_ok=True)
    beats, total, t0 = {}, 0.0, time.monotonic()
    for sc in story["scenes"]:
        for bt in sc["beats"]:
            text = bt.get("tts") or bt["say"]
            f = OUT / f'{sc["id"]}__{bt["id"]}.wav'
            with tempfile.NamedTemporaryFile(suffix=".wav") as tmp:
                synth(text, tmp.name)
                subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", tmp.name, "-af", TRIM, "-ar", "48000", "-ac", "1",
                                "-c:a", "pcm_s16le", str(f)], check=True)
            with wave.open(str(f), "rb") as w:
                dur = w.getnframes() / w.getframerate()
            beats[f'{sc["id"]}.{bt["id"]}'] = {"file": str(f.relative_to(P)), "duration": round(dur, 3), "text": text}
            total += dur
            print(f'  {sc["id"]}.{bt["id"]:<9} {dur:5.2f} с')
    manifest = {**meta, "beats": beats}
    (OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    how = f"length_scale={meta['length_scale']}" if engine == "piper" else f"{engine} {meta['model']}"
    print(f"{how}: {len(beats)} реплик, речь {total:.1f} с, синтез {time.monotonic() - t0:.0f} с")


if __name__ == "__main__":
    main()
