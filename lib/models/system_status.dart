class SystemStatus {
  const SystemStatus({
    required this.receivedAt,
    this.cpuTempC,
    this.ramUsagePercent,
    this.diskUsagePercent,
    this.uptime = 'Unavailable',
    this.i2cDevices = const [],
    this.thermalAddress,
    this.thermalError,
  });

  final DateTime receivedAt;
  final double? cpuTempC;
  final double? ramUsagePercent;
  final double? diskUsagePercent;
  final String uptime;
  final List<String> i2cDevices;
  final String? thermalAddress;
  final String? thermalError;

  factory SystemStatus.fromJson(Map<String, dynamic> json) {
    final ram = json['ram'] is Map<String, dynamic>
        ? json['ram'] as Map<String, dynamic>
        : <String, dynamic>{};
    final disk = json['disk'] is Map<String, dynamic>
        ? json['disk'] as Map<String, dynamic>
        : <String, dynamic>{};
    final thermal = json['thermal'] is Map<String, dynamic>
        ? json['thermal'] as Map<String, dynamic>
        : <String, dynamic>{};

    return SystemStatus(
      receivedAt: DateTime.now(),
      cpuTempC: _asDouble(
        json['cpu_temp_c'] ??
            json['cpu_temp'] ??
            json['cpu_temperature'] ??
            json['temperature'],
      ),
      ramUsagePercent: _asDouble(
        json['ram_usage_percent'] ??
            json['ram_percent'] ??
            json['ram_usage'] ??
            json['memory_usage'] ??
            ram['percent'] ??
            ram['usage_percent'],
      ),
      diskUsagePercent: _asDouble(
        json['disk_usage_percent'] ??
            json['disk_percent'] ??
            json['disk_usage'] ??
            disk['percent'],
      ),
      uptime: _formatUptime(json['uptime'] ?? json['uptime_seconds']),
      i2cDevices: _asStringList(
        json['i2c_devices'] ?? json['i2c'] ?? json['devices'],
      ),
      thermalAddress: thermal['address']?.toString(),
      thermalError: thermal['error']?.toString(),
    );
  }

  static double? _asDouble(dynamic value) {
    if (value is num) {
      return value.toDouble();
    }
    if (value is String) {
      return double.tryParse(value.replaceAll(RegExp('[^0-9.-]'), ''));
    }
    return null;
  }

  static List<String> _asStringList(dynamic value) {
    if (value is List) {
      return value.map((item) => item.toString()).toList(growable: false);
    }
    if (value is String && value.isNotEmpty) {
      return value.split(',').map((item) => item.trim()).toList();
    }
    return const [];
  }

  static String _formatUptime(dynamic value) {
    if (value is num) {
      final duration = Duration(seconds: value.round());
      final days = duration.inDays;
      final hours = duration.inHours.remainder(24);
      final minutes = duration.inMinutes.remainder(60);
      if (days > 0) {
        return '${days}d ${hours}h ${minutes}m';
      }
      if (hours > 0) {
        return '${hours}h ${minutes}m';
      }
      return '${minutes}m';
    }
    if (value is String && value.trim().isNotEmpty) {
      return value.trim();
    }
    return 'Unavailable';
  }
}
