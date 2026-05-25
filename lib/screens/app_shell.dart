import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../providers/alerts_provider.dart';
import '../providers/thermal_provider.dart';
import '../widgets/alert_overlay.dart';
import 'controls_screen.dart';
import 'history_screen.dart';
import 'monitor_screen.dart';
import 'settings_screen.dart';

class AppShell extends ConsumerStatefulWidget {
  const AppShell({super.key});

  @override
  ConsumerState<AppShell> createState() => _AppShellState();
}

class _AppShellState extends ConsumerState<AppShell> {
  int _selectedIndex = 0;

  static const _screens = [MonitorScreen(), HistoryScreen(), ControlsScreen()];

  @override
  Widget build(BuildContext context) {
    final activeAlert = ref.watch(
      alertsProvider.select((state) => state.activeAlert),
    );
    final activeAlertHumanDetected = ref.watch(
      alertsProvider.select((state) => state.activeAlertHumanDetected),
    );
    final activeAlertThermalFrame = ref.watch(
      alertsProvider.select((state) => state.activeAlertThermalFrame),
    );
    final thermal = ref.watch(thermalProvider);

    final thermalRange = activeAlertThermalFrame?.clippedTemperatureRange();
    final alertThermalMin = thermalRange?.min ?? thermal.displayMinTemp;
    final alertThermalMax = thermalRange?.max ?? thermal.displayMaxTemp;

    return Stack(
      children: [
        Scaffold(
          appBar: AppBar(
            title: const Text('Project Pi'),
            actions: [
              IconButton(
                tooltip: 'Settings',
                onPressed: () {
                  Navigator.of(context).push(
                    MaterialPageRoute<void>(
                      builder: (context) => const SettingsScreen(),
                    ),
                  );
                },
                icon: const Icon(Icons.settings_rounded),
              ),
            ],
          ),
          body: _screens[_selectedIndex],
          bottomNavigationBar: NavigationBar(
            selectedIndex: _selectedIndex,
            onDestinationSelected: (index) {
              setState(() => _selectedIndex = index);
            },
            destinations: const [
              NavigationDestination(
                icon: Icon(Icons.sensors_rounded),
                label: 'Monitor',
              ),
              NavigationDestination(
                icon: Icon(Icons.history_rounded),
                label: 'History',
              ),
              NavigationDestination(
                icon: Icon(Icons.tune_rounded),
                label: 'Controls',
              ),
            ],
          ),
        ),
        if (activeAlert != null)
          AlertOverlay(
            event: activeAlert,
            humanDetected: activeAlertHumanDetected,
            thermalFrame: activeAlertThermalFrame,
            thermalColorMap: thermal.colorMap,
            thermalMinTemp: alertThermalMin,
            thermalMaxTemp: alertThermalMax,
            onDismiss: () {
              ref.read(alertsProvider.notifier).dismissActiveAlert();
            },
          ),
      ],
    );
  }
}
