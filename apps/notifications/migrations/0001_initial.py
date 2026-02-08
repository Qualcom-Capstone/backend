from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Notification",
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
                    "detection_id",
                    models.BigIntegerField(
                        db_index=True, verbose_name="감지 내역 ID"
                    ),
                ),
                (
                    "fcm_token",
                    models.CharField(
                        blank=True, max_length=255, null=True, verbose_name="FCM 토큰"
                    ),
                ),
                (
                    "title",
                    models.CharField(
                        blank=True, max_length=255, null=True, verbose_name="알림 제목"
                    ),
                ),
                (
                    "body",
                    models.TextField(
                        blank=True, null=True, verbose_name="알림 내용"
                    ),
                ),
                (
                    "sent_at",
                    models.DateTimeField(
                        blank=True, null=True, verbose_name="전송 시간"
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("sent", "Sent"),
                            ("failed", "Failed"),
                        ],
                        default="pending",
                        max_length=20,
                        verbose_name="상태",
                    ),
                ),
                (
                    "retry_count",
                    models.IntegerField(default=0, verbose_name="재시도 횟수"),
                ),
                (
                    "error_message",
                    models.TextField(
                        blank=True, null=True, verbose_name="에러 메시지"
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "verbose_name": "알림",
                "verbose_name_plural": "알림 목록",
                "db_table": "notifications",
                "ordering": ["-created_at"],
                "indexes": [
                    models.Index(
                        fields=["detection_id"],
                        name="notifications_detection_id_idx",
                    ),
                    models.Index(
                        fields=["status", "retry_count"],
                        name="notifications_status_retry_idx",
                    ),
                    models.Index(
                        fields=["sent_at"], name="notifications_sent_at_idx"
                    ),
                ],
            },
        ),
    ]
