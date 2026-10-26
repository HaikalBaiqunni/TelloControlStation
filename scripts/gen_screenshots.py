"""
scripts/gen_screenshots.py
Generate marketing screenshots + animated GIF for README.

Renders 6 demo frames:
  1. HUD Standby (no drone)
  2. Connected + Flight HUD overlay (simulated telemetry)
  3. AI Object & Person Detection (with YOLO brackets)
  4. Attitude Sparkline Graphs
  5. Tactical Radar + Waypoint Mission Planner
  6. Person Target Lock

Output: assets/screenshots/  *.png + demo.gif
"""

import sys, os, math, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import urllib.request

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtGui import QColor, QPixmap

import numpy as np
from PIL import Image

ASSETS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "assets", "screenshots"
)
os.makedirs(ASSETS_DIR, exist_ok=True)

SAMPLE_IMAGES = [
    ("https://images.unsplash.com/photo-1477959858617-67f85cf4f1df?w=1280&q=80", "city_aerial.jpg"),
    ("https://images.unsplash.com/photo-1504701954957-2010ec3bcec1?w=1280&q=80", "forest_top.jpg"),
    ("https://images.unsplash.com/photo-1573496359142-b8d87734a5a2?w=1280&q=80", "person.jpg"),
    ("https://images.unsplash.com/photo-1522071820081-009f0129c71c?w=1280&q=80", "office.jpg"),
    ("https://images.unsplash.com/photo-1465056836041-7f43ac27dcb5?w=1280&q=80", "runway.jpg"),
]


def download_samples():
    import cv2
    cache_dir = os.path.join(ASSETS_DIR, "_cache")
    os.makedirs(cache_dir, exist_ok=True)
    frames = {}
    for url, name in SAMPLE_IMAGES:
        path = os.path.join(cache_dir, name)
        if not os.path.exists(path):
            print(f"  Downloading {name} ...")
            try:
                urllib.request.urlretrieve(url, path)
            except Exception as e:
                print(f"  SKIP {name}: {e}")
                continue
        img = cv2.imread(path)
        if img is not None:
            img = cv2.resize(img, (1280, 720))
            frames[name.replace(".jpg", "")] = img
    return frames


def pump(n: int = 20):
    for _ in range(n):
        QCoreApplication.processEvents()
        time.sleep(0.018)


def grab_window(win) -> QPixmap:
    pump(30)
    return win.grab()


def save_png(pix: QPixmap, name: str) -> str:
    path = os.path.join(ASSETS_DIR, name)
    pix.save(path)
    print(f"  Saved: {path}")
    return path


def pix_to_pil(pix: QPixmap) -> Image.Image:
    img = pix.toImage().convertToFormat(
        pix.toImage().Format.Format_RGBA8888
    )
    w, h = img.width(), img.height()
    ptr = img.bits()
    arr = np.frombuffer(ptr, dtype=np.uint8).reshape((h, w, 4))
    return Image.fromarray(arr, "RGBA").convert("RGB")


def inject_telemetry(win, t: float, bat: int = 87):
    """Push a simulated telemetry frame through the same path the real drone uses."""
    from src.drone.state_parser import DroneState

    spd   = 40.0 + 30.0 * math.sin(t * 0.7)
    alt   = 120.0 + 60.0 * math.sin(t * 0.4)
    pitch = 12.0 * math.sin(t * 1.1)
    roll  =  8.0 * math.sin(t * 0.9 + 0.5)
    yaw   = 45.0 * math.sin(t * 0.3)

    x, y = win._pose.x, win._pose.y           # keep the injected demo position
    win._on_state_received(DroneState(
        pitch=pitch, roll=roll, yaw=int(yaw), vgx=0, vgy=int(spd), vgz=0,
        templ=70, temph=74, tof=int(alt * 0.8), h=int(alt),
        bat=max(10, bat - int(t * 0.5)), baro=-44.0,
    ))
    win._pose.x, win._pose.y = x, y
    win._set_mode("AIRBORNE")


def inject_ai_detections(win):
    win._cam.set_detections([
        {"box_norm": [0.08, 0.18, 0.36, 0.82], "is_person": True,  "label": "PERSON",  "conf": 0.92},
        {"box_norm": [0.55, 0.38, 0.78, 0.90], "is_person": True,  "label": "PERSON",  "conf": 0.85},
        {"box_norm": [0.60, 0.10, 0.80, 0.33], "is_person": False, "label": "laptop",  "conf": 0.88},
        {"box_norm": [0.38, 0.22, 0.53, 0.55], "is_person": False, "label": "chair",   "conf": 0.73},
    ])


