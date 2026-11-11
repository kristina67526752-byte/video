# Статья для «Научного вестника МГТУ ГА» (задача Битрикс24 № 348342)

- `komplekt-v3.3/` — комплект версии 3.3: рукопись, рисунки, ответы на замечания и рецензию, документы подачи, эксперимент.
- `komplekt-v3.3-statya-mgtu-ga.zip` — тот же комплект одним архивом.
- `tools/build_v32.py`, `tools/build_v33.py`, `tools/texts_v33.py` — сборка рукописи из распакованного DOCX версии 3.1; все числа версии 3.3 подставляются из `5-eksperiment/results/summary.json`.
- `tools/update_docs_v32.py`, `tools/update_docs_v33.py` — документы комплекта.

С чего начать: `komplekt-v3.3/3-otvety-i-materialy/otvety-na-retsenziyu-2026-11-10.docx`.

PDF собираются LibreOffice; для формул нужен пакет `libreoffice-math` (без него формулы молча пропадают).
