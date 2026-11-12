# Ansnake LED Controller for macOS / Linux

Control an [Ansnake](https://ansnake.com/en.html) USB LED strip (monitor / desk ambient light) from macOS or Linux, without the official Windows-only software.

The official app is available at **https://ansnake.com/en.html**. This project is an unofficial, community-made alternative and is not affiliated with Ansnake.

## Requirements

- Python 3.9+
- [pySerial](https://pyserial.readthedocs.io/)
- An Ansnake LED strip plugged in over USB

## Setup

```bash
git clone <this repo>
cd <repo folder>

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

The controller is detected automatically by its USB ID. If detection fails, pass the port with `-p` (see [Troubleshooting](#troubleshooting)).

## Usage

```bash
python3 ansnake_led.py <mode> [args] [options]
```

Every mode runs until you press **Ctrl+C**, then turns the strip off. Run the script with no mode to get the [interactive prompt](#interactive-mode).

### Modes

| Mode | Example | Description |
|------|---------|-------------|
| `<color>` | `python3 ansnake_led.py warm` | Hold a named color |
| `#RRGGBB` | `python3 ansnake_led.py "#FF8000"` | Hold a hex color |
| `rgb R G B` | `python3 ansnake_led.py rgb 255 128 0` | Hold a custom RGB color (0–255) |
| `rainbow` | `python3 ansnake_led.py rainbow --speed 0.05` | Rainbow scrolling along the strip |
| `cycle` | `python3 ansnake_led.py cycle -s 0.5` | Whole strip fades through every hue |
| `breathe [color]` | `python3 ansnake_led.py breathe red` | Pulse a color in and out (default: white) |
| `off` | `python3 ansnake_led.py off` | Turn the strip off |

**Named colors:** `red`, `green`, `blue`, `white`, `yellow`, `cyan`, `magenta`, `orange`, `purple`, `pink`, `warm`, `cool`, `preset-1` (deep orange, `255 45 0`), `black`.

### Options

| Option | Default | Description |
|--------|---------|-------------|
| `-s`, `--speed SPEED` | `1.0` | Effect speed multiplier for `rainbow`, `cycle` and `breathe`. Lower is slower (e.g. `0.05`), higher is faster (e.g. `3`). |
| `--brightness PERCENT` | `100` | Brightness from 0 to 100, applied to every mode |
| `-n`, `--num-leds NUM` | `120` | Number of LEDs on your strip |
| `-p`, `--port PORT` | auto | Serial port, e.g. `/dev/cu.usbmodemXXXX` |
| `-b`, `--baud BAUD` | `115200` | Baud rate |

More examples:

```bash
python3 ansnake_led.py rainbow --speed 0.05          # very slow rainbow
python3 ansnake_led.py breathe "#00FFAA" -s 2        # fast teal breathing
python3 ansnake_led.py warm --brightness 30          # dim warm white
python3 ansnake_led.py rainbow -n 60                 # 60-LED strip
```

### Interactive mode

```bash
python3 ansnake_led.py
```

```
> rainbow             # start an effect, Ctrl+C to return to the prompt
> speed 0.1           # change effect speed
> brightness 40       # change brightness (percent)
> breathe cyan
> rgb 255 45 0
> colors              # list named colors
> off
> q                   # quit (Ctrl+D also works)
```

### Python API

```python
import time
from ansnake_led import AnsnakeLED

with AnsnakeLED(num_leds=120) as led:   # auto-detects the port
    led.start_streaming()               # the strip needs a continuous stream

    led.set_all(255, 0, 0)              # whole strip red
    time.sleep(2)

    led.set_colors([(255, 0, 0), (0, 255, 0), (0, 0, 255)] * 40)  # per-LED colors
    time.sleep(2)

    led.off()
```

## How it works

### Device

| Property | Value |
|----------|-------|
| Vendor ID | `0x2e3c` (Artery Technology) |
| Product ID | `0x5740` |
| Chip | AT32 (ARM Cortex-M microcontroller) |
| Interface | USB CDC (virtual COM port) |
| Serial port (macOS) | `/dev/cu.usbmodem*` |
| Baud rate | 115200 |
| Default LED count | 120 |

### Protocol

The device speaks the **Adalight protocol**, commonly used by PC ambient lighting systems (Ambilight clones).

**Important:** the device needs **high-speed continuous streaming** (~300+ FPS) to display colors. When streaming stops, it falls back to its built-in animation after ~10–20 seconds. Single frames or low-rate streaming don't work, which is why the script streams from a background thread for as long as a mode runs.

#### Frame format

```
┌─────┬─────┬─────┬──────┬──────┬──────────┬─────────────────┐
│ 'A' │ 'd' │ 'a' │  hi  │  lo  │ checksum │    RGB data     │
└─────┴─────┴─────┴──────┴──────┴──────────┴─────────────────┘
   3-byte header    LED count    1 byte     3 bytes × N LEDs
```

- **Header**: ASCII `"Ada"`
- **LED count**: `hi = (num_leds - 1) >> 8`, `lo = (num_leds - 1) & 0xFF`
- **Checksum**: `hi ^ lo ^ 0x55`
- **RGB data**: 3 bytes per LED (R, G, B)

Example (3 LEDs, all red):

```
Header:  41 64 61      "Ada"
Count:   00 02         (3 - 1 = 2)
Chksum:  57            (0x00 ^ 0x02 ^ 0x55)
Data:    FF 00 00      LED 0
         FF 00 00      LED 1
         FF 00 00      LED 2
```

The device replies with `0x81` for each valid frame.

### Official software

The official Windows app from [ansnake.com](https://ansnake.com/en.html) is a .NET 4.8 WPF application packaged with NSIS and talks to the strip through `System.IO.Ports.SerialPort`. Its built-in modes are:

| Index | Mode | | Index | Mode |
|-------|------|-|-------|------|
| 0 | Tracking (screen capture) | | 7 | Aurora |
| 1 | Music reactive | | 8 | Particle |
| 2 | Rainbow | | 9 | Christmas |
| 3 | Ocean | | 10 | Vagaries |
| 4 | Lightning | | 11 | Color (solid) |
| 5 | Breathing | | 12 | Summer |
| 6 | Flame | | 13 | Arctic |

## Project layout

| Path | Description |
|------|-------------|
| `ansnake_led.py` | The controller (CLI, interactive mode and Python API) |
| `requirements.txt` | Python dependencies |
| `research/` | Early protocol-probing scripts kept for reference; not needed to use the controller |

## Compatibility

- **macOS**: tested and working
- **Linux**: should work; the port is usually `/dev/ttyACM0`
- **Windows**: use the [official software](https://ansnake.com/en.html), or pass `-p COM3` (or whichever COM port)

## Troubleshooting

**Device not found**
1. Check the USB connection.
2. List serial ports: `ls /dev/cu.usb*` (macOS) or `ls /dev/ttyACM*` (Linux).
3. Pass the port manually: `python3 ansnake_led.py -p /dev/cu.usbmodemXXXX red`

**No LED response**
1. Make sure the official app (or anything else) isn't holding the port.
2. Match the LED count to your strip: `python3 ansnake_led.py -n 60 red`

**Permission denied (Linux)**
```bash
sudo usermod -a -G dialout $USER   # then log out and back in
```

## References

- [Ansnake official website and software](https://ansnake.com/en.html)
- [Adalight protocol](https://github.com/adafruit/Adalight)
- [Artery AT32 MCUs](https://www.arterychip.com/)
- [pySerial documentation](https://pyserial.readthedocs.io/)

## License

[MIT](LICENSE). Ansnake is a trademark of its respective owner; this project is not affiliated with or endorsed by Ansnake.
