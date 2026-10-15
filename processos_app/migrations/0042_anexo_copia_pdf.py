from django.db import migrations, models

import processos_app.models


class Migration(migrations.Migration):

    dependencies = [
        ('processos_app', '0041_evento_indicacao_desfeita'),
    ]

    operations = [
        migrations.AddField(
            model_name='anexoprocesso',
            name='arquivo_pdf',
            field=models.FileField(
                blank=True,
                null=True,
                upload_to=processos_app.models._caminho_anexo,
                verbose_name='Cópia em PDF para visualização',
            ),
        ),
    ]
