#!/usr/bin/env python3
"""
Ansnake LED Strip Control Script
Attempts to control the LED strip by probing common protocols.

Historical: written while reverse engineering the device, before it turned out
to speak Adalight. Use ../ansnake_led.py to actually control the strip.
"""

import serial
import serial.tools.list_ports
import time
import sys


def detect_port():
    for p in serial.tools.list_ports.comports():
        if p.vid == 0x2E3C and p.pid == 0x5740:
            return p.device
    raise SystemExit("Ansnake controller not found")


PORT = detect_port()
BAUD = 115200

class LEDController:
    def __init__(self, port=PORT, baud=BAUD):
        self.ser = serial.Serial(port, baud, timeout=0.5)
        time.sleep(0.3)  # Allow connection to stabilize
        self._drain()

    def _drain(self):
        """Drain any pending data."""
        while self.ser.in_waiting:
            self.ser.read(self.ser.in_waiting)
            time.sleep(0.05)

    def send(self, data, name="data"):
        """Send data and check for response."""
        self._drain()
        self.ser.write(data)
        time.sleep(0.1)
        response = None
        if self.ser.in_waiting:
            response = self.ser.read(self.ser.in_waiting)
            print(f"  Response: {response.hex()}")
        return response

    def close(self):
        self.ser.close()

def calc_checksum(data):
    """Calculate simple XOR checksum."""
    chk = 0
    for b in data:
        chk ^= b
    return chk

def calc_sum_checksum(data):
    """Calculate sum checksum (mod 256)."""
    return sum(data) & 0xFF

# Common LED controller protocol formats
def make_packet_aa55(cmd, *args):
    """Header: AA 55, then cmd, then args."""
    data = bytes([0xAA, 0x55, cmd] + list(args))
    return data

def make_packet_aa55_len(cmd, *args):
    """Header: AA 55, length, cmd, args, checksum."""
    payload = bytes([cmd] + list(args))
    length = len(payload)
    data = bytes([0xAA, 0x55, length]) + payload
    chk = calc_checksum(data)
    return data + bytes([chk])

def make_packet_55aa(cmd, *args):
    """Header: 55 AA, then cmd, then args."""
    return bytes([0x55, 0xAA, cmd] + list(args))

def make_packet_fafb(cmd, *args):
    """Header: FA FB, then cmd, then args."""
    return bytes([0xFA, 0xFB, cmd] + list(args))

def make_rgb_packet(r, g, b, num_leds=1, header_type=0):
    """Create RGB data packet in various formats."""
    if header_type == 0:  # Direct RGB
        return bytes([r, g, b] * num_leds)
    elif header_type == 1:  # AA55 + RGB
        return bytes([0xAA, 0x55, r, g, b])
    elif header_type == 2:  # AA55 + cmd + RGB
        return bytes([0xAA, 0x55, 0x10, r, g, b])
    elif header_type == 3:  # Length prefix
        rgb_data = bytes([r, g, b] * num_leds)
        return bytes([len(rgb_data)]) + rgb_data

def interactive_mode():
    """Interactive mode to test different commands."""
    print("\n=== Ansnake LED Strip Controller ===")
    print(f"Port: {PORT}")
    print(f"Baud: {BAUD}")
    print("="*40)

    try:
        led = LEDController()
        print("Connected successfully!\n")
    except Exception as e:
        print(f"Error connecting: {e}")
        return

    print("Commands:")
    print("  r/g/b     - Set solid color (red/green/blue)")
    print("  c R G B   - Custom RGB (0-255 each)")
    print("  on/off    - Turn LED on/off")
    print("  mode N    - Try mode N (0-13)")
    print("  bright N  - Brightness (0-100)")
    print("  raw HEX   - Send raw hex bytes (e.g., 'raw aa55010100')")
    print("  probe     - Run protocol probe")
    print("  q         - Quit")
    print()

    while True:
        try:
            cmd = input("> ").strip().lower()
            if not cmd:
                continue

            if cmd == 'q':
                break
            elif cmd == 'probe':
                probe_protocol(led)
            elif cmd == 'r':
                try_set_color(led, 255, 0, 0)
            elif cmd == 'g':
                try_set_color(led, 0, 255, 0)
            elif cmd == 'b':
                try_set_color(led, 0, 0, 255)
            elif cmd.startswith('c '):
                parts = cmd.split()
                if len(parts) == 4:
                    r, g, b = int(parts[1]), int(parts[2]), int(parts[3])
                    try_set_color(led, r, g, b)
                else:
                    print("Usage: c R G B")
            elif cmd == 'on':
                try_on_off(led, True)
            elif cmd == 'off':
                try_on_off(led, False)
            elif cmd.startswith('mode '):
                mode = int(cmd.split()[1])
                try_mode(led, mode)
            elif cmd.startswith('bright '):
                brightness = int(cmd.split()[1])
                try_brightness(led, brightness)
            elif cmd.startswith('raw '):
                hex_str = cmd[4:].replace(' ', '')
                try:
                    data = bytes.fromhex(hex_str)
                    print(f"Sending: {data.hex()}")
                    led.send(data, "raw")
                except ValueError:
                    print("Invalid hex string")
            else:
                print("Unknown command. Type 'q' to quit.")

        except KeyboardInterrupt:
            print("\nQuitting...")
            break
        except Exception as e:
            print(f"Error: {e}")

    led.close()
    print("Disconnected.")

