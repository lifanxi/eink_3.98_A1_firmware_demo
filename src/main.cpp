#include <Arduino.h>
#include <NimBLEDevice.h>
#include <freertos/FreeRTOS.h>
#include <freertos/semphr.h>
#include "config.h"
#include "epd.h"
#include "receiver.h"

namespace {
alignas(4) uint8_t frame[ink::FrameBytes];
ink::Receiver receiver(frame);
SemaphoreHandle_t receiverMutex;
NimBLEServer* server;
NimBLECharacteristic* statusCharacteristic;
uint32_t publishedSequence = 0;

class Lock {
public:
    Lock() { xSemaphoreTake(receiverMutex, portMAX_DELAY); }
    ~Lock() { xSemaphoreGive(receiverMutex); }
};
class ServerCallbacks : public NimBLEServerCallbacks {
    void onConnect(NimBLEServer* s, NimBLEConnInfo& info) override {
        s->updateConnParams(info.getConnHandle(), 12, 24, 0, 400);
        Serial.printf("[BLE] connected, free heap=%u\n", ESP.getFreeHeap());
    }
    void onDisconnect(NimBLEServer*, NimBLEConnInfo&, int reason) override {
        { Lock lock; receiver.disconnect(); }
        Serial.printf("[BLE] disconnected (%d), advertising again\n", reason);
    }
} serverCallbacks;
class ControlCallbacks : public NimBLECharacteristicCallbacks {
    void onWrite(NimBLECharacteristic* c, NimBLEConnInfo&) override {
        const auto value = c->getValue();
        Lock lock;
        receiver.control(value.data(), value.size(), millis());
    }
} controlCallbacks;
class DataCallbacks : public NimBLECharacteristicCallbacks {
    void onWrite(NimBLECharacteristic* c, NimBLEConnInfo&) override {
        const auto value = c->getValue();
        Lock lock;
        receiver.data(value.data(), value.size(), millis());
    }
} dataCallbacks;
class StatusCallbacks : public NimBLECharacteristicCallbacks {
    void onRead(NimBLECharacteristic* c, NimBLEConnInfo&) override {
        // Reads report the current offset even while the Arduino task is
        // refreshing the display; notifications are only a convenience.
        uint8_t value[20];
        Lock lock;
        receiver.status(value);
        c->setValue(value, sizeof(value));
    }
} statusCallbacks;

// Only the Arduino task sends notifications and performs screen refreshes.
// Serialize value updates with onRead so an older snapshot cannot overwrite it.
void publishStatus(bool force = false) {
    uint8_t value[20];
    {
        Lock lock;
        if (!force && publishedSequence == receiver.sequence()) return;
        receiver.status(value);
        publishedSequence = receiver.sequence();
        statusCharacteristic->setValue(value, sizeof(value));
    }
    if (server->getConnectedCount()) statusCharacteristic->notify();
}
}

void setup() {
    Serial.begin(115200);
    delay(100);
    ink::epdGpioInit(); // Keep the existing image until a complete new frame arrives.
    receiverMutex = xSemaphoreCreateMutex();
    if (!receiverMutex) { Serial.println("Mutex allocation failed"); while (true) delay(1000); }
    const uint64_t mac = ESP.getEfuseMac();
    char name[28];
    snprintf(name, sizeof(name), "InkBLE-A%u-%04X", ink::Revision, unsigned((mac >> 32) & 0xFFFF));
    NimBLEDevice::init(name);
    NimBLEDevice::setMTU(247);
    server = NimBLEDevice::createServer();
    server->setCallbacks(&serverCallbacks, false);
    server->advertiseOnDisconnect(true);
    auto* service = server->createService(ink::ServiceUuid);
    auto* control = service->createCharacteristic(ink::ControlUuid, NIMBLE_PROPERTY::WRITE, 19);
    auto* data = service->createCharacteristic(ink::DataUuid, NIMBLE_PROPERTY::WRITE, ink::MaxPacketBytes);
    statusCharacteristic = service->createCharacteristic(ink::StatusUuid, NIMBLE_PROPERTY::READ | NIMBLE_PROPERTY::NOTIFY, 20);
    auto* info = service->createCharacteristic(ink::InfoUuid, NIMBLE_PROPERTY::READ, 16);
    control->setCallbacks(&controlCallbacks); data->setCallbacks(&dataCallbacks);
    statusCharacteristic->setCallbacks(&statusCallbacks);
    uint8_t infoBytes[16]; ink::deviceInfo(infoBytes); info->setValue(infoBytes, sizeof(infoBytes));
    publishStatus(true);
    auto* advertising = NimBLEDevice::getAdvertising();
    // The 128-bit service UUID uses 18 advertising bytes. Put the complete
    // device name in the scan response so both fields fit legacy advertising.
    advertising->enableScanResponse(true);
    advertising->addServiceUUID(ink::ServiceUuid);
    advertising->setName(name);
    if (!advertising->start()) {
        Serial.println("[BLE] advertising failed; restarting");
        delay(1000);
        ESP.restart();
    }
    Serial.printf("[READY] %s, 768x552 BWRY, free heap=%u\n", name, ESP.getFreeHeap());
}

void loop() {
    const uint8_t* ready;
    {
        Lock lock;
        receiver.tick(millis());
        ready = receiver.takeReady();
    }
    publishStatus();
    if (ready) {
        Serial.println("[EPD] CRC verified, refreshing");
        const bool ok = ink::epdDisplay(ready);
        { Lock lock; receiver.finish(ok); }
        publishStatus(true);
        Serial.println(ok ? "[EPD] done, ready for another image" : "[EPD] BUSY timeout");
    }
    delay(10);
}
