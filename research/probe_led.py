#!/usr/bin/env python3
"""
LED Strip Protocol Probe Script
Tries various common protocols to communicate with the Ansnake LED strip.

Historical: written while reverse engineering the device, before it turned out
to speak Adalight. Use ../ansnake_led.py to actually control the strip.
"""

import serial
import serial.tools.list_ports
import time


def detect_port():
    for p in serial.tools.list_ports.comports():
        if p.vid == 0x2E3C and p.pid == 0x5740:
            return p.device
    raise SystemExit("Ansnake controller not found")


PORT = detect_port()
BAUD_RATES = [115200, 9600, 38400, 57600, 19200]

def try_protocol(ser, name, data, delay=0.2):
    """Send data and check for response or LED change."""
    print(f"  Trying {name}: {data.hex()}")
    ser.reset_input_buffer()
    ser.write(data)
    time.sleep(delay)
    if ser.in_waiting:
        response = ser.read(ser.in_waiting)
        print(f"    -> Response: {response.hex()} ({response})")
        return response
    return None

def probe_device():
    for baud in BAUD_RATES:
        print(f"\n{'='*50}")
        print(f"Testing baud rate: {baud}")
        print('='*50)

        try:
            ser = serial.Serial(PORT, baud, timeout=0.5)
            time.sleep(0.3)  # Allow connection to stabilize

            # Check for initial data
            if ser.in_waiting:
                initial = ser.read(ser.in_waiting)
                print(f"Initial data received: {initial.hex()}")

            # Common protocol patterns for LED controllers
            protocols = [
                # Header + command patterns
                ("aa55 header + solid red", bytes([0xaa, 0x55, 0x01, 0xff, 0x00, 0x00])),
                ("aa55 header + on cmd", bytes([0xaa, 0x55, 0x01, 0x01])),
                ("aa55 header + off cmd", bytes([0xaa, 0x55, 0x01, 0x00])),

                # 0xfa/0xfb patterns (seen in binary)
                ("fa fb header", bytes([0xfa, 0xfb, 0x01, 0xff, 0x00, 0x00])),

                # Simple RGB (no header)
                ("Direct RGB red", bytes([0xff, 0x00, 0x00])),
                ("Direct GRB red", bytes([0x00, 0xff, 0x00])),  # WS2812 style

                # With length prefix
                ("Len + RGB", bytes([0x03, 0xff, 0x00, 0x00])),
                ("Len + count + RGB", bytes([0x01, 0x03, 0xff, 0x00, 0x00])),

                # Command byte patterns
                ("Cmd 0x00", bytes([0x00])),
                ("Cmd 0x01", bytes([0x01])),
                ("Cmd 0xff", bytes([0xff])),

                # Text commands
                ("Text: on", b"on\r\n"),
                ("Text: OFF", b"OFF\r\n"),
                ("Text: RED", b"RED\r\n"),
                ("Text: #FF0000", b"#FF0000\r\n"),

                # AT commands
                ("AT", b"AT\r\n"),
                ("AT+RGB", b"AT+RGB=255,0,0\r\n"),

                # Mode commands (from strings analysis)
                ("FUNStart", b"FUNStart\r\n"),
                ("FUNStop", b"FUNStop\r\n"),

                # Brightness/mode patterns
                ("Brightness 100%", bytes([0xaa, 0x55, 0x02, 0x64])),  # 0x64 = 100
                ("Mode rainbow", bytes([0xaa, 0x55, 0x03, 0x02])),

                # Single byte commands 0-10
                ("Single 0x00", bytes([0x00])),
                ("Single 0x01", bytes([0x01])),
                ("Single 0x02", bytes([0x02])),

                # Longer packets with checksum
                ("Packet w/ checksum", bytes([0xaa, 0x55, 0x05, 0x01, 0xff, 0x00, 0x00, 0x05])),
            ]

            for name, data in protocols:
                response = try_protocol(ser, name, data, delay=0.3)
                if response:
                    print(f"  *** GOT RESPONSE! ***")

            print("\n--- Testing solid colors (watch the LED!) ---")
            colors = [
                ("RED", [0xff, 0x00, 0x00]),
                ("GREEN", [0x00, 0xff, 0x00]),
                ("BLUE", [0x00, 0x00, 0xff]),
            ]

            for color_name, rgb in colors:
                print(f"\nSending {color_name} in various formats...")
                # Try different frame formats
                formats = [
                    bytes([0xaa, 0x55, 0x01] + rgb),
                    bytes([0xaa, 0x55, 0x10] + rgb),  # 0x10 might be "set color"
                    bytes([0xaa, 0x55, 0x20] + rgb),
                    bytes([0xfa, 0xfb] + rgb),
                    bytes([0x55, 0xaa] + rgb),
                    bytes(rgb),
                    bytes([len(rgb)] + rgb),
                ]
                for fmt in formats:
                    ser.write(fmt)
                    time.sleep(0.1)

                input(f"  Did the LED turn {color_name}? Press Enter to continue...")

            ser.close()

        except serial.SerialException as e:
            print(f"Error at baud {baud}: {e}")
        except KeyboardInterrupt:
            print("\nStopping...")
            return

if __name__ == "__main__":
    print("LED Strip Protocol Probe")
    print(f"Port: {PORT}")
    print("Watch the LED strip for any color changes!")
    print("-" * 50)
    probe_device()
