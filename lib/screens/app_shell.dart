import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../providers/alerts_provider.dart';
import '../widgets/alert_overlay.dart';
import 'controls_screen.dart';
import 'direction_overlay.dart';
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
    final pendingGuidance = ref.watch(
      alertsProvider.select((state) => state.pendingGuidance),
    );
    final pendingGuidanceHumanDetected = ref.watch(
      alertsProvider.select((state) => state.pendingGuidanceHumanDetected),
    );

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
        if (pendingGuidance != null && activeAlert == null)
          DirectionOverlay(
            event: pendingGuidance,
            humanDetected: pendingGuidanceHumanDetected,
            onConfirm: () {
              ref.read(alertsProvider.notifier).confirmGuidanceAlert();
            },
            onDismiss: () {
              ref.read(alertsProvider.notifier).dismissGuidance();
            },
          ),
        if (activeAlert != null)
          AlertOverlay(
            event: activeAlert,
            humanDetected: activeAlertHumanDetected,
            onDismiss: () {
              ref.read(alertsProvider.notifier).dismissActiveAlert();
            },
          ),
      ],
    );
  }
}
