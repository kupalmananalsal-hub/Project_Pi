/// A background training job from GET /api/training/jobs/{job_id}.
class TrainingJob {
  const TrainingJob({
    required this.jobId,
    required this.type,
    required this.status,
    this.result,
    this.error,
    this.createdAt,
    this.completedAt,
  });

  factory TrainingJob.fromJson(Map<String, dynamic> json) => TrainingJob(
    jobId: json['job_id'] as String? ?? '',
    type: json['job_type'] as String? ?? json['type'] as String? ?? '',
    status: json['status'] as String? ?? 'unknown',
    result: json['result'] as Map<String, dynamic>?,
    error: json['error'] as String?,
    createdAt: json['created_at'] as String?,
    completedAt: json['finished_at'] as String? ?? json['completed_at'] as String?,
  );

  final String jobId;
  final String type;
  final String status;
  final Map<String, dynamic>? result;
  final String? error;
  final String? createdAt;
  final String? completedAt;

  bool get isRunning => status == 'queued' || status == 'running';
  bool get isSucceeded => status == 'succeeded';
  bool get isFailed => status == 'failed';
}
