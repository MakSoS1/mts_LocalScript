#!/usr/bin/env bash
set -euo pipefail

ollama create localscript-qwen25coder7b -f Modelfiles/qwen25coder7b
ollama create localscript-deepseekr1-8b -f Modelfiles/deepseekr1_8b
ollama create localscript-qwen3-8b -f Modelfiles/qwen3_8b
ollama create localscript-gemma3-4b -f Modelfiles/gemma3_4b
ollama create localscript-qwen25coder3b -f Modelfiles/qwen25coder3b

ollama list
