import pytest

from analytics import rhr_anomaly, risk_scores, workout_segments


@pytest.mark.parametrize(
    ("z_score", "expected"),
    [
        (-1.5, "LOW"),
        (1.49, "NORMAL"),
        (1.5, "ELEVATED"),
        (2.49, "ELEVATED"),
        (2.5, "HIGH"),
    ],
)
def test_rhr_classification_boundaries(z_score, expected):
    assert rhr_anomaly._classify(z_score) == expected


def test_standard_deviation_is_zero_for_constant_baseline():
    assert rhr_anomaly._sd([52.0, 52.0, 52.0], 52.0) == 0.0


def test_deviation_signal_is_unknown_without_inputs():
    assert risk_scores._illness(None, None, None, None, None) == (
        None,
        "UNKNOWN",
        None,
        0,
    )


def test_deviation_signal_reports_contributing_wearable_metrics():
    score, level, drivers, present = risk_scores._illness(2.5, 1, "SUPPRESSED", 2.0, 2.0)

    assert score == pytest.approx(52.0)
    assert level == "ELEVATED"
    assert set(drivers.split(",")) == {"RHR", "HRV", "Resp", "SpO2"}
    assert present == 4


@pytest.mark.parametrize(
    ("lap", "sport", "expected"),
    [
        ({"intensityType": "WARMUP", "distance": 400}, "swim", "rest"),
        ({"distance": 100, "duration": 70}, "swim", "work"),
        ({"intensityType": "RECOVERY", "distance": 100}, "run", "rest"),
        ({"intensityType": "INTERVAL", "distance": 400}, "run", "work"),
    ],
)
def test_workout_lap_classification(lap, sport, expected):
    assert workout_segments._classify(lap, sport) == expected
