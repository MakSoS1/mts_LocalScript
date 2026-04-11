# OpenAPI Summary

## API
Сервис предоставляет один основной endpoint для генерации Lua-кода по задаче на естественном языке.

## Base URL
`http://localhost:8080`

## Endpoint
### `POST /generate`

### Назначение
Сгенерировать Lua-код по текстовому описанию задачи.

### Request
Content-Type: `application/json`

Body:
```json
{
  "prompt": "Функция factorial(n) для n >= 0"
}
```

### Request schema

- `prompt` — string, обязательное поле
- содержит текст задачи на естественном языке

### Response 200

Content-Type: `application/json`

Body:

```json
{
  "code": "function factorial(n)\n  if n <= 1 then return 1 end\n  return n * factorial(n - 1)\nend"
}
```

### Response schema

- `code` — string, обязательное поле
- содержит сгенерированный Lua-код

## Выводы для реализации

1. Внешний контракт очень простой: на входе только `prompt`, на выходе только `code`.
2. Любая агентность, retrieval, уточнение, self-repair и валидация должны происходить внутри сервиса до формирования итогового поля `code`.
3. API не требует stream-ответа.
4. Для жюри важно, чтобы ответ был детерминированным, воспроизводимым и пригодным к автоматической проверке.
5. На уровне API удобно оставить сервис тонким, а всю логику вынести в orchestrator.

## Практический вывод

Лучший вариант — реализовать внутри `/generate` такой pipeline:

1. normalize prompt
2. retrieve domain rules and examples
3. run model
4. validate output
5. repair once if needed
6. return final code
