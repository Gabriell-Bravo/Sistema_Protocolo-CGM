from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('lai', '0006_numeracao_memorando'),
    ]

    operations = [
        migrations.AddField(
            model_name='manifestacaofalabr',
            name='drive_em',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='manifestacaofalabr',
            name='drive_link',
            field=models.URLField(blank=True, max_length=300),
        ),
    ]
