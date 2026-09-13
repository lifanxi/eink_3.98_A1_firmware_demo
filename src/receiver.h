#pragma once
#include "config.h"

namespace ink {
enum class State : uint8_t { Idle, Receiving, Queued, Refreshing, Done, Error };
enum class Error : uint8_t {
    None, BadControl, Busy, BadFormat, BadLength, BadTransfer,
    BadOffset, CrcMismatch, ReceiveTimeout, DisplayTimeout, Aborted
};
uint32_t crc32Update(uint32_t crc, const uint8_t* bytes, size_t length);
uint32_t read32(const uint8_t* p);
void write32(uint8_t* p, uint32_t value);
void deviceInfo(uint8_t out[16]);

// All methods are called under the application mutex. No heap allocation.
class Receiver {
public:
    explicit Receiver(uint8_t* frame) : frame_(frame) {}
    Error control(const uint8_t* bytes, size_t length, uint32_t now);
    Error data(const uint8_t* bytes, size_t length, uint32_t now);
    void disconnect();
    void tick(uint32_t now);
    const uint8_t* takeReady();
    void finish(bool success);
    void status(uint8_t out[20]) const;
    uint32_t sequence() const { return sequence_; }
    State state() const { return state_; }
    uint32_t received() const { return received_; }
private:
    Error reject(Error error);
    void changed();
    uint8_t* frame_;
    State state_ = State::Idle;
    Error error_ = Error::None;
    uint32_t id_ = 0, received_ = 0, expectedCrc_ = 0;
    uint32_t rollingCrc_ = 0xFFFFFFFF, lastActivity_ = 0, sequence_ = 0;
};
}
