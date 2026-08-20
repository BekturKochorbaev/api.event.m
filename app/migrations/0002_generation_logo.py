from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='generation',
            name='logo',
            field=models.ImageField(blank=True, null=True, upload_to='logos/'),
        ),
    ]
