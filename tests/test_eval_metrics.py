from dataclasses import dataclass

from eval.ground_truth import ReferenceTurn
from eval.metrics import char_error_rate, speaker_attribution_accuracy, word_error_rate


def test_wer_identical_is_zero():
    assert word_error_rate("Szia, ez egy teszt.", "szia ez egy teszt") == 0.0


def test_wer_counts_substitutions():
    # 1 substitution out of 4 reference words
    assert word_error_rate("egy kettő három négy", "egy kettő öt négy") == 0.25


def test_cer_identical_is_zero():
    assert char_error_rate("árvíztűrő tükörfúrógép", "árvíztűrő tükörfúrógép") == 0.0


def test_cer_nonzero_on_typo():
    assert char_error_rate("alma", "alna") > 0.0


@dataclass
class _FakeSpeakerLabel:
    id: str
    is_enrolled: bool = False
    display_name: str = None


@dataclass
class _FakeSegment:
    start: float
    end: float
    speaker: _FakeSpeakerLabel


def test_speaker_attribution_perfect_match_via_enrollment():
    reference = [
        ReferenceTurn(speaker="Alice", text="hi", start=0.0, end=5.0),
        ReferenceTurn(speaker="Bob", text="hello", start=5.0, end=10.0),
    ]
    predicted = [
        _FakeSegment(0.0, 5.0, _FakeSpeakerLabel(id="SPEAKER_00", is_enrolled=True, display_name="Alice")),
        _FakeSegment(5.0, 10.0, _FakeSpeakerLabel(id="SPEAKER_01", is_enrolled=True, display_name="Bob")),
    ]
    result = speaker_attribution_accuracy(reference, predicted)
    assert result.accuracy == 1.0
    assert result.mapping == {"Alice": "Alice", "Bob": "Bob"}


def test_speaker_attribution_anonymous_gets_permutation_mapped():
    reference = [
        ReferenceTurn(speaker="Alice", text="hi", start=0.0, end=5.0),
        ReferenceTurn(speaker="Bob", text="hello", start=5.0, end=10.0),
    ]
    # diarizer found the right split but doesn't know real names
    predicted = [
        _FakeSegment(0.0, 5.0, _FakeSpeakerLabel(id="SPEAKER_00")),
        _FakeSegment(5.0, 10.0, _FakeSpeakerLabel(id="SPEAKER_01")),
    ]
    result = speaker_attribution_accuracy(reference, predicted)
    assert result.accuracy == 1.0
    assert set(result.mapping.values()) == {"SPEAKER_00", "SPEAKER_01"}


def test_speaker_attribution_single_speaker_baseline_is_poor():
    reference = [
        ReferenceTurn(speaker="Alice", text="hi", start=0.0, end=5.0),
        ReferenceTurn(speaker="Bob", text="hello", start=5.0, end=10.0),
    ]
    # a "raw endpoint, no diarization" baseline: everything is one speaker
    predicted = [
        _FakeSegment(0.0, 10.0, _FakeSpeakerLabel(id="SPEAKER_00")),
    ]
    result = speaker_attribution_accuracy(reference, predicted)
    # only one of the two reference speakers can be mapped to the single predicted label
    assert 0.0 < result.accuracy < 1.0
