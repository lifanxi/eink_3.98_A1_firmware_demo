#pragma once
#include <cstddef>
#include <cstdint>

#ifndef HUAWEI_EPD_REVISION
#define HUAWEI_EPD_REVISION 1
#endif
#if HUAWEI_EPD_REVISION != 0 && HUAWEI_EPD_REVISION != 1
#error "HUAWEI_EPD_REVISION must be 0 (A0) or 1 (A1)"
#endif

namespace ink {
constexpr uint16_t Width = 768;
constexpr uint16_t Height = 552;
constexpr uint16_t GateHeight = 600;
constexpr size_t RowBytes = Width / 4;
constexpr size_t FrameBytes = RowBytes * Height;
constexpr uint8_t Revision = HUAWEI_EPD_REVISION;
constexpr uint32_t ReceiveTimeoutMs = 30000;
constexpr uint32_t BusyTimeoutMs = 45000;
constexpr uint16_t MaxPacketBytes = 244;
constexpr uint8_t ProtocolVersion = 1;
constexpr int Mosi = 6, Sck = 4, Cs = 7, Dc = 1, Rst = 2, Busy = 10;
constexpr char ServiceUuid[] = "cba00001-33c6-4d2e-a950-c61731a49a7e";
constexpr char ControlUuid[] = "cba00002-33c6-4d2e-a950-c61731a49a7e";
constexpr char DataUuid[] = "cba00003-33c6-4d2e-a950-c61731a49a7e";
constexpr char StatusUuid[] = "cba00004-33c6-4d2e-a950-c61731a49a7e";
constexpr char InfoUuid[] = "cba00005-33c6-4d2e-a950-c61731a49a7e";
}
