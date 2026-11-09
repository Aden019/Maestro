"""Moves the real mouse on macOS. This needs Accessibility permission."""

import threading
import time
from collections import deque

TICK_SECONDS = 1 / 90
EASING = 0.3


class Mouse:
    """Glides toward a target between camera frames, so the cursor stays smooth at low frame rates."""

    def __init__(self):
        import Quartz

        self._quartz = Quartz
        self._lock = threading.Lock()
        self._target = None
        self._position = None
        self._pressed = False
        threading.Thread(target=self._glide, daemon=True).start()

    def screen_size(self):
        bounds = self._quartz.CGDisplayBounds(self._quartz.CGMainDisplayID())
        return bounds.size.width, bounds.size.height

    def _post_mouse(self, event_type, position, click_count=1):
        q = self._quartz
        event = q.CGEventCreateMouseEvent(None, event_type, position, q.kCGMouseButtonLeft)
        q.CGEventSetIntegerValueField(event, q.kCGMouseEventClickState, click_count)
        q.CGEventPost(q.kCGHIDEventTap, event)

    def _glide(self):
        q = self._quartz
        while True:
            time.sleep(TICK_SECONDS)
            with self._lock:
                # With no target the real mouse is left alone, so it never fights your trackpad.
                if self._target is None:
                    continue
                if self._position is None:
                    location = q.CGEventGetLocation(q.CGEventCreate(None))
                    self._position = (location.x, location.y)
                x = self._position[0] + (self._target[0] - self._position[0]) * EASING
                y = self._position[1] + (self._target[1] - self._position[1]) * EASING
                self._position = (x, y)
                moved = q.kCGEventLeftMouseDragged if self._pressed else q.kCGEventMouseMoved
                self._post_mouse(moved, self._position)

    def move_to(self, x, y):
        with self._lock:
            self._target = (x, y)

    def stop_moving(self):
        with self._lock:
            self._target = None
            self._position = None

    def press(self, click_count=1):
        q = self._quartz
        with self._lock:
            if self._position is None:
                location = q.CGEventGetLocation(q.CGEventCreate(None))
                self._position = (location.x, location.y)
            self._pressed = True
            self._post_mouse(q.kCGEventLeftMouseDown, self._position, click_count)

    def release(self, click_count=1):
        q = self._quartz
        with self._lock:
            if not self._pressed:
                return
            self._pressed = False
            location = self._position or q.CGEventGetLocation(q.CGEventCreate(None))
            self._post_mouse(q.kCGEventLeftMouseUp, location, click_count)

    def scroll(self, pixels):
        q = self._quartz
        event = q.CGEventCreateScrollWheelEvent(None, q.kCGScrollEventUnitPixel, 1, int(pixels))
        q.CGEventPost(q.kCGHIDEventTap, event)


class PretendMouse:
    """Stands in for the real mouse in demo mode and tests."""

    def __init__(self):
        self.calls = deque(maxlen=1000)

    def screen_size(self):
        return 1920.0, 1080.0

    def move_to(self, x, y):
        self.calls.append(("move", x, y))

    def stop_moving(self):
        self.calls.append(("stop",))

    def press(self, click_count=1):
        self.calls.append(("press", click_count))

    def release(self, click_count=1):
        self.calls.append(("release", click_count))

    def scroll(self, pixels):
        self.calls.append(("scroll", pixels))


def has_permission():
    from ApplicationServices import AXIsProcessTrusted

    return bool(AXIsProcessTrusted())


def request_permission():
    """Shows the macOS prompt that leads to the Accessibility setting."""
    from ApplicationServices import AXIsProcessTrustedWithOptions, kAXTrustedCheckOptionPrompt

    return bool(AXIsProcessTrustedWithOptions({kAXTrustedCheckOptionPrompt: True}))
