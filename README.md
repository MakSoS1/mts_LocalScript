# LocalScript Agent

Локальный AI-агент для генерации Lua/LocalScript без внешних LLM API в runtime.

## Что делает проект
- Поднимает API для генерации Lua (`/generate`, `/agent/generate`)
- Проверяет код валидаторами (format/contract/domain/syntax)
- Поддерживает benchmark и контрольный pipeline
- Имеет веб-интерфейс (GUI) для чата

## Требования
- Docker (Linux containers)
- Ollama (`http://localhost:11434`)
- Модель для демо: `localscript-qwen25coder7b`

## API одной командой
Linux/macOS:
```bash
./scripts/start_api.sh
```

Windows PowerShell:
```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_api.ps1
```

Что делает этот запуск:
- проверяет Docker/Ollama
- создаёт `.env`, если файла нет
- подтягивает/создаёт модель `localscript-qwen25coder7b` (если её нет)
- проверяет порт API и при конфликте автоматически переключает с `8080` на `18080`
- собирает контейнер API
- поднимает API в фоне (`docker compose up -d`)

API работает, пока вы его не остановите (`docker compose stop api`).

## Интерфейс отдельно
Linux/macOS:
```bash
./scripts/start_ui.sh
```

Windows PowerShell:
```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_ui.ps1
```

По умолчанию GUI: `http://localhost:<API_PORT>/ui` (также доступно `/`).
Скрипт `start_api` печатает итоговый URL и сохраняет порт в `.api-port`, `start_ui` подхватывает его автоматически.

## Полный контрольный прогон одной командой (Docker-only)
Linux/macOS:
```bash
./scripts/control_run_container.sh
```

Windows PowerShell:
```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\control_run_container.ps1
```

Что делает команда:
- очищает workspace
- фиксирует demo-профиль модели
- собирает Docker image
- поднимает контейнер
- запускает `pytest` в контейнере
- запускает benchmark (`dataset_public` + `dataset_augmented`)
- строит comparative report
- делает post-check (включая VRAM guard)

## Кроссплатформенность контейнера
Контейнер универсальный для Docker Engine / Docker Desktop на Windows, Linux, macOS:
- образ собирается как Linux-контейнер (`Docker daemon = linux`)
- запуск не завязан на host shell (есть `.sh` и `.ps1` скрипты)
- compose-конфиг одинаковый для всех ОС

## Если Docker в SSH ругается на credentials helper
Для удалённого Windows-хоста скрипты уже используют устойчивый путь:
- сборка через `docker build`
- запуск через `docker compose up --no-build`
- локальный base image alias `localscript-python311-slim:local`

Нужно только, чтобы на хосте уже был `python:3.11-slim` (скрипт автоматически перетегирует его в локальный alias).

## Быстрая проверка генерации через API
```bash
curl -s -X POST http://localhost:8080/agent/generate \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Из номера телефона клиента phone очисти все символы кроме цифр. Если номер начинается с 8 и содержит 11 цифр, замени первую цифру на 7. Верни результат в переменную normalizedPhone.",
    "assumption": "json_with_lua_wrappers"
  }'
```

## Полезные команды
```bash
# API одной командой через Make
make api-up

# GUI отдельно
make ui-up

# локальные тесты
pytest -q

# benchmark вручную
python -m app.benchmark.runner --model localscript-qwen25coder7b --dataset app/benchmark/dataset_public.jsonl --mode R3

# остановить контейнер
docker compose down
```
