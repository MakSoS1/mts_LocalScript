# LocalScript Agent Pipeline (Final Submission Profile)

Финальный submission-профиль зафиксирован на одной основной модели:
- `required_demo_model = localscript-qwen25coder7b`

Решение полностью локальное:
- FastAPI + Ollama
- pipeline: `planner -> retrieval -> generation -> validators -> repair (max 1 pass)`
- без внешних LLM API

## Что делает репозиторий
- Поднимает HTTP API для генерации Lua/LocalScript (`/generate`, `/agent/generate`)
- Дает health/model introspection (`/health`, `/models`)
- Запускает benchmark (`/benchmark`, `app.benchmark.runner`)
- Содержит strict submission-пайплайн (`scripts/control_run*`, `scripts/judge_check.py`)
- Хранит расширенный Eval Pack отдельно от финального submission pipeline (`tools/eval_pack`)

## Требования

Обязательные:
- Docker (Docker Engine / Docker Desktop) с Linux containers mode
- Ollama, доступный по `http://localhost:11434`
- Python 3.11+ (для локального запуска скриптов/тестов)

Для strict judge-чеков:
- NVIDIA GPU + `nvidia-smi` (проверка `100% GPU` и peak VRAM)
- `luac5.4` (или `luac`) в `PATH` для host strict запуска (`scripts/control_run.sh/.ps1`)

Примечание:
- container-вариант (`control_run_container.*`) позволяет проводить strict syntax внутри контейнера (`lua5.4` ставится в `docker/Dockerfile.api`).

## Основной API контракт
- `POST /generate`
  - request: `{"prompt":"...", "model":"optional", "mode":"optional"}`
  - response: `{"code":"..."}`
- `POST /agent/generate`
  - demo endpoint для наблюдаемой агентности (clarification + repair)
  - статусы:
    - `clarification_required`: возвращает `question`, `acceptable_assumptions`, `assumptions`, `output_contract`
    - `generated` или `repaired`: возвращает `code` + метаданные
- `GET /health`
- `GET /models`
- `POST /benchmark`

## Быстрый запуск (bootstrap)

Linux/macOS:
```bash
./scripts/bootstrap.sh
```

Windows PowerShell:
```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\bootstrap.ps1
```

`bootstrap` делает:
1. создает `.env` из `.env.example` (если `.env` отсутствует)
2. `ollama pull qwen2.5-coder:7b`
3. `ollama create localscript-qwen25coder7b -f Modelfiles/qwen25coder7b`
4. `docker compose up --build -d`

Fail-fast поведение:
- если Docker не запущен или не в Linux containers mode, скрипт завершится ошибкой.

## Быстрая проверка после bootstrap
```bash
curl -s http://localhost:8080/health
curl -s http://localhost:8080/models
```

`/health` возвращает:
- `status=ok`, если Ollama доступен и required модель установлена
- `status=degraded`, если required модель отсутствует или Ollama недоступен

## Agent endpoint: практический сценарий

1) Запрос с неоднозначной задачей:
```json
POST /agent/generate
{
  "prompt": "Сделай LocalScript для GUI-инвентаря"
}
```
Можно получить `status=clarification_required`.

2) Подтверждение допущения и генерация:
```json
POST /agent/generate
{
  "prompt": "Сделай LocalScript для GUI-инвентаря",
  "assumption": "raw_lua"
}
```

3) Доисправление минимальным патчем:
```json
POST /agent/generate
{
  "prompt": "Сделай LocalScript для GUI-инвентаря",
  "previous_code": "...",
  "feedback": "Добавь debounce для кнопки"
}
```

## Контрольный прогон (submission check)

Host strict (рекомендуется для финальной self-check перед отправкой):
- Linux/macOS: `./scripts/control_run.sh`
- Windows: `powershell -ExecutionPolicy Bypass -File .\scripts\control_run.ps1`

Container reproducible (удобно для воспроизводимости окружения):
- Linux/macOS: `./scripts/control_run_container.sh`
- Windows: `powershell -ExecutionPolicy Bypass -File .\scripts\control_run_container.ps1`

