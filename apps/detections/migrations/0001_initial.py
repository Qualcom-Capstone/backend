from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Detection",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "vehicle_id",
                    models.BigIntegerField(
                        blank=True,
                        db_index=True,
                        null=True,
                        verbose_name="차량 ID",
                    ),
                ),
                (
                    "detected_speed",
                    models.FloatField(verbose_name="감지 속도"),
                ),
                (
                    "speed_limit",
                    models.FloatField(default=60.0, verbose_name="제한 속도"),
                ),
                (
                    "location",
                    models.CharField(
                        blank=True, max_length=255, null=True, verbose_name="위치"
                    ),
                ),
                (
                    "camera_id",
                    models.CharField(
                        blank=True,
                        max_length=50,
                        null=True,
                        verbose_name="카메라 ID",
                    ),
                ),
                (
                    "image_gcs_uri",
                    models.CharField(
                        max_length=500, verbose_name="GCS 이미지 경로"
                    ),
                ),
                (
                    "ocr_result",
                    models.CharField(
                        blank=True, max_length=20, null=True, verbose_name="OCR 결과"
                    ),
                ),
                (
                    "ocr_confidence",
                    models.FloatField(
                        blank=True, null=True, verbose_name="OCR 신뢰도"
                    ),
                ),
                (
                    "detected_at",
                    models.DateTimeField(verbose_name="감지 시간"),
                ),
                (
                    "processed_at",
                    models.DateTimeField(
                        blank=True, null=True, verbose_name="처리 완료 시간"
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("processing", "Processing"),
                            ("completed", "Completed"),
                            ("failed", "Failed"),
                        ],
                        default="pending",
                        max_length=20,
                        verbose_name="상태",
                    ),
                ),
                (
                    "error_message",
                    models.TextField(
                        blank=True, null=True, verbose_name="에러 메시지"
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "감지 내역",
                "verbose_name_plural": "감지 내역 목록",
                "db_table": "detections",
                "ordering": ["-detected_at"],
                "indexes": [
                    models.Index(
                        fields=["vehicle_id"], name="detections_vehicle_id_idx"
                    ),
                    models.Index(
                        fields=["detected_at"], name="detections_detected_at_idx"
                    ),
                    models.Index(
                        fields=["status", "created_at"],
                        name="detections_status_created_idx",
                    ),
                    models.Index(
                        fields=["camera_id", "detected_at"],
                        name="detections_camera_detected_idx",
                    ),
                ],
            },
        ),
    ]
