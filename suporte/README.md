# Closed WiFinder mount for the DJI Mavic 4 Pro

Two parts:

- **Base** (`wifinder-mavic4pro-base.stl`): the same ring as the AirTag mount
  (the fit on the drone is unchanged: the ring hugs the drone's body, standing
  up, like a band) with a box lying directly on top of the drone, with 1 mm of
  clearance. The top bar of the ring is built into the front wall of the box.
  The box is 69.5 × 81 mm (0.75 mm wider than the ring on each side); it
  starts at the front plane of the ring and extends backwards.
- **Lid** (`wifinder-mavic4pro-tampa.stl`): fits over the top with a 6 mm
  skirt so rain runs down the outside. It has a window over the OLED screen.

Assembled, the box rises 23 mm above the drone's body. Weight of both parts:
39 to 65 g in PETG, depending on infill.

Other files: `wifinder-mavic4pro.FCStd` and `.step` (edit in FreeCAD),
`montado-so-para-ver.stl` (assembled, for viewing only), `suporte.py`
(generates everything). `previa-no-drone.png` is out of date: it shows the old
59 mm box, made for a 50 × 25.5 mm board.

## Inside the box (64.7 × 73 × 17 mm free)

- **Left side:** ESP32 board standing on its own pins, screen up, against the
  left wall, with the USB port facing backwards. The USB plug goes through a
  hole in the back wall and plugs straight into the board.
- **Right side:** GPS board on the floor (hold it with double-sided tape) and
  the ceramic antenna stuck on top of it, facing up.
- The wires pass through the openings in the divider.
- Stick a piece of foam to the lid, outside the window, so the ESP32 board
  does not rise with vibration.

## Sealing

This protects against rain and splashes; it is not waterproof against
immersion:

- Window: glue a 21 × 34 mm piece of thin acetate or acrylic into the recess
  from the inside (silicone glue or clear double-sided tape).
- USB hole: after connecting the cable, close the gap with silicone or
  caulk. The lid's skirt covers the hole from above.
- Lid: 4 cable ties, one per pair of tabs. For a better seal, run a bead of
  silicone or foam tape along the top of the walls.
- There are two small drain holes in the floor, at the back corners.
- The box extends 81 mm behind the ring, 1 mm above the drone's body
  (`FOLGA_DRONE` in `suporte.py`). I only know that the 23 mm the AirTag box
  used to occupy are free: if the drone's body rises behind that, increase the
  clearance.
- The Mavic 4 Pro itself is not designed to fly in the rain.

## Check before printing

The dimensions are at the top of `suporte.py`. The boards were measured by
hand on 2026-11-12 (ESP32 about 7 × 3 cm, GPS 4 × 3 cm, antenna 3 × 3 cm), so
the box has 1 mm of clearance on each side and 2 mm at the end. The others
came from product listings and a guess, not from measurement:

| Dimension | Value used | How to check |
|---|---|---|
| `ESP_COMP` × `ESP_LARG` | 70 × 30 mm | Length and width of the ESP32 board, roughly measured. Up to 72 × 32 mm fits. |
| `ESP_PINOS` | 8.5 mm | From the pin tips to the underside of the board. Sets the height of the USB hole. |
| `USB_ACIMA` | 1.3 mm | Is the USB connector on the top face of the board? If it is on the bottom face, use −2.9. |
| `JAN_DESLOC` | 0 mm | The window is centred on the board. If the screen sits closer to one end, offset it. |
| `GPS_LARG` | 30 mm | Width of the GPS board and antenna, roughly measured (the bay is 31.5 wide by 73 long). |

To regenerate:

```sh
FreeCAD_1.1.4-Linux-x86_64-py311.AppImage freecadcmd suporte.py
```

## Printing

- Base: the STL is already oriented with the ring lying on the bed, like the
  AirTag mount, and the box standing up. No supports needed; use a brim,
  because the part is 81 mm tall.
- Lid: the STL is already upside down, with the top face on the bed; no
  supports needed.
- PETG or ASA; PLA softens in the sun. 0.2 mm layers, 4 walls (helps
  sealing), 20 to 30 % infill.

## Ready-made G-code (Ender-3 V2, PLA)

Sliced on 2026-11-12 with CuraEngine from Cura 5.14 and the Ender-3 "Standard
Quality" profile, by `fatiar.py` (the settings used are at its top):

| File | Time | Filament | Supports |
|---|---|---|---|
| `wifinder-mavic4pro-base-PLA.gcode` | 6 h 08 | 14.4 m (~43 g) | tree supports, plus an 8 mm brim |
| `wifinder-mavic4pro-tampa-PLA.gcode` | 2 h 29 | 6.3 m (~19 g) | none (no overhangs) |

PLA at 205 °C, bed at 60 °C, 0.2 mm layers, 4 walls, 25 % infill. On the
base, two trees rise from the bed on the open side of the box and hold the
back wall (which is printed as a ceiling, 78 mm up); there are small supports
under the dividers. If you change a dimension in `suporte.py`, the STLs change
and they need to be sliced again.

## Before flying

- **Power:** I have not confirmed that the Mavic 4 Pro's USB-C port powers
  accessories. Test on the bench: drone on, ESP32 on the cable, screen
  lighting up.
- **Drone GPS and compass:** the mount sits on top of the drone. Do a low
  hover and check that satellites and compass stay normal.
- **Weight:** box + boards + cable come to about 90 g on top of the drone.
- Secure the USB cable so it cannot reach the propellers.
