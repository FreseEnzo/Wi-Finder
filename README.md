# WiFinder

Locates WiFi routers from RSSI + GPS data collected in flight. Collection runs
on an ESP32 with a small OLED screen and a NEO-6M GPS; position estimation and
the map are produced on the computer.

```
ESP32 in flight ──(flash)──> v###.log logs ──(USB)──> flight.db ──> CSV + HTML map
```

> The program's interface (screens, command-line flags, report text, CSV
> columns) is in Portuguese. This documentation quotes those strings as they
> appear, with a translation where useful.

## Layout

| Folder / file | What it is |
|---|---|
| `firmware/wifinder/` | Arduino firmware for the ESP32 (WiFi + GPS collection, OLED screen, logs on flash) |
| `wifinder/` | Python program: start screen, import, estimation, map, report, simulator |
| `suporte/` | 3D-printed enclosure that carries the collector on top of a DJI Mavic 4 Pro (see `suporte/README.md`) |
| `tests/` | Tests (`python3 -m pytest tests`) |
| `empacotar.sh` | Builds the single-file Linux executable |
| `CHANGELOG.md` | What changed in each version |

## Hardware

- ESP32 WROOM-32 with a 0.96" OLED (SSD1306, I2C). The firmware finds the
  screen by itself on the most common pins (21/22, 5/4, Heltec 4/15).
- GY-NEO6M V2 GPS, wired to the ESP32's UART2:

| GPS NEO-6M | ESP32           |
|------------|-----------------|
| VCC        | VIN (5 V) or 3V3 |
| GND        | GND             |
| TX         | GPIO16 (RX2)    |
| RX         | GPIO17 (TX2), optional |

The GPS TX line is 3.3 V and can go straight to the ESP32. If the screen is a
Heltec (reset on GPIO16), the firmware moves the GPS to GPIO17 (RX) and GPIO13
(TX) and reports it on the screen and on the serial port.

## Firmware (`firmware/wifinder`)

```sh
arduino-cli core install esp32:esp32
arduino-cli lib install TinyGPSPlus U8g2
firmware/flash.sh /dev/ttyUSB0
arduino-cli monitor -p /dev/ttyUSB0 -c baudrate=115200
```

The screen shows: current file, GPS state (no data / no fix / satellites and
HDOP), UTC time and altitude, networks heard in the last sweep, samples
recorded and free flash. When the PC sends commands it switches to "PC
conectado" (PC connected), with a progress bar during the transfer and a check
mark at the end.

Buttons: **EN** restarts the board and starts a new mission (a new file;
earlier ones are kept until downloaded). Holding **BOOT** for 3 s erases all
logs, with a countdown on screen (release early to cancel). The serial port
prints a status line (`#...`) every 2 s and accepts the commands `help`, `ls`,
`dump <file>`, `rm <file>`, `rmall`, `pause`, `resume`, `info`.

How it works: it scans one channel at a time (120 ms each, channels 1 to 13)
and records every network heard with the time of the scan; the GPS records one
fix per second. Everything goes to flash (LittleFS, ~1.9 MB, enough for several
hours of flight). The position of each sample is interpolated on the computer
between the neighbouring fixes.

GPS diagnostics on the screen: `GPS SEM DADOS` (no data) = nothing arrives on
GPIO16 (wiring); `GPS lixo na serial` (garbage on serial) = bytes arrive but no
valid sentence (baud rate); `GPS SEM FIX n sat` (no fix) = module OK, waiting
for satellites (under open sky this takes 1 to 15 min the first time).

## On the computer

```sh
pip install -r requirements.txt
python3 -m wifinder                        # start screen in the browser
```

The start screen shows when the ESP32 is on USB, downloads its flights with
one click and stores each one in the `voos/` folder (one `.log` per flight).
Each flight opens on the map or becomes a PDF report; select several and they
open together on a single map. It only serves the local computer; Ctrl+C in
the terminal closes it. `--dir` changes the flights folder and `--port` the
port.

Linux executable: `./empacotar.sh` builds the `WiFinder` file (a single file,
~46 MB, no Python needed on the user's machine); `./empacotar.sh --atalho` also
adds WiFinder to the applications menu. It stores flights in a `voos/` folder
next to the executable. Launching it twice just shows the window already open;
the "Encerrar o WiFinder" (quit) button in the footer closes the program.

The same steps from the command line:

```sh
python3 -m wifinder pull voo.db            # download logs over USB and import them
python3 -m wifinder estimate voo.db        # writes voo-roteadores.csv and voo-mapa.html
python3 -m wifinder report voo.db          # writes voo-relatorio.pdf (summary, overview, table)
```

`pull` keeps the logs in `voo-logs/` and never imports the same file twice;
`--rm` erases them from the board after downloading. `import` imports logs
already downloaded (to view a single flight:
`python3 -m wifinder import voo20.db voo-logs/v020.log`).

How the position is estimated: for each device, the mean of the track points
where its signal was strongest. Networks broadcast by the same router (main,
guest, ISP) are merged into a single item. Each device gets a likely radius
(± m) and a confidence: good (heard strongly and at many points), medium, or
weak (heard at 1 or 2 points). A straight-line track cannot tell which side a
device is on; fly past both sides or in a zigzag to refine it.

The HTML map has 2D and 3D views (button on the panel; right mouse button tilts
and rotates), zoom up to level 22, search, filters by confidence and signal, a
device list, the points where the selected device was heard, coordinates in
decimal, degrees/minutes/seconds or MGRS (cursor, map click and each device,
with a copy button) and export of visible devices to CSV and KML (Google
Earth). It needs internet for the base map and the libraries.

`report` produces a summary with a map, an overview page (channels, signal,
strongest devices) and the full table. It needs internet for the satellite
background (Esri); without it, `--sem-fundo` draws the map in metres.
`simulate` creates a synthetic flight to test without hardware
(`--ambiente selva` models loss through forest vegetation, `--esp32-log` writes
it in the firmware's log format), and `collect` is the older Raspberry Pi
version.

Tests: `python3 -m pytest tests`.

To try it without hardware:

```sh
python3 -m wifinder simulate demo.db       # synthetic flight
python3 -m wifinder estimate demo.db       # demo-roteadores.csv and demo-mapa.html
```

## Drone mount

`suporte/` holds a closed enclosure (base + lid) that carries the ESP32 and the
GPS on top of a DJI Mavic 4 Pro: a parametric FreeCAD model (`suporte.py`),
STL, STEP and ready-to-print G-code for an Ender-3 V2. Dimensions, assembly,
sealing and printing are in `suporte/README.md`.
