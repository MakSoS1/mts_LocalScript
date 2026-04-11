from pathlib import Path

KB_FILES = [
    "lowcode_rules.md",
    "anti_patterns.md",
    "repair_hints.md",
    "openapi_summary.md",
    "examples_public.jsonl",
]


def main() -> None:
    kb_dir = Path("app/kb")
    missing = [name for name in KB_FILES if not (kb_dir / name).exists()]
    if missing:
        raise SystemExit(f"Missing KB files: {missing}")
    print("KB is ready")


if __name__ == "__main__":
    main()
