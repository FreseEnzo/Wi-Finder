// Ajustes do firmware WiFinder para ESP32.
#pragma once

#define WIFINDER_VERSION "1.6.0"

// GPS NEO-6M na UART2. O TX do GPS vai no RX do ESP32; o RX do GPS no TX do ESP32
// (o TX só é usado se um dia quisermos configurar o módulo).
// Se a telinha for Heltec (OLED com reset no GPIO16), o firmware troca sozinho
// para os pinos alternativos abaixo e avisa na serial e na tela.
#define GPS_RX_PIN 16
#define GPS_TX_PIN 17
#define GPS_RX_PIN_ALT 17
#define GPS_TX_PIN_ALT 13
#define GPS_BAUD 9600

// Varredura WiFi: um canal por vez, para saber em que instante cada rede foi
// ouvida. 120 ms por canal x 13 canais = uma volta completa a cada ~2 s.
#define SCAN_MS_PER_CHANNEL 120
#define SCAN_CHANNELS 13

// Serial USB.
#define USB_BAUD 115200

// Se a tela for OLED de 1,3" (SH1106) em vez de 0,96" (SSD1306), descomente:
// #define OLED_SH1106

// Espaço mínimo livre na flash antes de parar de gravar.
#define FS_MIN_FREE 8192
