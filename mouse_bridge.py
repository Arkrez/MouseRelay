#!/usr/bin/env python3
"""
Reads a physical USB mouse plugged into the Pi and forwards its movement,
buttons and scroll wheels to the Mac through the Pi's USB gadget HID device
(/dev/hidg0). Hot-plug safe: unplug/replug the mouse and it reconnects.
"""
import asyncio
import os
import struct
import sys

import evdev
from evdev import InputDevice, ecodes as e

HIDG_PATH = "/dev/hidg0"
BUTTON_BITS = {
    e.BTN_LEFT: 0x01,
    e.BTN_RIGHT: 0x02,
    e.BTN_MIDDLE: 0x04,
    e.BTN_SIDE: 0x08,
    e.BTN_EXTRA: 0x10,
}

buttons = 0
active = set()
hid_fd = None


def open_hid():
    global hid_fd
    while hid_fd is None:
        try:
            hid_fd = os.open(HIDG_PATH, os.O_WRONLY | os.O_NONBLOCK)
        except OSError as err:
            print(f"Waiting for {HIDG_PATH}: {err}", file=sys.stderr)
            import time
            time.sleep(2)


def clamp(v):
    return max(-127, min(127, v))


def send_report(dx, dy, wheel, hwheel=0):
    """Send HID reports; deltas are int8, so large moves are split up."""
    global hid_fd
    first = True
    while first or dx or dy or wheel or hwheel:
        first = False
        sx, sy, sw, sh = clamp(dx), clamp(dy), clamp(wheel), clamp(hwheel)
        dx, dy, wheel, hwheel = dx - sx, dy - sy, wheel - sw, hwheel - sh
        try:
            os.write(hid_fd, struct.pack("<Bbbbb", buttons, sx, sy, sw, sh))
        except BlockingIOError:
            pass  # Mac busy/asleep; drop the report
        except OSError as err:
            # Host disconnected or suspended; keep running, drop reports
            if err.errno not in (11, 108, 107, 19):
                print(f"HID write error: {err}", file=sys.stderr)


async def handle_device(dev: InputDevice):
    global buttons
    print(f"Forwarding: {dev.name} ({dev.path})")
    rel = dev.capabilities().get(e.EV_REL, [])
    # Some mice only report high-resolution scrolling (120 units per notch).
    hires_v = e.REL_WHEEL not in rel and e.REL_WHEEL_HI_RES in rel
    hires_h = e.REL_HWHEEL not in rel and e.REL_HWHEEL_HI_RES in rel
    hires_acc_v = hires_acc_h = 0
    dx = dy = wheel = hwheel = 0
    try:
        dev.grab()  # keep the Pi's own desktop from also reacting
        async for ev in dev.async_read_loop():
            if ev.type == e.EV_REL:
                if ev.code == e.REL_X:
                    dx += ev.value
                elif ev.code == e.REL_Y:
                    dy += ev.value
                elif ev.code == e.REL_WHEEL:
                    wheel += ev.value
                elif ev.code == e.REL_HWHEEL:
                    hwheel += ev.value
                elif ev.code == e.REL_WHEEL_HI_RES and hires_v:
                    hires_acc_v += ev.value
                    notches = int(hires_acc_v / 120)
                    hires_acc_v -= notches * 120
                    wheel += notches
                elif ev.code == e.REL_HWHEEL_HI_RES and hires_h:
                    hires_acc_h += ev.value
                    notches = int(hires_acc_h / 120)
                    hires_acc_h -= notches * 120
                    hwheel += notches
            elif ev.type == e.EV_KEY and ev.code in BUTTON_BITS:
                if ev.value:
                    buttons |= BUTTON_BITS[ev.code]
                else:
                    buttons &= ~BUTTON_BITS[ev.code]
                send_report(dx, dy, wheel, hwheel)
                dx = dy = wheel = hwheel = 0
            elif ev.type == e.EV_SYN and ev.code == e.SYN_REPORT:
                if dx or dy or wheel or hwheel:
                    send_report(dx, dy, wheel, hwheel)
                    dx = dy = wheel = hwheel = 0
    except OSError:
        pass  # device unplugged
    finally:
        try:
            dev.ungrab()
        except OSError:
            pass
        buttons = 0
        send_report(0, 0, 0)  # release any held buttons on the Mac
        active.discard(dev.path)
        print(f"Disconnected: {dev.name}")


def is_mouse(dev):
    caps = dev.capabilities()
    return (
        e.EV_REL in caps
        and e.REL_X in caps[e.EV_REL]
        and e.EV_KEY in caps
        and e.BTN_LEFT in caps[e.EV_KEY]
    )


async def main():
    open_hid()
    print("Mouse bridge running.")
    while True:
        for path in evdev.list_devices():
            if path in active:
                continue
            try:
                dev = InputDevice(path)
                if is_mouse(dev):
                    active.add(path)
                    asyncio.create_task(handle_device(dev))
            except OSError:
                pass
        await asyncio.sleep(2)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
