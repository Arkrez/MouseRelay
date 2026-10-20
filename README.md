# Pi Mouse Bridge

Plug a mouse into the Pi, plug the Pi into a Mac, and the mouse controls the Mac.

    [USB mouse] --USB-A--> [Raspberry Pi 4] --USB-C--> [Mac]
                            reads mouse via evdev,
                            replays it as a USB HID mouse

## Hardware
- **Raspberry Pi 4B** (recommended). Its USB-C port supports device mode, and its
  USB-A ports are free for the mouse. A Pi Zero only has one data port, so it can't
  do both. Pi 5's USB-C is not suitable for gadget mode.
- A USB-C to USB-C **data** cable (not charge-only), Pi to Mac.
- **Power:** a Pi 4 draws more than a Mac port should supply. Power the Pi through
  the 5V GPIO pins (or PoE hat) with its own supply, and use a cable/adapter
  that doesn't back-feed 5V, or accept the risk with a light load.

## Install (on the Pi)
    sudo ./install.sh
    sudo reboot

After reboot the Mac sees a "Pi USB Mouse". Move the mouse on the Pi. 

## Troubleshooting
- Logs: `journalctl -u mouse-bridge -f`
- `ls /sys/class/udc` should show a controller (e.g. `fe980000.usb`). If empty,
  check `dtoverlay=dwc2,dr_mode=peripheral` is in config.txt, then reboot.
- `ls /dev/hidg0` should exist.
- Mouse not detected: `sudo evtest` to confirm the Pi sees it.
- Use a data-capable cable.

## Notes
- The bridge grabs the physical mouse exclusively, so the Pi's own desktop
  (if any) won't react to it.
- Supports movement, 5 buttons, vertical scroll; hot-plug safe.
- macOS may show a one-time "Keyboard Setup Assistant" prompt for new HID devices;
  for a mouse this normally doesn't appear.