def inject_waypoints(win):
    """Demo mission, mid-flight: drone is on its way to waypoint 3."""
    from src.drone.mission import Waypoint
    from src.ui.mission_model import MissionModel

    m = win._model
    m.set_state(MissionModel.IDLE)
    m.set_items([
        Waypoint("TAKEOFF", 0, 0, 120), Waypoint("GO", 150, 200, 150, "50"),
        Waypoint("GO", 350, 300, 180, "50"), Waypoint("ROTATE", 350, 300, 180, "90"),
        Waypoint("GO", 300, -50, 150, "40"), Waypoint("GO", 100, -150, 120, "40"),
        Waypoint("LAND", 0, 0, 0),
    ])
    win._pose.reset()
    win._pose.trail[:] = [(150 * k / 20, 200 * k / 20) for k in range(21)] + \
                         [(150 + 100 * k / 12, 200 + 50 * k / 12) for k in range(13)]
    win._pose.x, win._pose.y, win._pose.yaw = 250.0, 250.0, 63.0
    m.set_state(MissionModel.RUNNING)
    m.set_target(2)
    win._ui_tick()


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyle("Fusion")

    print("[1/3] Downloading sample aerial images ...")
    frames = download_samples()
    print(f"  Loaded {len(frames)} frames: {list(frames.keys())}")

    print("\n[2/3] Generating screenshots ...")
    from src.ui.main_window import MainWindow

    win = MainWindow()
    win.resize(1280, 720)
    win.setWindowFlags(win.windowFlags() | Qt.WindowType.FramelessWindowHint)
    win.show()
    pump(50)

    saved_paths = []

    # ── Shot 1: HUD Standby ──────────────────────────────────────────────────
    print("  Shot 1/6: HUD Standby ...")
    win._set_mode("STANDBY")
    pump(25)
    saved_paths.append(save_png(grab_window(win), "01_hud_standby.png"))

    # ── Shot 2: Airborne HUD + Telemetry ──────────────────────────────────────
    print("  Shot 2/6: Airborne HUD + Telemetry ...")
    if "city_aerial" in frames:
        win._cam.set_frame(frames["city_aerial"])
    win._set_pad("🎮 PS4 DUALSHOCK", True)
    for i in range(90):
        inject_telemetry(win, i * 0.14)
    pump(30)
    saved_paths.append(save_png(grab_window(win), "02_hud_airborne.png"))

    # ── Shot 3: AI Object & Person Detection ─────────────────────────────────
    print("  Shot 3/6: AI Object & Person Detection ...")
    if "office" in frames:
        win._cam.set_frame(frames["office"])
        pump(10)
    inject_ai_detections(win)
    inject_telemetry(win, 14.0)
    pump(25)
    saved_paths.append(save_png(grab_window(win), "03_ai_detection.png"))

    # ── Shot 4: Attitude / Sparkline Graphs ──────────────────────────────────
    print("  Shot 4/6: Attitude Sparkline Graphs ...")
    if "forest_top" in frames:
        win._cam.set_frame(frames["forest_top"])
    win._cam.set_detections([])
    for i in range(130):
        inject_telemetry(win, i * 0.12)
    pump(30)
    saved_paths.append(save_png(grab_window(win), "04_attitude_graphs.png"))

    # ── Shot 5: Tactical Radar + Waypoints ───────────────────────────────────
    print("  Shot 5/6: Live mission map + progress ...")
    if "runway" in frames:
        win._cam.set_frame(frames["runway"])
    inject_waypoints(win)
    inject_telemetry(win, 22.0)
    pump(30)
    saved_paths.append(save_png(grab_window(win), "05_radar_waypoints.png"))

    # ── Shot 5b: Flight Plan page ────────────────────────────────────────────
    print("  Shot 5b: Flight Plan page ...")
    win._model.set_state(win._model.IDLE)
    win._goto(win.PLAN)
    pump(20)
    saved_paths.append(save_png(grab_window(win), "07_flight_plan.png"))
    win._goto(win.FLY)
    inject_waypoints(win)
    pump(10)

    # ── Shot 6: Single Person Lock-On ────────────────────────────────────────
    print("  Shot 6/6: Person Lock-On ...")
    if "person" in frames:
        win._cam.set_frame(frames["person"])
    win._cam.set_detections([
        {"box_norm": [0.16, 0.04, 0.82, 0.97], "is_person": True, "label": "PERSON", "conf": 0.93},
    ])
    inject_telemetry(win, 26.0)
    pump(30)
    saved_paths.append(save_png(grab_window(win), "06_person_lock.png"))

    # ── GIF: Animated demo (32 frames) ──────────────────────────────────────
    print("\n[3/3] Building animated GIF (32 frames) ...")
    gif_frames = []

    if "city_aerial" in frames:
        win._cam.set_frame(frames["city_aerial"])
    win._cam.set_detections([])

    for fi in range(32):
        t = fi * 0.38

        # Sequence transitions
        if fi == 0 and "city_aerial" in frames:
            win._cam.set_frame(frames["city_aerial"])
            win._cam.set_detections([])
        elif fi == 9 and "office" in frames:
            win._cam.set_frame(frames["office"])
            inject_ai_detections(win)
        elif fi == 17 and "city_aerial" in frames:
            win._cam.set_frame(frames["city_aerial"])
            win._cam.set_detections([])
        elif fi == 24 and "runway" in frames:
            win._cam.set_frame(frames["runway"])
            inject_waypoints(win)
            win._cam.set_detections([])

        inject_telemetry(win, t + 5)
        pump(6)

        pil_frame = pix_to_pil(grab_window(win))
        pil_frame = pil_frame.resize((960, 540), Image.LANCZOS)
        gif_frames.append(pil_frame)
        print(f"  GIF frame {fi + 1}/32 ✓")

    gif_path = os.path.join(ASSETS_DIR, "demo.gif")
    gif_frames[0].save(
        gif_path,
        save_all=True,
        append_images=gif_frames[1:],
        optimize=True,
        duration=110,
        loop=0,
    )
    size_kb = os.path.getsize(gif_path) // 1024
    print(f"  Saved GIF: {gif_path}  ({size_kb} KB)")

    win.close()

    print("\n✅ Done!")
    for p in saved_paths:
        print(f"   {p}")
    print(f"   {gif_path}")


if __name__ == "__main__":
    main()
