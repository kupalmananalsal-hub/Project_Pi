/// A canonical keyword from the training vocabulary.
class TrainingKeyword {
  const TrainingKeyword({required this.keyword, required this.slug, required this.language});

  factory TrainingKeyword.fromJson(Map<String, dynamic> json) => TrainingKeyword(
    keyword: json['keyword'] as String? ?? '',
    slug: json['slug'] as String? ?? '',
    language: json['language'] as String? ?? 'unknown',
  );

  final String keyword;
  final String slug;
  final String language;
}
