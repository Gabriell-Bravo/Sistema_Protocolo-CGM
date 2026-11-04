from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('processos_app', '0042_anexo_copia_pdf'),
    ]

    operations = [
        migrations.AddField(
            model_name='profile',
            name='funcoes_extras',
            field=models.JSONField(
                blank=True,
                default=list,
                verbose_name='Funções extras',
            ),
        ),
    ]
