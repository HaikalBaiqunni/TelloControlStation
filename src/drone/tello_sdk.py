"""
src/drone/tello_sdk.py
Low-level Tello SDK 1.3 UDP communication wrapper.

Architecture:
  - Commands are sent to 192.168.10.1:8889 via UDP
  - Responses come back on the same local socket (bound to 0.0.0.0:8889)
  - State telemetry is received on 0.0.0.0:8890
  - Video H.264 stream is on UDP 0.0.0.0:11111

Threading model:
  - _cmd_recv_thread: daemon thread receiving command responses
  - _state_recv_thread: daemon thread receiving telemetry (fires state_received signal)
  - All Qt signals are emitted from worker threads — connect to slots with
    Qt.ConnectionType.QueuedConnection to safely update UI from main thread.
"""

import socket
import threading
import time
from typing import Optional

from PySide6.QtCore import QObject, Signal, Qt

from src.drone.state_parser import DroneState, parse_state


class TelloSDK(QObject):
    """Tello SDK 1.3 controller (Non-EDU drone)."""

    # ── Qt Signals (emitted from worker threads) ─────────────────────
    state_received   = Signal(DroneState)   # ~10 Hz telemetry
    response_received = Signal(str)          # command response (ok/error/value)
    connected_sig    = Signal()
    disconnected_sig = Signal()
    error_sig        = Signal(str)

    # ── Tello Network Config ─────────────────────────────────────────
    TELLO_IP       = '192.168.10.1'
    TELLO_CMD_PORT = 8889
    LOCAL_CMD_PORT = 8889
    STATE_PORT     = 8890
    VIDEO_PORT     = 11111

    def __init__(self, parent=None):
        super().__init__(parent)

        self._cmd_sock: Optional[socket.socket] = None
        self._state_sock: Optional[socket.socket] = None

        self._connected = False
        self._running   = False

        # Lock guards _cmd_sock sends; response signaling uses an Event
        self._send_lock      = threading.Lock()
        self._response_event = threading.Event()
        self._last_response  = ''

        self._cmd_recv_thread:   Optional[threading.Thread] = None
        self._state_recv_thread: Optional[threading.Thread] = None
        self._keepalive_thread:  Optional[threading.Thread] = None

    # ── Connection lifecycle ─────────────────────────────────────────

    def connect(self) -> bool:
        """
        Open UDP sockets and enter Tello SDK mode.
        Returns True on success.
        Blocks up to ~3 seconds waiting for 'ok' from drone.
        """
        if self._connected:
            return True

        try:
            # Command socket (send + receive on same port)
            self._cmd_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._cmd_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._cmd_sock.settimeout(3.0)
            self._cmd_sock.bind(('', self.LOCAL_CMD_PORT))

            # State socket (receive-only)
            self._state_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._state_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._state_sock.settimeout(2.0)
            self._state_sock.bind(('', self.STATE_PORT))

            self._running = True

            # Start receiver threads
            self._cmd_recv_thread = threading.Thread(
                target=self._cmd_recv_loop, daemon=True, name='tello-cmd-recv')
            self._cmd_recv_thread.start()

            self._state_recv_thread = threading.Thread(
                target=self._state_recv_loop, daemon=True, name='tello-state-recv')
            self._state_recv_thread.start()

            # Enter SDK mode (mandatory first command)
            resp = self.send_command('command', timeout=5.0)
            if resp != 'ok':
                self._cleanup()
                self.error_sig.emit(f"SDK handshake failed (got: '{resp}'). Is Tello WiFi connected?")
                return False

            self._connected = True

            # Keepalive: query battery every 12 s to prevent Tello auto-land
            self._keepalive_thread = threading.Thread(
                target=self._keepalive_loop, daemon=True, name='tello-keepalive')
            self._keepalive_thread.start()

            self.connected_sig.emit()
            return True

        except OSError as e:
            self._cleanup()
            self.error_sig.emit(f"Socket error: {e}")
            return False

    def disconnect(self):
        """Gracefully disconnect from drone."""
        if self._connected:
            try:
                self.send_command('land', timeout=3.0)
            except Exception:
                pass

        self._running    = False
        self._connected  = False
        self._cleanup()
        self.disconnected_sig.emit()

    def _cleanup(self):
        """Close sockets. Safe to call multiple times."""
        for sock_attr in ('_cmd_sock', '_state_sock'):
            sock = getattr(self, sock_attr, None)
            if sock:
                try:
                    sock.close()
                except Exception:
                    pass
                setattr(self, sock_attr, None)

    @property
    def is_connected(self) -> bool:
        return self._connected

    # ── Command API ──────────────────────────────────────────────────

    def send_command(self, cmd: str, timeout: float = 3.0) -> str:
        """
        Send a Tello SDK command and block until a response is received.
        Returns the response string (e.g. 'ok', 'error', or a value like '88').
        """
        if not self._cmd_sock:
            return 'error: no socket'

        with self._send_lock:
            self._response_event.clear()
            self._last_response = ''
            try:
                self._cmd_sock.sendto(
                    cmd.encode('utf-8'),
                    (self.TELLO_IP, self.TELLO_CMD_PORT)
                )
            except OSError as e:
                return f'error: {e}'

            got_response = self._response_event.wait(timeout)
            return self._last_response if got_response else 'timeout'

    def send_rc(self, left_right: int, fwd_back: int, up_down: int, yaw: int):
        """
        Send RC control values without waiting for a response.
        All values must be in the range [-100, 100].

        Args:
            left_right: negative = left, positive = right
            fwd_back:   negative = backward, positive = forward
            up_down:    negative = down, positive = up
            yaw:        negative = counter-clockwise, positive = clockwise
        """
        if not self._cmd_sock or not self._connected:
            return

        def clamp(v): return max(-100, min(100, int(v)))

        cmd = f'rc {clamp(left_right)} {clamp(fwd_back)} {clamp(up_down)} {clamp(yaw)}'
        try:
            self._cmd_sock.sendto(cmd.encode('utf-8'), (self.TELLO_IP, self.TELLO_CMD_PORT))
        except OSError:
            pass

    def takeoff(self) -> str:
        return self.send_command('takeoff', timeout=10.0)

    def land(self) -> str:
        return self.send_command('land', timeout=10.0)

    def emergency(self):
        """Immediately cut all motors. Use only in emergencies."""
        if self._cmd_sock:
            try:
                self._cmd_sock.sendto(b'emergency', (self.TELLO_IP, self.TELLO_CMD_PORT))
            except OSError:
                pass

    def stream_on(self) -> str:
        return self.send_command('streamon', timeout=5.0)

    def stream_off(self) -> str:
        return self.send_command('streamoff', timeout=5.0)

    def flip(self, direction: str) -> str:
        """direction: 'l', 'r', 'f', 'b'"""
        if direction not in ('l', 'r', 'f', 'b'):
            return 'error: invalid direction'
        return self.send_command(f'flip {direction}', timeout=5.0)

    def query_battery(self) -> str:
        return self.send_command('battery?', timeout=3.0)

    def set_speed(self, speed_cms: int) -> str:
        """Set speed 10–100 cm/s."""
        speed_cms = max(10, min(100, speed_cms))
        return self.send_command(f'speed {speed_cms}')

    # ── Worker threads ───────────────────────────────────────────────

    def _cmd_recv_loop(self):
        """Receive command responses on the command socket."""
        while self._running:
            if not self._cmd_sock:
                break
            try:
                data, _ = self._cmd_sock.recvfrom(1024)
                resp = data.decode('utf-8', errors='replace').strip()
                self._last_response = resp
                self._response_event.set()
                self.response_received.emit(resp)
            except socket.timeout:
                continue
            except OSError:
                break

    def _state_recv_loop(self):
        """Receive and parse state telemetry on port 8890."""
        while self._running:
            if not self._state_sock:
                break
            try:
                data, _ = self._state_sock.recvfrom(1024)
                raw = data.decode('utf-8', errors='replace').strip()
                state = parse_state(raw)
                if state is not None:
                    self.state_received.emit(state)
            except socket.timeout:
                continue
            except OSError:
                break

    def _keepalive_loop(self):
        """Query battery every 12 s to keep the Tello from auto-disconnecting."""
        while self._running and self._connected:
            time.sleep(12)
            if self._connected:
                self.send_command('battery?', timeout=2.0)
