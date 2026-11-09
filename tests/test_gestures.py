import pytest

from maestro.gestures import Conductor, classify, read_fingers
from maestro.poses import POSES

BINDINGS = {"victory": "Safari", "three": "Notes", "shaka": "Music"}


@pytest.mark.parametrize("name", POSES)
def test_each_pose_is_recognized(name):
    assert classify(read_fingers(POSES[name])) == name


def test_unknown_finger_combinations_do_nothing():
    assert classify([False, False, True, False, True]) is None
    assert classify([False, True, False, True, False]) is None


def hold(conductor, gesture, start, seconds, step=1 / 30):
    """Feeds one gesture frame by frame, returning the commands fired and the end time."""
    commands = []
    now = start
    while now < start + seconds:
        command = conductor.update(gesture, now)
        if command:
            commands.append(command)
        now += step
    return commands, now


def awake_conductor():
    conductor = Conductor(dict(BINDINGS))
    conductor.set_listening(True)
    return conductor


def test_starts_at_rest_and_ignores_app_gestures():
    conductor = Conductor(dict(BINDINGS))
    commands, _ = hold(conductor, "victory", 0, 3)
    assert commands == []
    assert conductor.progress == 0


def test_a_fist_wakes_and_the_sleep_gesture_sleeps():
    conductor = Conductor(dict(BINDINGS))
    commands, now = hold(conductor, "fist", 0, 1.5)
    assert [c.kind for c in commands] == ["listen"]
    assert conductor.listening

    _, now = hold(conductor, None, now, 1.5)
    commands, _ = hold(conductor, "thumbs_up", now, 1.5)
    assert [c.kind for c in commands] == ["sleep"]
    assert not conductor.listening


def test_a_fist_does_not_sleep_once_awake():
    conductor = awake_conductor()
    commands, _ = hold(conductor, "fist", 0, 3)
    assert commands == []
    assert conductor.listening


def test_the_sleep_gesture_does_not_wake():
    conductor = Conductor(dict(BINDINGS))
    commands, _ = hold(conductor, "thumbs_up", 0, 3)
    assert commands == []
    assert not conductor.listening


def test_the_sleep_gesture_can_be_changed():
    conductor = Conductor(dict(BINDINGS), sleep_gesture="rock")
    conductor.set_listening(True)
    commands, now = hold(conductor, "thumbs_up", 0, 2)
    assert commands == []
    commands, _ = hold(conductor, "rock", now, 2)
    assert [c.kind for c in commands] == ["sleep"]


def test_a_brief_gesture_does_not_fire():
    commands, _ = hold(awake_conductor(), "victory", 0, 0.5)
    assert commands == []


def test_a_held_gesture_opens_its_app_once():
    commands, _ = hold(awake_conductor(), "three", 0, 5)
    assert [(c.kind, c.app) for c in commands] == [("open", "Notes")]


def test_must_release_before_firing_again():
    conductor = awake_conductor()
    commands, now = hold(conductor, "victory", 0, 3)
    assert len(commands) == 1
    _, now = hold(conductor, None, now, 0.5)
    _, now = hold(conductor, None, now, 1)
    commands, _ = hold(conductor, "victory", now, 2)
    assert len(commands) == 1


def test_one_frame_flicker_does_not_reset_a_hold():
    conductor = awake_conductor()
    _, now = hold(conductor, "victory", 0, 0.5)
    progress = conductor.progress
    conductor.update("three", now)
    conductor.update("victory", now + 1 / 30)
    assert conductor.gesture == "victory"
    assert conductor.progress >= progress


def test_cooldown_delays_the_next_command():
    conductor = awake_conductor()
    commands, now = hold(conductor, "victory", 0, 1.1)
    assert len(commands) == 1
    # Switching straight to another gesture can't fire until the cooldown has passed.
    commands, _ = hold(conductor, "three", now, 1.0)
    assert commands == []


def test_unbound_gesture_does_nothing():
    conductor = awake_conductor()
    commands, _ = hold(conductor, "point", 0, 3)
    assert commands == []
