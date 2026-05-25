# Headless Pi And APK Server

Use this flow when the Pi should boot without a monitor and the Android APK
should be installed over Wi-Fi.

## Mobile Hotspot Autoconnect

Create one NetworkManager Wi-Fi profile on the Pi. Keep the real hotspot
password out of the repository:

```bash
sudo nmcli con add type wifi con-name "AutoHotspot" ifname wlan0 ssid "<HOTSPOT_SSID>"
sudo nmcli con modify "AutoHotspot" wifi-sec.key-mgmt wpa-psk
sudo nmcli con modify "AutoHotspot" wifi-sec.psk "<HOTSPOT_PASSWORD>"
sudo nmcli con modify "AutoHotspot" connection.autoconnect yes
sudo nmcli con modify "AutoHotspot" connection.autoconnect-priority 10
sudo nmcli con up "AutoHotspot"
```

Check the profile and the active wireless network:

```bash
nmcli con show "AutoHotspot"
nmcli con show --active
iwgetid -r
ip addr show wlan0
```

If another Wi-Fi profile keeps winning boot-time selection, list profiles with
`nmcli con show` and disable autoconnect on the unwanted profile:

```bash
sudo nmcli con modify "<OTHER_WIFI_PROFILE>" connection.autoconnect no
```

## Build And Serve The APK

This repository is the Flutter project root, so build from `~/Project_Pi`:

```bash
cd ~/Project_Pi
flutter build apk --debug
cp raspberry_pi/apk_server/index.html build/app/outputs/flutter-apk/index.html
```

Install the systemd HTTP server once:

```bash
cd ~/Project_Pi
sudo cp raspberry_pi/systemd/apk-server.service /etc/systemd/system/apk-server.service
sudo systemctl daemon-reload
sudo systemctl enable --now apk-server.service
sudo systemctl status apk-server.service --no-pager
```

The service serves:

```text
/home/thesis/Project_Pi/build/app/outputs/flutter-apk/
```

After each APK rebuild, copy `index.html` again if the build output directory
was recreated. The service does not need a restart when only the APK changes.

## Install From The Phone

Connect the phone to the same hotspot as the Pi. The current hotspot address is:

```text
http://10.159.83.236:8080/
```

If the hotspot assigns a different address later, find it with `hostname -I`
on the Pi, then open:

```text
http://<PI_IP>:8080/
```

The direct debug APK path is:

```text
http://10.159.83.236:8080/app-debug.apk
```

Android may ask for permission to install apps downloaded by that browser.
