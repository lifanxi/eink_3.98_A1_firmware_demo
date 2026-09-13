// Host bridge: Python exercises the exact receiver compiled into the ESP32.
#include "receiver.h"
#include <algorithm>
#include <cstring>
struct Harness {
    uint8_t memory[ink::FrameBytes + 32];
    ink::Receiver receiver;
    Harness() : receiver(memory + 16) { memset(memory, 0xA6, sizeof(memory)); }
};
extern "C" {
void* rx_create() { return new Harness; }
void rx_delete(Harness* h) { delete h; }
int rx_control(Harness* h, const uint8_t* p, size_t n, uint32_t now) { return int(h->receiver.control(p, n, now)); }
int rx_data(Harness* h, const uint8_t* p, size_t n, uint32_t now) { return int(h->receiver.data(p, n, now)); }
void rx_status(Harness* h, uint8_t* out) { h->receiver.status(out); }
void rx_info(uint8_t* out) { ink::deviceInfo(out); }
void rx_disconnect(Harness* h) { h->receiver.disconnect(); }
void rx_tick(Harness* h, uint32_t now) { h->receiver.tick(now); }
int rx_ready(Harness* h) { return h->receiver.takeReady() != nullptr; }
void rx_finish(Harness* h, int ok) { h->receiver.finish(ok); }
void rx_frame(Harness* h, uint8_t* out) { memcpy(out, h->memory + 16, ink::FrameBytes); }
int rx_guards(Harness* h) {
    for (int i = 0; i < 16; ++i)
        if (h->memory[i] != 0xA6 || h->memory[16 + ink::FrameBytes + i] != 0xA6) return 0;
    return 1;
}
}
