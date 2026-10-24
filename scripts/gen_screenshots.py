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
    """Push simulated sinusoidal telemetry to the HUD + sparklines."""
    from PySide6.QtGui import QColor

    spd   = 40.0 + 30.0 * math.sin(t * 0.7)
    alt   = 120.0 + 60.0 * math.sin(t * 0.4)
    pitch = 12.0 * math.sin(t * 1.1)
    roll  =  8.0 * math.sin(t * 0.9 + 0.5)
    yaw   = 45.0 * math.sin(t * 0.3)

    # HUD
    win._hud.update_telemetry(
        roll=roll, pitch=pitch, yaw=yaw,
        alt=alt, speed=spd, tof=int(alt * 0.8)
    )

    # Sparklines (use update_values)
    win._spark_spd.update_values(
        [spd],
        readouts=[("", f"{spd:.0f} cm/s", QColor(0x55, 0xff, 0x99))]
    )
    win._spark_alt.update_values(
        [alt],
        readouts=[("", f"{alt:.0f} cm", QColor(0x00, 0xf0, 0xff))]
    )
    yaw_w = (yaw + 180) % 360 - 180
    win._spark_att.update_values(
        [pitch, roll, yaw_w],
        readouts=[
            ("P", f"{pitch:+.0f}°", QColor(0x55, 0xff, 0x99)),
            ("R", f"{roll:+.0f}°",  QColor(0x00, 0xf0, 0xff)),
            ("Y", f"{int(yaw):03d}°", QColor(0xff, 0xbb, 0x33)),
        ]
    )

    bat_now = max(10, bat - int(t * 0.5))
    bat_color = "#55ff99" if bat_now > 30 else ("#ffbb33" if bat_now > 15 else "#ff4455")
    win._stats_card.setText(
        f"⚡ BAT: <span style='color:{bat_color};'>{bat_now}%</span> | "
        f"TOF: <span style='color:#55ff99;'>{int(alt * 0.8)}cm</span> | "
        f"TEMP: <span style='color:#55ff99;'>72°C</span>"
    )
    win._stats_card.adjustSize()
    win._lbl_mode.setText("MODE: AIRBORNE")


def inject_ai_detections(win):
    win._cam.set_detections([
        {"box_norm": [0.08, 0.18, 0.36, 0.82], "is_person": True,  "label": "PERSON",  "conf": 0.92},
        {"box_norm": [0.55, 0.38, 0.78, 0.90], "is_person": True,  "label": "PERSON",  "conf": 0.85},
        {"box_norm": [0.60, 0.10, 0.80, 0.33], "is_person": False, "label": "laptop",  "conf": 0.88},
        {"box_norm": [0.38, 0.22, 0.53, 0.55], "is_person": False, "label": "chair",   "conf": 0.73},
    ])


def inject_waypoints(win):
    win._radar.reset_origin()
    waypoints = [(60, -80), (-40, 120), (120, 50), (200, 200), (100, -150)]
    for wp in waypoints:
        win._radar._waypoints.append(wp)
    # Fake spiral trajectory breadcrumb
    for i in range(80):
        a = i * 0.18
        win._radar._trajectory.append((int(60 * math.cos(a)), int(60 * math.sin(a))))
    win._radar.update()


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
    win._ctrl_badge.setText("🎮 KEYBOARD PILOT // STANDBY")
    win._stats_card.setText("BAT: --% | TOF: --cm | TEMP: --°C")
    win._lbl_mode.setText("MODE: STANDBY")
    pump(25)
    saved_paths.append(save_png(grab_window(win), "01_hud_standby.png"))

    # ── Shot 2: Airborne HUD + Telemetry ──────────────────────────────────────
    print("  Shot 2/6: Airborne HUD + Telemetry ...")
    if "city_aerial" in frames:
        win._cam.set_frame(frames["city_aerial"])
    win._ctrl_badge.setText("🎮 PS4 DUALSHOCK // ARMED")
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
    win._btn_ai.setText("🎯 AI TRACK: ON")
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
    print("  Shot 5/6: Tactical Radar + Waypoints ...")
    if "runway" in frames:
        win._cam.set_frame(frames["runway"])
    inject_waypoints(win)
    inject_telemetry(win, 22.0)
    pump(30)
    saved_paths.append(save_png(grab_window(win), "05_radar_waypoints.png"))

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
