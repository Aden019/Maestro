"""Turns hand landmarks into gestures, and held gestures into commands."""

from dataclasses import dataclass
from math import acos, dist, pi

WRIST = 0
THUMB_IP, THUMB_TIP = 3, 4
INDEX_MCP = 5
PINKY_MCP = 17
FINGERS = {
    "index": (5, 6, 8),
    "middle": (9, 10, 12),
    "ring": (13, 14, 16),
    "pinky": (17, 18, 20),
}

WAKE_GESTURE = "fist"
SLEEP_GESTURES = ("thumbs_up", "rock")
APP_GESTURES = ("victory", "three", "shaka")


def _angle(a, b, c):
    """The angle at b, in degrees."""
    ab = [p - q for p, q in zip(a, b)]
    cb = [p - q for p, q in zip(c, b)]
    length = dist(a, b) * dist(c, b)
    if length == 0:
        return 0.0
    cosine = sum(p * q for p, q in zip(ab, cb)) / length
    return acos(max(-1.0, min(1.0, cosine))) * 180 / pi


def _finger_is_extended(points, mcp, pip, tip):
    is_straight = _angle(points[mcp], points[pip], points[tip]) > 140
    reaches_out = dist(points[WRIST], points[tip]) > dist(points[WRIST], points[pip]) * 1.1
    return is_straight and reaches_out


def _thumb_is_extended(points):
    palm_width = dist(points[INDEX_MCP], points[PINKY_MCP])
    if palm_width == 0:
        return False
    away_from_palm = dist(points[THUMB_TIP], points[INDEX_MCP]) / palm_width > 0.8
    pointing_out = dist(points[THUMB_TIP], points[PINKY_MCP]) > dist(points[THUMB_IP], points[PINKY_MCP])
    return away_from_palm and pointing_out


def read_fingers(points):
    """Returns which fingers are extended, as [thumb, index, middle, ring, pinky]."""
    return [_thumb_is_extended(points)] + [
        _finger_is_extended(points, *FINGERS[name]) for name in FINGERS
    ]


def classify(fingers):
    """Names the gesture for a set of extended fingers, or None if it isn't one we know."""
    thumb, index, middle, ring, pinky = fingers
    match (index, middle, ring, pinky):
        case (False, False, False, False):
            return "thumbs_up" if thumb else "fist"
        case (True, False, False, False):
            return "point"
        case (True, False, False, True):
            return "rock"
        case (True, True, False, False):
            return "victory"
        case (True, True, True, False):
            return "three"
        case (False, False, False, True):
            return "shaka" if thumb else None
        case (True, True, True, True):
            return "open"
    return None


@dataclass(frozen=True)
class Command:
    kind: str  # "listen", "rest" or "open"
    gesture: str
    app: str | None = None


class Conductor:
    """Decides when a gesture was deliberate, so everyday hand movement does nothing.

    A gesture only counts once it has been steady for a moment and then held. Maestro
    also starts asleep, and apps can only open after a fist has woken it up.
    """

    SETTLE_SECONDS = 0.12
    COOLDOWN_SECONDS = 1.0
    WAKE_HOLD_SECONDS = 1.0

    def __init__(self, bindings, sleep_gesture="thumbs_up", hold_seconds=0.8):
        self.bindings = bindings
        self.sleep_gesture = sleep_gesture
        self.hold_seconds = hold_seconds
        self.listening = False
        self.gesture = None
        self.progress = 0.0
        self._pending = None
        self._pending_since = 0.0
        self._held_since = 0.0
        self._done = False
        self._last_command_at = float("-inf")

    def _settle(self, raw, now):
        """Ignores gestures that flicker for only a frame or two."""
        if raw == self.gesture:
            self._pending = None
            return
        if raw != self._pending:
            self._pending = raw
            self._pending_since = now
            return
        if now - self._pending_since >= self.SETTLE_SECONDS:
            self.gesture = raw
            self._pending = None
            self._held_since = now
            self._done = False

    def _required_hold(self):
        """How long the current gesture must be held, or None if it does nothing right now."""
        if not self.listening:
            return self.WAKE_HOLD_SECONDS if self.gesture == WAKE_GESTURE else None
        if self.gesture == self.sleep_gesture:
            return self.WAKE_HOLD_SECONDS
        return self.hold_seconds if self.bindings.get(self.gesture) else None

    def update(self, raw, now):
        """Takes the gesture seen in this frame, and returns a Command when one fires."""
        self._settle(raw, now)

        required = self._required_hold()
        if required is None or self._done:
            self.progress = 0.0
            return None

        # A gesture started during the cooldown only begins counting once it ends.
        started = max(self._held_since, self._last_command_at + self.COOLDOWN_SECONDS)
        self.progress = min(1.0, max(0.0, (now - started) / required))
        if self.progress < 1.0:
            return None

        self.progress = 0.0
        self._done = True
        self._last_command_at = now
        if not self.listening:
            return self.set_listening(True)
        if self.gesture == self.sleep_gesture:
            return self.set_listening(False)
        return Command("open", self.gesture, self.bindings[self.gesture])

    def set_listening(self, listening):
        self.listening = listening
        return Command("listen" if listening else "sleep", WAKE_GESTURE if listening else self.sleep_gesture)

    def target(self):
        """What the gesture being held will do, for showing on screen."""
        if not self.listening:
            return "Wake" if self.gesture == WAKE_GESTURE else None
        if self.gesture == self.sleep_gesture:
            return "Sleep"
        return self.bindings.get(self.gesture)
