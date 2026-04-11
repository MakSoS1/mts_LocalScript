import json

from app.config import Settings
from app.core.retrieval import LocalRetriever


def test_retrieval_ranks_email_example_first(tmp_path) -> None:
    kb = tmp_path / "kb"
    kb.mkdir()
    (kb / "lowcode_rules.md").write_text("rules", encoding="utf-8")
    (kb / "anti_patterns.md").write_text("anti", encoding="utf-8")
    (kb / "repair_hints.md").write_text("hints", encoding="utf-8")
    (kb / "openapi_summary.md").write_text("openapi", encoding="utf-8")

    examples = [
        {
            "id": "email_case",
            "lang": "ru",
            "task": "верни последний email",
            "input_context": {"wf": {"vars": {"emails": ["a", "b"]}}},
            "output_mode": "json_with_lua_wrappers",
            "expected_lua": "return wf.vars.emails[#wf.vars.emails]",
            "expected_json": {"lastEmail": "lua{return wf.vars.emails[#wf.vars.emails]}lua"},
            "tags": ["email", "last-element"],
        },
        {
            "id": "date_case",
            "lang": "ru",
            "task": "конвертируй дату в unix",
            "input_context": {"wf": {"initVariables": {"recallTime": "2024-01-01T00:00:00+00:00"}}},
            "output_mode": "json_with_lua_wrappers",
            "expected_lua": "return 1704067200",
            "expected_json": {"unix": "lua{return 1704067200}lua"},
            "tags": ["datetime", "unix-time"],
        },
    ]
    (kb / "examples_public.jsonl").write_text(
        "\n".join(json.dumps(x, ensure_ascii=False) for x in examples),
        encoding="utf-8",
    )

    settings = Settings(
        kb_dir=str(kb),
        reports_dir=str(tmp_path / "reports"),
        strict_models="localscript-qwen25coder7b",
        default_model="localscript-qwen25coder7b",
    )

    retriever = LocalRetriever(settings)
    context = retriever.retrieve_context("получи последний email", include_rules=True, include_examples=True)

    assert context.examples
    assert context.examples[0].id == "email_case"
