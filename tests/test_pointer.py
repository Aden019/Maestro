from maestro.gestures import classify, read_fingers
from maestro.mouse import PretendMouse
from maestro.pointer import Pointer
from maestro.poses import PINCH_POSE, POSES

STEP = 1 / 30


def feed(pointer, pose, start, seconds, allowed=True, shift_y=0.0):
    """Feeds a pose frame by frame, returning the end time and the last reported gesture."""
    fingers = read_fingers(pose)
    gesture = classify(fingers)
    screen = [(x, y + shift_y) for x, y, _ in pose]
    now = start
    reported = None
    while now < start + seconds:
        reported = pointer.update(gesture, fingers, pose, screen, allowed, now)
        now += STEP
    return now, reported


def calls(pointer, kind):
    return [call for call in pointer.mouse.calls if call[0] == kind]


def make_pointer():
    return Pointer(PretendMouse())


def test_pointing_moves_the_cursor_inside_the_screen():
    pointer = make_pointer()
    feed(pointer, POSES["point"], 0, 1)
    assert pointer.mode == "cursor"
    moves = calls(pointer, "move")
    assert moves
    assert all(0 <= x <= 1919 and 0 <= y <= 1079 for _, x, y in moves)


def test_a_brief_point_does_not_take_the_cursor():
    pointer = make_pointer()
    feed(pointer, POSES["point"], 0, 0.1)
    assert pointer.mode is None
    assert not pointer.mouse.calls


def test_nothing_happens_without_permission_or_while_at_rest():
    pointer = make_pointer()
    feed(pointer, POSES["point"], 0, 1, allowed=False)
    assert pointer.mode is None
    assert not pointer.mouse.calls


def test_pinching_clicks_once():
    pointer = make_pointer()
    now, _ = feed(pointer, POSES["point"], 0, 0.6)
    now, _ = feed(pointer, PINCH_POSE, now, 0.3)
    assert pointer.pressed
    feed(pointer, POSES["point"], now, 0.3)
    assert not pointer.pressed
    assert calls(pointer, "press") == [("press", 1)]
    assert calls(pointer, "release") == [("release", 1)]


def test_two_quick_pinches_double_click():
    pointer = make_pointer()
    now, _ = feed(pointer, POSES["point"], 0, 0.6)
    for _ in range(2):
        now, _ = feed(pointer, PINCH_POSE, now, 0.1)
        now, _ = feed(pointer, POSES["point"], now, 0.1)
    assert calls(pointer, "press") == [("press", 1), ("press", 2)]


def test_a_pinch_is_never_reported_as_a_fist():
    pointer = make_pointer()
    now, _ = feed(pointer, POSES["point"], 0, 0.6)
    _, reported = feed(pointer, PINCH_POSE, now, 2)
    assert reported == "point"


def test_a_fist_is_not_a_click_and_ends_the_cursor():
    pointer = make_pointer()
    now, _ = feed(pointer, POSES["point"], 0, 0.6)
    _, reported = feed(pointer, POSES["fist"], now, 0.5)
    assert reported == "fist"
    assert pointer.mode is None
    assert calls(pointer, "press") == []


def test_losing_the_hand_lets_go_of_a_drag():
    pointer = make_pointer()
    now, _ = feed(pointer, POSES["point"], 0, 0.6)
    now, _ = feed(pointer, PINCH_POSE, now, 0.3)
    assert pointer.pressed
    pointer.update(None, [False] * 5, None, None, True, now)
    assert not pointer.pressed
    assert calls(pointer, "release")
    assert pointer.mode is None


def test_going_to_rest_lets_go_of_a_drag():
    pointer = make_pointer()
    now, _ = feed(pointer, POSES["point"], 0, 0.6)
    now, _ = feed(pointer, PINCH_POSE, now, 0.3)
    feed(pointer, PINCH_POSE, now, 0.1, allowed=False)
    assert not pointer.pressed
    assert calls(pointer, "release")


def test_moving_an_open_hand_scrolls_with_the_hand():
    pointer = make_pointer()
    now, _ = feed(pointer, POSES["open"], 0, 0.5)
    assert pointer.mode == "scroll"
    feed(pointer, POSES["open"], now, 0.1, shift_y=0.05)
    scrolls = calls(pointer, "scroll")
    assert scrolls
    assert scrolls[0][1] > 0


def test_a_still_open_hand_does_not_scroll():
    pointer = make_pointer()
    feed(pointer, POSES["open"], 0, 2)
    assert calls(pointer, "scroll") == []