def try_set_color(led, r, g, b):
    """Try various ways to set a solid color."""
    print(f"Trying to set color RGB({r},{g},{b})...")

    formats = [
        ("AA 55 01 RGB", bytes([0xAA, 0x55, 0x01, r, g, b])),
        ("AA 55 10 RGB", bytes([0xAA, 0x55, 0x10, r, g, b])),
        ("AA 55 20 RGB", bytes([0xAA, 0x55, 0x20, r, g, b])),
        ("AA 55 30 RGB", bytes([0xAA, 0x55, 0x30, r, g, b])),
        ("AA 55 len cmd RGB chk", make_packet_aa55_len(0x01, r, g, b)),
        ("55 AA 01 RGB", bytes([0x55, 0xAA, 0x01, r, g, b])),
        ("FA FB 01 RGB", bytes([0xFA, 0xFB, 0x01, r, g, b])),
        ("Direct RGB", bytes([r, g, b])),
        ("AA 01 RGB", bytes([0xAA, 0x01, r, g, b])),
        ("FF 55 RGB", bytes([0xFF, 0x55, r, g, b])),
        # With mode byte
        ("AA 55 01 mode=12 RGB", bytes([0xAA, 0x55, 0x01, 12, r, g, b])),  # mode 12 is "Color"
        # Longer packets
        ("AA 55 len=4 01 RGB", bytes([0xAA, 0x55, 0x04, 0x01, r, g, b])),
    ]

    for name, data in formats:
        print(f"  {name}: {data.hex()}")
        led.send(data, name)
        time.sleep(0.15)

    print("Check if LED changed color. If not, the protocol might be different.")

def try_on_off(led, on):
    """Try various ways to turn LED on/off."""
    state = 1 if on else 0
    state_name = "ON" if on else "OFF"
    print(f"Trying to turn LED {state_name}...")

    formats = [
        ("AA 55 00 state", bytes([0xAA, 0x55, 0x00, state])),
        ("AA 55 01 state", bytes([0xAA, 0x55, 0x01, state])),
        ("AA 55 02 state", bytes([0xAA, 0x55, 0x02, state])),
        ("AA 55 state", bytes([0xAA, 0x55, state])),
        ("55 AA state", bytes([0x55, 0xAA, state])),
        ("Single byte", bytes([state])),
        ("Single byte FF/00", bytes([0xFF if on else 0x00])),
    ]

    for name, data in formats:
        print(f"  {name}: {data.hex()}")
        led.send(data, name)
        time.sleep(0.15)

def try_mode(led, mode):
    """Try to set effect mode."""
    print(f"Trying to set mode {mode}...")

    # Modes from the language file:
    # 0=Tracking, 1=Music, 2=Rainbow, 3=Ocean, 4=Lightning, 5=Breathing
    # 6=Flame, 7=Aurora, 8=Particle, 9=Christmas, 10=Vagaries, 11=Color
    # 12=Summer, 13=Arctic

    formats = [
        ("AA 55 02 mode", bytes([0xAA, 0x55, 0x02, mode])),
        ("AA 55 03 mode", bytes([0xAA, 0x55, 0x03, mode])),
        ("AA 55 10 mode", bytes([0xAA, 0x55, 0x10, mode])),
        ("AA 55 mode", bytes([0xAA, 0x55, mode])),
        ("55 AA 02 mode", bytes([0x55, 0xAA, 0x02, mode])),
    ]

    for name, data in formats:
        print(f"  {name}: {data.hex()}")
        led.send(data, name)
        time.sleep(0.15)

def try_brightness(led, brightness):
    """Try to set brightness (0-100)."""
    print(f"Trying to set brightness {brightness}%...")

    # Convert 0-100 to 0-255
    bval = int(brightness * 255 / 100)

    formats = [
        ("AA 55 04 bright%", bytes([0xAA, 0x55, 0x04, brightness])),
        ("AA 55 04 bright/255", bytes([0xAA, 0x55, 0x04, bval])),
        ("AA 55 05 bright%", bytes([0xAA, 0x55, 0x05, brightness])),
        ("AA 55 05 bright/255", bytes([0xAA, 0x55, 0x05, bval])),
    ]

    for name, data in formats:
        print(f"  {name}: {data.hex()}")
        led.send(data, name)
        time.sleep(0.15)

def probe_protocol(led):
    """Systematically probe the protocol."""
    print("\n=== Protocol Probe ===")
    print("Watch the LED strip for any changes!\n")

    # Test single bytes
    print("Testing single bytes 0x00-0xFF...")
    for i in range(0, 256, 16):
        data = bytes([i])
        led.send(data, f"byte 0x{i:02X}")
        time.sleep(0.05)

    # Test AA 55 with different command bytes
    print("\nTesting AA 55 XX patterns...")
    for cmd in range(0, 256, 8):
        data = bytes([0xAA, 0x55, cmd])
        led.send(data, f"AA 55 {cmd:02X}")
        time.sleep(0.05)

    # Test with some fixed payload
    print("\nTesting AA 55 XX with RGB payload (FF 00 00)...")
    for cmd in range(0, 32):
        data = bytes([0xAA, 0x55, cmd, 0xFF, 0x00, 0x00])
        led.send(data, f"AA 55 {cmd:02X} RGB")
        time.sleep(0.05)

    print("\nProbe complete. Check if any command caused a change.")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--probe":
        try:
            led = LEDController()
            probe_protocol(led)
            led.close()
        except Exception as e:
            print(f"Error: {e}")
    else:
        interactive_mode()
