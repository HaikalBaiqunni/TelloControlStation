# 🚁 Tello Control Station — Modern Aerospace Glass Cockpit & Tactical HUD

A next-generation desktop Ground Control Station (GCS) for the **Ryze Tello** (Non-EDU) drone built with **Python**, **PySide6 (Qt6)**, **OpenCV**, and **YOLOv8**.

Designed with an **Ace Combat / Modern Fighter Jet Glass Cockpit** aesthetic, featuring real-time AI object/person tracking, in-HUD rolling telemetry oscilloscopes, and an interactive tactical radar waypoint mission planner.

---

## ⚡ Key Features

- **🛩️ 100% Full-Bleed Ace Combat Jet Fighter HUD**:
  - Fluorescent emerald vector canopy (`#55ff99`) with zero clunky opaque docks.
  - Dynamic rotating & shifting Pitch Ladder (solid bars for positive, dashed for negative).
  - Center Aircraft Watermark flight path reticle (`-\v/-`).
  - Vertical Speed Ladder Tape (`SPEED >`) and Altitude Ladder Tape (`< ALT`).
  - Top Horizontal Linear Heading Compass Ribbon with caret pointer.
  - Tactical Military Radio Transmission Banner.

- **🎯 Real-Time AI Object & Human Tracking (YOLOv8)**:
  - Powered by asynchronous background YOLOv8 inference with zero video latency.
  - **Person Target Lock**: Cyan/Emerald combat tracking brackets with `[ 👤 TGT // PERSON 94% ]` and crosshairs.
  - **Object Target Lock**: Tactical amber brackets with `[ 🎯 OBJ // <LABEL> ]` for everyday items (chairs, bottles, laptops, etc.).
  - One-click toggle (`[🎯 AI TRACK: ON/OFF]` or hotkey `O`).

- **📊 In-HUD Micro-Sparklines & Telemetry Oscilloscopes**:
  - `// SPEED PROFILE`: Real-time rolling wave graph (0–80 cm/s).
  - `// ALT PROFILE`: Real-time altitude profile (0–200 cm).
  - `// ATTITUDE`: 3-channel live waveforms for **Pitch** (green), **Roll** (cyan), and **Yaw** (amber).
  - One-click toggle (`[📈 PLOTS: ON/OFF]` or hotkey `P`).

- **🗺️ Tactical Radar & Waypoint Mission Planner**:
  - Bottom-left chamfered glass radar card with concentric range rings (`±2m`, `±3m`, `±5m`, `±10m`).
  - Live breadcrumb flight trajectory trail.
  - **Interactive Click-to-Add Waypoints**: Tap anywhere on the radar grid to plot flight paths (`WP1`, `WP2`, `WP3`...).
  - `[EXEC]` triggers autonomous step-by-step navigation via Tello SDK motion commands.

- **🎮 Dual-Input: Keyboard + Gamepad Controller Support**:
  - Full support for **PlayStation (PS4 / PS5 DualSense)**, **Nintendo Switch Pro Controller**, and **Xbox** controllers via `pygame`.
  - Standard Drone Mode 2 (Left stick: Throttle/Yaw, Right stick: Pitch/Roll).
  - Action buttons: Takeoff, Land, Flip, Hover brake, Emergency engine cutoff.
  - Global Key Event Filter: Ensures keyboard controls (`WASD`, arrow keys) are never blocked by button focus.

---

## 🎮 Flight Controls

### Keyboard Mapping
| Key | Action |
|---|---|
| `W` / `S` | Pitch Forward / Backward |
| `A` / `D` | Roll Left / Right |
| `↑` / `↓` | Throttle Up / Down (Altitude) |
| `←` / `→` | Yaw CCW / CW |
| `Space` | Active Hover Brake (Zero RC) |
| `T` | Auto Takeoff |
| `L` | Auto Land |
| `Esc` | Emergency Engine Cutoff |
| `P` | Toggle In-HUD Sparkline Plots |
| `O` | Toggle AI Object / Person Tracking |

### Gamepad Mapping (Mode 2)
| Axis / Button | Function |
|---|---|
| Left Analog Stick | Vertical: Throttle (Up/Down) · Horizontal: Yaw (Turn) |
| Right Analog Stick | Vertical: Pitch (Fwd/Back) · Horizontal: Roll (Left/Right) |
| `Cross / A` | Auto Takeoff |
| `Circle / B` | Auto Land |
| `Triangle / Y` | Flip Forward |
| `Square / X` | Active Hover Brake |
| `L1 / LB` | Emergency Cutoff |
| `R1 / RB` | Speed Boost Toggle (60% ➔ 90%) |

---

## 🛠️ Installation & Setup

### Prerequisites
- Python 3.10+ (tested on Python 3.13)
- Windows 10 / 11

### 1. Clone & Set Up Environment
```bash
git clone https://github.com/HaikalBaiqunni/TelloControlStation.git
cd TelloControlStation

# Create virtual environment
python -m venv .venv
.\.venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Connect to Tello Wi-Fi
1. Power on your Ryze Tello drone.
2. Connect your PC's Wi-Fi adapter (or secondary USB Wi-Fi dongle) to the drone's SSID (e.g. `TELLO-XXXXXX`).

### 3. Launch the Cockpit
```bash
python main.py
# Or run using the launcher script:
.\run.bat
```
4. Click **`⚡ UPLINK`** in the bottom Action Deck to connect and initialize the video stream!

---

## 🗂️ Project Architecture

```
TelloControlStation/
├── main.py                          # Application entry point
├── requirements.txt                 # Dependencies (PySide6, opencv, numpy, pygame, ultralytics)
├── run.bat                          # One-click Windows launcher
├── src/
│   ├── drone/
│   │   ├── tello_sdk.py             # UDP Socket wrapper for Tello SDK 1.3
│   │   ├── state_parser.py          # Real-time state string parser (DroneState)
│   │   ├── video_stream.py          # H.264 UDP OpenCV decoder thread
│   │   ├── mission_planner.py       # Autonomous waypoint navigation engine
│   │   └── object_detector.py       # Asynchronous YOLOv8 AI object & person detector
│   ├── input/
│   │   └── gamepad_handler.py       # Pygame joystick input handler (PS4/Switch/Xbox)
│   ├── ui/
│   │   ├── main_window.py           # Modern Glass Canopy MainWindow & Action Deck
│   │   └── widgets/
│   │       ├── fighter_hud.py       # Ace Combat vector green HUD (Pitch ladder, tapes)
│   │       ├── tactical_radar.py    # Waypoint radar card with trajectory trail
│   │       ├── flight_log.py        # Glass telemetry & comms log panel
│   │       └── sparkline_widget.py  # In-HUD rolling micro-sparklines & oscilloscopes
│   └── utils/
│       └── logger.py                # Thread-safe flight event logger
```

---

## 📄 License
MIT License. Built for drone hobbyists, FPV enthusiasts, and robotics tinkerers.
