import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../providers/alerts_provider.dart';
import '../widgets/alert_overlay.dart';
import 'audio_alerts_screen.dart';
import 'connection_status_screen.dart';
import 'controls_screen.dart';
import 'settings_screen.dart';
import 'thermal_camera_screen.dart';

class AppShell extends ConsumerStatefulWidget {
  const AppShell({super.key});

  @override
  ConsumerState<AppShell> createState() => _AppShellState();
}

class _AppShellState extends ConsumerState<AppShell> {
  int _selectedIndex = 0;

  static const _screens = [
    ConnectionStatusScreen(),
    ThermalCameraScreen(),
    AudioAlertsScreen(),
    ControlsScreen(),
    SettingsScreen(),
  ];

  @override
  Widget build(BuildContext context) {
    final activeAlert = ref.watch(
      alertsProvider.select((state) => state.activeAlert),
    );

    return Stack(
      children: [
        Scaffold(
          appBar: AppBar(title: const Text('Pi Thermal Monitor')),
          body: _screens[_selectedIndex],
          bottomNavigationBar: NavigationBar(
            selectedIndex: _selectedIndex,
            onDestinationSelected: (index) {
              setState(() => _selectedIndex = index);
            },
            destinations: const [
              NavigationDestination(
                icon: Icon(Icons.sensors_rounded),
                label: 'Status',
              ),
              NavigationDestination(
                icon: Icon(Icons.thermostat_rounded),
                label: 'Thermal',
              ),
              NavigationDestination(
                icon: Icon(Icons.graphic_eq_rounded),
                label: 'Alerts',
              ),
              NavigationDestination(
                icon: Icon(Icons.tune_rounded),
                label: 'Controls',
              ),
              NavigationDestination(
                icon: Icon(Icons.settings_rounded),
                label: 'Settings',
              ),
            ],
          ),
        ),
        if (activeAlert != null)
          AlertOverlay(
            event: activeAlert,
            onDismiss: () {
              ref.read(alertsProvider.notifier).dismissActiveAlert();
            },
          ),
      ],
    );
  }
}
