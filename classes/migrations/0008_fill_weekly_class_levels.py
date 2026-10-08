from django.db import migrations


def fill_levels(apps, schema_editor):
    # A class booked before classes had a level gets its subject's first
    # level, in Level order. A subject with a single level gives that one.
    WeeklyClass = apps.get_model("classes", "WeeklyClass")

    unfilled = []
    classes = WeeklyClass.objects.filter(level__isnull=True).select_related("subject")
    for weekly_class in classes:
        level = weekly_class.subject.levels.order_by("id").first()
        if level is None:
            unfilled.append(weekly_class.pk)
            continue
        weekly_class.level = level
        weekly_class.save(update_fields=["level"])

    if unfilled:
        raise RuntimeError(
            "Cannot choose a level for weekly classes "
            f"{unfilled}: their subject has no levels. Give the subject a "
            "level in the Django admin, then migrate again."
        )


class Migration(migrations.Migration):

    dependencies = [
        ('classes', '0007_weeklyclass_level'),
    ]

    operations = [
        # Nothing to undo: unapplying 0007 drops the column.
        migrations.RunPython(fill_levels, migrations.RunPython.noop),
    ]
