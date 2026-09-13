#include "epd.h"
#include "config.h"
#include <Arduino.h>

namespace ink {
namespace {
void spiByte(uint8_t value) {
    for (int i = 0; i < 8; ++i) {
        digitalWrite(Mosi, (value & 0x80) ? HIGH : LOW);
        value <<= 1;
        digitalWrite(Sck, HIGH);
        digitalWrite(Sck, LOW);
    }
}
void send(uint8_t value, bool data) {
    digitalWrite(Dc, data ? HIGH : LOW);
    digitalWrite(Cs, LOW);
    spiByte(value);
    digitalWrite(Cs, HIGH);
}
void command(uint8_t value) { send(value, false); }
void data(uint8_t value) { send(value, true); }
bool waitIdle() {
    const uint32_t start = millis();
    while (digitalRead(Busy) == LOW) {
        if (uint32_t(millis() - start) > BusyTimeoutMs) return false;
        delay(10);
    }
    return true;
}
void window(uint16_t y0, uint16_t y1) {
    command(0x83);
    data(0); data(0); data((Width - 1) >> 8); data((Width - 1) & 255);
    data(y0 >> 8); data(y0 & 255); data(y1 >> 8); data(y1 & 255); data(1);
}
uint16_t gateRow(uint16_t y) {
#if HUAWEI_EPD_REVISION == 1
    return y < 300 ? 2 * y : 2 * y - 599;
#else
    return y < 276 ? 2 * y : 1103 - 2 * y;
#endif
}
uint8_t reversePixels(uint8_t v) {
    return ((v & 3) << 6) | ((v & 12) << 2) | ((v & 48) >> 2) | ((v & 192) >> 6);
}
bool powerOff() {
    command(0x02); data(0);
    const bool ok = waitIdle();
    command(0x07); data(0xA5); delay(200);
    return ok;
}
}

void epdGpioInit() {
    pinMode(Busy, INPUT);
    for (int pin : {Mosi, Sck, Cs, Dc, Rst}) pinMode(pin, OUTPUT);
    digitalWrite(Rst, HIGH); digitalWrite(Cs, HIGH); digitalWrite(Sck, LOW);
}

bool epdDisplay(const uint8_t* image) {
    if (!image) return false;
    // Initialization and gate mapping match the hardware-verified old project.
    delay(20); digitalWrite(Rst, LOW); delay(40);
    digitalWrite(Rst, HIGH); delay(50);
    if (!waitIdle()) return false;
    delay(30);
    command(0x00); data(0x0B);
    command(0x61); data(Width >> 8); data(Width & 255);
    data(GateHeight >> 8); data(GateHeight & 255);
    command(0x04);
    if (!waitIdle()) { powerOff(); return false; }
    command(0x04);
    if (!waitIdle()) { powerOff(); return false; }
    for (uint16_t y = 0; y < Height; ++y) {
        window(gateRow(y), gateRow(y));
        command(0x10);
        // Same physical orientation as the verified color setup screen, while
        // exposing a conventional top-left origin to every BLE sender.
        const uint8_t* row = image + (Height - 1 - y) * RowBytes;
        for (size_t x = 0; x < RowBytes; ++x) data(reversePixels(row[RowBytes - 1 - x]));
        if ((y & 7) == 7) delay(1); // Let the BLE host and watchdog run during SPI.
    }
    window(0, GateHeight - 1);
    command(0x12); data(0x01);
    const bool refreshed = waitIdle();
    const bool poweredOff = powerOff();
    return refreshed && poweredOff;
}
}
