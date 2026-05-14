import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'providers/app_services_provider.dart';
import 'providers/settings_provider.dart';
import 'screens/app_shell.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const ProviderScope(child: ThermalAudioMonitorApp()));
}

class ThermalAudioMonitorApp extends ConsumerWidget {
  const ThermalAudioMonitorApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final settings = ref.watch(settingsProvider);

    return MaterialApp(
      debugShowCheckedModeBanner: false,
      title: 'Project Pi',
      themeMode: settings.darkMode ? ThemeMode.dark : ThemeMode.light,
      theme: _buildTheme(Brightness.light),
      darkTheme: _buildTheme(Brightness.dark),
      home: const AppBootstrap(child: AppShell()),
    );
  }
}

class AppBootstrap extends ConsumerStatefulWidget {
  const AppBootstrap({super.key, required this.child});

  final Widget child;

  @override
  ConsumerState<AppBootstrap> createState() => _AppBootstrapState();
}

class _AppBootstrapState extends ConsumerState<AppBootstrap> {
  @override
  void initState() {
    super.initState();
    Future.microtask(() async {
      try {
        await ref.read(alertRuntimeServiceProvider).initialize();
      } catch (_) {
        // Plugin channels are unavailable in widget tests and some desktop runs.
      }
    });
  }

  @override
  Widget build(BuildContext context) => widget.child;
}

ThemeData _buildTheme(Brightness brightness) {
  final scheme = ColorScheme.fromSeed(
    seedColor: const Color(0xFF00A884),
    brightness: brightness,
  );

  return ThemeData(
    useMaterial3: true,
    brightness: brightness,
    colorScheme: scheme,
    scaffoldBackgroundColor: brightness == Brightness.dark
        ? const Color(0xFF101413)
        : null,
    cardTheme: CardThemeData(
      margin: const EdgeInsets.only(bottom: 10),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      border: OutlineInputBorder(borderRadius: BorderRadius.circular(8)),
    ),
    navigationBarTheme: NavigationBarThemeData(
      indicatorShape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(8),
      ),
    ),
  );
}
