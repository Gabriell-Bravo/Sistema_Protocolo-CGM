from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('processos_app', '0037_controle_relatorio_grupo_liquidacoes'),
    ]

    operations = [
        migrations.AddField(
            model_name='processo',
            name='processo_prestacao',
            field=models.CharField(
                blank=True,
                default='',
                max_length=255,
                verbose_name='Processo de prestação',
            ),
        ),
    ]
