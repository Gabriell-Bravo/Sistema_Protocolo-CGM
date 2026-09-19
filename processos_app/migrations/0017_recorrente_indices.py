"""Bloco E — normalização de `recorrente` (item 54) e índices (item 57).

item 54: o campo foi criado com valor padrão 'NÃO' (com acento) e escolhas
SIM/NÃO, enquanto o formulário de entrada gravava 'NAO' (sem acento). Os
dois valores convivem no banco e quebram qualquer comparação. Aqui o valor
interno passa a ser sempre SIM/NAO e o histórico é corrigido por migration,
não por default. O rótulo exibido continua Sim/Não.

item 57: índices nos campos usados pelas listas, pelo Dashboard e pelos
indicadores do período.
"""

from django.db import migrations, models

EQUIVALENTES_NAO = ['NÃO', 'Não', 'não', 'nao', 'Nao', 'N', 'n', '']
EQUIVALENTES_SIM = ['Sim', 'sim', 'S', 's']


def normalizar(apps, schema_editor):
    Processo = apps.get_model('processos_app', 'Processo')
    Processo.objects.filter(recorrente__in=EQUIVALENTES_NAO).update(recorrente='NAO')
    Processo.objects.filter(recorrente__isnull=True).update(recorrente='NAO')
    Processo.objects.filter(recorrente__in=EQUIVALENTES_SIM).update(recorrente='SIM')
    # Qualquer valor fora do padrão que ainda restar é listado pelo comando
    # `python manage.py sanear_dados` — não é convertido às cegas.


def reverter(apps, schema_editor):
    # O valor anterior podia ser 'NAO' ou 'NÃO'; não há como distinguir.
    # Manter 'NAO' é compatível com as duas versões do código.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('processos_app', '0016_cadastros_gestao_pessoas'),
    ]

    operations = [
        migrations.AlterField(
            model_name='processo',
            name='recorrente',
            field=models.CharField(
                choices=[('SIM', 'Sim'), ('NAO', 'Não')],
                default='NAO', max_length=3, verbose_name='Recorrente'),
        ),
        migrations.RunPython(normalizar, reverter),

        migrations.AddIndex(
            model_name='processo',
            index=models.Index(fields=['data_saida'], name='idx_proc_data_saida'),
        ),
        migrations.AddIndex(
            model_name='processo',
            index=models.Index(fields=['saida_concluida_em'], name='idx_proc_saida_concluida'),
        ),
        migrations.AddIndex(
            model_name='processo',
            index=models.Index(fields=['liberado_assinatura_em'], name='idx_proc_liberado_em'),
        ),
        migrations.AddIndex(
            model_name='processo',
            index=models.Index(fields=['cancelado_em'], name='idx_proc_cancelado_em'),
        ),
        migrations.AddIndex(
            model_name='pendencia',
            index=models.Index(fields=['status', 'responsavel_tecnico'],
                               name='idx_pend_status_resp'),
        ),
    ]
