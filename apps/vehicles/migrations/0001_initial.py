from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Vehicle",
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
                    "plate_number",
                    models.CharField(
                        max_length=20, unique=True, verbose_name="차량 번호"
                    ),
                ),
                (
                    "owner_name",
                    models.CharField(
                        blank=True, max_length=100, null=True, verbose_name="소유자명"
                    ),
                ),
                (
                    "owner_phone",
                    models.CharField(
                        blank=True, max_length=20, null=True, verbose_name="연락처"
                    ),
                ),
                (
                    "fcm_token",
                    models.CharField(
                        blank=True, max_length=255, null=True, verbose_name="FCM 토큰"
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "차량",
                "verbose_name_plural": "차량 목록",
                "db_table": "vehicles",
                "indexes": [
                    models.Index(
                        fields=["plate_number"], name="vehicles_plate_number_idx"
                    ),
                    models.Index(
                        fields=["fcm_token"], name="vehicles_fcm_token_idx"
                    ),
                ],
            },
        ),
    ]
