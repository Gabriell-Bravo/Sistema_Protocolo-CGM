from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('processos_app', '0039_processo_pagamento'),
    ]

    operations = [
        migrations.AddField(
            model_name='pendencia',
            name='itens_concluidos',
            field=models.JSONField(
                blank=True, default=list, verbose_name='Itens concluídos'),
        ),
    ]
