#!/usr/bin/env python3
"""macOS sender: prepare an image, upload over CoreBluetooth, wait for display."""
import argparse
import asyncio
from pathlib import Path
import secrets
import sys

from image_processing import FRAME_BYTES, prepare_image
import protocol as p


async def read_status(client):
    if not client.is_connected:
        raise ConnectionError('蓝牙连接已断开；请重新发送图片')
    return p.Status.parse(await asyncio.wait_for(client.read_gatt_char(p.STATUS), 10))


async def wait_status(client, predicate, timeout, transfer_id=None):
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        status = await read_status(client)
        if transfer_id is None or status.transfer_id == transfer_id:
            if transfer_id is not None:
                status.check_error()
            if predicate(status):
                return status
        await asyncio.sleep(0.1)
    raise TimeoutError('等待设备状态超时；若已提交图片，请先查看屏幕是否完成刷新')


async def send_frame(client, payload, packet_size=None, progress=print, refresh_timeout=180):
    if len(payload) != FRAME_BYTES:
        raise ValueError('图像必须恰好为 105984 字节')
    info = p.DeviceInfo.parse(await client.read_gatt_char(p.INFO))
    initial = await read_status(client)
    if initial.state in (p.RECEIVING, p.QUEUED, p.REFRESHING):
        progress('设备正在处理上一张图，等待完成……')
        await wait_status(client, lambda s: s.state not in (p.RECEIVING, p.QUEUED, p.REFRESHING), refresh_timeout)
    size = packet_size or min(info.max_packet, max(20, client.mtu_size - 3))
    if not 20 <= size <= info.max_packet:
        raise ValueError(f'每包长度应在 20 到 {info.max_packet} 之间')
    transfer_id = secrets.randbits(32)
    committed = False
    progress(f'已连接 A{info.revision}，上传 {len(payload)} 字节，每包最多 {size - 8} 字节图像')
    try:
        await asyncio.wait_for(client.write_gatt_char(p.CONTROL, p.begin(transfer_id, payload), response=True), 10)
        status = await wait_status(client, lambda s: s.state == p.RECEIVING, 5, transfer_id)
        offset, checkpoint = status.received, status.received
        sent_limit = offset
        while offset < len(payload):
            block = payload[offset:offset + size - 8]
            sent_limit = max(sent_limit, offset + len(block))
            try:
                await asyncio.wait_for(client.write_gatt_char(p.DATA, p.chunk(transfer_id, offset, block), response=True), 10)
            except Exception:
                if size == 20 or not client.is_connected:
                    raise
                # A lost response may follow a successful write. Read the
                # authoritative offset before retrying with minimum-size ATT.
                await asyncio.sleep(0.1)
                status = await read_status(client)
                status.check_error()
                if status.transfer_id != transfer_id or status.state != p.RECEIVING:
                    raise RuntimeError('设备传输状态已改变')
                if not offset <= status.received <= offset + len(block):
                    raise RuntimeError('设备接收偏移异常')
                offset = status.received
                size = 20
                progress('切换为兼容数据包大小，继续上传……')
                continue
            offset += len(block)
            if offset - checkpoint >= 4096 or offset == len(payload):
                # A lost ATT response followed by a stale status can make us
                # retry an accepted prefix. The receiver may already be ahead.
                status = await wait_status(client, lambda s: s.received >= offset and s.state == p.RECEIVING, 5, transfer_id)
                if status.received > sent_limit:
                    raise RuntimeError('设备接收偏移超出已发送数据')
                offset = status.received
                progress(f'上传 {offset / len(payload):.0%} ({offset}/{len(payload)})')
                checkpoint = offset
        await asyncio.wait_for(client.write_gatt_char(p.CONTROL, p.commit(transfer_id), response=True), 10)
        committed = True
        progress('上传完成，等待屏幕刷新……')
        await wait_status(client, lambda s: s.state == p.DONE, refresh_timeout, transfer_id)
        progress('屏幕刷新完成。设备可继续接收下一张图片。')
    except BaseException:
        if not committed and client.is_connected:
            try:
                await asyncio.wait_for(client.write_gatt_char(p.CONTROL, p.abort(transfer_id), response=True), 3)
            except Exception:
                pass
        raise


async def discover(timeout):
    from bleak import BleakScanner
    found = await BleakScanner.discover(timeout=timeout, service_uuids=[p.SERVICE], return_adv=True)
    return [(device, advertising.local_name or device.name or '(未命名)') for device, advertising in found.values()]


async def run_ble(args, payload):
    from bleak import BleakClient
    print('正在扫描 InkBLE 设备……', flush=True)
    devices = await discover(args.scan_seconds)
    if args.scan:
        for device, name in devices:
            print(f'{name}  {device.address}')
        if not devices:
            print('未找到设备，请确认固件已启动且未被其他设备连接。')
        return
    if args.device:
        devices = [(device, name) for device, name in devices
                   if args.device.casefold() in (name.casefold(), device.address.casefold())]
    if not devices:
        raise RuntimeError('未找到目标设备；请检查蓝牙权限、设备供电和连接状态')
    if len(devices) != 1:
        raise RuntimeError('找到多台设备，请用 --device 指定名称或 UUID：\n' + '\n'.join(name for _, name in devices))
    device, name = devices[0]
    print('连接 ' + name, flush=True)
    async with BleakClient(device, services=[p.SERVICE], timeout=20) as client:
        await send_frame(client, payload, args.packet_size, lambda text: print(text, flush=True), args.refresh_timeout)


def main():
    parser = argparse.ArgumentParser(description='InkBLE macOS 图片发送工具（自动按比例顺时针旋转、Atkinson 四色、等比留白）')
    parser.add_argument('image', type=Path, nargs='?', help='待发送图片（PNG/JPEG/WebP 等）')
    parser.add_argument('--scan', action='store_true', help='只扫描并列出设备')
    parser.add_argument('--device', help='设备名称或 macOS 蓝牙 UUID；只有一台设备时可省略')
    parser.add_argument('--preview', type=Path, help='保存四色预览 PNG')
    parser.add_argument('--raw-output', type=Path, help='保存 105984 字节原始四色数据')
    parser.add_argument('--prepare-only', action='store_true', help='只转换图片，不使用蓝牙')
    parser.add_argument('--packet-size', type=int, help='每个 GATT 数据包总长度；默认协商，20 为兼容模式')
    parser.add_argument('--scan-seconds', type=float, default=6)
    parser.add_argument('--refresh-timeout', type=float, default=180)
    args = parser.parse_args()
    if not args.scan and not args.image:
        parser.error('请指定图片，或使用 --scan')
    if args.prepare_only and not (args.preview or args.raw_output):
        parser.error('--prepare-only 请同时指定 --preview 或 --raw-output')
    try:
        payload = None
        if not args.scan:
            print('正在按屏幕比例选择方向、等比缩放、居中留白并进行 Atkinson 四色转换……', flush=True)
            payload, preview = prepare_image(args.image)
            if args.preview:
                preview.save(args.preview, format='PNG')
                print('预览已保存：' + str(args.preview))
            if args.raw_output:
                args.raw_output.write_bytes(payload)
            if args.prepare_only:
                print(f'转换完成：768×552，{len(payload)} 字节')
                return 0
        asyncio.run(run_ble(args, payload))
        return 0
    except KeyboardInterrupt:
        print('\n已停止。未提交的图片不会刷新屏幕。', file=sys.stderr)
        return 130
    except Exception as error:
        print('错误：' + str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
