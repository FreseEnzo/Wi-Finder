// WiFinder - coleta embarcada no ESP32: GPS NEO-6M + varredura WiFi, gravado
// na flash (LittleFS). Depois do voo, `python3 -m wifinder pull voo.db` baixa
// os logs pela USB e monta o banco usado pela estimativa.
//
// Formato do log (texto, um registro por linha):
//   F <millis> <unix_t> <lat> <lon> <alt_m> <sats> <hdop>      fix do GPS (1 Hz)
//   S <millis> <bssid> <canal> <rssi_dBm> <ssid_hex>           rede ouvida
// As posições das redes são interpoladas no computador a partir dos fixes.
//
// Comandos pela serial USB (115200): help, ls, dump <arq>, rm <arq>, rmall,
// pause, resume, info.

#include <LittleFS.h>
#include <Preferences.h>
#include <TinyGPSPlus.h>
#include <WiFi.h>

#include "config.h"
#include "oled.h"

static TinyGPSPlus gps;
static HardwareSerial &gpsSerial = Serial2;
static Oled oled;
static File logFile;
static String logName;
static int gpsRx = GPS_RX_PIN, gpsTx = GPS_TX_PIN;

struct State {
  bool fix = false;
  int sats = 0;
  float hdop = 0;
  double lat = 0, lon = 0, alt = 0;
  uint32_t utc = 0;              // último fix, segundos Unix
  uint32_t lastFixTimeValue = 0;  // hhmmsscc do último fix gravado (evita duplicar)
  uint32_t gpsBytes = 0, lastGpsByteMs = 0, lastFixMs = 0;
  uint32_t fixes = 0, saved = 0, apsLastSweep = 0, apsThisSweep = 0, sweeps = 0;
  int channel = 1;
  bool scanning = false;
  uint32_t scanStartMs = 0;
  bool paused = false, full = false, dirty = false;
  // Interface: PC conectado / transferência / apagar.
  uint32_t lastCmdMs = 0, doneMs = 0, erasedMs = 0, pressStartMs = 0;
  int doneFiles = 0;
  bool waitRelease = false;
} st;

#define BOOT_BUTTON 0
#define PC_TIMEOUT_MS 15000

// ---------------------------------------------------------------- utilidades

static uint32_t toEpoch(int y, int m, int d, int hh, int mm, int ss) {
  // "days from civil", Howard Hinnant.
  y -= m <= 2;
  int era = (y >= 0 ? y : y - 399) / 400;
  unsigned yoe = y - era * 400;
  unsigned doy = (153 * (m + (m > 2 ? -3 : 9)) + 2) / 5 + d - 1;
  unsigned doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
  int64_t days = (int64_t)era * 146097 + (int64_t)doe - 719468;
  return (uint32_t)(days * 86400 + hh * 3600 + mm * 60 + ss);
}

static String toHex(const String &s) {
  static const char *H = "0123456789abcdef";
  String out;
  out.reserve(s.length() * 2);
  for (size_t i = 0; i < s.length(); i++) {
    uint8_t b = (uint8_t)s[i];
    out += H[b >> 4];
    out += H[b & 15];
  }
  return out;
}

static size_t fsFree() {
  return LittleFS.totalBytes() > LittleFS.usedBytes() ? LittleFS.totalBytes() - LittleFS.usedBytes() : 0;
}

// --------------------------------------------------------------------- flash

static bool openLog() {
  if (logFile) return true;
  logFile = LittleFS.open(logName, "a");
  if (!logFile) {
    Serial.printf("# erro: nao consegui abrir %s\n", logName.c_str());
    return false;
  }
  logFile.printf("# wifinder esp32 %s\n", logName.c_str());
  return true;
}

static void writeLine(const String &line) {
  if (st.full) return;
  if (fsFree() < FS_MIN_FREE) {
    st.full = true;
    Serial.println("# flash CHEIA: parei de gravar. Baixe e apague os logs (rmall).");
    return;
  }
  if (!openLog()) return;
  logFile.println(line);
  st.dirty = true;
}

static void flushLog() {
  if (logFile && st.dirty) {
    logFile.flush();
    st.dirty = false;
  }
}

// ----------------------------------------------------------------------- GPS

