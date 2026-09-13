#pragma once
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <initializer_list>
constexpr int LOW = 0, HIGH = 1, INPUT = 1, OUTPUT = 3, INPUT_PULLUP = 5;
void pinMode(int, int);
void digitalWrite(int, int);
int digitalRead(int);
unsigned long millis();
void delay(unsigned long);
struct MockSerial {
    template <typename... Args> void printf(const char*, Args...) {}
    void println(const char*) {}
};
extern MockSerial Serial;
