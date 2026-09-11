"""Ground-truth schema for evaluation: {"speakers": [...], "turns": [...]}.

Matches the format the project's own test-data generator
(`meeting-audio-forge`, ld. README) already produces, so its output can be
fed into the evaluation tool with zero conversion.
"""
from __future__ import annotations

import json
from dataclasses import dataclass


@dataclass
class ReferenceTurn:
    speaker: str
    text: str
    start: float
    end: float


@dataclass
class GroundTruth:
    speakers: list[str]
    turns: list[ReferenceTurn]

    @property
    def full_text(self) -> str:
        return " ".join(t.text for t in sorted(self.turns, key=lambda t: t.start))

    @property
    def total_speech_seconds(self) -> float:
        return sum(t.end - t.start for t in self.turns)


def load_ground_truth(path: str) -> GroundTruth:
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    turns = [
        ReferenceTurn(speaker=t["speaker"], text=t["text"], start=float(t["start"]), end=float(t["end"]))
        for t in data["turns"]
    ]
    speakers = data.get("speakers") or sorted({t.speaker for t in turns})
    return GroundTruth(speakers=speakers, turns=turns)
