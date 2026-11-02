import 'dart:async';
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../models/app_settings.dart';
import '../services/device_pairing_service.dart';

class ResidentSettingsScreen extends StatefulWidget {
  const ResidentSettingsScreen({super.key, this.isInitialSetup = false});
  final bool isInitialSetup;
  @override
  State<ResidentSettingsScreen> createState() => _ResidentSettingsScreenState();
}

class _ResidentSettingsScreenState extends State<ResidentSettingsScreen> {
  final _host = TextEditingController(),
      _port = TextEditingController(text: '8765');
  final _form = GlobalKey<FormState>();
  Timer? _retry;
  bool _loading = true, _connecting = false;
  String? _message;
  int _generation = 0;
  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final prefs = await SharedPreferences.getInstance();
    if (!mounted) return;
    setState(() {
      _host.text = prefs.getString('host') ?? AppSettings.defaultHost;
      _port.text = (prefs.getInt('port') ?? 8765).toString();
      _loading = false;
    });
  }

  @override
  void dispose() {
    ++_generation;
    _retry?.cancel();
    _host.dispose();
    _port.dispose();
    super.dispose();
  }

  Future<void> _connect() async {
    if (!_form.currentState!.validate()) return;
    _retry?.cancel();
    final generation = ++_generation;
    final host = AppSettings.normalizeBackendHost(_host.text)!;
    final port = int.parse(_port.text);
    setState(() {
      _connecting = true;
      _message = 'Connecting to Pi…';
    });
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString('host', host);
      await prefs.setInt('port', port);
      await DevicePairingService().ensure(host, port, 'resident');
      if (!mounted || generation != _generation) return;
      if (widget.isInitialSetup) {
        Navigator.of(context).pushReplacementNamed('/');
      } else {
        Navigator.of(context).pop(true);
      }
    } catch (error) {
      if (!mounted || generation != _generation) return;
      setState(() {
        _connecting = false;
        _message = error is PairingRequired
            ? error.message
            : 'Unable to connect. Check the IP and port.';
      });
      if (error is! PairingRequired || error.retryable) {
        _retry = Timer(const Duration(seconds: 2), _connect);
      }
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    backgroundColor: Colors.black,
    appBar: AppBar(title: const Text('Pi Connection Settings')),
    body: _loading
        ? const Center(child: CircularProgressIndicator())
        : Form(
            key: _form,
            child: ListView(
              padding: const EdgeInsets.all(24),
              children: [
                TextFormField(
                  controller: _host,
                  key: const ValueKey('pi-ip-field'),
                  decoration: const InputDecoration(
                    labelText: 'Pi IP / Hostname',
                  ),
                  onChanged: (_) {
                    _retry?.cancel();
                    ++_generation;
                    setState(() => _connecting = false);
                  },
                  validator: (value) =>
                      AppSettings.normalizeBackendHost(value) == null
                      ? 'Enter a valid IP address or hostname'
                      : null,
                ),
                const SizedBox(height: 20),
                TextFormField(
                  controller: _port,
                  key: const ValueKey('pi-port-field'),
                  keyboardType: TextInputType.number,
                  decoration: const InputDecoration(labelText: 'Port'),
                  onChanged: (_) {
                    _retry?.cancel();
                    ++_generation;
                    setState(() => _connecting = false);
                  },
                  validator: (value) {
                    final port = int.tryParse(value ?? '');
                    return port == null || port < 1 || port > 65535
                        ? 'Enter port 1–65535'
                        : null;
                  },
                ),
                const SizedBox(height: 20),
                const Text(
                  'First connection needs local operator approval on the Pi. Compare the displayed code. Future connections use securely saved credentials; the Pi address stays editable.',
                ),
                const SizedBox(height: 20),
                FilledButton(
                  key: const ValueKey('save-settings-button'),
                  onPressed: _connecting ? null : _connect,
                  child: Text(_connecting ? 'Connecting…' : 'Connect'),
                ),
                if (_message != null)
                  Padding(
                    padding: const EdgeInsets.only(top: 20),
                    child: Text(_message!),
                  ),
              ],
            ),
          ),
  );
}
