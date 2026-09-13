"""Version 1 of the InkBLE protocol, independent of the Bluetooth library."""
from dataclasses import dataclass
import struct
import zlib

SERVICE = 'cba00001-33c6-4d2e-a950-c61731a49a7e'
CONTROL = 'cba00002-33c6-4d2e-a950-c61731a49a7e'
DATA = 'cba00003-33c6-4d2e-a950-c61731a49a7e'
STATUS = 'cba00004-33c6-4d2e-a950-c61731a49a7e'
INFO = 'cba00005-33c6-4d2e-a950-c61731a49a7e'
IDLE, RECEIVING, QUEUED, REFRESHING, DONE, ERROR = range(6)
ERRORS = ('无错误', '无效控制命令', '设备正忙', '图像格式不匹配', '数据长度不正确',
          '传输编号不匹配', '数据偏移不正确', 'CRC32 校验失败', '接收超时', '屏幕 BUSY 超时', '已取消')


@dataclass(frozen=True)
class DeviceInfo:
    revision: int
    width: int
    height: int
    frame_bytes: int
    max_packet: int

    @classmethod
    def parse(cls, value):
        if len(value) != 16:
            raise ValueError('设备信息长度不正确')
        magic, version, revision, width, height, size, packet = struct.unpack('<4sBBHHIH', value)
        if ((magic, version, width, height, size) != (b'EINK', 1, 768, 552, 105984)
                or revision not in (0, 1) or not 20 <= packet <= 244):
            raise ValueError('设备协议或屏幕尺寸不兼容')
        return cls(revision, width, height, size, packet)


@dataclass(frozen=True)
class Status:
    state: int
    error: int
    revision: int
    transfer_id: int
    received: int
    total: int
    sequence: int

    @classmethod
    def parse(cls, value):
        if len(value) != 20:
            raise ValueError('设备状态长度不正确')
        version, *fields = struct.unpack('<BBBBIIII', value)
        if version != 1 or fields[0] not in range(6):
            raise ValueError('设备状态版本不兼容')
        return cls(*fields)

    def check_error(self):
        if self.error:
            message = ERRORS[self.error] if self.error < len(ERRORS) else str(self.error)
            raise RuntimeError('设备报告：' + message)


def begin(transfer_id, payload):
    return struct.pack('<BBIIIHHB', 1, 1, transfer_id, len(payload), zlib.crc32(payload), 768, 552, 1)


def commit(transfer_id):
    return struct.pack('<BI', 2, transfer_id)


def abort(transfer_id):
    return struct.pack('<BI', 3, transfer_id)


def chunk(transfer_id, offset, data):
    return struct.pack('<II', transfer_id, offset) + data
