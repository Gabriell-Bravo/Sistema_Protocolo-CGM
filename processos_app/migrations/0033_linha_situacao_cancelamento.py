from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('processos_app', '0032_especie_sequencia_numeracao'),
    ]

    operations = [
        migrations.AddField(
            model_name='linhacontrolerelatorio',
            name='situacao_linha',
            field=models.CharField(
                choices=[
                    ('ATIVA', 'Ativa'),
                    ('RESERVADA', 'Número guardado'),
                    ('CANCELADA', 'Excluída da sequência'),
                ],
                db_index=True,
                default='ATIVA',
                max_length=20,
                verbose_name='Situação na planilha',
            ),
        ),
    ]
