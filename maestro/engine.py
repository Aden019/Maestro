"""Runs the camera, hand tracking, and gestures, and publishes the result for the interface."""

import os
import threading
import time
from collections import deque
from datetime import datetime
from math import sin

import cv2
import numpy as np

from .actions import open_app
from .config import ROOT, save_settings
from .gestures import Conductor, classify, read_fingers
from .mouse import Mouse, PretendMouse, has_permission, request_permission
from .pointer import REGION, Pointer
from .poses import PINCH_POSE, POSES

MODEL_PATH = ROOT / "models" / "hand_landmarker.task"
FRAME_WIDTH = 960
JPEG_QUALITY = 72

DEMO_SCRIPT = (
    ("open", 1.6),
    ("fist", 1.7),
    ("open", 1.2),
    ("victory", 1.6),
    ("open", 1.2),
    ("three", 1.6),
    ("open", 1.2),
    ("shaka", 1.6),
    ("open", 1.2),
    ("point", 2.0),
    ("pinch", 0.8),
    ("point", 1.4),
    ("open", 1.2),
    ("sleep", 1.7),
)


class Engine:
    def __init__(self, bindings, sleep_gesture, camera_index=0, demo=False, open_app=open_app):
        self.conductor = Conductor(bindings, sleep_gesture)
        self.pointer = Pointer(PretendMouse() if demo else Mouse())
        self.has_cursor_permission = demo
        self._permission_checked_at = float("-inf")
        self.camera_index = camera_index
        self.demo = demo
        self.open_app = open_app
        self.camera_status = "ok" if demo else "starting"
        self.fps = 0.0
        self.aspect = 16 / 9
        self.hand = None
        self.fingers = [False] * 5
        self.fired = None
        self.log = deque(maxlen=30)
        self.seq = 0
        self.frame = None
        self._log_id = 0
        self._capture = None
        self._landmarker = None
        self._last_timestamp = 0
        self._retry = False
        self._failed_reads = 0
        self._lock = threading.Lock()
        self._changed = threading.Condition(self._lock)
        self._stop = threading.Event()

    # Camera

    def open_camera(self):
        """Opens the camera. The first call must be on the main thread, as macOS may ask permission."""
        capture = cv2.VideoCapture(self.camera_index, cv2.CAP_AVFOUNDATION)
        if not capture.isOpened():
            capture.release()
            self.camera_status = "denied"
            return
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        self._capture = capture
        self._failed_reads = 0
        self.camera_status = "ok"

    def retry_camera(self):
        self._retry = True

    def _load_landmarker(self):
        os.environ.setdefault("GLOG_minloglevel", "2")
        from mediapipe.tasks.python import BaseOptions, vision

        options = vision.HandLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(MODEL_PATH)),
            running_mode=vision.RunningMode.VIDEO,
            num_hands=1,
            min_hand_detection_confidence=0.6,
            min_hand_presence_confidence=0.6,
            min_tracking_confidence=0.6,
        )
        self._landmarker = vision.HandLandmarker.create_from_options(options)

    def _read_camera(self):
        """Reads one mirrored frame and finds the hand. Returns (frame, screen points, 3D points)."""
        ok, frame = self._capture.read()
        if not ok or frame is None:
            self._failed_reads += 1
            if self._failed_reads > 30:
                self._capture.release()
                self._capture = None
                self.camera_status = "missing"
            time.sleep(0.03)
            return None, None, None
        self._failed_reads = 0

        height, width = frame.shape[:2]
        frame = cv2.resize(frame, (FRAME_WIDTH, round(height * FRAME_WIDTH / width)))
        frame = cv2.flip(frame, 1)

        import mediapipe as mp

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        self._last_timestamp = max(self._last_timestamp + 1, int(time.monotonic() * 1000))
        result = self._landmarker.detect_for_video(image, self._last_timestamp)
        if not result.hand_landmarks:
            return frame, None, None

        screen = [(p.x, p.y) for p in result.hand_landmarks[0]]
        world = [(p.x, p.y, p.z) for p in result.hand_world_landmarks[0]]
        return frame, screen, world

    # Demo mode

    def _read_demo(self, elapsed):
        """Plays a scripted hand, for previewing the interface. It never opens real apps."""
        cycle = sum(seconds for _, seconds in DEMO_SCRIPT)
        moment = elapsed % cycle
        for name, seconds in DEMO_SCRIPT:
            if moment < seconds:
                break
            moment -= seconds
        if name == "sleep":
            name = self.conductor.sleep_gesture
        pose = PINCH_POSE if name == "pinch" else POSES[name]

        drift = (sin(elapsed * 0.9) * 0.012, sin(elapsed * 1.3) * 0.009)
        points = [(x + drift[0], y + drift[1], z) for x, y, z in pose]
        # Spread the square pose evenly across the widescreen frame.
        screen = [(0.5 + (x - 0.5) * 9 / 16, y) for x, y, _ in points]

        frame = np.full((540, FRAME_WIDTH, 3), (22, 26, 30), dtype=np.uint8)
        noise = np.random.randint(0, 7, frame.shape, dtype=np.uint8)
        return cv2.add(frame, noise), screen, points

    # The main loop

    def _add_log(self, kind, text):
        self._log_id += 1
        self.log.appendleft(
            {"id": self._log_id, "time": datetime.now().strftime("%H:%M:%S"), "kind": kind, "text": text}
        )

    def _open_in_background(self, app):
        error = self.open_app(app)
        with self._changed:
            if error:
                self._add_log("error", f"Couldn't open {app}: {error}")
            else:
                self._add_log("open", f"Opened {app}")

    def _run_command(self, command):
        if command.kind == "listen":
            self._add_log("state", "Listening for gestures")
        elif command.kind == "sleep":
            self._add_log("state", "Asleep")
        elif self.demo:
            self._add_log("open", f"Demo: would open {command.app}")
        else:
            threading.Thread(target=self._open_in_background, args=(command.app,), daemon=True).start()

    def _publish(self, frame, screen, world):
        fingers = read_fingers(world) if world else [False] * 5
        gesture = classify(fingers) if world else None

        encoded = None
        if frame is not None:
            ok, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
            encoded = jpeg.tobytes() if ok else None

        now = time.monotonic()
        with self._changed:
            if not self.demo and now - self._permission_checked_at >= 2:
                self._permission_checked_at = now
                self.has_cursor_permission = has_permission()

            allowed = self.conductor.listening and self.has_cursor_permission
            gesture = self.pointer.update(gesture, fingers, world, screen, allowed, now)
            command = self.conductor.update(gesture, now)
            if command:
                self.fired = {"id": self.seq, "kind": command.kind, "app": command.app}
                self._run_command(command)
            self.hand = screen
            self.fingers = fingers
            if frame is not None:
                self.aspect = frame.shape[1] / frame.shape[0]
            if encoded:
                self.frame = encoded
            self.seq += 1
            self._changed.notify_all()

    def run(self):
        try:
            if not self.demo:
                self._load_landmarker()
        except Exception as error:
            print(f"Couldn't load hand tracking: {error}")
            self.camera_status = "error"

        started = time.monotonic()
        last_frame_at = started
        while not self._stop.is_set():
            if self._retry:
                self._retry = False
                os.environ["OPENCV_AVFOUNDATION_SKIP_AUTH"] = "1"
                self.open_camera()

            if self.demo:
                self._publish(*self._read_demo(time.monotonic() - started))
                time.sleep(1 / 30)
            elif self._capture is not None and self._landmarker is not None:
                self._publish(*self._read_camera())
            else:
                self._publish(None, None, None)
                time.sleep(0.2)

            now = time.monotonic()
            self.fps = self.fps * 0.9 + (0.1 / max(now - last_frame_at, 0.001))
            last_frame_at = now

        if self._capture is not None:
            self._capture.release()

    def start(self):
        threading.Thread(target=self.run, daemon=True).start()

    def stop(self):
        self._stop.set()
        with self._changed:
            self.pointer.stop()
            self._changed.notify_all()

    # Used by the interface

    def snapshot(self):
        with self._lock:
            return {
                "seq": self.seq,
                "demo": self.demo,
                "camera": self.camera_status,
                "fps": round(self.fps),
                "aspect": self.aspect,
                "hand": self.hand,
                "fingers": self.fingers,
                "gesture": self.conductor.gesture,
                "progress": self.conductor.progress,
                "target": self.conductor.target(),
                "listening": self.conductor.listening,
                "sleepGesture": self.conductor.sleep_gesture,
                "pointer": {
                    "mode": self.pointer.mode,
                    "pressed": self.pointer.pressed,
                    "permission": self.has_cursor_permission,
                    "region": REGION,
                },
                "fired": self.fired,
                "log": list(self.log),
                "bindings": self.conductor.bindings,
            }

    def wait_for_update(self, last_seq, timeout=1.0):
        with self._changed:
            self._changed.wait_for(lambda: self.seq != last_seq or self._stop.is_set(), timeout)
            return self.seq

    def latest_frame(self):
        with self._lock:
            return self.frame

    def set_listening(self, listening):
        with self._changed:
            if listening != self.conductor.listening:
                self._run_command(self.conductor.set_listening(listening))

    def request_cursor_permission(self):
        if not self.demo:
            request_permission()

    def set_binding(self, gesture, app):
        with self._changed:
            self.conductor.bindings[gesture] = app
            self._add_log("state", f"{app} assigned")
        self._save_settings()

    def set_sleep_gesture(self, gesture):
        with self._changed:
            self.conductor.sleep_gesture = gesture
            self._add_log("state", "Sleep gesture changed")
        self._save_settings()

    def _save_settings(self):
        with self._lock:
            bindings = dict(self.conductor.bindings)
            sleep_gesture = self.conductor.sleep_gesture
        if not self.demo:
            save_settings(bindings, sleep_gesture)
