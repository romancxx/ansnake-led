#!/usr/bin/env python3
"""
Ansnake LED strip controller for macOS and Linux.

Drives an Ansnake USB LED strip with the Adalight protocol over USB serial.
The device only shows a color while it receives a continuous, high-speed
stream of frames, so frames are pushed from a background thread for as long
as a mode is running.

Usage:
    python3 ansnake_led.py                       # Interactive mode
    python3 ansnake_led.py red                   # Hold a named color
    python3 ansnake_led.py "#FF8000"             # Hold a hex color
    python3 ansnake_led.py rgb 255 128 0         # Hold a custom RGB color
    python3 ansnake_led.py rainbow --speed 0.05  # Slow rainbow
    python3 ansnake_led.py breathe red           # Breathing effect
    python3 ansnake_led.py cycle                 # Whole-strip color cycle
    python3 ansnake_led.py off                   # Turn off
"""

import argparse
import colorsys
import math
import sys
import threading
import time

import serial
import serial.tools.list_ports

USB_VID = 0x2E3C  # Artery Technology
USB_PID = 0x5740
DEFAULT_BAUD = 115200
DEFAULT_NUM_LEDS = 120
EFFECT_FRAME_INTERVAL = 0.016  # ~60 FPS effect updates; the serial stream itself runs flat out

NAMED_COLORS = {
    "red": (255, 0, 0),
    "green": (0, 255, 0),
    "blue": (0, 0, 255),
    "white": (255, 255, 255),
    "yellow": (255, 255, 0),
    "cyan": (0, 255, 255),
    "magenta": (255, 0, 255),
    "orange": (255, 128, 0),
    "purple": (128, 0, 255),
    "pink": (255, 105, 180),
    "warm": (255, 180, 100),
    "cool": (200, 220, 255),
    "preset-1": (255, 45, 0),
    "black": (0, 0, 0),
}

EFFECTS = ("rainbow", "cycle", "breathe")


def find_port():
    """Return the serial device of the first connected Ansnake controller, or None."""
    for port in serial.tools.list_ports.comports():
        if port.vid == USB_VID and port.pid == USB_PID:
            return port.device
    return None


def _clamp(value):
    return max(0, min(255, int(value)))


class AnsnakeLED:
    """Controller for an Ansnake LED strip using the Adalight protocol."""

    def __init__(self, port=None, baud=DEFAULT_BAUD, num_leds=DEFAULT_NUM_LEDS):
        self.port = port or find_port()
        self.baud = baud
        self.num_leds = num_leds
        self.ser = None
        self._frame = self._make_frame([])
        self._lock = threading.Lock()
        self._streaming = False
        self._stream_thread = None

    # -- connection -----------------------------------------------------------

    def connect(self):
        """Open the serial port. Returns True on success."""
        if not self.port:
            print("No Ansnake controller found. Is it plugged in? "
                  "You can also pass the port with -p.", file=sys.stderr)
            return False
        try:
            self.ser = serial.Serial(self.port, self.baud, timeout=0.1)
        except serial.SerialException as e:
            print(f"Error connecting to {self.port}: {e}", file=sys.stderr)
            return False
        time.sleep(0.3)  # let the USB CDC link settle
        return True

    def disconnect(self):
        """Stop streaming and close the serial port."""
        self.stop_streaming()
        if self.ser and self.ser.is_open:
            self.ser.close()

    def __enter__(self):
        if not self.connect():
            raise ConnectionError(f"Could not connect to LED strip on {self.port}")
        return self

    def __exit__(self, *exc):
        self.disconnect()

    # -- frames ---------------------------------------------------------------

    def _make_frame(self, colors):
        """Build an Adalight frame, padding/truncating colors to num_leds."""
        colors = list(colors)[:self.num_leds]
        colors += [(0, 0, 0)] * (self.num_leds - len(colors))

        count = self.num_leds - 1
        hi, lo = count >> 8, count & 0xFF
        header = b"Ada" + bytes((hi, lo, hi ^ lo ^ 0x55))
        return header + bytes(_clamp(c) for rgb in colors for c in rgb)

    def set_colors(self, colors):
        """Set per-LED colors from a list of (r, g, b) tuples."""
        frame = self._make_frame(colors)
        with self._lock:
            self._frame = frame

    def set_all(self, r, g, b):
        """Set every LED to the same color."""
        self.set_colors([(r, g, b)] * self.num_leds)

    def off(self):
        """Turn all LEDs off."""
        self.set_all(0, 0, 0)
        # The device needs a short burst of frames for the change to stick.
        self.start_streaming()
        time.sleep(0.3)
        self.stop_streaming()

    # -- streaming ------------------------------------------------------------

    @property
    def is_streaming(self):
        return self._streaming

    def start_streaming(self):
        """Start pushing the current frame continuously in the background."""
        if self._streaming:
            return
        self._streaming = True
        self._stream_thread = threading.Thread(target=self._stream_loop, daemon=True)
        self._stream_thread.start()

    def stop_streaming(self):
        """Stop the background stream."""
        self._streaming = False
        if self._stream_thread:
            self._stream_thread.join(timeout=1)
            self._stream_thread = None

    def _stream_loop(self):
        # No sleep: the device needs ~300+ FPS or it falls back to its built-in animation.
        while self._streaming:
            with self._lock:
                frame = self._frame
            try:
                self.ser.write(frame)
                # The device ACKs each frame with 0x81; discard them so the buffer never fills.
                if self.ser.in_waiting > 50:
                    self.ser.reset_input_buffer()
            except (serial.SerialException, OSError) as e:
                print(f"\nLost connection to LED strip: {e}", file=sys.stderr)
                self._streaming = False


