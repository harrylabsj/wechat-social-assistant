"""Deterministic perception benchmark for synthetic, privacy-safe fixtures."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Iterable

from .connectors import TextCapture, _parse_accessibility_output, merge_text_captures


DEFAULT_FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "perception"


@dataclass(frozen=True)
class BenchmarkCaseResult:
    case_id: str
    observed_texts: tuple[str, ...]
    expected_texts: tuple[str, ...]
    text_precision: float
    text_recall: float
    speaker_precision: float
    speaker_recall: float
    stability: float
    passed: bool


@dataclass(frozen=True)
class PerceptionBenchmarkReport:
    fixture_dir: Path
    cases: tuple[BenchmarkCaseResult, ...]
    text_precision: float
    text_recall: float
    speaker_precision: float
    speaker_recall: float
    stability: float
    passed: bool


def run_perception_benchmark(
    fixture_dir: Path | str = DEFAULT_FIXTURE_DIR,
    *,
    min_text_precision: float = 1.0,
    min_text_recall: float = 1.0,
    min_speaker_precision: float = 1.0,
    min_speaker_recall: float = 1.0,
) -> PerceptionBenchmarkReport:
    root = Path(fixture_dir)
    cases = tuple(
        _evaluate_case(case)
        for manifest in sorted(root.glob("*.json"))
        for case in _load_cases(manifest)
    )
    if not cases:
        raise ValueError(f"no perception benchmark fixtures found in {root}")
    text_precision = _mean(case.text_precision for case in cases)
    text_recall = _mean(case.text_recall for case in cases)
    speaker_precision = _mean(case.speaker_precision for case in cases)
    speaker_recall = _mean(case.speaker_recall for case in cases)
    stability = _mean(case.stability for case in cases)
    passed = all(
        (
            case.passed
            and text_precision >= min_text_precision
            and text_recall >= min_text_recall
            and speaker_precision >= min_speaker_precision
            and speaker_recall >= min_speaker_recall
        )
        for case in cases
    )
    return PerceptionBenchmarkReport(
        fixture_dir=root,
        cases=cases,
        text_precision=text_precision,
        text_recall=text_recall,
        speaker_precision=speaker_precision,
        speaker_recall=speaker_recall,
        stability=stability,
        passed=passed,
    )


def benchmark_report_to_dict(report: PerceptionBenchmarkReport) -> dict[str, Any]:
    return {
        "fixture_dir": str(report.fixture_dir),
        "passed": report.passed,
        "metrics": {
            "text_precision": report.text_precision,
            "text_recall": report.text_recall,
            "speaker_precision": report.speaker_precision,
            "speaker_recall": report.speaker_recall,
            "stability": report.stability,
        },
        "cases": [
            {
                "case_id": case.case_id,
                "observed_texts": list(case.observed_texts),
                "expected_texts": list(case.expected_texts),
                "text_precision": case.text_precision,
                "text_recall": case.text_recall,
                "speaker_precision": case.speaker_precision,
                "speaker_recall": case.speaker_recall,
                "stability": case.stability,
                "passed": case.passed,
            }
            for case in report.cases
        ],
    }


def render_perception_benchmark(report: PerceptionBenchmarkReport) -> str:
    status = "PASS" if report.passed else "FAIL"
    lines = [
        f"# WSA 感知评测：{status}",
        "",
        f"- fixture：`{report.fixture_dir}`",
        f"- 文本 precision / recall：{report.text_precision:.3f} / {report.text_recall:.3f}",
        f"- speaker precision / recall：{report.speaker_precision:.3f} / {report.speaker_recall:.3f}",
        f"- 多帧稳定度：{report.stability:.3f}",
        "",
        "| case | text P | text R | speaker P | speaker R | stability | result |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for case in report.cases:
        lines.append(
            f"| {case.case_id} | {case.text_precision:.3f} | {case.text_recall:.3f} "
            f"| {case.speaker_precision:.3f} | {case.speaker_recall:.3f} "
            f"| {case.stability:.3f} | {'PASS' if case.passed else 'FAIL'} |"
        )
    return "\n".join(lines) + "\n"


def _load_cases(path: Path) -> Iterable[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("cases"), list):
        raise ValueError(f"invalid perception fixture manifest: {path}")
    for case in payload["cases"]:
        if not isinstance(case, dict):
            raise ValueError(f"invalid perception fixture case in {path}")
        yield case


def _evaluate_case(case: dict[str, Any]) -> BenchmarkCaseResult:
    case_id = str(case.get("id") or "unnamed")
    raw_frames = case.get("frames")
    if not isinstance(raw_frames, list) or not raw_frames:
        raise ValueError(f"fixture case {case_id} must contain frames")
    captures: list[TextCapture] = []
    for frame in raw_frames:
        if not isinstance(frame, list):
            raise ValueError(f"fixture case {case_id} contains an invalid frame")
        output = "\n".join(json.dumps(item, ensure_ascii=False) for item in frame)
        captures.append(_parse_accessibility_output(output))
    merged = merge_text_captures(captures, min_stable_frames=len(captures))
    expected = case.get("expected") or {}
    expected_texts = tuple(str(item) for item in expected.get("texts", ()))
    observed_texts = tuple(item.text for item in merged.observations)
    text_precision, text_recall = _multiset_scores(observed_texts, expected_texts)

    expected_speakers = {
        str(text): str(speaker)
        for text, speaker in (expected.get("speaker_by_text") or {}).items()
    }
    observed_speakers = {
        observation.text: observation.speaker_candidate
        for observation in merged.observations
        if observation.speaker_candidate
    }
    speaker_precision, speaker_recall = _speaker_scores(observed_speakers, expected_speakers)
    expected_stable = Counter(str(item) for item in expected.get("stable_texts", expected_texts))
    observed_stable = Counter(observed_texts)
    stable_hits = sum((expected_stable & observed_stable).values())
    stability = stable_hits / sum(expected_stable.values()) if expected_stable else 1.0
    passed = (
        text_precision == 1.0
        and text_recall == 1.0
        and speaker_precision == 1.0
        and speaker_recall == 1.0
        and stability == 1.0
    )
    return BenchmarkCaseResult(
        case_id=case_id,
        observed_texts=observed_texts,
        expected_texts=expected_texts,
        text_precision=text_precision,
        text_recall=text_recall,
        speaker_precision=speaker_precision,
        speaker_recall=speaker_recall,
        stability=stability,
        passed=passed,
    )


def _multiset_scores(observed: Iterable[str], expected: Iterable[str]) -> tuple[float, float]:
    observed_counts = Counter(observed)
    expected_counts = Counter(expected)
    hits = sum((observed_counts & expected_counts).values())
    precision = hits / sum(observed_counts.values()) if observed_counts else (1.0 if not expected_counts else 0.0)
    recall = hits / sum(expected_counts.values()) if expected_counts else 1.0
    return precision, recall


def _speaker_scores(observed: dict[str, str | None], expected: dict[str, str]) -> tuple[float, float]:
    if not observed and not expected:
        return 1.0, 1.0
    hits = sum(1 for text, speaker in observed.items() if expected.get(text) == speaker)
    precision = hits / len(observed) if observed else (1.0 if not expected else 0.0)
    recall = hits / len(expected) if expected else 1.0
    return precision, recall


def _mean(values: Iterable[float]) -> float:
    values = tuple(values)
    return sum(values) / len(values) if values else 0.0
