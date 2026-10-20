#!/usr/bin/env bash
# Run on the Raspberry Pi:  sudo ./install.sh
set -euo pipefail
[ "$EUID" -eq 0 ] || { echo "Run with sudo"; exit 1; }
HERE="$(cd "$(dirname "$0")" && pwd)"

apt-get update
apt-get install -y python3-evdev

# 1. Enable USB device (gadget) mode on the USB-C port
CFG=/boot/firmware/config.txt
[ -f "$CFG" ] || CFG=/boot/config.txt
# Stock config.txt has "dtoverlay=dwc2,dr_mode=host" under [cm5], so only
# count a peripheral-mode line that sits in the [all] section.
if ! awk '/^\[/{s=$0} s=="[all]" && /^dtoverlay=dwc2,dr_mode=peripheral/{f=1} END{exit !f}' "$CFG"; then
  printf '\n[all]\ndtoverlay=dwc2,dr_mode=peripheral\n' >> "$CFG"
fi
grep -q '^dwc2$' /etc/modules || echo 'dwc2' >> /etc/modules

# 2. Gadget setup script: makes the Pi look like a USB mouse
cat > /usr/local/bin/hid-gadget-setup.sh <<'GADGET'
#!/bin/bash
set -e
modprobe libcomposite
G=/sys/kernel/config/usb_gadget/mousebridge
[ -d "$G" ] && exit 0
mkdir -p "$G" && cd "$G"
echo 0x1d6b > idVendor
echo 0x0104 > idProduct
echo 0x0101 > bcdDevice   # bump when report_desc changes so hosts re-read it
echo 0x0200 > bcdUSB
mkdir -p strings/0x409
echo "pimouse0001"      > strings/0x409/serialnumber
echo "Pi Mouse Bridge"  > strings/0x409/manufacturer
echo "Pi USB Mouse"     > strings/0x409/product
mkdir -p configs/c.1/strings/0x409
echo "Mouse" > configs/c.1/strings/0x409/configuration
echo 250 > configs/c.1/MaxPower
mkdir -p functions/hid.usb0
# Not a boot-interface device: a host that switches a boot mouse into boot
# protocol only reads 3 bytes (buttons, X, Y) and drops the scroll wheel.
echo 0 > functions/hid.usb0/protocol
echo 0 > functions/hid.usb0/subclass
echo 5 > functions/hid.usb0/report_length
# 5 buttons, relative X/Y, vertical wheel, horizontal pan (5-byte reports)
echo -ne '\x05\x01\x09\x02\xA1\x01\x09\x01\xA1\x00\x05\x09\x19\x01\x29\x05\x15\x00\x25\x01\x95\x05\x75\x01\x81\x02\x95\x01\x75\x03\x81\x03\x05\x01\x09\x30\x09\x31\x09\x38\x15\x81\x25\x7F\x75\x08\x95\x03\x81\x06\x05\x0C\x0A\x38\x02\x15\x81\x25\x7F\x75\x08\x95\x01\x81\x06\xC0\xC0' > functions/hid.usb0/report_desc
ln -s functions/hid.usb0 configs/c.1/
# dwc2 can come up a little after this service starts
for _ in $(seq 20); do [ -n "$(ls /sys/class/udc)" ] && break; sleep 0.5; done
ls /sys/class/udc | head -n1 > UDC
GADGET
chmod +x /usr/local/bin/hid-gadget-setup.sh

# 3. Bridge app
mkdir -p /opt/mouse-bridge
cp "$HERE/mouse_bridge.py" /opt/mouse-bridge/
chmod +x /opt/mouse-bridge/mouse_bridge.py

# 4. systemd services
cat > /etc/systemd/system/hid-gadget.service <<'UNIT'
[Unit]
Description=USB HID mouse gadget
After=local-fs.target
[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/local/bin/hid-gadget-setup.sh
[Install]
WantedBy=multi-user.target
UNIT

cat > /etc/systemd/system/mouse-bridge.service <<'UNIT'
[Unit]
Description=Mouse bridge (Pi mouse -> Mac)
After=hid-gadget.service
Requires=hid-gadget.service
[Service]
ExecStart=/usr/bin/python3 /opt/mouse-bridge/mouse_bridge.py
Restart=always
RestartSec=2
[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable hid-gadget.service mouse-bridge.service
echo
echo "Done. Reboot now:  sudo reboot"
