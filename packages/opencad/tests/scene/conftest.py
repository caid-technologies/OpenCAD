"""Scene snapshot assertions shared by the Python/browser parity tests."""

import pytest

from opencad.scene import SceneState


@pytest.fixture
def assert_scene_state_matches():
    def compare(actual, expected, path):
        if isinstance(expected, dict):
            assert actual.keys() == expected.keys(), path
            for key in expected:
                compare(actual[key], expected[key], f"{path}.{key}")
        elif isinstance(expected, list):
            assert len(actual) == len(expected), path
            for index, (value, reference) in enumerate(zip(actual, expected)):
                compare(value, reference, f"{path}[{index}]")
        elif isinstance(expected, float):
            # Match the browser tests' nine-decimal absolute precision. Platform
            # math libraries can differ by an ULP in interpolated quaternions.
            # Disable relative tolerance so large coordinates get no extra slack.
            assert actual == pytest.approx(expected, rel=0, abs=5e-10), path
        else:
            assert actual == expected, path

    def assert_matches(actual: SceneState, expected: SceneState):
        assert actual.time_s == expected.time_s
        compare(
            actual.model_dump(mode="json"),
            expected.model_dump(mode="json"),
            f"state at {expected.time_s}s",
        )

    return assert_matches