static void onGpsSentence() {
  if (gps.satellites.isUpdated()) st.sats = gps.satellites.value();
  if (gps.hdop.isUpdated()) st.hdop = gps.hdop.hdop();
  // Só o GGA traz altitude; é nele que gravamos o fix (uma vez por segundo).
  if (!gps.altitude.isUpdated()) return;
  double alt = gps.altitude.meters();
  if (!gps.location.isValid() || !gps.date.isValid() || !gps.time.isValid()) {
    st.fix = false;
    return;
  }
  uint32_t tv = gps.time.value();
  if (tv == st.lastFixTimeValue) return;
  st.lastFixTimeValue = tv;

  uint32_t ms = millis();
  st.fix = true;
  st.lastFixMs = ms;
  st.lat = gps.location.lat();
  st.lon = gps.location.lng();
  st.alt = alt;
  st.utc = toEpoch(gps.date.year(), gps.date.month(), gps.date.day(),
                   gps.time.hour(), gps.time.minute(), gps.time.second());
  double t = st.utc + gps.time.centisecond() / 100.0;
  st.fixes++;

  char buf[128];
  snprintf(buf, sizeof buf, "F %lu %.2f %.7f %.7f %.1f %d %.2f",
           (unsigned long)ms, t, st.lat, st.lon, st.alt, st.sats, st.hdop);
  writeLine(buf);
}

static void feedGps() {
  while (gpsSerial.available()) {
    char c = gpsSerial.read();
    st.gpsBytes++;
    st.lastGpsByteMs = millis();
    if (gps.encode(c)) onGpsSentence();
  }
  if (st.fix && millis() - st.lastFixMs > 3000) st.fix = false;
}

// ---------------------------------------------------------------------- WiFi

static void startScan() {
  st.scanStartMs = millis();
  int16_t r = WiFi.scanNetworks(true, true, false, SCAN_MS_PER_CHANNEL, st.channel);
  st.scanning = r == WIFI_SCAN_RUNNING;
}

static void pollScan() {
  if (st.paused) return;
  if (!st.scanning) {
    startScan();
    return;
  }
  int16_t n = WiFi.scanComplete();
  if (n == WIFI_SCAN_RUNNING) return;
  st.scanning = false;
  if (n < 0) {  // falhou: tenta de novo o mesmo canal
    WiFi.scanDelete();
    return;
  }
  // Instante médio da escuta neste canal.
  uint32_t mid = st.scanStartMs + (millis() - st.scanStartMs) / 2;
  for (int i = 0; i < n; i++) {
    String line = "S " + String(mid) + " " + WiFi.BSSIDstr(i) + " " + String(WiFi.channel(i)) +
                  " " + String(WiFi.RSSI(i)) + " " + toHex(WiFi.SSID(i));
    writeLine(line);
    st.saved++;
  }
  st.apsThisSweep += n;
  WiFi.scanDelete();

  if (++st.channel > SCAN_CHANNELS) {
    st.channel = 1;
    st.apsLastSweep = st.apsThisSweep;
    st.apsThisSweep = 0;
    st.sweeps++;
    flushLog();
  }
}

// ------------------------------------------------------------------- display

static void updateDisplay() {
  static uint32_t frame = 0;
  uint32_t now = millis();
  frame++;
  if (st.pressStartMs && now - st.pressStartMs > 300) {
    oled.showErase(3000 - (int)(now - st.pressStartMs));
    return;
  }
  if (st.erasedMs && now - st.erasedMs < 2500) {
    oled.showMessage("Apagado", "logs removidos, missao nova");
    return;
  }
  if (st.doneMs && now - st.doneMs < 4000) {
    oled.showDone(st.doneFiles, (now - st.doneMs) / 80);
    return;
  }
  if (st.lastCmdMs && now - st.lastCmdMs < PC_TIMEOUT_MS) {
    int files; uint32_t kb;
    countLogs(files, kb);
    oled.showPc(frame, files, kb);
    return;
  }
  char l1[24], l2[24], l3[24], l4[24], l5[24];
  const char *flag = st.full ? "CHEIO" : st.paused ? "PAUSA" : "";
  snprintf(l1, sizeof l1, "WiFinder %-7s%5s", logName.c_str() + 1, flag);
  if (st.gpsBytes == 0 || now - st.lastGpsByteMs > 5000) {
    snprintf(l2, sizeof l2, "GPS SEM DADOS");
    snprintf(l3, sizeof l3, "TX do GPS -> GPIO%d", gpsRx);
  } else if (gps.passedChecksum() == 0) {
    snprintf(l2, sizeof l2, "GPS lixo na serial");
    snprintf(l3, sizeof l3, "baud? %lu bytes", (unsigned long)st.gpsBytes);
  } else if (!st.fix) {
    snprintf(l2, sizeof l2, "GPS SEM FIX  %2d sat", st.sats);
    snprintf(l3, sizeof l3, "esperando satelites");
  } else {
    snprintf(l2, sizeof l2, "GPS %2d sat  hdop %.1f", st.sats, st.hdop);
    uint32_t s = st.utc % 86400;
    snprintf(l3, sizeof l3, "%02lu:%02lu:%02luZ  alt %.0fm", (unsigned long)s / 3600,
             (unsigned long)(s / 60) % 60, (unsigned long)s % 60, st.alt);
  }
  snprintf(l4, sizeof l4, "APs %-4lu  canal %2d", (unsigned long)st.apsLastSweep, st.channel);
  snprintf(l5, sizeof l5, "Grav %-7lu %4luKB", (unsigned long)st.saved,
           (unsigned long)(fsFree() / 1024));
  oled.show(l1, l2, l3, l4, l5);
}

