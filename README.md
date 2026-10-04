# StroySync — интеллектуальное сопоставление видеонаблюдения с календарным графиком

Прототип для хакатона: по снимку строительной площадки система находит технику
(самосвал, экскаватор, каток, кран-манипулятор, бетоносмеситель, бульдозер,
грузовик, автокран), связывает кадр с этапом WBS и формирует **объяснимые**
предупреждения об отклонениях.

## Что внутри

| Компонент | Стек |
|---|---|
| Детекция | YOLO-World (open-vocabulary) / YOLOv8 COCO / demo-режим |
| Backend | Python, FastAPI, SQLAlchemy |
| Frontend | React + Vite |
| БД | SQLite (локально) или PostgreSQL (Docker) |
| Документы | `docs/` — презентация PPTX и сопроводительный DOCX |

Ключевая идея: не «просто детектор техники», а **проверяемая связь**
`камера → зона → активный WBS → допустимый состав машин → предупреждение с правилом`.

```
Снимок камеры ──► Детектор техники ──► Множество классов
                         │
Календарный график ──────┼──► Jaccard к typical_signature этапа
Камера.linked_wbs ───────┘
                         │
                         ▼
              Статус: в графике / отклонение / критично
              + объяснение: какое правило, какой WBS, что видно
```

## Быстрый старт (Windows)

Нужны Python 3.11+ и Node.js 20+. Команды ниже запускаются из корня репозитория.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
python scripts\generate_samples.py
$env:PYTHONPATH = "$pwd\backend"
$env:DETECTOR_BACKEND = "demo"
uvicorn app.main:app --app-dir backend --reload --port 8000
```

В другом терминале:

```powershell
cd frontend
npm install
npm run dev
```

Откройте http://localhost:8000 — дашборд и API в одном процессе.

- Демо-сцены на панели слева прогоняют готовые кадры.
- Можно загрузить своё фото и выбрать камеру.
- OpenAPI: http://localhost:8000/docs

Опционально React-интерфейс (если установлен Node.js):

```powershell
cd frontend
npm install
npm run dev
```

http://localhost:5173 (проксирует `/api` на backend).

CLI:

```powershell
$env:PYTHONPATH = "$pwd\backend"
python -m app.cli analyze data\samples\sample_foundation.jpg --camera CAM-01 --at 2026-09-17T10:15:00
```

## Docker

```powershell
docker compose up --build
```

Интерфейс: http://localhost:8080  
API: http://localhost:8000/docs

По умолчанию контейнер стартует с `DETECTOR_BACKEND=demo` (без скачивания весов).
Чтобы включить YOLO-World:

```powershell
$env:DETECTOR_BACKEND = "world"   # или auto
docker compose up --build
```

и задайте ту же переменную в `docker-compose.yml` у сервиса `backend`.

## Режимы детектора

| `DETECTOR_BACKEND` | Поведение |
|---|---|
| `demo` | Стабильные боксы по имени сцены. Для питча и CI. |
| `world` | Ultralytics YOLO-World, 8 классов по текстовым промптам. |
| `coco` | YOLOv8n, грубое отображение COCO→техника. |
| `auto` | world → coco → demo |

Модель **не дообучалась на закрытом датасете организаторов**: прототип использует
открытую open-vocabulary модель и явную базу правил. Дообучение на разметке
площадки — следующий шаг (см. документацию).

## Структура

```
backend/app/          API, модели БД, детектор, matcher
frontend/             дашборд
data/schedule/        CSV/XLSX календарный график
data/samples/         синтетические снимки для демо
docs/                 презентация и сопроводительная документация
scripts/              генерация сэмплов и документов
```

## Тесты логики сопоставления

```powershell
cd backend
pytest -q
```

## Сдача

- Репозиторий: этот каталог
- Прототип: веб-интерфейс + REST API
- Презентация: `docs/StroySync_Presentation.pptx`
- Документация: `docs/StroySync_Documentation.docx`
- Краткое описание (промежуточная сдача): `docs/INTERIM.md`
