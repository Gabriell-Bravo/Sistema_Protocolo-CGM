from django.db import migrations, models


def renomear(apps, schema_editor):
    Prioridade = apps.get_model('processos_app', 'Prioridade')
    Prioridade.objects.filter(codigo='PRIORITARIO').update(nome='Prioridade Alta')


def reverter(apps, schema_editor):
    Prioridade = apps.get_model('processos_app', 'Prioridade')
    Prioridade.objects.filter(codigo='PRIORITARIO').update(nome='Prioridade de obras')


class Migration(migrations.Migration):

    dependencies = [
        ('processos_app', '0045_papel_lai'),
    ]

    operations = [
        migrations.RunPython(renomear, reverter),
        migrations.AlterField(
            model_name='processo',
            name='prioridade',
            field=models.CharField(
                choices=[
                    ('NORMAL', 'Normal'),
                    ('PRIORITARIO', 'Prioridade Alta'),
                    ('RECORRENTE', 'Prioridade recorrente'),
                    ('N_RECORRENTE', 'Prioridade N/Recorrente'),
                    ('URGENTE', 'Urgente'),
                ],
                default='NORMAL',
                max_length=50,
                verbose_name='Prioridade',
            ),
        ),
    ]
