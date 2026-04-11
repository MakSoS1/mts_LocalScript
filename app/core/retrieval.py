from __future__ import annotations

import json
import math
from dataclasses import dataclass

from app.config import Settings
from app.utils.normalize import tokenize


@dataclass(slots=True)
class ExampleItem:
    id: str
    lang: str
    task: str
    output_mode: str
    expected_lua: str
    tags: list[str]
    archetype: str
    critical_pattern: str


@dataclass(slots=True)
class RetrievalContext:
    rules: str
    anti_patterns: str
    repair_hints: str
    examples: list[ExampleItem]


KEYWORD_BOOSTS = {
    "email": ["email", "last-element"],
    "последний": ["last-element"],
    "last": ["last-element"],
    "iso": ["iso8601", "datetime"],
    "yyyy": ["iso8601", "datetime"],
    "unix": ["unix-time", "datetime"],
    "array": ["array", "array-normalization"],
    "массив": ["array", "array-normalization"],
    "discount": ["filter"],
    "markdown": ["filter"],
    "try_count": ["increment", "counter"],
    "idoc": ["idoc", "datetime"],
    "recalltime": ["unix-time"],
}


def _infer_archetype(example_id: str, tags: list[str]) -> str:
    lowered_id = example_id.lower()
    lowered_tags = " ".join(tag.lower() for tag in tags)

    if "last" in lowered_id or "last-element" in lowered_tags:
        return "last_element"
    if "increment" in lowered_id or "counter" in lowered_tags:
        return "increment"
    if "cleanup" in lowered_id or "filter-keys" in lowered_tags:
        return "keep_only_fields"
    if "datum" in lowered_id or ("iso8601" in lowered_tags and "unix-time" not in lowered_tags):
        return "datum_time_to_iso"
    if "unix" in lowered_id or "unix-time" in lowered_tags:
        return "iso_to_unix"
    if "ensure" in lowered_id or "array-normalization" in lowered_tags:
        return "ensure_array"
    if "discount" in lowered_id or ("filter" in lowered_tags and "markdown" in lowered_tags):
        return "filter_non_empty"
    if "square" in lowered_id or "squared" in lowered_tags:
        return "multi_field_json"
    return "generic"


def _infer_critical_pattern(expected_lua: str) -> str:
    code = expected_lua.strip()
    if "wf.vars.emails[#wf.vars.emails]" in code:
        return "Use last element via #array index."
    if "try_count_n + 1" in code:
        return "Increment counter by one."
    if "RESTbody.result" in code and "filteredEntry[key] = nil" in code:
        return "Keep only required keys and nil others."
    if "DATUM" in code and "string.format" in code:
        return "Parse DATUM/TIME and format ISO 8601."
    if "ensureArray" in code and "ipairs" in code:
        return "Normalize object/array shape before iteration."
    if "_utils.array.new()" in code and "Discount" in code and "Markdown" in code:
        return "Filter non-empty Discount/Markdown into array result."
    if "recallTime" in code and "days_since_epoch" in code:
        return "Parse ISO8601 with timezone to unix epoch."
    if "squared" in code and "tonumber" in code:
        return "Build multi-field JSON with derived value."
    return "Minimal valid Lua using domain paths only."


class LocalRetriever:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._rules = self._read_text("lowcode_rules.md")
        self._anti_patterns = self._read_text("anti_patterns.md")
        self._repair_hints = self._read_text("repair_hints.md")
        self._examples = self._load_examples(["examples_public.jsonl", "examples_synthetic.jsonl"])

    def _read_text(self, file_name: str) -> str:
        path = self.settings.kb_path / file_name
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8").strip()

    def _load_examples(self, file_names: list[str]) -> list[ExampleItem]:
        items: list[ExampleItem] = []
        for file_name in file_names:
            path = self.settings.kb_path / file_name
            if not path.exists():
                continue

            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                payload = json.loads(line)
                tags = [str(t) for t in payload.get("tags", [])]
                example_id = str(payload.get("id", "unknown"))
                expected_lua = str(payload.get("expected_lua", ""))
                items.append(
                    ExampleItem(
                        id=example_id,
                        lang=str(payload.get("lang", "unknown")),
                        task=str(payload.get("task", "")),
                        output_mode=str(payload.get("output_mode", "raw_lua")),
                        expected_lua=expected_lua,
                        tags=tags,
                        archetype=_infer_archetype(example_id, tags),
                        critical_pattern=_infer_critical_pattern(expected_lua),
                    )
                )
        return items

    def _idf(self, token: str, docs: list[list[str]]) -> float:
        docs_with_token = sum(1 for doc in docs if token in doc)
        return math.log((len(docs) - docs_with_token + 0.5) / (docs_with_token + 0.5) + 1)

    def _bm25_score(self, query: list[str], doc: list[str], all_docs: list[list[str]]) -> float:
        if not doc:
            return 0.0
        avg_len = sum(len(d) for d in all_docs) / max(len(all_docs), 1)
        k1 = 1.5
        b = 0.75
        score = 0.0
        for token in query:
            tf = doc.count(token)
            if tf == 0:
                continue
            idf = self._idf(token, all_docs)
            numer = tf * (k1 + 1)
            denom = tf + k1 * (1 - b + b * len(doc) / max(avg_len, 1e-9))
            score += idf * (numer / denom)
        return score

    def _keyword_boost(self, query_tokens: list[str], tags: list[str]) -> float:
        tags_set = set(tag.lower() for tag in tags)
        boost = 0.0
        for token in query_tokens:
            for mapped in KEYWORD_BOOSTS.get(token, []):
                if mapped.lower() in tags_set:
                    boost += 0.75
        return boost

    def _rank_examples(self, task: str, top_k: int = 2) -> list[ExampleItem]:
        if not self._examples:
            return []

        query_tokens = tokenize(task)
        docs = [tokenize(f"{item.task} {' '.join(item.tags)} {item.archetype}") for item in self._examples]

        scored: list[tuple[float, int]] = []
        for idx, item in enumerate(self._examples):
            bm25 = self._bm25_score(query_tokens, docs[idx], docs)
            boost = self._keyword_boost(query_tokens, item.tags)
            scored.append((bm25 + boost, idx))

        scored.sort(reverse=True)
        if not scored:
            return []

        selected_top_k = top_k
        if len(scored) > 1 and (scored[0][0] - scored[1][0]) >= 1.2:
            selected_top_k = 1

        return [self._examples[idx] for _, idx in scored[:selected_top_k]]

    def retrieve_context(
        self,
        task: str,
        include_rules: bool = True,
        include_examples: bool = True,
        top_k: int = 2,
    ) -> RetrievalContext:
        examples = self._rank_examples(task, top_k=top_k) if include_examples else []
        return RetrievalContext(
            rules=self._rules if include_rules else "",
            anti_patterns=self._anti_patterns if include_rules else "",
            repair_hints=self._repair_hints if include_rules else "",
            examples=examples,
        )
