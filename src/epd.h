#pragma once
#include <cstdint>
namespace ink {
void epdGpioInit();
// Row-major, top-to-bottom, MSB-first: 0 black, 1 white, 2 yellow, 3 red.
// The caller keeps the 105984-byte buffer immutable until this returns.
bool epdDisplay(const uint8_t* image);
}
