# reSpeaker Flex microphone

Hardware: reSpeaker Flex XVF3800 Circular-4 with XIAO ESP32S3 (SKU -C4-1). Four microphones on a 44 mm circle, 360° pickup.

The XVF3800 does the audio work: beamforming, noise suppression, gain control, echo cancellation, and direction of arrival. The XIAO reads its output and forwards it to the computer (the Mac, or the rover's Linux computer) over USB serial. The XVF3800 firmware is not reflashed.

```text
4 mics -> XVF3800 --I2S 48 kHz--> XIAO ESP32S3 --USB serial 16 kHz--> Mac (rover_voice)
                  <--I2C 0x2C---  (direction, speech energy, settings)
```

## Connections

- Plug the USB-C data cable into the **XIAO's own port**. The core board's side USB-C port only supplies power. The Mac sees nothing on it.
- The XIAO shows up as `/dev/cu.usbmodem*` on a Mac and `/dev/ttyACM*` on Linux, Espressif USB VID `0x303a`. On Linux the user must be in the `dialout` group to open it.
- The mic array connects to the core board with the 24-pin FPC cable that comes in the box.

## What the board ships with

Read over I2C from the XVF3800:

| Field | Value |
|---|---|
| `VERSION` | 1.0.0 |
| `BLD_MSG` | `inthost-lr48-sqr-i2c` |

That build means I2S, 48 kHz, stereo, 32-bit, and the **XVF3800 is the I2S clock master**. The XIAO must be the slave.

Seeed's wiki example sets 16 kHz and `is_master = true`. On this board that setup reads random bits. Seeed's "I2S RX PASS" test still passes, because it only counts non-zero samples.

## XIAO pins

| Signal | XIAO GPIO |
|---|---|
| I2S BCLK | 8 |
| I2S WS (LRCLK) | 7 |
| I2S data to XVF3800 | 44 |
| I2S data from XVF3800 | 43 |
| I2C SDA | 5 |
| I2C SCL | 6 |

Two devices answer on I2C: `0x2C` is the XVF3800 and `0x18` is the AIC3104 audio codec.

## Bridge firmware

`firmware/xiao_mic_bridge/xiao_mic_bridge.ino` does the following:

- Reads the left I2S channel at 48 kHz. Left is the processed beam used for speech recognition.
- Low-pass filters it at 7 kHz (63-tap windowed sinc), keeps every third sample to get 16 kHz, and converts it to 16-bit.
- Sends 15 ms frames, plus a direction frame every 60 ms.
- Sends silence to the XVF3800 as the far-end echo reference. Echo cancellation is unused for now.
- Reports a protocol version. The app refuses to stream from a bridge with a different version, and says to run `scripts/flash_bridge`.
- Has a 3 s watchdog. If `loop()` stalls (for example, the XVF3800 stops the I2S clocks), the XIAO reboots.

The app recovers on its side too. If the USB link drops, it reopens the port and checks the version again. If the port stays open but audio stops for 2 s, it asks the bridge to stream again. Both are logged to stderr.

Setup and upload:

```bash
scripts/setup_firmware.sh   # arduino-cli, esp32 core 3.3.12, audio-tools v1.2.6
scripts/flash_bridge        # finds /dev/cu.usbmodem* or /dev/ttyACM*, or pass the port
scripts/run --check-array   # real-time audio, sane level, direction frames
```

If the upload cannot connect, hold the XIAO's **B** button while plugging it in, then run `scripts/flash_bridge` again. This is needed after the board is moved or bumped mid-upload.

## Serial protocol

The port runs at 115200 baud, though USB CDC ignores the rate. All values are little-endian.

The host sends single bytes to control the bridge:

| Byte | Effect |
|---|---|
| `S` | start streaming |
| `X` | stop streaming |
| `L` / `R` | choose the left (default) or right I2S channel |
| `V` | report the protocol version |
| `Q` resid cmd n | read n bytes of an XVF3800 parameter |
| `W` resid cmd n data | write n bytes to an XVF3800 parameter |

The bridge sends three kinds of frame:

| Header | Body |
|---|---|
| `A5 5A` | 240 × int16 audio samples (15 ms at 16 kHz) |
| `A5 5B` | n, status, n data bytes (reply to `Q` or `W`) |
| `A5 5C` | DOA u16, speech u8, free beam u16, auto beam u16, auto beam speech energy f32 |
| `A5 5D` | protocol version u8 (currently 3) |

A beam angle of `0xFFFF` means unknown, which happens when the XVF3800 reports NaN. In a reply, status `0` means OK and `64` means busy, try again. The bridge retries direction reads itself. `0xFF` means an I2C bus error. `src/rover_voice/audio/serial_capture.py` is the host side.

Change a frame or command on both sides together. Bump `PROTOCOL_VERSION` in the firmware and in `serial_capture.py` at the same time, so a mismatched pair fails loudly instead of misreading data.

## XVF3800 parameters in use

| Name | resid, cmd | Bytes | Use |
|---|---|---|---|
| `VERSION` | 48, 0 | 3 | firmware version |
| `BLD_MSG` | 48, 1 | 50 | build name |
| `DOA_VALUE` | 20, 18 | 4 | angle 0 to 359, speech flag |
| `AEC_AZIMUTH_VALUES` | 33, 75 | 16 | 4 floats in radians: beam 1, beam 2, free-running, auto-select |
| `AEC_SPENERGY_VALUES` | 33, 80 | 16 | speech energy per beam, the same 4 beams |

The full list is in Seeed's `python_control/xvf_host.py`, in https://github.com/respeaker/reSpeaker_Flex. To read a parameter, write `resid, cmd | 0x80, n + 1`, then read `n + 1` bytes with a repeated start. The first byte read is the status.

## Direction and speech

These were measured on the bench with speech played from the Mac speakers:

- The auto-select beam's speech energy rises within the same 60 ms window as the app's loudness gate, and falls about 0.1 s after speech ends. It gates commands without adding delay.
- Between words, the auto-select beam points at the loudest noise source (a fan, for example). The app only uses beam angles while speech energy is above zero.
- `DOA_VALUE` is smoothed. It lags a second or more and keeps its speech flag about 1 s after speech ends. It is only the fallback.
- The XVF3800's noise suppression removes chimes and white-noise bursts before the audio reaches the app.

## LEDs

The Flex has no RGB LEDs, only the green power LED on the core board. The `LED_*` commands in Seeed's tool are meant for the reSpeaker XVF3800 USB 4-Mic Array. Here a write is acknowledged but reads back `0`. Direction is shown in the terminal instead. A NeoPixel ring on a spare XIAO pin could show it later.

## Not used yet

- **Echo cancellation.** This needs the rover's voice sent through the XIAO to the board's audio output, so the XVF3800 has a reference.
- **The right I2S channel**, which carries a second processed output.
- **Saving tuning to flash** (`SAVE_CONFIGURATION`).
- **XVF3800 firmware 1.0.4.** It restores fixed-beam settings after startup. Updating means reflashing the XVF3800, which this project avoids. Safe Mode can always recover the board.
