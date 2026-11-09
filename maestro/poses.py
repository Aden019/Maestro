"""Drawn hand poses, used for the gesture diagrams, demo mode, and tests."""

from math import cos, radians, sin

WRIST_POINT = (0.5, 0.86)
# Knuckle position, and the direction each finger points in degrees from straight up.
FINGER_LAYOUT = (
    ((0.42, 0.56), -13, (0.105, 0.075, 0.065)),  # index
    ((0.50, 0.53), -2, (0.115, 0.085, 0.07)),  # middle
    ((0.58, 0.56), 9, (0.105, 0.08, 0.065)),  # ring
    ((0.65, 0.62), 21, (0.085, 0.06, 0.055)),  # pinky
)


def _step(point, angle, length):
    return (point[0] + sin(radians(angle)) * length, point[1] - cos(radians(angle)) * length)


def _thumb(extended):
    if extended:
        return [(0.40, 0.78), (0.31, 0.70), (0.235, 0.63), (0.17, 0.57)]
    return [(0.41, 0.78), (0.37, 0.70), (0.42, 0.65), (0.48, 0.64)]


def _finger(knuckle, angle, lengths, extended):
    points = [knuckle]
    if extended:
        for length in lengths:
            points.append(_step(points[-1], angle, length))
    else:
        points.append(_step(knuckle, angle, lengths[0] * 0.8))
        points.append(_step(points[-1], angle + 150, lengths[1]))
        points.append(_step(points[-1], angle + 180, lengths[2]))
    return points


def make_pose(thumb, index, middle, ring, pinky):
    """Builds the 21 standard hand landmarks as (x, y, z) from which fingers are extended."""
    points = [WRIST_POINT] + _thumb(thumb)
    for (knuckle, angle, lengths), extended in zip(FINGER_LAYOUT, (index, middle, ring, pinky)):
        points += _finger(knuckle, angle, lengths, extended)
    return [(x, y, 0.0) for x, y in points]


POSES = {
    "open": make_pose(True, True, True, True, True),
    "fist": make_pose(False, False, False, False, False),
    "point": make_pose(False, True, False, False, False),
    "victory": make_pose(False, True, True, False, False),
    "three": make_pose(False, True, True, True, False),
    "shaka": make_pose(True, False, False, False, True),
    "thumbs_up": make_pose(True, False, False, False, False),
    "rock": make_pose(False, True, False, False, True),
}


def _make_pinch_pose():
    """A pointing hand with the thumb and index fingertips touching."""
    points = list(POSES["point"])
    points[6:9] = [(0.39, 0.46, 0.0), (0.355, 0.39, 0.0), (0.33, 0.45, 0.0)]
    points[1:5] = [(0.40, 0.78, 0.0), (0.33, 0.68, 0.0), (0.31, 0.56, 0.0), (0.325, 0.465, 0.0)]
    return points


PINCH_POSE = _make_pinch_pose()
