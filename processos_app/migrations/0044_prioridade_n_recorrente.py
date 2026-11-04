from django.db import migrations, models


def semear(apps, schema_editor):
    Prioridade = apps.get_model('processos_app', 'Prioridade')
    Prioridade.objects.update_or_create(
        codigo='N_RECORRENTE',
        defaults={
            'nome': 'Prioridade N/Recorrente',
            'prazo_dias': 3,
            'ordem': 27,
            'ativo': True,
            'palavras_chave': '',
        },
    )


def reverter(apps, schema_editor):
    Prioridade = apps.get_model('processos_app', 'Prioridade')
    Prioridade.objects.filter(codigo='N_RECORRENTE').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('processos_app', '0043_profile_funcoes_extras'),
    ]

    operations = [
        migrations.AlterField(
            model_name='processo',
            name='prioridade',
            field=models.CharField(
                choices=[
                    ('NORMAL', 'Normal'),
                    ('PRIORITARIO', 'Prioridade de obras'),
                    ('RECORRENTE', 'Prioridade recorrente'),
                    ('N_RECORRENTE', 'Prioridade N/Recorrente'),
                    ('URGENTE', 'Urgente'),
                ],
                default='NORMAL',
                max_length=50,
                verbose_name='Prioridade',
            ),
        ),
        migrations.RunPython(semear, reverter),
    ]
