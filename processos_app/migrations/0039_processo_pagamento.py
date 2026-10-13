from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('processos_app', '0038_processo_processo_prestacao'),
    ]

    operations = [
        migrations.AddField(
            model_name='linhacontrolerelatorio',
            name='processo_pagamento',
            field=models.CharField(
                blank=True,
                default='',
                max_length=255,
                verbose_name='Processo de pagamento',
            ),
        ),
        migrations.AddField(
            model_name='processo',
            name='processo_pagamento',
            field=models.CharField(
                blank=True,
                default='',
                max_length=255,
                verbose_name='Processo de pagamento',
            ),
        ),
    ]
