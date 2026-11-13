// Telinha OLED I2C (SSD1306/SH1106, endereço 0x3C) com detecção automática dos
// pinos. Tenta as combinações mais comuns das placas "ESP32 com OLED".
#pragma once

#include <U8g2lib.h>
#include <Wire.h>

#include "config.h"

struct OledPins {
  int sda, scl, rst;
  const char *name;
};

static const OledPins OLED_CANDIDATES[] = {
    {21, 22, -1, "SDA21/SCL22"},     // ESP32 DevKit + OLED nos pinos I2C padrão
    {5, 4, -1, "SDA5/SCL4"},         // placas "ESP32 WROOM-32 OLED 0.96" genéricas
    {4, 15, 16, "Heltec SDA4/SCL15"},// Heltec WiFi Kit 32 (reset no GPIO16)
    {4, 5, -1, "SDA4/SCL5"},
};

class Oled {
 public:
  // Procura a tela. Retorna true se achou; pins() diz onde.
  bool begin() {
    for (const OledPins &p : OLED_CANDIDATES) {
      if (p.rst >= 0) {
        pinMode(p.rst, OUTPUT);
        digitalWrite(p.rst, LOW);
        delay(20);
        digitalWrite(p.rst, HIGH);
        delay(50);
      }
      Wire.begin(p.sda, p.scl);
      Wire.beginTransmission(0x3C);
      bool found = Wire.endTransmission() == 0;
      Wire.end();
      if (!found) continue;
      pins_ = &p;
#ifdef OLED_SH1106
      u_ = new U8G2_SH1106_128X64_NONAME_F_HW_I2C(U8G2_R0, p.rst >= 0 ? p.rst : U8X8_PIN_NONE, p.scl, p.sda);
#else
      u_ = new U8G2_SSD1306_128X64_NONAME_F_HW_I2C(U8G2_R0, p.rst >= 0 ? p.rst : U8X8_PIN_NONE, p.scl, p.sda);
#endif
      u_->setBusClock(400000);  // I2C rápido: a tela atualiza em ~25 ms
      u_->begin();
      u_->setFont(u8g2_font_6x12_tf);  // 21 colunas x 5 linhas
      return true;
    }
    return false;
  }

  bool ok() const { return u_ != nullptr; }
  const char *pins() const { return pins_ ? pins_->name : "nenhum"; }
  int resetPin() const { return pins_ ? pins_->rst : -1; }

  // Mostra até 5 linhas de texto (21 caracteres cada).
  void show(const char *l1, const char *l2, const char *l3, const char *l4, const char *l5) {
    if (!u_) return;
    u_->clearBuffer();
    const char *lines[] = {l1, l2, l3, l4, l5};
    for (int i = 0; i < 5; i++) u_->drawStr(0, 10 + 12 * i, lines[i]);
    u_->sendBuffer();
  }

  // Tela de abertura (novo boot = nova missão).
  void showSplash(const char *mission) {
    if (!u_) return;
    u_->clearBuffer();
    u_->setFont(u8g2_font_10x20_tf);
    u_->drawStr(14, 24, "WiFinder");
    u_->setFont(u8g2_font_6x12_tf);
    u_->drawStr(0, 44, "Nova missao:");
    u_->drawStr(78, 44, mission);
    u_->drawStr(0, 60, "iniciando GPS e WiFi");
    u_->sendBuffer();
  }

  // PC conectado: bolinhas girando.
  void showPc(uint32_t frame, int files, uint32_t kb) {
    if (!u_) return;
    u_->clearBuffer();
    u_->drawStr(0, 10, "PC conectado");
    spinner(104, 14, frame);
    char b[24];
    snprintf(b, sizeof b, "%d arquivo%s, %luKB", files, files == 1 ? "" : "s", (unsigned long)kb);
    u_->drawStr(0, 36, b);
    u_->drawStr(0, 60, "aguardando comandos");
    u_->sendBuffer();
  }

  // Transferindo um arquivo: barra de progresso.
  void showProgress(const char *name, size_t sent, size_t total, uint32_t frame) {
    if (!u_) return;
    u_->clearBuffer();
    u_->drawStr(0, 10, "Transferindo");
    spinner(104, 14, frame);
    u_->drawStr(0, 26, name);
    int pct = total ? (int)(100ULL * sent / total) : 100;
    u_->drawFrame(0, 32, 128, 12);
    u_->drawBox(2, 34, (124 * pct) / 100, 8);
    char b[24];
    snprintf(b, sizeof b, "%3d%%  %lu/%luKB", pct, (unsigned long)(sent / 1024), (unsigned long)(total / 1024));
    u_->drawStr(0, 60, b);
    u_->sendBuffer();
  }

  // Fim da transferência: check que vai sendo desenhado.
  void showDone(int files, uint32_t frame) {
    if (!u_) return;
    u_->clearBuffer();
    int steps = frame > 12 ? 12 : frame;
    // Check: de (20,32) a (32,46) e de (32,46) a (56,16), em 12 passos.
    for (int k = 0; k < steps; k++) {
      int x0, y0, x1, y1;
      if (k < 4) { x0 = 20 + 3 * k; y0 = 32 + 3 * k + 2; x1 = x0 + 3; y1 = y0 + 3; }
      else { x0 = 32 + 3 * (k - 4); y0 = 46 - 4 * (k - 4); x1 = x0 + 3; y1 = y0 - 4; }
      for (int w = -1; w <= 1; w++) u_->drawLine(x0, y0 + w, x1, y1 + w);
    }
    u_->drawStr(66, 28, "Pronto!");
    char b[24];
    snprintf(b, sizeof b, "%d arquivo%s", files, files == 1 ? "" : "s");
    u_->drawStr(66, 44, b);
    u_->drawStr(0, 62, "pode desconectar");
    u_->sendBuffer();
  }

  // Segurando BOOT: contagem para apagar.
  void showErase(int msLeft) {
    if (!u_) return;
    u_->clearBuffer();
    u_->setFont(u8g2_font_10x20_tf);
    u_->drawStr(4, 20, "APAGAR TUDO?");
    u_->setFont(u8g2_font_6x12_tf);
    u_->drawStr(0, 36, "solte para cancelar");
    u_->drawFrame(0, 44, 128, 12);
    int w = 124 - (124 * msLeft) / 3000;
    u_->drawBox(2, 46, w < 0 ? 0 : w, 8);
    u_->sendBuffer();
  }

  void showMessage(const char *l1, const char *l2) {
    if (!u_) return;
    u_->clearBuffer();
    u_->setFont(u8g2_font_10x20_tf);
    u_->drawStr(0, 24, l1);
    u_->setFont(u8g2_font_6x12_tf);
    u_->drawStr(0, 48, l2);
    u_->sendBuffer();
  }

 private:
  void spinner(int cx, int cy, uint32_t frame) {
    for (int i = 0; i < 8; i++) {
      float a = i * 0.7854f;
      int x = cx + (int)(8 * cosf(a)), y = cy + (int)(8 * sinf(a));
      int r = ((int)(frame % 8) == i) ? 2 : (((int)((frame + 7) % 8) == i) ? 1 : 0);
      if (r) u_->drawDisc(x, y, r); else u_->drawPixel(x, y);
    }
  }

  U8G2 *u_ = nullptr;
  const OledPins *pins_ = nullptr;
};
