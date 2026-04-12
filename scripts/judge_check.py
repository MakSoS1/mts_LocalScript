from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


def _run(cmd: list[str]) -> str:
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        stderr = (proc.stderr or "").strip()
        stdout = (proc.stdout or "").strip()
        details = stderr or stdout or "unknown error"
        raise RuntimeError(f"Command failed: {' '.join(cmd)} :: {details}")
    return (proc.stdout or "").strip()


def _assert_model_parameters(
    model: str,
    expected_num_ctx: int,
    expected_num_predict: int,
) -> None:
    output = _run(["ollama", "show", model])

    num_ctx_match = re.search(r"^\s*num_ctx\s+(\d+)\s*$", output, re.MULTILINE)
    num_predict_match = re.search(r"^\s*num_predict\s+(\d+)\s*$", output, re.MULTILINE)

    if not num_ctx_match:
        raise RuntimeError("Could not find num_ctx in `ollama show` output.")
    if not num_predict_match:
        raise RuntimeError("Could not find num_predict in `ollama show` output.")

    num_ctx = int(num_ctx_match.group(1))
    num_predict = int(num_predict_match.group(1))

    if num_ctx != expected_num_ctx:
        raise RuntimeError(f"num_ctx mismatch: expected {expected_num_ctx}, got {num_ctx}")
    if num_predict != expected_num_predict:
        raise RuntimeError(f"num_predict mismatch: expected {expected_num_predict}, got {num_predict}")


def _assert_runtime_parallel_and_batch(expected_num_batch: int, expected_parallel: int) -> None:
    env_num_batch = os.getenv("OLLAMA_NUM_BATCH", "").strip()
    if env_num_batch and int(env_num_batch) != expected_num_batch:
        raise RuntimeError(
            f"OLLAMA_NUM_BATCH mismatch: expected {expected_num_batch}, got {env_num_batch}"
        )

    env_parallel = os.getenv("OLLAMA_NUM_PARALLEL", "").strip()
    if env_parallel and int(env_parallel) != expected_parallel:
        raise RuntimeError(
            f"OLLAMA_NUM_PARALLEL mismatch: expected {expected_parallel}, got {env_parallel}"
        )


def _assert_runtime_gpu(model: str, expected_context: int) -> None:
    output = _run(["ollama", "ps"])
    lines = [line for line in output.splitlines() if line.strip()]
    model_lines = [line for line in lines if model in line]

    if not model_lines:
        raise RuntimeError(f"`ollama ps` does not show running model `{model}`.")

    line = model_lines[0]
    if "100% GPU" not in line:
        raise RuntimeError(f"Model is not fully on GPU: `{line}`")
    if str(expected_context) not in line:
        raise RuntimeError(f"Model context does not match expected {expected_context}: `{line}`")


def _assert_luac_available(luac_binary: str) -> None:
    if shutil.which(luac_binary) is None and shutil.which("luac") is None:
        raise RuntimeError(
            f"Required Lua compiler is missing (`{luac_binary}` or `luac`). "
            "Install lua5.4 or run strict checks in container."
        )


def _parse_vram_log(path: Path) -> int:
    if not path.exists():
        raise RuntimeError(f"VRAM log does not exist: {path}")

    peak = 0
    found = False
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) < 4:
            continue
        used_part = parts[3]
        match = re.search(r"(\d+)", used_part)
        if not match:
            continue
        peak = max(peak, int(match.group(1)))
        found = True

    if not found:
        raise RuntimeError(f"No parseable memory.used values found in {path}")
    return peak


def _sample_vram_once() -> int:
    output = _run(
        [
            "nvidia-smi",
            "--query-gpu=timestamp,name,memory.total,memory.used,utilization.gpu",
            "--format=csv,noheader",
        ]
    )
    peak = 0
    for line in output.splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) < 4:
            continue
        match = re.search(r"(\d+)", parts[3])
        if match:
            peak = max(peak, int(match.group(1)))
    if peak <= 0:
        raise RuntimeError("Could not parse current VRAM usage from nvidia-smi output.")
    return peak


def main() -> None:
    parser = argparse.ArgumentParser(description="Strict judge guardrails check")
    parser.add_argument("--phase", choices=["preflight", "post"], required=True)
    parser.add_argument("--model", default="localscript-qwen25coder7b")
    parser.add_argument("--expected-num-ctx", type=int, default=4096)
    parser.add_argument("--expected-num-predict", type=int, default=256)
    parser.add_argument("--expected-num-batch", type=int, default=1)
    parser.add_argument("--expected-parallel", type=int, default=1)
    parser.add_argument("--max-vram-mib", type=int, default=8192)
    parser.add_argument("--vram-log", default="")
    parser.add_argument("--strict-luac", action="store_true")
    parser.add_argument("--luac-binary", default="luac5.4")
    args = parser.parse_args()

    try:
        if args.phase == "preflight":
            _assert_model_parameters(
                model=args.model,
                expected_num_ctx=args.expected_num_ctx,
                expected_num_predict=args.expected_num_predict,
            )
            _assert_runtime_parallel_and_batch(
                expected_num_batch=args.expected_num_batch,
                expected_parallel=args.expected_parallel,
            )
            if args.strict_luac:
                _assert_luac_available(args.luac_binary)

        if args.phase == "post":
            _assert_runtime_gpu(args.model, expected_context=args.expected_num_ctx)
            if args.vram_log:
                peak = _parse_vram_log(Path(args.vram_log))
            else:
                peak = _sample_vram_once()

            if peak > args.max_vram_mib:
                raise RuntimeError(
                    f"Peak VRAM exceeded limit: peak={peak} MiB, limit={args.max_vram_mib} MiB"
                )
            print(f"Peak VRAM check passed: {peak} MiB <= {args.max_vram_mib} MiB")

        print(f"Judge check ({args.phase}) passed.")
    except Exception as exc:
        print(f"Judge check ({args.phase}) failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
