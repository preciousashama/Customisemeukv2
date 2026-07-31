from django.db import migrations, models

import customiseapp.file_validators
import customiseapp.models


class Migration(migrations.Migration):

    dependencies = [
        ("customiseapp", "0008_product_customisation_config"),
    ]

    operations = [
        migrations.CreateModel(
            name="ArtworkResource",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=200)),
                ("description", models.TextField(blank=True)),
                (
                    "pdf_file",
                    models.FileField(
                        storage=customiseapp.models._firebase_storage,
                        upload_to="artwork-resources/",
                        validators=[customiseapp.file_validators.validate_pdf_asset],
                    ),
                ),
                ("button_label", models.CharField(blank=True, default="Download PDF", max_length=80)),
                ("position", models.PositiveSmallIntegerField(default=0)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ["position", "id"],
            },
        ),
    ]
