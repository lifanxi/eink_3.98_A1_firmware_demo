#include "receiver.h"
#include <cstring>

namespace ink {
uint32_t read32(const uint8_t* p) {
    return uint32_t(p[0]) | (uint32_t(p[1]) << 8) | (uint32_t(p[2]) << 16) | (uint32_t(p[3]) << 24);
}
void write32(uint8_t* p, uint32_t v) { for (unsigned i = 0; i < 4; ++i) p[i] = v >> (8 * i); }
static uint16_t read16(const uint8_t* p) { return uint16_t(p[0]) | (uint16_t(p[1]) << 8); }
static void write16(uint8_t* p, uint16_t v) { p[0] = v; p[1] = v >> 8; }
uint32_t crc32Update(uint32_t crc, const uint8_t* bytes, size_t length) {
    for (size_t i = 0; i < length; ++i) {
        crc ^= bytes[i];
        for (unsigned bit = 0; bit < 8; ++bit) crc = (crc >> 1) ^ (0xEDB88320u & (0u - (crc & 1u)));
    }
    return crc;
}
void deviceInfo(uint8_t out[16]) {
    memcpy(out, "EINK", 4); out[4] = ProtocolVersion; out[5] = Revision;
    write16(out + 6, Width); write16(out + 8, Height);
    write32(out + 10, FrameBytes); write16(out + 14, MaxPacketBytes);
}
Error Receiver::reject(Error error) { error_ = error; ++sequence_; return error; }
void Receiver::changed() { error_ = Error::None; ++sequence_; }

Error Receiver::control(const uint8_t* b, size_t n, uint32_t now) {
    if (!b || n == 0) return reject(Error::BadControl);
    if (b[0] == 1) { // BEGIN: opcode, version, id, length, crc32, width, height, format.
        if (n != 19) return reject(Error::BadLength);
        if (b[1] != ProtocolVersion || b[18] != 1 || read16(b + 14) != Width || read16(b + 16) != Height)
            return reject(Error::BadFormat);
        if (read32(b + 6) != FrameBytes) return reject(Error::BadLength);
        if (state_ == State::Receiving && read32(b + 2) == id_ && read32(b + 10) == expectedCrc_) {
            lastActivity_ = now; changed(); return Error::None; // Lost BEGIN response: resume, don't reset.
        }
        if (state_ == State::Receiving || state_ == State::Queued || state_ == State::Refreshing)
            return reject(Error::Busy);
        id_ = read32(b + 2); expectedCrc_ = read32(b + 10); received_ = 0;
        rollingCrc_ = 0xFFFFFFFF; lastActivity_ = now; state_ = State::Receiving;
        changed(); return Error::None;
    }
    if (b[0] != 2 && b[0] != 3) return reject(Error::BadControl);
    if (n != 5) return reject(Error::BadLength);
    if (read32(b + 1) != id_) return reject(Error::BadTransfer);
    if (b[0] == 2) { // COMMIT is idempotent after the frame has been accepted.
        if (state_ == State::Queued || state_ == State::Refreshing || state_ == State::Done) {
            changed(); return Error::None;
        }
        if (state_ != State::Receiving) return reject(Error::BadControl);
        if (received_ != FrameBytes) return reject(Error::BadLength);
        if ((rollingCrc_ ^ 0xFFFFFFFF) != expectedCrc_) {
            state_ = State::Error; return reject(Error::CrcMismatch);
        }
        state_ = State::Queued; changed(); return Error::None;
    }
    if (state_ == State::Queued || state_ == State::Refreshing) return reject(Error::Busy);
    state_ = State::Idle; received_ = 0;
    return reject(Error::Aborted);
}

Error Receiver::data(const uint8_t* b, size_t n, uint32_t now) {
    if (!b || n <= 8 || n > MaxPacketBytes) return reject(Error::BadLength);
    if (state_ != State::Receiving) return reject(Error::Busy);
    if (read32(b) != id_) return reject(Error::BadTransfer);
    const uint32_t offset = read32(b + 4);
    const size_t count = n - 8;
    if (offset > FrameBytes || count > FrameBytes - offset) return reject(Error::BadLength);
    if (offset < received_ && count <= received_ - offset && memcmp(frame_ + offset, b + 8, count) == 0) {
        lastActivity_ = now; changed(); return Error::None; // Retry after a lost ATT response.
    }
    if (offset != received_) return reject(Error::BadOffset);
    memcpy(frame_ + received_, b + 8, count);
    rollingCrc_ = crc32Update(rollingCrc_, b + 8, count);
    received_ += count; lastActivity_ = now;
    changed(); return Error::None;
}
void Receiver::disconnect() {
    // A committed frame must still finish when the sender disconnects.
    if (state_ == State::Receiving) { state_ = State::Idle; received_ = 0; changed(); }
}
void Receiver::tick(uint32_t now) {
    if (state_ == State::Receiving && uint32_t(now - lastActivity_) > ReceiveTimeoutMs) {
        state_ = State::Error; reject(Error::ReceiveTimeout);
    }
}
const uint8_t* Receiver::takeReady() {
    if (state_ != State::Queued) return nullptr;
    state_ = State::Refreshing; changed(); return frame_;
}
void Receiver::finish(bool success) {
    if (state_ != State::Refreshing) return;
    state_ = success ? State::Done : State::Error;
    if (success) changed(); else reject(Error::DisplayTimeout);
}
void Receiver::status(uint8_t out[20]) const {
    out[0] = ProtocolVersion; out[1] = uint8_t(state_); out[2] = uint8_t(error_); out[3] = Revision;
    write32(out + 4, id_); write32(out + 8, received_); write32(out + 12, FrameBytes);
    write32(out + 16, sequence_);
}
}
