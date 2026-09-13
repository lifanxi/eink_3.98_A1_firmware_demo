#!/usr/bin/env python3
"""Host tests; no Bluetooth adapter or device is accessed."""
import asyncio
import ctypes as c
import gzip
from pathlib import Path
import random
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'sender'))
import protocol as p
from image_processing import PALETTE, FRAME_BYTES, fit_image, atkinson, pack_pixels
from send_image import send_frame
from PIL import Image

TEMP = tempfile.TemporaryDirectory(prefix='inkble-tests-')
OUT = Path(TEMP.name)
LIB = None
FRAME = bytes((i * 37 + i // 192) & 255 for i in range(FRAME_BYTES))


def setUpModule():
    global LIB
    subprocess.run(['g++', '-std=c++11', '-O2', '-Wall', '-Wextra', '-Werror', '-shared', '-fPIC',
                    '-I' + str(ROOT / 'src'), str(ROOT / 'src/receiver.cpp'),
                    str(ROOT / 'tests/receiver_bridge.cpp'), '-o', str(OUT / 'receiver.so')], check=True)
    LIB = c.CDLL(str(OUT / 'receiver.so'))
    LIB.rx_create.restype = c.c_void_p
    signatures = {'delete': [c.c_void_p], 'control': [c.c_void_p, c.c_void_p, c.c_size_t, c.c_uint32],
                  'data': [c.c_void_p, c.c_void_p, c.c_size_t, c.c_uint32],
                  'status': [c.c_void_p, c.c_void_p], 'info': [c.c_void_p],
                  'disconnect': [c.c_void_p], 'tick': [c.c_void_p, c.c_uint32],
                  'ready': [c.c_void_p], 'finish': [c.c_void_p, c.c_int],
                  'frame': [c.c_void_p, c.c_void_p], 'guards': [c.c_void_p]}
    for name, args in signatures.items():
        getattr(LIB, 'rx_' + name).argtypes = args


class Receiver:
    def __init__(self): self.handle = LIB.rx_create()
    def __del__(self): LIB.rx_delete(self.handle)
    def control(self, data, now=0): return LIB.rx_control(self.handle, data, len(data), now)
    def data(self, data, now=0): return LIB.rx_data(self.handle, data, len(data), now)
    def tick(self, now): LIB.rx_tick(self.handle, now)
    def disconnect(self): LIB.rx_disconnect(self.handle)
    def ready(self): return bool(LIB.rx_ready(self.handle))
    def finish(self, ok=True): LIB.rx_finish(self.handle, ok)
    def status_bytes(self):
        out = c.create_string_buffer(20); LIB.rx_status(self.handle, out); return out.raw
    def status(self): return p.Status.parse(self.status_bytes())
    def frame(self):
        out = c.create_string_buffer(FRAME_BYTES); LIB.rx_frame(self.handle, out); return out.raw
    def info(self):
        out = c.create_string_buffer(16); LIB.rx_info(out); return out.raw
    def guards(self): return LIB.rx_guards(self.handle)
    def upload(self, payload=FRAME, id=123):
        assert self.control(p.begin(id, payload)) == 0
        for offset in range(0, len(payload), 236):
            assert self.data(p.chunk(id, offset, payload[offset:offset + 236])) == 0


class ReceiverTests(unittest.TestCase):
    def setUp(self): self.rx = Receiver()
    def tearDown(self): self.assertTrue(self.rx.guards())
    def test_info_and_crc_known_vector(self):
        info = p.DeviceInfo.parse(self.rx.info())
        self.assertEqual((info.revision, info.frame_bytes, info.max_packet), (1, 105984, 244))
        self.assertEqual(zlib.crc32(b'123456789'), 0xCBF43926)
        self.rx.upload(); self.assertEqual(self.rx.control(p.commit(123)), 0)
    def test_full_frame_and_second_update(self):
        for payload in (FRAME, bytes([0x1B]) * FRAME_BYTES):
            self.rx.upload(payload)
            self.assertFalse(self.rx.ready())
            self.assertEqual(self.rx.control(p.commit(123)), 0)
            self.assertTrue(self.rx.ready()); self.assertFalse(self.rx.ready())
            self.assertEqual(self.rx.frame(), payload)
            self.rx.finish(); self.assertEqual(self.rx.status().state, p.DONE)
    def test_duplicate_begin_data_and_commit(self):
        self.rx.control(p.begin(123, FRAME))
        first = p.chunk(123, 0, FRAME[:236])
        self.rx.data(first); self.rx.control(p.begin(123, FRAME)); self.rx.data(first)
        self.assertEqual(self.rx.status().received, 236)
        for off in range(236, len(FRAME), 236): self.rx.data(p.chunk(123, off, FRAME[off:off + 236]))
        self.assertEqual(self.rx.control(p.commit(123)), 0)
        self.assertEqual(self.rx.control(p.commit(123)), 0)
        self.rx.ready(); self.rx.finish()
        self.assertEqual(self.rx.control(p.commit(123)), 0)
        self.assertFalse(self.rx.ready())
    def test_partial_commit_and_wrong_id(self):
        self.rx.control(p.begin(123, FRAME))
        self.assertEqual(self.rx.control(p.commit(123)), 4)
        self.assertEqual(self.rx.data(p.chunk(124, 0, b'x')), 5)
        self.assertEqual(self.rx.control(p.commit(124)), 5)
        self.assertFalse(self.rx.ready())
    def test_crc_mismatch_never_displays(self):
        self.rx.upload()
        # Start over with the expected CRC of a different image.
        self.rx.disconnect()
        expected = bytes([0x55]) * FRAME_BYTES
        self.rx.control(p.begin(123, expected))
        for off in range(0, len(FRAME), 236): self.rx.data(p.chunk(123, off, FRAME[off:off + 236]))
        self.assertEqual(self.rx.control(p.commit(123)), 7)
        self.assertEqual(self.rx.status().state, p.ERROR)
        self.assertFalse(self.rx.ready())
        self.rx.upload(); self.assertEqual(self.rx.control(p.commit(123)), 0)
    def test_offset_bounds_and_changed_duplicate(self):
        self.rx.control(p.begin(123, FRAME))
        for offset in (FRAME_BYTES, 0xFFFFFFFF, FRAME_BYTES - 1):
            self.assertEqual(self.rx.data(p.chunk(123, offset, b'abc')), 4)
        self.assertEqual(self.rx.data(p.chunk(123, 1, b'x')), 6)
        self.rx.data(p.chunk(123, 0, FRAME[:12]))
        self.assertEqual(self.rx.data(p.chunk(123, 0, bytes([FRAME[0] ^ 255]))), 6)
        self.assertEqual(self.rx.data(p.chunk(123, 0, FRAME[:13])), 6)
        self.assertEqual(self.rx.status().received, 12)
    def test_disconnect_aborts_partial_but_preserves_commit(self):
        self.rx.control(p.begin(123, FRAME)); self.rx.data(p.chunk(123, 0, FRAME[:12]))
        self.rx.disconnect(); self.assertEqual(self.rx.status().state, p.IDLE)
        self.assertEqual(self.rx.status().received, 0); self.assertFalse(self.rx.ready())
        self.rx.upload(); self.rx.control(p.commit(123)); self.rx.disconnect()
        self.assertTrue(self.rx.ready()); self.rx.disconnect(); self.rx.finish()
        self.assertEqual(self.rx.status().state, p.DONE)
    def test_accepted_frame_is_immutable(self):
        self.rx.upload(); self.rx.control(p.commit(123))
        for state in (p.QUEUED, p.REFRESHING):
            self.assertEqual(self.rx.status().state, state)
            self.assertEqual(self.rx.control(p.abort(123)), 2)
            self.assertEqual(self.rx.control(p.begin(124, FRAME)), 2)
            self.assertEqual(self.rx.data(p.chunk(123, 0, b'x')), 2)
            self.assertEqual(self.rx.frame(), FRAME)
            self.rx.ready()
        self.rx.finish(); self.assertEqual(self.rx.status().error, 0)
    def test_receive_timeout_with_millis_wrap(self):
        self.rx.control(p.begin(123, FRAME), 0xFFFFFFF0)
        self.rx.tick(29900); self.assertEqual(self.rx.status().state, p.RECEIVING)
        self.rx.tick(30000); self.assertEqual(self.rx.status().error, 8)
        self.assertFalse(self.rx.ready())
    def test_abort_and_display_failure(self):
        self.rx.control(p.begin(123, FRAME)); self.assertEqual(self.rx.control(p.abort(123)), 10)
        self.assertFalse(self.rx.ready()); self.rx.upload(); self.rx.control(p.commit(123))
        self.rx.ready(); self.rx.finish(False)
        self.assertEqual((self.rx.status().state, self.rx.status().error), (p.ERROR, 9))
    def test_malformed_packets_and_fuzz(self):
        original = p.begin(123, FRAME)
        for index in (1, 14, 16, 18):
            bad = bytearray(original); bad[index] ^= 255
            self.assertEqual(self.rx.control(bytes(bad)), 3)
        self.assertEqual(self.rx.control(original[:-1]), 4)
        self.assertEqual(self.rx.control(b''), 1)
        self.rx.control(original)
        rng = random.Random(781)
        for _ in range(2000):
            n = rng.randrange(270)
            packet = bytes(rng.randrange(256) for _ in range(n))
            self.rx.data(packet); self.rx.control(packet)
        self.assertFalse(self.rx.ready()); self.assertTrue(self.rx.guards())


class ImageTests(unittest.TestCase):
    def test_contain_landscape_portrait_square(self):
        for size, expected in [((200, 100), (0, 6, 40, 26)), ((100, 200), (0, 6, 40, 26)),
                               ((100, 100), (4, 0, 36, 32))]:
            fitted, bounds = fit_image(Image.new('RGB', size, 'red'), 40, 32)
            self.assertEqual(bounds, expected)
            self.assertEqual(fitted.getpixel((20, 16)), (255, 0, 0))
            self.assertEqual(fitted.getpixel((0, 0)), (255, 255, 255))
    def test_portrait_rotates_once_clockwise_to_fill_screen(self):
        src = Image.new('RGB', (2, 4), 'white')
        for point, color in zip(((0, 0), (1, 0), (0, 3), (1, 3)), PALETTE): src.putpixel(point, color)
        original = src.tobytes()
        fitted, bounds = fit_image(src, 4, 2)
        self.assertEqual(bounds, (0, 0, 4, 2))
        for point, color in zip(((3, 0), (3, 1), (0, 0), (0, 1)), PALETTE): self.assertEqual(fitted.getpixel(point), color)
        self.assertEqual(src.tobytes(), original)
    def test_keep_orientation_when_rotation_does_not_improve_coverage(self):
        for size, screen, bounds in [((4, 2), (4, 2), (0, 0, 4, 2)),
                                     ((4, 4), (8, 4), (2, 0, 6, 4)),
                                     ((2, 4), (4, 4), (1, 0, 3, 4))]:
            src = Image.new('RGB', size, 'white')
            src.putpixel((0, 0), PALETTE[3]); src.putpixel((size[0] - 1, size[1] - 1), PALETTE[0])
            fitted, actual_bounds = fit_image(src, *screen)
            self.assertEqual(actual_bounds, bounds)
            self.assertEqual(fitted.crop(bounds).tobytes(), src.tobytes())
    def test_default_screen_ratio_fills_after_rotation(self):
        fitted, bounds = fit_image(Image.new('RGB', (552, 768), 'black'))
        self.assertEqual(fitted.size, (768, 552))
        self.assertEqual(bounds, (0, 0, 768, 552))
    def test_exif_is_normalized_before_choosing_orientation(self):
        src = Image.new('RGB', (2, 4), 'white')
        src.putpixel((0, 0), PALETTE[3]); src.putpixel((1, 3), PALETTE[0])
        src.getexif()[274] = 6  # EXIF presents the image as 4x2, already fitting.
        fitted, bounds = fit_image(src, 4, 2)
        self.assertEqual(bounds, (0, 0, 4, 2))
        self.assertEqual(fitted.getpixel((3, 0)), PALETTE[3])
        self.assertEqual(fitted.getpixel((0, 1)), PALETTE[0])
    def test_no_crop_preserves_four_corners(self):
        src = Image.new('RGB', (20, 10), 'white')
        for point, color in zip(((0, 0), (19, 0), (0, 9), (19, 9)), PALETTE): src.putpixel(point, color)
        fitted, bounds = fit_image(src, 20, 20)
        for point, color in zip(((0, 5), (19, 5), (0, 14), (19, 14)), PALETTE): self.assertEqual(fitted.getpixel(point), color)
    def test_transparency_and_exif_orientation(self):
        transparent, _ = fit_image(Image.new('RGBA', (8, 8), (0, 0, 0, 0)), 8, 8)
        self.assertEqual(transparent.tobytes(), b'\xff' * (8 * 8 * 3))
        src = Image.new('RGB', (12, 6), 'black'); src.getexif()[274] = 6
        fitted, bounds = fit_image(src, 12, 12)
        self.assertEqual(bounds, (3, 0, 9, 12))
    def test_palette_and_bit_order(self):
        src = Image.new('RGB', (4, 1)); src.putdata(PALETTE)
        indexed = atkinson(src)
        self.assertEqual(indexed.tobytes(), bytes(range(4)))
        self.assertEqual(pack_pixels(indexed), b'\x1b')
    def test_atkinson_error_diffusion_and_white_padding(self):
        # Uniform gray creates both black and white, unlike nearest-color-only.
        fitted, bounds = fit_image(Image.new('RGB', (8, 4), (127, 127, 127)), 16, 16)
        indexed = atkinson(fitted, bounds)
        colors = set(indexed.tobytes()); self.assertIn(0, colors); self.assertIn(1, colors)
        self.assertTrue(colors <= {0, 1, 2, 3})
        for y in range(16):
            for x in range(16):
                if y < bounds[1] or y >= bounds[3]: self.assertEqual(indexed.getpixel((x, y)), 1)
    def test_invalid_pixels_rejected(self):
        with self.assertRaises(ValueError): pack_pixels(Image.new('RGB', (4, 1)))
        with self.assertRaises(ValueError): pack_pixels(Image.new('P', (4, 1), 4))


class FakeClient:
    """GATT transport double with the real C++ receiver, including fault injection."""
    mtu_size = 247
    is_connected = True
    def __init__(self, fault=None):
        self.rx = Receiver(); self.fault = fault; self.fired = False; self.refreshes = 0
        self.stale_status = None
    async def read_gatt_char(self, uuid):
        if not self.is_connected: raise ConnectionError('disconnected')
        if uuid == p.INFO: return self.rx.info()
        if self.stale_status is not None:
            status, self.stale_status = self.stale_status, None
            return status
        if self.rx.ready():
            self.refreshes += 1; self.rx.finish(self.fault != 'display_timeout')
        return self.rx.status_bytes()
    async def write_gatt_char(self, uuid, data, response):
        assert response
        if uuid == p.CONTROL:
            if self.fault == 'crc' and data[0] == 1:
                data = bytearray(data); data[10] ^= 1; data = bytes(data)
            self.rx.control(data)
            if self.fault == 'commit_lost_ack' and data[0] == 2:
                raise OSError('lost commit acknowledgement')
            return
        assert uuid == p.DATA
        should_fail = self.fault in ('mtu', 'lost_ack', 'disconnect')
        # Lose the response just across a progress checkpoint. The next status
        # read is stale, forcing duplicate-prefix recovery in the sender.
        if self.fault == 'stale_lost_ack' and struct.unpack_from('<I', data, 4)[0] >= 4000:
            should_fail = True
        if should_fail and not self.fired:
            self.fired = True
            if self.fault == 'lost_ack': self.rx.data(data)
            if self.fault == 'stale_lost_ack':
                self.stale_status = self.rx.status_bytes(); self.rx.data(data)
            if self.fault == 'disconnect': self.is_connected = False; self.rx.disconnect()
            raise OSError('injected transport failure')
        self.rx.data(data)


class SenderTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        asyncio.get_running_loop().set_debug(False)
    async def test_two_successive_frames(self):
        client = FakeClient(); messages = []
        for payload in (FRAME, bytes([0xAA]) * FRAME_BYTES):
            await send_frame(client, payload, progress=messages.append)
            self.assertEqual(client.rx.frame(), payload)
        self.assertEqual(client.refreshes, 2)
        self.assertEqual(sum('屏幕刷新完成。' in s for s in messages), 2)
    async def test_minimum_mtu_fallback_and_lost_ack(self):
        for fault in ('mtu', 'lost_ack', 'stale_lost_ack'):
            client = FakeClient(fault)
            await send_frame(client, FRAME, progress=lambda _: None)
            self.assertEqual(client.rx.frame(), FRAME); self.assertEqual(client.refreshes, 1)
    async def test_failures_do_not_report_success(self):
        for fault in ('disconnect', 'crc', 'display_timeout'):
            client = FakeClient(fault); messages = []
            with self.assertRaises((OSError, RuntimeError)):
                await send_frame(client, FRAME, progress=messages.append)
            self.assertFalse(any('屏幕刷新完成。' in s for s in messages))
            self.assertEqual(client.refreshes, 1 if fault == 'display_timeout' else 0)
    async def test_lost_commit_response_does_not_cancel_accepted_frame(self):
        client = FakeClient('commit_lost_ack')
        with self.assertRaises(OSError): await send_frame(client, FRAME, progress=lambda _: None)
        self.assertEqual(client.rx.status().state, p.QUEUED)
        client.rx.disconnect(); self.assertTrue(client.rx.ready()); client.rx.finish()
        self.assertEqual(client.rx.status().state, p.DONE)
    async def test_default_mtu_23(self):
        client = FakeClient(); client.mtu_size = 23
        await send_frame(client, FRAME, progress=lambda _: None)
        self.assertEqual(client.rx.frame(), FRAME)


class ScreenTests(unittest.TestCase):
    def test_a0_a1_match_verified_spi_fixtures(self):
        for revision in (0, 1):
            src = ROOT / 'src'
            binary = OUT / f'trace-{revision}'
            subprocess.run(['g++', '-std=c++11', '-O2', '-I' + str(ROOT / 'tests'), '-I' + str(src),
                            f'-DHUAWEI_EPD_REVISION={revision}', str(src / 'epd.cpp'),
                            str(ROOT / 'tests/trace_epd.cpp'), '-o', str(binary)], check=True)
            trace = subprocess.check_output([str(binary)], text=True).splitlines()
            # Reference traces were captured from the verified original driver;
            # see fixtures/provenance.json. No checkout of that project is needed.
            with gzip.open(ROOT / f'tests/fixtures/huawei_a{revision}.trace.gz', 'rt') as reference:
                expected = reference.read().splitlines()
            # This driver yields to FreeRTOS every 8 rows (69 x 1 ms).
            self.assertEqual(trace.count('E delay 1'), 69)
            self.assertEqual([line for line in trace if line != 'E delay 1'], expected,
                             f'A{revision}: SPI bytes/reset/delays differ')
            for mode in ('boot', 'null', 'busy', 'refresh_timeout'):
                subprocess.run([str(binary), mode], stdout=subprocess.DEVNULL, check=True)
    def test_invalid_revision_rejected(self):
        result = subprocess.run(['g++', '-std=c++11', '-DHUAWEI_EPD_REVISION=2', '-fsyntax-only',
                                 str(ROOT / 'src/receiver.cpp')], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('HUAWEI_EPD_REVISION must be', result.stderr)


if __name__ == '__main__':
    unittest.main(verbosity=2)
