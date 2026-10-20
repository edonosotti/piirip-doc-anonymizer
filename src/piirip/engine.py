"""Detection engine built on Presidio Analyzer."""
from __future__ import annotations

import inspect
from dataclasses import dataclass

from presidio_analyzer import AnalyzerEngine, EntityRecognizer, PatternRecognizer, RecognizerRegistry
from presidio_analyzer import predefined_recognizers as predefined
from presidio_analyzer.nlp_engine import NlpEngineProvider

from .playbooks import ALL, Playbook

DEFAULT_MODEL = "en_core_web_lg"


@dataclass(frozen=True)
class Span:
    start: int
    end: int
    entity: str
    score: float


def _extra_recognizers(language: str) -> list[EntityRecognizer]:
    """Instantiate all pattern-based predefined recognizers (country-specific ones included)."""
    found = []
    for name in dir(predefined):
        cls = getattr(predefined, name)
        if not (inspect.isclass(cls) and issubclass(cls, PatternRecognizer)) or cls is PatternRecognizer:
            continue
        try:
            rec = cls()
        except Exception:  # needs arguments / remote service
            continue
        rec.supported_language = language
        found.append(rec)
    return found


class Redactor:
    def __init__(
        self,
        playbook: Playbook,
        language: str = "en",
        model: str = DEFAULT_MODEL,
        threshold: float | None = None,
        label: bool = True,
        pdf_style: str = "box",
    ):
        nlp = NlpEngineProvider(
            nlp_configuration={
                "nlp_engine_name": "spacy",
                "models": [{"lang_code": language, "model_name": model}],
            }
        ).create_engine()
        registry = RecognizerRegistry(supported_languages=[language])
        registry.load_predefined_recognizers(languages=[language], nlp_engine=nlp)
        loaded = {r.name for r in registry.recognizers}
        for rec in _extra_recognizers(language):
            if rec.name not in loaded:
                registry.add_recognizer(rec)
        self.analyzer = AnalyzerEngine(nlp_engine=nlp, registry=registry, supported_languages=[language])
        self.supported = sorted({e for r in self.analyzer.registry.recognizers for e in r.supported_entities})
        if playbook.name == ALL and not playbook.entities:
            self.entities = self.supported
        else:
            unknown = sorted(set(playbook.entities) - set(self.supported))
            if unknown:
                raise ValueError(
                    f"Entities not supported by Presidio for '{language}': {', '.join(unknown)}"
                )
            self.entities = list(playbook.entities)
        self.language = language
        self.threshold = threshold if threshold is not None else (playbook.score_threshold or 0.35)
        self.label = label
        self.pdf_style = pdf_style
        self.count = 0

    def find(self, text: str) -> list[Span]:
        if not text or not text.strip():
            return []
        results = self.analyzer.analyze(
            text=text,
            language=self.language,
            entities=self.entities,
            score_threshold=self.threshold,
        )
        # Resolve overlaps: prefer higher score, then longer span.
        chosen: list[Span] = []
        for r in sorted(results, key=lambda r: (-r.score, -(r.end - r.start), r.start)):
            if all(r.end <= c.start or r.start >= c.end for c in chosen):
                chosen.append(Span(r.start, r.end, r.entity_type, r.score))
        return sorted(chosen, key=lambda s: s.start)

    def replacement(self, span: Span) -> str:
        return f"<{span.entity}>" if self.label else "<REDACTED>"

    def redact_text(self, text: str) -> str:
        spans = self.find(text)
        self.count += len(spans)
        for s in reversed(spans):
            text = text[: s.start] + self.replacement(s) + text[s.end :]
        return text

    def redact_segments(self, segments: list, get, set_) -> None:
        """Redact PII across a list of text pieces forming one logical paragraph.

        Spans may cross piece boundaries (e.g. formatting runs); the replacement is placed
        in the piece where the span starts and the rest of the span is removed.
        """
        texts = [get(s) or "" for s in segments]
        full = "".join(texts)
        spans = self.find(full)
        if not spans:
            return
        self.count += len(spans)
        bounds, pos = [], 0
        for t in texts:
            bounds.append((pos, pos + len(t)))
            pos += len(t)
        new = [list(t) for t in texts]
        for s in reversed(spans):
            first = True
            for i, (b0, b1) in enumerate(bounds):
                lo, hi = max(s.start, b0), min(s.end, b1)
                if lo >= hi:
                    continue
                piece = new[i]
                piece[lo - b0 : hi - b0] = list(self.replacement(s)) if first else []
                first = False
        for seg, chars, old in zip(segments, new, texts):
            out = "".join(chars)
            if out != old:
                set_(seg, out)
