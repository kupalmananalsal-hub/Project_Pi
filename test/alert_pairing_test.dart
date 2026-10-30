import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:thermal_audio_monitor/providers/alerts_provider.dart';
import 'package:thermal_audio_monitor/providers/app_services_provider.dart';
import 'package:thermal_audio_monitor/services/alert_delivery_service.dart';
import 'package:thermal_audio_monitor/services/alert_runtime_service.dart';
import 'package:thermal_audio_monitor/services/reconnecting_web_socket_service.dart';

class QuietRuntime extends AlertRuntimeService {
  @override
  Future<void> stopEmergency() async {}
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUp(() {
    SharedPreferences.setMockInitialValues({});
    FlutterSecureStorage.setMockInitialValues({});
  });

  test(
    'changed host of a previously paired installation blocks legacy socket',
    () async {
      // Pre-marker upgrade: the original hostname credential alone must protect it.
      FlutterSecureStorage.setMockInitialValues({
        'caregiver_token_raspberrypi.local': 'administrator-test-secret',
      });
      final container = ProviderContainer(
        overrides: [
          alertRuntimeServiceProvider.overrideWithValue(QuietRuntime()),
        ],
      );
      addTearDown(container.dispose);
      await container.read(alertsProvider.notifier).connect('192.0.2.10', 8765);
      final state = container.read(alertsProvider);
      expect(state.pairingState, AlertPairingState.reconfigurationRequired);
      expect(state.socketStatus, SocketConnectionStatus.disconnected);
      expect(state.error, contains('requires pairing'));
      expect(
        await CaregiverCredentials.endpointState('raspberrypi.local'),
        AlertPairingState.reliable,
      );
    },
  );

  test(
    're-pair enables new endpoint; unpair requires administrator secret',
    () async {
      await CaregiverCredentials.saveToken('old', 'administrator-test-secret');
      expect(
        await CaregiverCredentials.endpointState('new'),
        AlertPairingState.reconfigurationRequired,
      );
      await CaregiverCredentials.saveToken(
        'new',
        'new-administrator-test-secret',
      );
      expect(
        await CaregiverCredentials.endpointState('new'),
        AlertPairingState.reliable,
      );
      await expectLater(CaregiverCredentials.unpair('wrong'), throwsStateError);
      expect(
        await CaregiverCredentials.endpointState('other'),
        AlertPairingState.reconfigurationRequired,
      );
      await CaregiverCredentials.unpair('administrator-test-secret');
      expect(
        await CaregiverCredentials.endpointState('new'),
        AlertPairingState.legacy,
      );
      expect(await CaregiverCredentials.token('new'), isNull);
    },
  );

  test(
    'interrupted pairing marker without token stays blocked; fresh install permits legacy',
    () async {
      expect(
        await CaregiverCredentials.endpointState('new'),
        AlertPairingState.legacy,
      );
      FlutterSecureStorage.setMockInitialValues({
        'caregiver_pairing_required': 'true',
      });
      expect(
        await CaregiverCredentials.endpointState('new'),
        AlertPairingState.reconfigurationRequired,
      );
    },
  );
}
