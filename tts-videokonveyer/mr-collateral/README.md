# Патч для internal/collateral (задача B24 №349836)

| Файл | Что это |
|---|---|
| `tts-voice-engine.patch` | изменения `video/engine/tts.py` и `video/README.md` относительно версий от 02.11.2026 |
| `commit-message.txt` | сообщение коммита для MR |
| `tts.py` | готовый `video/engine/tts.py`, если патч не накладывается |
| `test_tts_server.py` | проверка HTTP-движка на имитаторе сервера (127.0.0.1); в MR не входит. Запуск: `python3 test_tts_server.py ПУТЬ/video/engine/tts.py`, нужен ffmpeg |

Порядок применения — `../vybor-sintezatora.md`, п. 5. `engine/config.json` и `themes/gololed/story.json` в патч не
входят: их содержимого не было, правки описаны там же.
