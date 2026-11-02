import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'providers/app_services_provider.dart';
import 'providers/settings_provider.dart';
import 'screens/app_shell.dart';
import 'services/api_token.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  // Before runApp: the auto-connect on first build needs the token.
  try {
    await ApiToken.load();
  } catch (_) {
    // Unreadable secure storage: the Pi will reject requests and Settings asks for the token.
  }
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
  var scheme = ColorScheme.fromSeed(
    seedColor: const Color(0xFF00A884),
    brightness: brightness,
    surface: brightness == Brightness.dark ? const Color(0xFF141D27) : null,
  );
  if (brightness == Brightness.dark) {
    scheme = scheme.copyWith(
      surfaceContainerLow: const Color(0xFF141D27),
      surfaceContainer: const Color(0xFF18232E),
      surfaceContainerHigh: const Color(0xFF1D2935),
      surfaceContainerHighest: const Color(0xFF26333F),
      onSurface: const Color(0xFFE4EBF3),
      onSurfaceVariant: const Color(0xFFADBCCB),
      outlineVariant: const Color(0xFF304052),
    );
  }

  return ThemeData(
    useMaterial3: true,
    fontFamily: 'Roboto',
    brightness: brightness,
    colorScheme: scheme,
    scaffoldBackgroundColor: brightness == Brightness.dark
        ? const Color(0xFF0B121A)
        : null,
    cardTheme: CardThemeData(
      elevation: 0,
      margin: const EdgeInsets.only(bottom: 16),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(20),
        side: BorderSide(color: scheme.outlineVariant.withValues(alpha: .5)),
      ),
    ),
    appBarTheme: AppBarTheme(
      backgroundColor: brightness == Brightness.dark
          ? const Color(0xFF0B121A)
          : scheme.surface,
      surfaceTintColor: Colors.transparent,
      titleTextStyle: TextStyle(
        fontFamily: 'Roboto',
        color: scheme.onSurface,
        fontSize: 20,
        fontWeight: FontWeight.w700,
      ),
    ),
    dividerTheme: DividerThemeData(
      color: scheme.outlineVariant.withValues(alpha: .5),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(minimumSize: const Size(48, 48)),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(minimumSize: const Size(48, 48)),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      border: OutlineInputBorder(borderRadius: BorderRadius.circular(8)),
    ),
    navigationBarTheme: NavigationBarThemeData(
      height: 72,
      backgroundColor: scheme.surface,
      indicatorShape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(8),
      ),
    ),
  );
}
