"""Turns hand movement into cursor movement, clicks, drags, and scrolling."""

from math import dist, exp, pi

from .gestures import INDEX_MCP, PINKY_MCP, THUMB_TIP, WRIST

INDEX_TIP = 8
MIDDLE_MCP = 9

# The part of the camera view that maps onto the whole screen, so your arm needn't travel far.
REGION = {"left": 0.22, "right": 0.78, "top": 0.2, "bottom": 0.68}

PINCH_CLOSE = 0.3
PINCH_OPEN = 0.48


def pinch_ratio(points):
    """How far apart the thumb and index fingertips are, relative to the size of the palm."""
    palm_width = dist(points[INDEX_MCP], points[PINKY_MCP])
    if palm_width == 0:
        return float("inf")
    return dist(points[THUMB_TIP], points[INDEX_TIP]) / palm_width


def _index_reaches_out(points):
    """Tells a pinch apart from a fist, where the fingertips can also touch."""
    return dist(points[WRIST], points[INDEX_TIP]) > dist(points[WRIST], points[INDEX_MCP]) * 1.15


class _OneEuroFilter:
    """Smooths heavily when the hand is still and lightly when it moves, to hide jitter without lag."""

    MIN_CUTOFF = 1.2
    BETA = 0.02

    def __init__(self):
        self._value = None
        self._speed = 0.0
        self._time = None

    @staticmethod
    def _blend(cutoff, elapsed):
        return 1 - exp(-2 * pi * cutoff * elapsed)

    def __call__(self, value, now):
        if self._value is None:
            self._value, self._time = value, now
            return value
        elapsed = max(now - self._time, 1e-3)
        self._speed += self._blend(1.0, elapsed) * ((value - self._value) / elapsed - self._speed)
        cutoff = self.MIN_CUTOFF + self.BETA * abs(self._speed)
        self._value += self._blend(cutoff, elapsed) * (value - self._value)
        self._time = now
        return self._value


class Pointer:
    """Runs the air cursor. It only acts while Maestro is listening and has permission."""

    ENTER_SECONDS = 0.2
    LEAVE_SECONDS = 0.15
    CLICK_READY_SECONDS = 0.25
    PINCH_FREEZE_SECONDS = 0.15
    DOUBLE_CLICK_SECONDS = 0.45
    SCROLL_ENTER_SECONDS = 0.35
    SCROLL_GAIN = 2600
    SCROLL_DEAD_ZONE = 0.002

    def __init__(self, mouse):
        self.mouse = mouse
        self.mode = None
        self.pressed = False
        self._candidate = None
        self._candidate_since = 0.0
        self._leaving_since = None
        self._entered_at = 0.0
        self._freeze_until = 0.0
        self._last_click_at = float("-inf")
        self._click_count = 1
        self._scroll_y = None
        self._filters = (_OneEuroFilter(), _OneEuroFilter())

    def stop(self):
        """Lets go of everything. A drag must never stay stuck down."""
        if self.pressed:
            self.mouse.release(self._click_count)
            self.pressed = False
        if self.mode == "cursor":
            self.mouse.stop_moving()
        self.mode = None
        self._candidate = None
        self._leaving_since = None
        self._scroll_y = None
        self._filters = (_OneEuroFilter(), _OneEuroFilter())

    def update(self, gesture, fingers, world, screen, allowed, now):
        """Takes one camera frame. Returns the gesture Maestro should treat the hand as making."""
        if not allowed or not world or not screen:
            self.stop()
            return gesture

        if self.mode == "cursor":
            return self._update_cursor(gesture, fingers, world, screen, now)
        if self.mode == "scroll":
            self._update_scroll(gesture, screen, now)
            return gesture
        self._maybe_enter(gesture, now, screen)
        return gesture

    def _maybe_enter(self, gesture, now, screen):
        if gesture != self._candidate:
            self._candidate = gesture
            self._candidate_since = now
            return
        held = now - self._candidate_since
        if gesture == "point" and held >= self.ENTER_SECONDS:
            self.mode = "cursor"
            self._entered_at = now
        elif gesture == "open" and held >= self.SCROLL_ENTER_SECONDS:
            self.mode = "scroll"
            self._scroll_y = screen[MIDDLE_MCP][1]

    def _update_cursor(self, gesture, fingers, world, screen, now):
        _, index, middle, ring, pinky = fingers
        threshold = PINCH_OPEN if self.pressed else PINCH_CLOSE
        pinching = pinch_ratio(world) < threshold and _index_reaches_out(world)

        still_cursor = not (middle or ring or pinky) and (index or pinching)
        if still_cursor:
            self._leaving_since = None
        else:
            if self._leaving_since is None:
                self._leaving_since = now
            if now - self._leaving_since >= self.LEAVE_SECONDS:
                self.stop()
                return gesture

        # Follows the knuckle, not the fingertip, so that pinching doesn't drag the cursor away.
        if now >= self._freeze_until:
            self._move(screen[INDEX_MCP], now)

        ready = now - self._entered_at >= self.CLICK_READY_SECONDS
        if pinching and not self.pressed and ready:
            is_double = now - self._last_click_at <= self.DOUBLE_CLICK_SECONDS
            self._click_count = 2 if is_double else 1
            self.mouse.press(self._click_count)
            self.pressed = True
            self._freeze_until = now + self.PINCH_FREEZE_SECONDS
        elif self.pressed and not pinching:
            self.mouse.release(self._click_count)
            self.pressed = False
            self._last_click_at = now
            self._freeze_until = now + self.PINCH_FREEZE_SECONDS

        # A pinch can look like a fist, so it's reported as pointing to avoid putting Maestro to rest.
        return "point" if still_cursor else gesture

    def _move(self, point, now):
        width, height = self.mouse.screen_size()
        x = (point[0] - REGION["left"]) / (REGION["right"] - REGION["left"])
        y = (point[1] - REGION["top"]) / (REGION["bottom"] - REGION["top"])
        x = self._filters[0](min(1.0, max(0.0, x)), now)
        y = self._filters[1](min(1.0, max(0.0, y)), now)
        self.mouse.move_to(x * (width - 1), y * (height - 1))

    def _update_scroll(self, gesture, screen, now):
        if gesture != "open":
            if self._leaving_since is None:
                self._leaving_since = now
            if now - self._leaving_since >= self.LEAVE_SECONDS:
                self.stop()
            return
        self._leaving_since = None
        y = screen[MIDDLE_MCP][1]
        change = y - self._scroll_y
        if abs(change) >= self.SCROLL_DEAD_ZONE:
            self.mouse.scroll(change * self.SCROLL_GAIN)
            self._scroll_y = y
