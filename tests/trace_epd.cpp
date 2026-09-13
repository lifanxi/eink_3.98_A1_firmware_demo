#include <Arduino.h>
#include "config.h"
#include <cassert>
#include <cstdio>
#include <string>
#include <vector>
#include "epd.h"
using namespace ink;
MockSerial Serial;
struct Packet { uint8_t command; std::vector<uint8_t> data; };
static std::vector<Packet> packets;
static std::vector<std::string> events;
static int pins[40] = {}, bits = 0;
static uint8_t spi = 0;
static unsigned long elapsed = 0;
static int stuckAt = 0;
void pinMode(int, int) {}
int digitalRead(int pin) {
    assert(pin == Busy);
    if (stuckAt == 1 || (stuckAt == 2 && !packets.empty() && packets.back().command >= 0x12)) return LOW;
    return HIGH;
}
unsigned long millis() { return elapsed; }
void delay(unsigned long ms) { elapsed += ms; events.push_back("delay " + std::to_string(ms)); }
void digitalWrite(int pin, int value) {
    if (pin == Rst) events.push_back("gpio " + std::to_string(pin) + " " + std::to_string(value));
    if (pin == Cs && value == LOW) { assert(pins[pin] == HIGH); bits = 0; spi = 0; }
    if (pin == Sck && pins[pin] == LOW && value == HIGH) {
        assert(pins[Cs] == LOW); spi = (spi << 1) | pins[Mosi]; ++bits;
    }
    if (pin == Cs && pins[pin] == LOW && value == HIGH && bits) {
        assert(bits == 8);
        if (pins[Dc] == LOW) packets.push_back({spi, {}});
        else { assert(!packets.empty()); packets.back().data.push_back(spi); }
    }
    pins[pin] = value;
}
int main(int argc, char** argv) {
    const std::string mode = argc > 1 ? argv[1] : "normal";
    std::vector<uint8_t> raw(FrameBytes);
    for (size_t i = 0; i < FrameBytes; ++i) raw[i] = (i * 37 + i / RowBytes) & 255;
    epdGpioInit(); events.clear();
    assert(packets.empty()); // Boot retains the previous image.
    if (mode == "boot") return 0;
    if (mode == "busy") stuckAt = 1;
    if (mode == "refresh_timeout") stuckAt = 2;
    const bool ok = epdDisplay(mode == "null" ? nullptr : raw.data());
    assert(ok == (mode == "normal"));
    if (mode == "busy" || mode == "null") assert(packets.empty());
    if (mode == "busy") assert(elapsed >= BusyTimeoutMs && elapsed < BusyTimeoutMs + 1000);
    for (const auto& event : events) printf("E %s\n", event.c_str());
    for (const auto& packet : packets) {
        printf("P %02x ", packet.command);
        for (uint8_t b : packet.data) printf("%02x", b);
        printf("\n");
    }
}
