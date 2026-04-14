SHELL := /bin/bash

.PHONY: dev test benchmark docker demo lint bootstrap clean control-run

dev:
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8080

test:
	pytest -q

benchmark:
	python -m app.benchmark.runner --model $${MODEL:-localscript-qwen25coder7b} --dataset $${DATASET:-app/benchmark/dataset_public.jsonl} --mode $${MODE:-R3}

docker:
	docker compose up --build

demo:
	docker compose up --build

lint:
	python -m py_compile app/main.py

bootstrap:
	./scripts/bootstrap.sh

clean:
	./scripts/clean_submission.sh

control-run:
	./scripts/control_run.sh
