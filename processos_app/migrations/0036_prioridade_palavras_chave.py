from django.db import migrations, models


PALAVRAS = {
    'URGENTE': '\n'.join([
        'JP',
        'AMX',
        'FXX',
        'LAND',
        'ONIX',
        'Expedito',
        'DUO SANTOS',
        'ELITE',
    ]),
    'PRIORITARIO': '\n'.join([
        'M. COSTA',
        'M COSTA',
        'HYDRA',
        'CONSÓRCIO BGH',
        'CONSORCIO BGH',
        'METROPOLITANA',
        'MIDAS',
        'GLOBO',
        'CONSÓRCIO INOVAR',
        'CONSORCIO INOVAR',
        'INOVA',
        'Santa Luzia',
        'Borges e Gomes',
        'WL Engenharia',
    ]),
    'RECORRENTE': '\n'.join([
        'CLARICIA FLORES',
        'R3M',
        'CM DISTRIBUIDORA',
        'CM DSTRIBUIDORA',
        'ELFRIG',
        'R.SABINO',
        'R SABINO',
        'Consórcio Nova Conectividade',
        'Nova Conectividade',
        'HASHIMOTO',
        'FORÇA AMBIENTAL',
        'FORCA AMBIENTAL',
        'ARTELAGOS',
        'PROGENIUS',
        'Cartão Cidadania',
        'Cartao Cidadania',
    ]),
}


def semear(apps, schema_editor):
    Prioridade = apps.get_model('processos_app', 'Prioridade')

    Prioridade.objects.update_or_create(
        codigo='URGENTE',
        defaults={
            'nome': 'Urgente',
            'prazo_dias': 1,
            'ordem': 10,
            'ativo': True,
            'palavras_chave': PALAVRAS['URGENTE'],
        },
    )
    Prioridade.objects.update_or_create(
        codigo='PRIORITARIO',
        defaults={
            'nome': 'Prioridade de obras',
            'prazo_dias': 2,
            'ordem': 20,
            'ativo': True,
            'palavras_chave': PALAVRAS['PRIORITARIO'],
        },
    )
    Prioridade.objects.update_or_create(
        codigo='RECORRENTE',
        defaults={
            'nome': 'Prioridade recorrente',
            'prazo_dias': 3,
            'ordem': 25,
            'ativo': True,
            'palavras_chave': PALAVRAS['RECORRENTE'],
        },
    )
    Prioridade.objects.update_or_create(
        codigo='NORMAL',
        defaults={
            'nome': 'Normal',
            'prazo_dias': 7,
            'ordem': 40,
            'ativo': True,
            'palavras_chave': '',
        },
    )


def reverter(apps, schema_editor):
    Prioridade = apps.get_model('processos_app', 'Prioridade')
    Prioridade.objects.filter(codigo='RECORRENTE').delete()
    Prioridade.objects.filter(codigo='PRIORITARIO').update(
        nome='Prioritário', palavras_chave='')
    Prioridade.objects.filter(codigo='URGENTE').update(palavras_chave='')


class Migration(migrations.Migration):

    dependencies = [
        ('processos_app', '0035_especie_auxilio_competicao'),
    ]

    operations = [
        migrations.AddField(
            model_name='prioridade',
            name='palavras_chave',
            field=models.TextField(
                blank=True,
                default='',
                help_text=(
                    'Uma por linha. Se contratada/objeto/secretaria contiver '
                    'o termo na entrada, o processo nasce com esta prioridade.'
                ),
                verbose_name='Palavras-chave',
            ),
        ),
        migrations.AlterField(
            model_name='processo',
            name='prioridade',
            field=models.CharField(
                choices=[
                    ('NORMAL', 'Normal'),
                    ('PRIORITARIO', 'Prioridade de obras'),
                    ('RECORRENTE', 'Prioridade recorrente'),
                    ('URGENTE', 'Urgente'),
                ],
                default='NORMAL',
                max_length=50,
                verbose_name='Prioridade',
            ),
        ),
        migrations.RunPython(semear, reverter),
    ]