# -- color parsing --------------------------------------------------------------

def parse_color(text):
    """Parse a color name or hex string (#RRGGBB / RRGGBB) to an (r, g, b) tuple, or None."""
    text = text.lower().strip()
    if text in NAMED_COLORS:
        return NAMED_COLORS[text]
    hex_str = text.removeprefix("#")
    if len(hex_str) == 6:
        try:
            return tuple(int(hex_str[i:i + 2], 16) for i in (0, 2, 4))
        except ValueError:
            pass
    return None


def parse_rgb(values):
    """Parse three 0-255 integers to an (r, g, b) tuple."""
    if len(values) != 3:
        raise ValueError("rgb needs exactly three values, e.g. rgb 255 128 0")
    rgb = tuple(int(v) for v in values)
    if any(not 0 <= c <= 255 for c in rgb):
        raise ValueError("rgb values must be between 0 and 255")
    return rgb


def _hue(h):
    r, g, b = colorsys.hsv_to_rgb(h % 1.0, 1.0, 1.0)
    return (r * 255, g * 255, b * 255)


# -- modes ----------------------------------------------------------------------
# A mode is a function step -> list of (r, g, b) colors, called ~60 times a second.

def solid(num_leds, color):
    frame = [color] * num_leds
    return lambda step: frame


def rainbow(num_leds, speed=1.0):
    def frame(step):
        offset = step * 0.005 * speed
        return [_hue(i / num_leds + offset) for i in range(num_leds)]
    return frame


def color_cycle(num_leds, speed=1.0):
    return lambda step: [_hue(step * 0.003 * speed)] * num_leds


def breathe(num_leds, color, speed=1.0):
    def frame(step):
        level = (math.sin(step * 0.05 * speed) + 1) / 2
        return [tuple(c * level for c in color)] * num_leds
    return frame


def resolve_mode(command, args, num_leds, speed=1.0):
    """Turn a command and its arguments into (label, mode). Raises ValueError if unknown."""
    if command == "rainbow":
        return "Rainbow", rainbow(num_leds, speed)
    if command == "cycle":
        return "Color cycle", color_cycle(num_leds, speed)
    if command == "breathe":
        color = parse_color(args[0]) if args else NAMED_COLORS["white"]
        if color is None:
            raise ValueError(f"Unknown color: {args[0]}")
        return "Breathing", breathe(num_leds, color, speed)
    if command == "rgb":
        color = parse_rgb(args)
    else:
        color = parse_color(command)
        if color is None:
            raise ValueError(f"Unknown command or color: {command}")
    return f"Holding RGB{color}", solid(num_leds, color)


