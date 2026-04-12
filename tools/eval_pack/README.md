# Eval Pack (Out of Submission Pipeline)

Расширенный набор проверок для внутренних quality/agentness/locality экспериментов.

## Что внутри
- `dataset.jsonl` — кейсы для:
  - metamorphic
  - oracle
  - mutation
  - false-friend
  - retrieval-poisoning
  - contract-drift
  - ambiguity
  - contradiction
  - multi-turn-repair
  - minimal-delta
  - determinism-band
  - manual suites: no-network, judge-lock, gpu-offload-guard
- `run_eval_pack.py` — runner, который пишет отчёты в `tools/eval_pack/reports/`.

## Быстрый запуск
```bash
python tools/eval_pack/run_eval_pack.py
```

## Важно
- Eval pack не вызывается из `scripts/bootstrap.*` и `scripts/control_run.*`.
- Сюиты `no-network`, `judge-lock`, `gpu-offload-guard` отмечены как manual и не проходят автоматически.
