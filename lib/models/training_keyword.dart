/// A canonical keyword from the training vocabulary.
class TrainingKeyword {
  const TrainingKeyword({
    required this.keyword,
    required this.slug,
    required this.language,
  });

  factory TrainingKeyword.fromJson(Map<String, dynamic> json) =>
      TrainingKeyword(
        keyword: json['keyword'] as String? ?? '',
        slug: json['slug'] as String? ?? '',
        language: json['language'] as String? ?? 'unknown',
      );

  final String keyword;
  final String slug;
  final String language;
}

const fallbackTrainingKeywords = <TrainingKeyword>[
  TrainingKeyword(keyword: 'help', slug: 'help', language: 'en'),
  TrainingKeyword(keyword: 'help me', slug: 'help_me', language: 'en'),
  TrainingKeyword(keyword: 'save me', slug: 'save_me', language: 'en'),
  TrainingKeyword(keyword: 'please help', slug: 'please_help', language: 'en'),
  TrainingKeyword(keyword: 'emergency', slug: 'emergency', language: 'en'),
  TrainingKeyword(keyword: 'rescue', slug: 'rescue', language: 'en'),
  TrainingKeyword(keyword: 'over here', slug: 'over_here', language: 'en'),
  TrainingKeyword(keyword: 'ouch', slug: 'ouch', language: 'en'),
  TrainingKeyword(keyword: 'tulong', slug: 'tulong', language: 'fil'),
  TrainingKeyword(keyword: 'saklolo', slug: 'saklolo', language: 'fil'),
  TrainingKeyword(
    keyword: 'tulungan niyo ako',
    slug: 'tulungan_niyo_ako',
    language: 'fil',
  ),
  TrainingKeyword(
    keyword: 'tulungan mo ako',
    slug: 'tulungan_mo_ako',
    language: 'fil',
  ),
  TrainingKeyword(
    keyword: 'kailangan ko ng tulong',
    slug: 'kailangan_ko_ng_tulong',
    language: 'fil',
  ),
  TrainingKeyword(keyword: 'ang sakit', slug: 'ang_sakit', language: 'fil'),
  TrainingKeyword(keyword: 'aray', slug: 'aray', language: 'fil'),
  TrainingKeyword(keyword: 'sunog', slug: 'sunog', language: 'fil'),
  TrainingKeyword(keyword: 'agai', slug: 'agai', language: 'fil'),
];