### Что делают оба варианта
1. чистят workspace (`app/reports/*`, `.pytest_cache`, `__pycache__`, `*.pyc`, `.DS_Store`)
2. фиксируют профиль модели (`REQUIRED_DEMO_MODEL/DEFAULT_MODEL=localscript-qwen25coder7b`, `OPTIONAL_BENCHMARK_MODELS=`)
3. включают runtime guardrails (`OLLAMA_NUM_BATCH=1`, `OLLAMA_NUM_PARALLEL=1`)
4. выполняют preflight через `scripts/judge_check.py --phase preflight`
5. запускают `pytest`
6. запускают `R3` benchmark на `dataset_public` и `dataset_augmented`
7. строят `comparative_report.md`
8. выполняют post-check через `scripts/judge_check.py --phase post` (GPU-only + peak VRAM <= 8GB)
9. печатают `ollama ps` и `nvidia-smi`

### Важное различие между host и container
- `control_run.sh/.ps1` запускает preflight с `--strict-luac` (требует `luac5.4` на хосте)
- `control_run_container.sh/.ps1` запускает preflight без `--strict-luac` на хосте, но внутри контейнера ставит `SYNTAX_REQUIRE_LUAC=true` и исполняет strict syntax в контейнере

## Пример ручного benchmark запуска
```powershell
$env:OLLAMA_BASE_URLS="http://localhost:11434"
py -m app.benchmark.runner --model localscript-qwen25coder7b --dataset app/benchmark/dataset_public.jsonl --mode R3
```

## Конфиг финального профиля (`.env.example`)
- `REQUIRED_DEMO_MODEL=localscript-qwen25coder7b`
- `DEFAULT_MODEL=localscript-qwen25coder7b`
- `OPTIONAL_BENCHMARK_MODELS=` (пусто)
- `STRICT_MODELS=` (пусто)
- `OLLAMA_NUM_BATCH=1`
- `SYNTAX_REQUIRE_LUAC=false` (в strict run включается скриптами)
- `OLLAMA_BASE_URLS=http://host.docker.internal:11434,http://localhost:11434`

## Make targets
- `make bootstrap`
- `make clean`
- `make control-run`
- `make control-run-container`
- `make benchmark MODEL=localscript-qwen25coder7b DATASET=app/benchmark/dataset_public.jsonl MODE=R3`
- `make judge-preflight`
- `make judge-post`
- `make eval-pack`

## Eval Pack (вне submission pipeline)
- Папка: `tools/eval_pack/`
- Назначение: расширенные проверки (metamorphic, oracle, mutation, false-friend, ambiguity, multi-turn, determinism и др.)
- Эти проверки не запускаются из `bootstrap/control_run` и хранятся отдельно от финального judge pipeline

## Ключевые файлы
- `app/main.py` — сборка FastAPI приложения и роутеров
- `app/core/planner.py` — task planning + контракт вывода
- `app/core/retrieval.py` — retrieval контекста
- `app/core/orchestrator.py` — orchestration + repair loop
- `app/validators/*` — domain/format/syntax/task validators
- `scripts/bootstrap.*` — воспроизводимый bootstrap
- `scripts/control_run.*` — host strict контрольный прогон
- `scripts/control_run_container.*` — container reproducible контрольный прогон
- `scripts/judge_check.py` — preflight/post judge guardrails

## Официальные источники моделей
- [qwen2.5-coder](https://ollama.com/library/qwen2.5-coder)
- [deepseek-r1](https://ollama.com/library/deepseek-r1)
- [qwen3](https://ollama.com/library/qwen3)
- [gemma3](https://ollama.com/library/gemma3)
- [gemma4](https://ollama.com/library/gemma4)

## Чеклист для жюри
1. Запустить bootstrap (`scripts/bootstrap.ps1` или `scripts/bootstrap.sh`).
2. Проверить `/health` и `/models`.
3. Выполнить `scripts/control_run.ps1`/`scripts/control_run.sh` (или container-вариант).
4. Проверить `app/reports/*.json` и `comparative_report.md`.
