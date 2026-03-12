# Add target_set to separate production/test data.
# Generated manually for set-specific monitor history.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("monitor", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="monitortarget",
            name="target_set",
            field=models.PositiveSmallIntegerField(default=1),
        ),
        migrations.AlterField(
            model_name="monitortarget",
            name="target_id",
            field=models.SlugField(max_length=100),
        ),
        migrations.AlterModelOptions(
            name="monitortarget",
            options={"ordering": ["target_set", "sort_order", "target_id"]},
        ),
        migrations.AddConstraint(
            model_name="monitortarget",
            constraint=models.UniqueConstraint(
                fields=("target_set", "target_id"),
                name="uniq_target_set_target_id",
            ),
        ),
    ]