static void printStatus() {
  Serial.printf("# gps=%s sats=%d hdop=%.1f lat=%.6f lon=%.6f alt=%.1f fixes=%lu "
                "gpsbytes=%lu nmea=%lu aps=%lu saved=%lu sweeps=%lu file=%s livre=%luKB%s%s\n",
                st.fix ? "fix" : (st.gpsBytes && millis() - st.lastGpsByteMs < 5000 ? "semfix" : "semdados"),
                st.sats, st.hdop,
                st.lat, st.lon, st.alt, (unsigned long)st.fixes, (unsigned long)st.gpsBytes,
                (unsigned long)gps.passedChecksum(), (unsigned long)st.apsLastSweep,
                (unsigned long)st.saved, (unsigned long)st.sweeps, logName.c_str(),
                (unsigned long)(fsFree() / 1024), st.paused ? " PAUSA" : "", st.full ? " CHEIO" : "");
}

// ------------------------------------------------------------ comandos (USB)

static void cmdLs() {
  Serial.println("--- LS ---");
  File root = LittleFS.open("/");
  for (File f = root.openNextFile(); f; f = root.openNextFile()) {
    if (!f.isDirectory()) Serial.printf("%s %u\n", f.name(), (unsigned)f.size());
  }
  Serial.println("--- END LS ---");
}

static void countLogs(int &files, uint32_t &kb) {
  files = 0;
  uint32_t bytes = 0;
  File root = LittleFS.open("/");
  for (File f = root.openNextFile(); f; f = root.openNextFile()) {
    if (!f.isDirectory()) { files++; bytes += f.size(); }
  }
  kb = bytes / 1024;
}

static String fullPath(const String &name) { return name.startsWith("/") ? name : "/" + name; }

static void cmdDump(const String &name) {
  flushLog();
  File f = LittleFS.open(fullPath(name), "r");
  if (!f) {
    Serial.println("err: arquivo nao existe");
    return;
  }
  // O arquivo atual continua crescendo durante o dump: manda só o tamanho anunciado.
  size_t total = f.size(), left = total;
  Serial.printf("--- BEGIN %s %u ---\n", name.c_str(), (unsigned)total);
  uint8_t buf[512];
  uint32_t lastDraw = 0, frame = 0;
  oled.showProgress(name.c_str(), 0, total, frame);
  while (left) {
    size_t n = f.read(buf, left < sizeof buf ? left : sizeof buf);
    if (!n) break;
    Serial.write(buf, n);
    left -= n;
    if (millis() - lastDraw > 150) {
      lastDraw = millis();
      oled.showProgress(name.c_str(), total - left, total, frame++);
    }
  }
  f.close();
  oled.showProgress(name.c_str(), total, total, frame);
  Serial.printf("--- END %s ---\n", name.c_str());
}

static void cmdRm(const String &name) {
  String path = fullPath(name);
  if (path == logName && logFile) logFile.close();
  bool ok = LittleFS.remove(path);
  if (path == logName) st.full = false;  // o arquivo atual reabre vazio na proxima gravacao
  Serial.println(ok ? "ok" : "err: nao apagou");
}

static void cmdRmAll() {
  if (logFile) logFile.close();
  int n = 0;
  File root = LittleFS.open("/");
  std::vector<String> names;
  for (File f = root.openNextFile(); f; f = root.openNextFile()) {
    if (!f.isDirectory()) names.push_back(fullPath(f.name()));
  }
  root.close();
  for (auto &p : names) n += LittleFS.remove(p);
  st.full = false;
  Serial.printf("ok: %d apagados\n", n);
}

