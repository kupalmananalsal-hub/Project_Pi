# Project Pi Mobile App

The Flutter mobile app currently lives at the repository root of `Project_Pi`
because this repository was scaffolded directly as a Flutter project.

Use these commands from the repository root:

```bash
flutter pub get
flutter analyze
flutter test
flutter build apk --debug
```

Current hotspot backend settings:

```text
IP: 172.20.10.8
Port: 8765
```

Install the debug APK from:

```text
build/app/outputs/flutter-apk/app-debug.apk
```

In the app, use the Status or Settings tab to change the Pi IP if the hotspot
assigns a new address.
