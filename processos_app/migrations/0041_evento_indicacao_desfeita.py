from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('processos_app', '0040_pendencia_itens_concluidos'),
    ]

    operations = [
        migrations.AlterField(
            model_name='eventopendencia',
            name='tipo',
            field=models.CharField(
                choices=[
                    ('CRIADA', 'Criada'),
                    ('ATENDIMENTO_INDICADO', 'Atendimento indicado'),
                    ('ATENDIMENTO_INSUFICIENTE', 'Atendimento insuficiente'),
                    ('INDICACAO_DESFEITA', 'Indicação desfeita'),
                    ('RESOLVIDA', 'Resolvida'),
                    ('CANCELADA', 'Cancelada'),
                ],
                max_length=30,
                verbose_name='Evento',
            ),
        ),
    ]