def play(led, label, mode, brightness=1.0):
    """Stream a mode until Ctrl+C (or the connection drops), then turn the strip off."""
    print(f"{label} - Ctrl+C to stop")
    led.start_streaming()
    step = 0
    try:
        while led.is_streaming:
            colors = mode(step)
            if brightness < 1.0:
                colors = [tuple(c * brightness for c in rgb) for rgb in colors]
            led.set_colors(colors)
            step += 1
            time.sleep(EFFECT_FRAME_INTERVAL)
    except KeyboardInterrupt:
        print("\nStopped")
    finally:
        led.stop_streaming()
        led.off()


def run_command(led, command, args, speed=1.0, brightness=1.0):
    command = command.lower()
    if command == "off":
        led.off()
        print("LEDs off")
        return
    label, mode = resolve_mode(command, args, led.num_leds, speed)
    play(led, label, mode, brightness)


# -- interactive mode -------------------------------------------------------------

INTERACTIVE_HELP = """\
Commands:
  <color>            Hold a color (red, warm, #FF00FF, ...)
  rgb R G B          Hold a custom RGB color (0-255)
  rainbow            Rainbow effect
  cycle              Whole-strip color cycle
  breathe [color]    Breathing effect (default: white)
  speed N            Effect speed multiplier (e.g. 0.05, 1, 3)
  brightness N       Brightness in percent (0-100)
  colors             List named colors
  off                Turn off
  q                  Quit
"""


def interactive_mode(led, speed=1.0, brightness=1.0):
    print("\n=== Ansnake LED Controller ===")
    print(f"Port: {led.port}")
    print(f"LEDs: {led.num_leds}\n")
    print(INTERACTIVE_HELP)

    while True:
        try:
            line = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            continue

        command, *args = line.split()
        command = command.lower()
        try:
            if command in ("q", "quit", "exit"):
                break
            elif command in ("help", "?"):
                print(INTERACTIVE_HELP)
            elif command == "colors":
                print(", ".join(NAMED_COLORS))
            elif command == "speed" and args:
                speed = float(args[0])
                print(f"Speed: {speed}")
            elif command == "brightness" and args:
                brightness = max(0, min(100, int(args[0]))) / 100
                print(f"Brightness: {int(brightness * 100)}%")
            else:
                run_command(led, command, args, speed, brightness)
        except ValueError as e:
            print(e)

    led.off()
    print("Goodbye!")


# -- CLI --------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Control an Ansnake LED strip over USB serial.",
        epilog=f"Modes: {', '.join(EFFECTS)}, rgb R G B, off, or a color "
               f"({', '.join(NAMED_COLORS)}, #RRGGBB). Run without a command for interactive mode.",
    )
    parser.add_argument("command", nargs="?", help="mode or color (omit for interactive mode)")
    parser.add_argument("args", nargs="*", help="mode arguments, e.g. RGB values or a breathe color")
    parser.add_argument("-p", "--port", help="serial port (default: auto-detect)")
    parser.add_argument("-n", "--num-leds", type=int, default=DEFAULT_NUM_LEDS,
                        help=f"number of LEDs on the strip (default: {DEFAULT_NUM_LEDS})")
    parser.add_argument("-b", "--baud", type=int, default=DEFAULT_BAUD,
                        help=f"baud rate (default: {DEFAULT_BAUD})")
    parser.add_argument("-s", "--speed", type=float, default=1.0,
                        help="effect speed multiplier (default: 1.0, slower: 0.1)")
    parser.add_argument("--brightness", type=int, default=100, metavar="PERCENT",
                        help="brightness 0-100 (default: 100)")
    args = parser.parse_args()
    brightness = max(0, min(100, args.brightness)) / 100

    led = AnsnakeLED(port=args.port, baud=args.baud, num_leds=args.num_leds)
    if not led.connect():
        sys.exit(1)

    try:
        if args.command is None:
            interactive_mode(led, args.speed, brightness)
        else:
            run_command(led, args.command, args.args, args.speed, brightness)
    except ValueError as e:
        print(e, file=sys.stderr)
        sys.exit(2)
    except KeyboardInterrupt:
        print("\nStopped")
    finally:
        led.disconnect()


if __name__ == "__main__":
    main()
