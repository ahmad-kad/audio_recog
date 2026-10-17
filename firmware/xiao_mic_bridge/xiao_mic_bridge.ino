// reSpeaker Flex (XVF3800, I2S firmware) -> XIAO ESP32S3 -> Mac over USB serial.
//
// The board ships with XVF3800 firmware "inthost-lr48-sqr-i2c": processed
// stereo audio, 48 kHz, 32-bit, over I2S. The XVF3800 drives the clocks, so
// the XIAO is the I2S slave (the Seeed wiki example says master; that reads noise).
// This sketch keeps one channel, low-pass filters and decimates it to 16 kHz,
// converts it to 16-bit, and streams it to the host in frames:
// 0xA5 0x5A, then FRAME_SAMPLES little-endian int16 samples.
// The host sends 'S' to start streaming, 'X' to stop, 'L' or 'R' to pick the
// channel (left is the default ASR beam).
//
// 'V' asks for the protocol version: reply 0xA5 0x5D, version (u8). The host
// refuses to run against a different version. Bump PROTOCOL_VERSION whenever
// a frame layout or command changes.
//
// XVF3800 control (I2C 0x2C) is passed through the same link:
//   'Q' resid cmd n          read n bytes  -> reply frame
//   'W' resid cmd n data[n]  write n bytes -> reply frame
// Reply frame: 0xA5 0x5B, n, status, data[n] (data is empty for writes).
//
// While streaming, a direction frame follows every DOA_EVERY audio frames:
// 0xA5 0x5C, doa_deg u16, speech u8, free_deg u16, auto_deg u16, energy f32
// (all little-endian, 0xFFFF for an unknown angle). doa_deg and speech come
// from DOA_VALUE; free_deg and auto_deg are the free-running and auto-select
// beam azimuths; energy is the auto-select beam's speech energy.
#include <Wire.h>
#include <esp_task_wdt.h>
#include "AudioTools.h"

constexpr uint8_t PROTOCOL_VERSION = 3;
constexpr uint32_t WATCHDOG_MS = 3000;  // reboot if loop() stalls, e.g. I2S clocks stop
constexpr uint32_t I2S_RATE = 48000;
constexpr int DECIMATE = 3;           // 48 kHz -> 16 kHz
constexpr int FRAME_SAMPLES = 240;    // 15 ms at 16 kHz
constexpr int TAPS = 63;
constexpr float CUTOFF_HZ = 7000.0f;
constexpr uint8_t MAGIC[2] = {0xA5, 0x5A};
constexpr uint8_t REPLY_MAGIC[2] = {0xA5, 0x5B};
constexpr uint8_t DOA_MAGIC[2] = {0xA5, 0x5C};
constexpr uint8_t VERSION_MAGIC[2] = {0xA5, 0x5D};
constexpr int DOA_EVERY = 4;  // 60 ms
constexpr uint8_t STATUS_RETRY = 64;
constexpr uint8_t XVF_ADDR = 0x2C;
constexpr int MAX_PARAM = 64;

I2SStream bus;
int32_t rx[FRAME_SAMPLES * DECIMATE * 2];
int32_t tx[FRAME_SAMPLES * DECIMATE * 2] = {0};  // silent far-end reference
uint8_t frame[2 + FRAME_SAMPLES * 2];
float taps[TAPS];
float history[TAPS] = {0};
int head = 0;
bool streaming = false;
int channel = 0;
int framesSinceDoa = 0;

// Windowed-sinc low-pass so content above 8 kHz does not alias on decimation.
void designFilter() {
  const float fc = CUTOFF_HZ / I2S_RATE;
  const int mid = TAPS / 2;
  float sum = 0;
  for (int i = 0; i < TAPS; i++) {
    int n = i - mid;
    float sinc = n == 0 ? 2 * fc : sinf(2 * PI * fc * n) / (PI * n);
    float window = 0.54f - 0.46f * cosf(2 * PI * i / (TAPS - 1));
    taps[i] = sinc * window;
    sum += taps[i];
  }
  for (int i = 0; i < TAPS; i++) taps[i] /= sum;
}

float filtered() {
  float acc = 0;
  int idx = head;
  for (int i = 0; i < TAPS; i++) {
    acc += taps[i] * history[idx];
    idx = idx == 0 ? TAPS - 1 : idx - 1;
  }
  return acc;
}

void setup() {
  Serial.setTxBufferSize(8192);  // default 256 bytes is smaller than one frame
  Serial.setTxTimeoutMs(0);      // drop a frame instead of stalling I2S
  Serial.begin(115200);

  Serial.setTimeout(50);
  Wire.begin(5, 6);
  Wire.setClock(400000);
  designFilter();

  auto cfg = bus.defaultConfig(RXTX_MODE);
  cfg.copyFrom(AudioInfo(I2S_RATE, 2, 32));
  cfg.pin_bck = 8;
  cfg.pin_ws = 7;
  cfg.pin_data = 44;     // TX to XVF3800
  cfg.pin_data_rx = 43;  // RX from XVF3800
  cfg.is_master = false;  // XVF3800 is clock master
  bus.begin(cfg);

  frame[0] = MAGIC[0];
  frame[1] = MAGIC[1];

  // The Arduino core usually starts the task watchdog already; adjust it.
  esp_task_wdt_config_t wdt = {
      .timeout_ms = WATCHDOG_MS, .idle_core_mask = 0, .trigger_panic = true};
  if (esp_task_wdt_reconfigure(&wdt) != ESP_OK) esp_task_wdt_init(&wdt);
  esp_task_wdt_add(NULL);
}

