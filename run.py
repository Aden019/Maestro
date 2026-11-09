"""Starts Maestro. Add --demo to preview it with a pretend hand and no camera."""

import argparse
import threading

from maestro.config import load_settings
from maestro.engine import Engine
from maestro.server import create_server


def main():
    parser = argparse.ArgumentParser(description="Control your Mac with hand gestures.")
    parser.add_argument("--demo", action="store_true", help="play a pretend hand; opens no apps or camera")
    parser.add_argument("--browser", action="store_true", help="serve the interface without opening a window")
    parser.add_argument("--port", type=int, default=0, help="port for the interface (default: any free port)")
    parser.add_argument("--camera", type=int, default=0, help="which camera to use (default: 0)")
    args = parser.parse_args()

    bindings, sleep_gesture = load_settings()
    engine = Engine(bindings, sleep_gesture, camera_index=args.camera, demo=args.demo)
    if not args.demo:
        engine.open_camera()
    engine.start()

    server = create_server(engine, args.port)
    url = f"http://127.0.0.1:{server.server_address[1]}/"

    if args.browser:
        print(f"Maestro is running at {url}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
    else:
        import webview

        threading.Thread(target=server.serve_forever, daemon=True).start()
        webview.create_window(
            "Maestro", url, width=1280, height=840, min_size=(1000, 700), background_color="#14110E"
        )
        webview.start()

    engine.stop()


if __name__ == "__main__":
    main()
