"""
scripts/gen_screenshots.py
Generate marketing screenshots + animated GIF for README.

Renders 7 demo frames:
  1. HUD Standby (no drone)
  2. Connected + Flight HUD overlay (simulated telemetry)
  3. AI Object & Person Detection (with YOLO brackets)
  4. Flight Data trace
  5. Live mission map + progress strip
  6. Person Target Lock
  7. Flight Plan page (waypoint planner)

By default the video frames are generated locally (no network). Pass --download to use
real sample photos from Unsplash instead.

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


def make_frames():
    """Procedurally generated stand-in FPV scenes (1280x720 BGR), so no download is needed."""
    import cv2
    rng = np.random.default_rng(7)
    W, H = 1280, 720

    def noise(img, amt=6):
        n = rng.normal(0, amt, img.shape).astype(np.int16)
        return np.clip(img.astype(np.int16) + n, 0, 255).astype(np.uint8)

    def vgrad(top, bottom):
        t = np.linspace(0, 1, H)[:, None, None]
        row = (np.array(top) * (1 - t) + np.array(bottom) * t).astype(np.uint8)
        return np.repeat(row, W, axis=1)

    frames = {}

    # city: dusk sky + skyline with lit windows
    img = vgrad((120, 80, 50), (60, 70, 90))
    horizon = int(H * 0.62)
    for _ in range(60):
        bw, bh = int(rng.integers(50, 150)), int(rng.integers(120, 380))
        bx = int(rng.integers(-20, W))
        shade = int(rng.integers(25, 60))
        cv2.rectangle(img, (bx, horizon - bh), (bx + bw, horizon + 40), (shade, shade + 6, shade + 14), -1)
        for wy in range(horizon - bh + 10, horizon, 18):
            for wx in range(bx + 8, bx + bw - 8, 16):
                if rng.random() < 0.35:
                    cv2.rectangle(img, (wx, wy), (wx + 6, wy + 8), (90, 190, 240), -1)
    cv2.rectangle(img, (0, horizon + 30), (W, H), (35, 38, 42), -1)
    for x in range(-W, 2 * W, 140):
        cv2.line(img, (W // 2, horizon + 30), (x, H), (70, 74, 80), 2)
    frames["city_aerial"] = noise(cv2.GaussianBlur(img, (3, 3), 0))

    # forest from above
    img = np.full((H, W, 3), (40, 90, 50), np.uint8)
    for _ in range(900):
        c = (int(rng.integers(20, 70)), int(rng.integers(70, 150)), int(rng.integers(30, 80)))
        cv2.circle(img, (int(rng.integers(0, W)), int(rng.integers(0, H))), int(rng.integers(14, 44)), c, -1)
    frames["forest_top"] = noise(cv2.GaussianBlur(img, (9, 9), 0))

    # office: wall, desk, laptop, chair
    img = vgrad((190, 185, 175), (150, 140, 130))
    cv2.rectangle(img, (0, 470), (W, H), (70, 95, 130), -1)
    cv2.rectangle(img, (160, 380), (700, 420), (60, 80, 110), -1)
    cv2.rectangle(img, (260, 280), (560, 380), (50, 50, 55), -1)
    cv2.rectangle(img, (275, 292), (545, 372), (200, 170, 120), -1)
    cv2.rectangle(img, (830, 300), (980, 420), (45, 45, 50), -1)
    cv2.rectangle(img, (810, 420), (1000, 450), (45, 45, 50), -1)
    cv2.line(img, (905, 450), (905, 560), (40, 40, 40), 8)
    frames["office"] = noise(cv2.GaussianBlur(img, (5, 5), 0))

    # person: studio wall + large silhouette
    img = vgrad((150, 120, 90), (110, 90, 70))
    cv2.ellipse(img, (640, 220), (80, 100), 0, 0, 360, (140, 170, 210), -1)
    cv2.rectangle(img, (500, 310), (780, 720), (70, 60, 120), -1)
    cv2.circle(img, (500, 380), 45, (70, 60, 120), -1)
    cv2.circle(img, (780, 380), 45, (70, 60, 120), -1)
    frames["person"] = noise(cv2.GaussianBlur(img, (7, 7), 0))

    # runway: asphalt in perspective under a bright sky
    img = vgrad((235, 200, 150), (200, 215, 225))
    hz = int(H * 0.45)
    cv2.rectangle(img, (0, hz), (W, H), (60, 120, 70), -1)
    cv2.fillPoly(img, [np.array([(W // 2 - 30, hz), (W // 2 + 30, hz), (W - 80, H), (80, H)])], (70, 70, 74))
    for k in range(10):
        t0, t1 = k / 10, (k + 0.5) / 10
        y0, y1 = int(hz + (H - hz) * t0 ** 1.6), int(hz + (H - hz) * t1 ** 1.6)
        w0, w1 = 2 + 18 * t0 ** 1.6, 2 + 18 * t1 ** 1.6
        cv2.fillPoly(img, [np.array([(W // 2 - w0, y0), (W // 2 + w0, y0), (W // 2 + w1, y1), (W // 2 - w1, y1)], np.int32)],
                     (230, 230, 235))
    frames["runway"] = noise(cv2.GaussianBlur(img, (3, 3), 0))
    return frames


def mission_progress(win, u: float):
    """Place the drone `u` (0..1) along the planned path and advance the active waypoint."""
    from src.drone.mission import cumulative, bearing_deg

    items = win._model.items
    cum, total = cumulative(items)
    s = u * total
    for i in range(1, len(items)):
        if s <= cum[i] or i == len(items) - 1:
            seg = cum[i] - cum[i - 1]
            f = (s - cum[i - 1]) / seg if seg > 0 else 1.0
            a, b = items[i - 1], items[i]
            win._pose.x = a.x + (b.x - a.x) * f
            win._pose.y = a.y + (b.y - a.y) * f
            win._pose.yaw = bearing_deg(a, b) if seg > 1 else win._pose.yaw
            win._pose.trail.append((win._pose.x, win._pose.y))
            win._model.set_target(i)
            break
    win._ui_tick()


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

    if "--download" in sys.argv:
        print("[1/3] Downloading sample photos ...")
        frames = download_samples()
    else:
        print("[1/3] Generating local sample frames ...")
        frames = make_frames()
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
    print("  Shot 4/6: Flight Data trace ...")
    if "forest_top" in frames:
        win._cam.set_frame(frames["forest_top"])
    win._cam.set_detections([])
    for i in range(130):
        inject_telemetry(win, i * 0.12)
    pump(30)
    saved_paths.append(save_png(grab_window(win), "04_flight_data.png"))

    # ── Shot 5: Tactical Radar + Waypoints ───────────────────────────────────
    print("  Shot 5/6: Live mission map + progress ...")
    if "runway" in frames:
        win._cam.set_frame(frames["runway"])
    inject_waypoints(win)
    inject_telemetry(win, 22.0)
    pump(30)
    saved_paths.append(save_png(grab_window(win), "05_live_mission.png"))

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
    print("\n[3/3] Building animated GIF (42 frames) ...")
    gif_frames = []
    N_FLY, N_MISSION = 36, 24          # frames on the FLIGHT DATA page / where the mission starts

    if "city_aerial" in frames:
        win._cam.set_frame(frames["city_aerial"])
    win._cam.set_detections([])
    inject_waypoints(win)               # load the demo plan, then rewind it to "ready"
    win._model.set_state(win._model.IDLE)
    win._pose.reset()
    win._goto(win.FLY)

    for fi in range(42):
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
        elif fi == N_MISSION and "runway" in frames:
            win._cam.set_frame(frames["runway"])
            win._cam.set_detections([])
            win._pose.reset()
            win._model.set_state(win._model.RUNNING)

        if N_MISSION <= fi < N_FLY:
            mission_progress(win, 0.06 + (fi - N_MISSION) * 0.08)
        elif fi == N_FLY:
            win._model.set_state(win._model.IDLE)
            win._goto(win.PLAN)
        if fi >= N_FLY:
            win._model.select(1 + (fi - N_FLY) % (len(win._model.items) - 1))

        inject_telemetry(win, t + 5)
        pump(6)

        pil_frame = pix_to_pil(grab_window(win))
        pil_frame = pil_frame.resize((800, 450), Image.LANCZOS)
        pil_frame = pil_frame.quantize(colors=96, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
        gif_frames.append(pil_frame)
        print(f"  GIF frame {fi + 1}/42 ok")

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

    print("\nDone!")
    for p in saved_paths:
        print(f"   {p}")
    print(f"   {gif_path}")


if __name__ == "__main__":
    main()