static void handleCommand(String line) {
  line.trim();
  if (!line.length()) return;
  st.lastCmdMs = millis();
  int sp = line.indexOf(' ');
  String cmd = sp < 0 ? line : line.substring(0, sp);
  String arg = sp < 0 ? "" : line.substring(sp + 1);
  arg.trim();
  if (cmd == "ls") cmdLs();
  else if (cmd == "dump") cmdDump(arg);
  else if (cmd == "rm") cmdRm(arg);
  else if (cmd == "rmall") cmdRmAll();
  else if (cmd == "done") { st.doneMs = millis(); st.doneFiles = arg.toInt(); Serial.println("ok"); }
  else if (cmd == "pause") { st.paused = true; Serial.println("ok"); }
  else if (cmd == "resume") { st.paused = false; Serial.println("ok"); }
  else if (cmd == "info") {
    Serial.printf("ok: versao=" WIFINDER_VERSION " tela=%s gps_rx=%d gps_tx=%d flash_total=%luKB flash_livre=%luKB arquivo=%s\n",
                  oled.pins(), gpsRx, gpsTx, (unsigned long)(LittleFS.totalBytes() / 1024),
                  (unsigned long)(fsFree() / 1024), logName.c_str());
  } else if (cmd == "help") {
    Serial.println("ok: ls | dump <arq> | rm <arq> | rmall | done <n> | pause | resume | info");
  } else Serial.println("err: comando desconhecido (help)");
}

static void handleSerial() {
  static String buf;
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n' || c == '\r') {
      handleCommand(buf);
      buf = "";
    } else if (buf.length() < 80) {
      buf += c;
    }
  }
}

// ------------------------------------------------------------- botão BOOT

// Segurar BOOT por 3 s apaga todos os logs (depois de baixar pelo PC).
static void handleButton() {
  bool pressed = digitalRead(BOOT_BUTTON) == LOW;
  if (!pressed) {
    st.pressStartMs = 0;
    st.waitRelease = false;
    return;
  }
  if (st.waitRelease) return;
  if (!st.pressStartMs) st.pressStartMs = millis();
  if (millis() - st.pressStartMs >= 3000) {
    cmdRmAll();
    st.saved = 0;
    st.erasedMs = millis();
    st.waitRelease = true;
  }
}

// ---------------------------------------------------------------------- main

void setup() {
  Serial.begin(USB_BAUD);
  delay(200);
  Serial.println("\n# WiFinder ESP32 " WIFINDER_VERSION);

  pinMode(BOOT_BUTTON, INPUT_PULLUP);
  if (oled.begin()) {
    Serial.printf("# tela OLED em %s\n", oled.pins());
  } else {
    Serial.println("# tela OLED nao encontrada (seguindo sem tela)");
  }
  if (oled.resetPin() == GPS_RX_PIN || oled.resetPin() == GPS_TX_PIN) {
    gpsRx = GPS_RX_PIN_ALT;
    gpsTx = GPS_TX_PIN_ALT;
  }
  Serial.printf("# GPS: TX do modulo -> GPIO%d (RX), RX do modulo -> GPIO%d (TX), %d baud\n",
                gpsRx, gpsTx, GPS_BAUD);
  gpsSerial.setRxBufferSize(2048);
  gpsSerial.begin(GPS_BAUD, SERIAL_8N1, gpsRx, gpsTx);
  // Com o GPS desligado o pino ficaria flutuando e leria ruído.
  gpio_pullup_en((gpio_num_t)gpsRx);

  if (!LittleFS.begin(true)) {
    Serial.println("# erro: LittleFS nao montou");
    oled.show("WiFinder", "ERRO: flash", "", "", "");
  }
  Preferences prefs;
  prefs.begin("wifinder", false);
  uint32_t boot = prefs.getUInt("boot", 0) + 1;
  prefs.putUInt("boot", boot);
  prefs.end();
  char name[16];
  snprintf(name, sizeof name, "/v%03lu.log", (unsigned long)boot);
  logName = name;  // criado na primeira gravação, para não deixar arquivos vazios
  Serial.printf("# log: %s, flash livre %luKB\n", name, (unsigned long)(fsFree() / 1024));
  oled.showSplash(name + 1);
  delay(1500);

  WiFi.mode(WIFI_STA);
  WiFi.disconnect();
  delay(100);
  Serial.println("# pronto. Comandos: help");
}

void loop() {
  static uint32_t lastDisplay = 0, lastStatus = 0;
  feedGps();
  pollScan();
  handleSerial();
  handleButton();
  uint32_t now = millis();
  // Animações a 8 fps; coleta normal a 2 fps.
  bool animating = st.pressStartMs || st.doneMs || st.erasedMs || (st.lastCmdMs && now - st.lastCmdMs < PC_TIMEOUT_MS);
  if (now - lastDisplay >= (animating ? 125u : 500u)) {
    lastDisplay = now;
    updateDisplay();
  }
  if (now - lastStatus >= 2000) {
    lastStatus = now;
    printStatus();
    flushLog();
  }
}
