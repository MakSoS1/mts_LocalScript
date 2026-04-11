# LocalScript Agent Pipeline (Final Submission Profile)

Финальный профиль зафиксирован на одной основной модели:
- `required_demo_model = localscript-qwen25coder7b`

Решение локальное:
- FastAPI + Ollama
- planner -> retrieval -> generation -> validators -> repair(1 pass)
- без внешних LLM API

## Основной контракт API
- `POST /generate`  
  request: `{"prompt":"..."}`  
  response: `{"code":"..."}`
- `GET /health`
- `GET /models`
- `POST /benchmark`

## Что важно для жюри
- Финальный runtime использует только `localscript-qwen25coder7b`.
- Optional benchmark модели не требуются для `health=ok`.
- `docker-compose` Linux-safe:
  - `extra_hosts: host.docker.internal:host-gateway`
- Есть fail-fast bootstrap.
- Есть контрольный прогон одной командой.

## Быстрый запуск (bootstrap)

Linux/macOS:
```bash
./scripts/bootstrap.sh
```

Windows PowerShell:
```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\bootstrap.ps1
```

Bootstrap делает:
1. `ollama pull qwen2.5-coder:7b`
2. `ollama create localscript-qwen25coder7b -f Modelfiles/qwen25coder7b`
3. `docker compose up --build -d`

Если Docker не запущен или не в Linux containers mode, скрипт завершится с ошибкой.

## Контрольный прогон (submission check)

Linux/macOS:
```bash
./scripts/control_run.sh
```

Windows PowerShell:
```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\control_run.ps1
```

Контрольный прогон:
1. чистит workspace от `app/reports/*`, `.pytest_cache`, `__pycache__`, `*.pyc`, `.DS_Store`
2. запускает `pytest`
3. запускает `R3` benchmark на `dataset_public` и `dataset_augmented` только на `localscript-qwen25coder7b`
4. строит `comparative_report.md`
5. печатает `ollama ps` и `nvidia-smi`

## Пример ручного запуска
```powershell
$env:OLLAMA_BASE_URLS="http://localhost:11434"
py -m app.benchmark.runner --model localscript-qwen25coder7b --dataset app/benchmark/dataset_public.jsonl --mode R3
```

## Конфиг финального профиля
См. `.env.example`:
- `REQUIRED_DEMO_MODEL=localscript-qwen25coder7b`
- `DEFAULT_MODEL=localscript-qwen25coder7b`
- `OPTIONAL_BENCHMARK_MODELS=` (пусто)

## Make targets
- `make bootstrap`
- `make clean`
- `make control-run`
- `make benchmark MODEL=localscript-qwen25coder7b DATASET=app/benchmark/dataset_public.jsonl MODE=R3`

## Файлы
- `app/core/planner.py` — stage 1 planning
- `app/core/retrieval.py` — retrieval + archetype selection
- `app/core/orchestrator.py` — pipeline orchestration
- `app/validators/*` — output/domain/contract/syntax/task validators
- `scripts/bootstrap.*` — воспроизводимый bootstrap
- `scripts/control_run.*` — контрольный прогон для submission

## Официальные источники моделей
- [qwen2.5-coder](https://ollama.com/library/qwen2.5-coder)
- [deepseek-r1](https://ollama.com/library/deepseek-r1)
- [qwen3](https://ollama.com/library/qwen3)
- [gemma3](https://ollama.com/library/gemma3)
- [gemma4](https://ollama.com/library/gemma4)

## Чеклист для жюри
1. Запустить bootstrap (`scripts/bootstrap.ps1` или `scripts/bootstrap.sh`).
2. Проверить `/health` и `/models`.
3. Выполнить `scripts/control_run.ps1` или `scripts/control_run.sh`.
4. Открыть `app/reports/*.json` и `comparative_report.md`.