void sendReply(uint8_t status, const uint8_t* data, uint8_t n) {
  uint8_t head[4] = {REPLY_MAGIC[0], REPLY_MAGIC[1], n, status};
  Serial.write(head, sizeof(head));
  if (n) Serial.write(data, n);
}

// Returns the XVF3800 status byte (0 ok, 64 retry) or 0xFF on a bus error.
uint8_t xvfReadOnce(uint8_t resid, uint8_t cmd, uint8_t n, uint8_t* data) {
  Wire.beginTransmission(XVF_ADDR);
  Wire.write(resid);
  Wire.write(cmd | 0x80);
  Wire.write(n + 1);
  if (n > MAX_PARAM || Wire.endTransmission(false) != 0 ||
      Wire.requestFrom(XVF_ADDR, (uint8_t)(n + 1)) != n + 1) {
    return 0xFF;
  }
  uint8_t status = Wire.read();
  for (int i = 0; i < n; i++) data[i] = Wire.read();
  return status;
}

uint8_t xvfReadInto(uint8_t resid, uint8_t cmd, uint8_t n, uint8_t* data) {
  uint8_t status = 0xFF;
  for (int attempt = 0; attempt < 4; attempt++) {
    status = xvfReadOnce(resid, cmd, n, data);
    if (status != STATUS_RETRY) break;
    delayMicroseconds(300);
  }
  return status;
}

void xvfRead(uint8_t resid, uint8_t cmd, uint8_t n) {
  uint8_t data[MAX_PARAM] = {0};
  uint8_t status = xvfReadInto(resid, cmd, n, data);
  sendReply(status, data, n);
}

uint16_t toDegrees(float radians) {
  if (radians != radians) return 0xFFFF;  // NaN: beam has no direction yet
  float deg = radians * 180.0f / PI;
  while (deg < 0) deg += 360.0f;
  return (uint16_t)deg % 360;
}

void sendDirection() {
  uint8_t doa[4] = {0xFF, 0xFF, 0, 0};
  float az[4] = {NAN, NAN, NAN, NAN};
  float energy[4] = {0, 0, 0, 0};
  bool haveDoa = xvfReadInto(20, 18, sizeof(doa), doa) == 0;                // DOA_VALUE
  bool haveAz = xvfReadInto(33, 75, sizeof(az), (uint8_t*)az) == 0;        // AEC_AZIMUTH_VALUES
  bool haveEnergy = xvfReadInto(33, 80, sizeof(energy), (uint8_t*)energy) == 0;  // AEC_SPENERGY_VALUES
  if (!haveDoa && !haveAz) return;
  if (!haveAz) az[2] = az[3] = NAN;
  if (!haveEnergy) energy[3] = 0;

  uint16_t freeDeg = toDegrees(az[2]);
  uint16_t autoDeg = toDegrees(az[3]);
  uint8_t out[13] = {DOA_MAGIC[0], DOA_MAGIC[1], doa[0], doa[1], doa[2],
                     (uint8_t)(freeDeg & 0xFF), (uint8_t)(freeDeg >> 8),
                     (uint8_t)(autoDeg & 0xFF), (uint8_t)(autoDeg >> 8)};
  memcpy(out + 9, &energy[3], 4);
  if (Serial.availableForWrite() >= (int)sizeof(out)) Serial.write(out, sizeof(out));
}

void xvfWrite(uint8_t resid, uint8_t cmd, uint8_t n, const uint8_t* data) {
  Wire.beginTransmission(XVF_ADDR);
  Wire.write(resid);
  Wire.write(cmd);
  Wire.write(n);
  Wire.write(data, n);
  sendReply(Wire.endTransmission() == 0 ? 0 : 0xFF, nullptr, 0);
}

void handleCommands() {
  while (Serial.available()) {
    uint8_t hdr[3];
    uint8_t data[MAX_PARAM];
    switch (Serial.read()) {
      case 'S': streaming = true; break;
      case 'X': streaming = false; break;
      case 'L': channel = 0; break;
      case 'R': channel = 1; break;
      case 'V': {
        uint8_t out[3] = {VERSION_MAGIC[0], VERSION_MAGIC[1], PROTOCOL_VERSION};
        Serial.write(out, sizeof(out));
        break;
      }
      case 'Q':
        if (Serial.readBytes(hdr, 3) == 3) xvfRead(hdr[0], hdr[1], hdr[2]);
        break;
      case 'W':
        if (Serial.readBytes(hdr, 3) == 3 && hdr[2] <= MAX_PARAM &&
            Serial.readBytes(data, hdr[2]) == hdr[2]) {
          xvfWrite(hdr[0], hdr[1], hdr[2], data);
        }
        break;
    }
  }
}

void loop() {
  esp_task_wdt_reset();
  handleCommands();

  bus.write((uint8_t*)tx, sizeof(tx));
  size_t got = bus.readBytes((uint8_t*)rx, sizeof(rx));
  if (got != sizeof(rx)) return;

  for (int i = 0; i < FRAME_SAMPLES; i++) {
    for (int k = 0; k < DECIMATE; k++) {
      head = (head + 1) % TAPS;
      history[head] = rx[(i * DECIMATE + k) * 2 + channel] / 2147483648.0f;
    }
    float y = filtered() * 32767.0f;
    int16_t s = y > 32767 ? 32767 : y < -32768 ? -32768 : (int16_t)y;
    frame[2 + i * 2] = s & 0xFF;
    frame[3 + i * 2] = (s >> 8) & 0xFF;
  }
  if (!streaming) return;
  if (Serial.availableForWrite() >= (int)sizeof(frame)) {
    Serial.write(frame, sizeof(frame));
  }
  if (++framesSinceDoa >= DOA_EVERY) {
    framesSinceDoa = 0;
    sendDirection();
  }
}
