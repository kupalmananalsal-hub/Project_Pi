import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'screens/resident_mode_screen.dart';
import 'screens/resident_settings_screen.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  SystemChrome.setPreferredOrientations([
    DeviceOrientation.portraitUp,
    DeviceOrientation.portraitDown,
  ]);
  runApp(const ResidentApp());
}

class ResidentApp extends StatelessWidget {
  const ResidentApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Resident Alert',
      debugShowCheckedModeBanner: false,
      theme: ThemeData.dark().copyWith(
        scaffoldBackgroundColor: Colors.black,
        colorScheme: const ColorScheme.dark(
          primary: Color(0xFFE53935),
          surface: Colors.black,
        ),
      ),
      routes: {
        '/': (_) => const _ResidentHomeWrapper(),
        '/settings': (_) => const ResidentSettingsScreen(),
      },
    );
  }
}

class _ResidentHomeWrapper extends StatefulWidget {
  const _ResidentHomeWrapper();

  @override
  State<_ResidentHomeWrapper> createState() => _ResidentHomeWrapperState();
}

class _ResidentHomeWrapperState extends State<_ResidentHomeWrapper> {
  late final Future<bool> _hasSavedHostFuture;

  @override
  void initState() {
    super.initState();
    _hasSavedHostFuture = _checkSavedHost();
  }

  Future<bool> _checkSavedHost() async {
    final prefs = await SharedPreferences.getInstance();
    final host = prefs.getString('host');
    return host != null && host.trim().isNotEmpty;
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<bool>(
      future: _hasSavedHostFuture,
      builder: (context, snapshot) {
        if (snapshot.connectionState == ConnectionState.waiting) {
          return const Scaffold(
            backgroundColor: Colors.black,
            body: Center(
              child: CircularProgressIndicator(
                color: Color(0xFFE53935),
              ),
            ),
          );
        }
        final hasSavedHost = snapshot.data ?? false;
        if (!hasSavedHost) {
          return const ResidentSettingsScreen(isInitialSetup: true);
        }
        return const ResidentModeScreen();
      },
    );
  }
}
