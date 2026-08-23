/// Dataset statistics from GET /api/training/statistics.
class TrainingStatistics {
  const TrainingStatistics({
    required this.totalRecordings,
    required this.byKeyword,
    required this.bySpeaker,
    required this.byAgeGroup,
  });

  factory TrainingStatistics.fromJson(Map<String, dynamic> json) {
    return TrainingStatistics(
      totalRecordings: json['total_recordings'] as int? ?? 0,
      byKeyword: _castStringIntMap(json['by_keyword']),
      bySpeaker: _castStringIntMap(json['by_speaker']),
      byAgeGroup: _castStringIntMap(json['by_age_group']),
    );
  }

  final int totalRecordings;
  final Map<String, int> byKeyword;
  final Map<String, int> bySpeaker;
  final Map<String, int> byAgeGroup;

  static Map<String, int> _castStringIntMap(dynamic value) {
    if (value is! Map) return const {};
    return value.map((k, v) => MapEntry(k.toString(), (v as num?)?.toInt() ?? 0));
  }
}
