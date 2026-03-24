import pytest

from kmer_judge import classify_peaks


@pytest.mark.parametrize(
    "depths, tolerance, expected_pattern, expected_is_normal",
    [
        ([23, 45, 90, 135, 179], 0.2, 'high_repetitive_diplo', True),
        ([20, 40], 0.2, 'diploid_hetero', True),
        ([20, 40, 60], 0.2, 'triploid', True),
        ([20, 40, 80], 0.2, 'high_repetitive_diplo', True),
        ([20, 40, 60, 80], 0.2, 'tetraploid', True),
        ([20, 40, 62], 0.2, 'triploid', True),
    ],
)
def test_classify_peaks_known_patterns(depths, tolerance, expected_pattern, expected_is_normal):
    pattern, is_normal, detail = classify_peaks(depths, tolerance)
    assert pattern == expected_pattern
    assert is_normal == expected_is_normal
    assert isinstance(detail, str)


def test_classify_peaks_unknown_when_12_mismatch():
    pattern, is_normal, detail = classify_peaks([20, 37], 0.05)
    assert pattern == 'unknown'
    assert is_normal is False
    assert '1:2' not in detail or '不符合1:2' in detail
