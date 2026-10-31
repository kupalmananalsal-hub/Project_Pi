import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:thermal_audio_monitor/providers/connection_provider.dart';

DioException _status(int code) {
  final request = RequestOptions(path: '/api/status');
  return DioException(
    requestOptions: request,
    response: Response(requestOptions: request, statusCode: code),
    type: DioExceptionType.badResponse,
  );
}

void main() {
  test('401 asks for the token and names a locked Pi', () {
    final message = piConnectionErrorMessage(_status(401));
    expect(message, contains('API token in Settings'));
    expect(message, contains('locked'));
  });

  test('other failures keep the generic message', () {
    expect(
      piConnectionErrorMessage(_status(500)),
      'Unable to connect to Raspberry Pi.',
    );
    expect(
      piConnectionErrorMessage(StateError('x')),
      'Unable to connect to Raspberry Pi.',
    );
  });
}
