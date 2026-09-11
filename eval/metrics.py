"""Self-contained scoring: WER/CER (transcript accuracy) and a
diarization-agnostic speaker-attribution-accuracy metric. No extra
dependency (jiwer, pyannote.metrics, ...) — plain edit-distance DP plus a
small assignment search, kept dependency-free so this tool runs anywhere
the rest of the repo's unit tests do.
"""
from __future__ import annotations

import itertools
import math
import re
from dataclasses import dataclass, field
from typing import Optional, Sequence

_PUNCT_RE = re.compile(r"[^\w\s]", flags=re.UNICODE)
_WS_RE = re.compile(r"\s+")


def normalize_text(text: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace. Deliberately does
    NOT touch Unicode composition — Hungarian letters (á/é/ő/ű/...) are
    literal word characters under \\w with re.UNICODE, so they survive
    untouched; only ASCII/Unicode punctuation is stripped."""
    text = text.lower()
    text = _PUNCT_RE.sub(" ", text)
    return _WS_RE.sub(" ", text).strip()


def _edit_distance(ref: Sequence, hyp: Sequence) -> int:
    """Classic Levenshtein DP over arbitrary token sequences (words or chars)."""
    n, m = len(ref), len(hyp)
    if n == 0:
        return m
    if m == 0:
        return n
    prev = list(range(m + 1))
    for i in range(1, n + 1):
        curr = [i] + [0] * m
        for j in range(1, m + 1):
            cost = 0 if ref[i - 1] == hyp[j - 1] else 1
            curr[j] = min(
                prev[j] + 1,  # deletion
                curr[j - 1] + 1,  # insertion
                prev[j - 1] + cost,  # substitution
            )
        prev = curr
    return prev[m]


def word_error_rate(reference: str, hypothesis: str) -> float:
    ref_words = normalize_text(reference).split()
    hyp_words = normalize_text(hypothesis).split()
    if not ref_words:
        return 0.0 if not hyp_words else float("inf")
    return _edit_distance(ref_words, hyp_words) / len(ref_words)


def char_error_rate(reference: str, hypothesis: str) -> float:
    ref_chars = normalize_text(reference).replace(" ", "")
    hyp_chars = normalize_text(hypothesis).replace(" ", "")
    if not ref_chars:
        return 0.0 if not hyp_chars else float("inf")
    return _edit_distance(ref_chars, hyp_chars) / len(ref_chars)


@dataclass
class SpeakerAttributionResult:
    accuracy: float  # fraction of reference speech duration correctly attributed
    mapping: dict[str, Optional[str]]  # reference speaker -> predicted label (or None)
    total_reference_seconds: float
    correctly_attributed_seconds: float
    per_speaker: dict[str, float] = field(default_factory=dict)  # ref speaker -> its own accuracy


def _overlap(a_start: float, a_end: float, b_start: float, b_end: float) -> float:
    return max(0.0, min(a_end, b_end) - max(a_start, b_start))


def _predicted_label(segment) -> str:
    """A predicted segment's scoring label: the enrolled display name if
    matched, else the raw (anonymous) diarizer speaker id."""
    speaker = segment.speaker
    if getattr(speaker, "is_enrolled", False) and getattr(speaker, "display_name", None):
        return speaker.display_name
    return speaker.id


def speaker_attribution_accuracy(
    reference_turns: Sequence,
    predicted_segments: Sequence,
    *,
    max_permutations: int = 40320,  # 8! — beyond this, fall back to greedy
) -> SpeakerAttributionResult:
    ref_speakers = sorted({t.speaker for t in reference_turns})
    pred_labels = sorted({_predicted_label(s) for s in predicted_segments})

    # overlap[(ref, pred)] = total seconds where ref-speaker and pred-label speak simultaneously
    overlap: dict[tuple[str, str], float] = {}
    for turn in reference_turns:
        for seg in predicted_segments:
            sec = _overlap(turn.start, turn.end, seg.start, seg.end)
            if sec <= 0:
                continue
            key = (turn.speaker, _predicted_label(seg))
            overlap[key] = overlap.get(key, 0.0) + sec

    mapping: dict[str, Optional[str]] = {}
    if ref_speakers and pred_labels:
        n_perms = math.perm(max(len(ref_speakers), len(pred_labels)), min(len(ref_speakers), len(pred_labels)))
        if n_perms <= max_permutations:
            best_total = -1.0
            best_assignment: tuple[Optional[str], ...] = tuple(None for _ in ref_speakers)
            padded_labels = list(pred_labels) + [None] * max(0, len(ref_speakers) - len(pred_labels))
            for perm in itertools.permutations(padded_labels, len(ref_speakers)):
                total = sum(overlap.get((ref, lbl), 0.0) for ref, lbl in zip(ref_speakers, perm) if lbl is not None)
                if total > best_total:
                    best_total = total
                    best_assignment = perm
            mapping = dict(zip(ref_speakers, best_assignment))
        else:
            # greedy fallback for pathological speaker counts (e.g. bad over-segmentation)
            remaining_pred = set(pred_labels)
            pairs = sorted(overlap.items(), key=lambda kv: -kv[1])
            assigned_ref: set[str] = set()
            for (ref, lbl), _sec in pairs:
                if ref in assigned_ref or lbl not in remaining_pred:
                    continue
                mapping[ref] = lbl
                assigned_ref.add(ref)
                remaining_pred.discard(lbl)
            for ref in ref_speakers:
                mapping.setdefault(ref, None)
    else:
        mapping = {ref: None for ref in ref_speakers}

    total_ref_seconds = 0.0
    correct_seconds = 0.0
    per_speaker: dict[str, float] = {}
    for ref in ref_speakers:
        ref_duration = sum(t.end - t.start for t in reference_turns if t.speaker == ref)
        total_ref_seconds += ref_duration
        matched_label = mapping.get(ref)
        correct = overlap.get((ref, matched_label), 0.0) if matched_label else 0.0
        correct_seconds += correct
        per_speaker[ref] = (correct / ref_duration) if ref_duration > 0 else 0.0

    accuracy = (correct_seconds / total_ref_seconds) if total_ref_seconds > 0 else 0.0
    return SpeakerAttributionResult(
        accuracy=accuracy,
        mapping=mapping,
        total_reference_seconds=total_ref_seconds,
        correctly_attributed_seconds=correct_seconds,
        per_speaker=per_speaker,
    )
