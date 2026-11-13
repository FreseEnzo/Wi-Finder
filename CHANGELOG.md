# WiFinder — changelog

## 1.7.0 — 2026-11-11

Driven by the first flight with many networks (flight 20: 113 networks).

### Start screen (new)
- `python3 -m wifinder` opens the start screen in the browser (local computer
  only, at http://127.0.0.1:8737/).
- Detects on its own when the ESP32 is plugged into USB; one click downloads
  the flights from the board, with a progress bar. Erasing them from the board
  afterwards is optional.
- Flight library in the `voos/` folder: one `.log` file per flight, with the
  GPS date and time in the name. Downloading again does not duplicate; a
  flight that grew is updated; empty logs are ignored.
- Each flight has a card with a drawing of the track, devices, networks,
  duration and distance, plus buttons for the map and the PDF report. Flights
  can be renamed, deleted, and `.log` files can be imported from the computer.
- Several flights together: select the cards and open a single map or report,
  with the samples of all of them combined in the estimate.

### Linux executable (new)
- `./empacotar.sh` builds the single `WiFinder` file; with `--atalho` it also
  creates an entry in the applications menu.
- Launching the program while it is already open just shows the existing
  window; "Encerrar o WiFinder" (quit) button in the footer.

### Estimation
- Position from the centroid of the strongest-signal points, instead of the
  path-loss fit. In simulations the median error dropped from ~40 m to ~20 m
  in the city scenario and from ~27 m to ~16 m in the forest scenario; the
  worst case from ~380 m to ~100 m.
- Hovering no longer pulls the estimate: samples are grouped into 8 m cells
  before the calculation.
- Networks from the same device (main, guest, ISP) become a single item. In
  flight 20, 113 networks are 73 devices.
- Likely radius (± m) instead of an uncertainty radius of hundreds of metres;
  in simulations the true position falls inside it 94 % of the time.
- Confidence good / medium / weak, based on signal and on how many track
  points heard the device.
- Bad fixes at the start (GPS still settling) are left out of the estimate
  and of the drawn track.

### Interactive map
- Much deeper zoom (up to level 22; native satellite imagery up to 19 where
  available, detected automatically).
- 3D view: 2D/3D button, tilt and rotate with the right mouse button, one
  column per device with height by signal, buildings where OpenStreetMap has
  them, and the flight altitude as a curtain under the track.
- Colour = signal, size = confidence. Labels no longer overlap: the strongest
  are shown and the others appear when zooming in.
- Header with devices, networks, duration and track length; list with channel
  and confidence; popup with all of the device's networks.
- CSV and KML with channel, the device's networks and confidence.

### PDF report
- Page 1 with flight indicators and a sharper satellite map, framed on the
  track, without the giant circles and with non-overlapping labels.
- New "Panorama" page: devices per channel, per signal, the ten strongest and
  a box explaining how to read the report.
- Redesigned table (alternating rows, signal colour, channel, number of
  networks).

### Changed
- `<db>-roteadores.csv` has new columns: ssid, bssid, redes (networks), canal
  (channel), lat, lon, raio_m (radius), confianca (confidence), amostras
  (samples), pontos (points), rssi_max.
- `--ground-alt` and `--min-samples` are still accepted but no longer have an
  effect.
- The map moved from Leaflet to MapLibre GL.

### Known issues
- The median error in the city simulation is ~20 m; the old 15 m target of
  `test_simulated_flight` was not reached and the test limit is now 25 m.
- On a straight-line track it is not possible to tell which side a device is
  on.

## 1.6.0 — 2026-11-11

Previous base: 1.5.1 (collection on a Raspberry Pi with `iw scan`, simulator,
estimation and a simple map).

### On-board collection on the ESP32 (new)
- Arduino firmware in `firmware/wifinder` for an ESP32 WROOM-32 with an OLED
  screen: reads the NEO-6M GPS (UART2, GPIO16/17), scans WiFi channel by
  channel (120 ms per channel, one sweep every ~2 s) and writes everything to
  flash (LittleFS, ~1.9 MB).
- Automatic OLED detection (pins 21/22, 5/4, Heltec 4/15 and 4/5). With a
  Heltec screen, the GPS pins switch to 17/13 automatically.
- Collection screen: current mission, GPS state with diagnostics (no data,
  garbage on serial, no fix, fix with satellites and HDOP), UTC time,
  altitude, networks heard, samples recorded and free flash.
- USB commands: `help`, `ls`, `dump`, `rm`, `rmall`, `done`, `pause`,
  `resume`, `info`.
- EN button: restarts and opens a new mission ("Nova missão: vNNN" screen).
  BOOT button held for 3 s: erases all logs, with a countdown on screen.
- Animations: "PC conectado" with a spinner, progress bar during the transfer
  and a "Pronto!" check mark at the end.
- Pull-up on the GPS RX (no noise with the module off); `dump` limited to the
  announced size (the current file grows during the transfer).
- `firmware/flash.sh` compiles and flashes in one command (no_ota partition:
  2 MB app + 2 MB logs).

### Command line
- `pull`: downloads the logs over USB, keeps them in `<db>-logs/` and imports
  them into the database without importing the same file twice (`imports`
  table). `--rm` erases them from the board after downloading.
- `import`: imports logs already downloaded. The position of each network is
  interpolated between the neighbouring fixes using the board clock (up to
  2 s apart).
- `report`: PDF report with a flight summary (start, duration, distance,
  altitude, fixes, samples, networks), a satellite map built from Esri tiles
  (cached in `~/.cache/wifinder-tiles`) and the network table. `--sem-fundo`
  for offline use.
- `simulate`: `--ambiente selva` (forest scenario: drone above the canopy,
  vegetation loss using the Weissberger model, routers in clearings or under
  the trees, strong shadowing), `--esp32-log` (writes the flight in the
  firmware format), `--alt` and `--lane`.

### Interactive map
- Panel with search by SSID/BSSID, filters by status, minimum samples,
  maximum RSSI and maximum uncertainty; layers for track, circles and labels.
- Network list; clicking flies to the network and shows the points where it
  was heard, coloured from weak to strong signal.
- Coordinates in decimal, degrees/minutes/seconds or MGRS: in the bottom bar
  following the cursor, on map click and in each network's popup, with a copy
  button and a Google Maps link.
- Export of visible networks to CSV (with MGRS) and KML (Google Earth).
- Network name always visible next to each point.
- Satellite (Esri) and street (CARTO) base maps; OpenStreetMap was removed
  because it blocks pages opened from disk. Native zoom limited to 17.

### Other
- README with wiring, flashing and the full workflow.
- New tests: log import, download with a mocked serial port, full ESP32 flow,
  report. 7 pass.

### Known issues
- The path-loss fit estimator is off by ~50 m in the city simulation and
  ~70 m in the forest one; the signal-weighted centroid does better in the
  forest (~17 m). `test_simulated_flight` still fails because of this.
  Suggested next step: centroid or hybrid in `estimate`.
- The GPS part of the firmware has not yet been tested with the module
  connected.
