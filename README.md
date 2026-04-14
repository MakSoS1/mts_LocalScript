# LocalScript Agent Pipeline (Final Submission Profile)

> **Инструкция для легкого запуска** см. раздел [Быстрый запуск (Docker)](#быстрый-запуск-docker) ниже. Рекомендуемый способ: `docker compose up --build`, однострочный.
>
> Обязательно приложите инструкцию для легкого запуска вашего решения на любой ОС (рекомендуем Docker) и перепроверьте процесс запуска на разных машинах! От этого напрямую зависит, сможет ли комиссия жюри оценить работоспособность проекта.

Финальный submission-профиль зафиксирован на одной основной модели:
- `required_demo_model = localscript-qwen25coder7b`

Решение полностью локальное:
- FastAPI + Ollama
- pipeline: `TaskCard spec -> IR generation -> Lua code generation -> luac/luacheck/stylua + domain/runtime validators -> runtime oracle -> structured failure report -> targeted repair`
- без внешних LLM API
- **Оценка по результату выполнения кода**, а не по совпадению с текстовым шаблоном (runtime oracle)
- **IR-first generation**: модель сначала выдает структурированный JSON-IR, потом из него генерируется Lua (inspired by AutoBe)
- **TaskCard spec**: планировщик формирует исполнимую спецификацию с edge cases и acceptance criteria
- **GUI chat interface**: веб-интерфейс в стиле Codex с сессиями, историей и подсветкой кода

> **Примечание о версии Lua**: В задании указан Lua 5.5, но на момент хакатона стабильного Lua 5.5 не существует. Проверка и исполнение производятся на Lua 5.4 (в Docker-контейнере) или Lua 5.1 (на Windows-хосте). Синтаксис генерируемого кода совместим с обоими.

## Что делает репозиторий
- Поднимает HTTP API для генерации Lua/LocalScript (`/generate`, `/agent/generate`)
- **GUI chat interface**: веб-интерфейс по адресу `/` или `/ui` с сессиями, историей, подсветкой кода и статусами валидации
- Дает health/model introspection (`/health`, `/models`)
- Запускает benchmark (`/benchmark`, `app.benchmark.runner`)
- Содержит strict submission-пайплайн (`scripts/control_run*`, `scripts/judge_check.py`)
- Хранит расширенный Eval Pack отдельно от финального submission pipeline (`tools/eval_pack`)
- **Runtime oracle**: оценивает семантику кода не по ключевым словам, а по результату исполнения на fixture-данных
- **IR-first generation**: структурированный промежуточный формат (AutoBe-style) для повышения качества генерации
- **User business cases**: 18 реальных сценариев из CRM/интеграций в `tools/eval_pack/user_cases.py`

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

## Быстрый запуск (Docker)

### Рекомендуемый способ - Docker (одна команда):

Linux/macOS:
```bash
# 1. Убедитесь, что Ollama запущена и модель скачана:
ollama pull qwen2.5-coder:7b
ollama create localscript-qwen25coder7b -f Modelfiles/qwen25coder7b

# 2. Создайте .env (если нет):
cp .env.example .env

# 3. Запустите:
docker compose up --build -d

# 4. Проверьте:
curl -s http://localhost:8080/health
curl -s http://localhost:8080/models
```

Windows PowerShell:
```powershell
# 1. Убедитесь, что Ollama запущена и модель скачана:
ollama pull qwen2.5-coder:7b
ollama create localscript-qwen25coder7b -f Modelfiles/qwen25coder7b

# 2. Создайте .env (если нет):
Copy-Item .env.example .env

# 3. Запустите:
docker compose up --build -d

# 4. Проверьте:
Invoke-RestMethod http://localhost:8080/health
Invoke-RestMethod http://localhost:8080/models
```

Docker-образ содержит все необходимые инструменты: `lua5.4`, `luacheck`, `stylua`.

### Альтернатива - bootstrap-скрипт (автоматизирует всё выше):

Linux/macOS:
```bash
./scripts/bootstrap.sh
```

Windows PowerShell:
```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\bootstrap.ps1
```

`bootstrap` делает всё автоматически:
1. создает `.env` из `.env.example` (если `.env` отсутствует)
2. `ollama pull qwen2.5-coder:7b`
3. `ollama create localscript-qwen25coder7b -f Modelfiles/qwen25coder7b`
4. `docker compose up --build -d`

### Запуск без Docker (локально):

```bash
# Требования: Python 3.11+, Lua (5.1+), Ollama

# 1. Установите зависимости:
pip install -r requirements.txt

# 2. Создайте .env:
cp .env.example .env
# Отредактируйте OLLAMA_BASE_URL и LUAC_BINARY под вашу систему

# 3. Запустите API:
python -m uvicorn app.main:app --host 0.0.0.0 --port 8080

# 4. Проверьте:
curl -s http://localhost:8080/health
```

## Быстрая проверка после запуска
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

## Система оценки (runtime oracle)

Система оценки основана на **результате выполнения кода**, а не на совпадении с текстовым шаблоном:

1. **Hard gate** (код должен пройти обязательно):
   - output valid (есть return, нет prose)
   - contract valid (формат json_with_lua_wrappers или raw_lua как ожидается)
   - domain valid (нет JsonPath, нет запрещенных путей)
   - syntax valid (luac pass)

2. **Runtime oracle** (основная семантическая оценка):
   - если в кейсе есть `wf_fixture` и `expected_runtime_output` - код исполняется на fixture и результат сравнивается с ожидаемым
   - если runtime oracle недоступен - fallback на pattern-based heuristic (ослабленную)

3. **Scoring weights** (после hard gate):
   - 55% runtime semantics
   - 15% syntax
   - 10% output/contract
   - 10% domain compliance
   - 10% latency

4. **Task validator** - используется как repair-hint, а не как главный scorer. Корректное решение с другим именем функции или стилем не будет отвергнуто.

## Инновационные подходы

### IR-first generation (inspired by AutoBe)
Вместо прямой генерации Lua из промпта, система использует двухфазный подход:
1. **IR phase**: модель генерирует структурированный JSON-IR (intermediate representation) с полями `read_from`, `operation`, `fields`, `return_as`, `edge_cases`
2. **Code phase**: из IR генерируется Lua код

Преимущества:
- Уменьшает хаос генерации - модель сначала фиксирует структуру задачи
- Позволяет валидировать IR до генерации кода
- При ошибке ремонт чинит конкретный фрагмент, а не весь код
- Если IR генерация неуспешна, система автоматически откатывается к прямой генерации

### TaskCard spec (inspired by Claude Code framework)
Планировщик формирует исполнимую спецификацию TaskCard:
- `operation_type` - тип операции (increment, filter, conditional_return, aggregate, etc.)
- `source_paths` - откуда берутся данные
- `fields_to_keep` - какие поля сохранять
- `edge_cases` - граничные случаи (nil_guard, empty_array, string_number)
- `acceptance_criteria` - критерии приемки

### Structured failure report для targeted repair (AutoBe-style)
При ошибке ремонт получает не общий текст, а структурированный отчет:
- `syntax: unexpected symbol near ')'`
- `contract: expected json_with_lua_wrappers`
- `runtime: expected 1697383800, got nil`

### Dynamic benchmark (inspired by DRAGOn)
- 18 пользовательских бизнес-сценариев (CRM, интеграции, SLA, маршрутизация)
- Каждая задача проверяется на реальной fixture через runtime oracle
- Variants: ru/en/noisy формулировки одной задачи
- Followup scenarios: смена ключа, смена формата
- False-friend: "последний" vs "предпоследний"

## GUI Chat Interface

Веб-интерфейс доступен по адресу `http://localhost:8080/` или `/ui`:
- Темная тема в стиле VS Code / Codex
- Сессии с сохранением в localStorage
- Подсветка Lua кода (highlight.js)
- Кнопка копирования кода
- Статусы валидации (pass/fail badges)
- Выбор модели из списка
- Кнопка "Regenerate"
- Поддержка follow-up диалога

## Конфиг финального профиля (`.env.example`)
- `REQUIRED_DEMO_MODEL=localscript-qwen25coder7b`
- `DEFAULT_MODEL=localscript-qwen25coder7b`
- `OPTIONAL_BENCHMARK_MODELS=` (пусто)
- `STRICT_MODELS=` (пусто)
- `OLLAMA_NUM_BATCH=1`
- `GENERATION_CANDIDATE_COUNT=3`
- `SYNTAX_REQUIRE_LUAC=false` (в strict run включается скриптами)
- `OLLAMA_BASE_URLS=http://host.docker.internal:11434,http://localhost:11434`

Judge-профиль зафиксирован так:
- `num_ctx=4096`
- `num_predict=256`
- `batch=1`
- `parallel=1`
- GPU-only runtime, без внешних AI API

Windows host defaults в `.env.example` указывают на project-local `.tools` для `luacheck/stylua`.
В Docker эти значения переопределяются на `luacheck` и `stylua`, потому что оба инструмента встроены в контейнер.

## Соответствие заданию
- Локальный запуск: весь runtime работает через Ollama + Docker локально, без внешних LLM-вендоров.
- Агентность: есть clarification endpoint и управляемый цикл генерации/ремонта, а не один слепой ответ модели.
- Валидация: используются `luac`, `luacheck`, `stylua`, доменные валидаторы и runtime-проверки на фикстурах.
- Воспроизводимость: для жюри есть однострочный bootstrap на Windows и Linux/macOS, плюс container control run.
- Без CI/CD: все проверки, контейнеры и окружения запускаются локально, как требуется условиями.
- База знаний и retrieval работают локально из `app/kb`.
- Архитектура C4 находится в `docs/C4.md`.

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
- Теперь включает runtime oracle проверки для кейсов с `wf_fixture` и `expected_runtime_output`
- Эти проверки не запускаются из `bootstrap/control_run` и хранятся отдельно от финального judge pipeline

## Ключевые файлы
- `app/main.py` - сборка FastAPI приложения и роутеров
- `app/static/index.html` - GUI chat interface (Codex-like)
- `app/core/planner.py` - TaskCard spec planning + контракт вывода
- `app/core/retrieval.py` - retrieval контекста
- `app/core/prompts.py` - промпты для генерации, IR и ремонта
- `app/core/orchestrator.py` - orchestration + IR phase + repair loop
- `app/benchmark/oracle.py` - runtime oracle: исполнение Lua на fixture + сравнение результата
- `app/benchmark/scoring.py` - scoring с runtime oracle priority
- `app/validators/*` - domain/format/syntax/task validators
- `tools/eval_pack/user_cases.py` - 18 бизнес-сценариев для тестирования
- `scripts/bootstrap.*` - воспроизводимый bootstrap
- `scripts/control_run.*` - host strict контрольный прогон
- `scripts/control_run_container.*` - container reproducible контрольный прогон
- `scripts/judge_check.py` - preflight/post judge guardrails

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
