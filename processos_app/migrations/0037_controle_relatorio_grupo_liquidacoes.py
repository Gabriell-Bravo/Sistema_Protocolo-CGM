from django.db import migrations


# Sequências da planilha de Controle (todas pertencem a Liquidações).
SEQUENCIAS = (
    'LIQUIDACOES',
    'ADIANTAMENTO',
    'COTA_PATROCINIO',
    'SUBVENCAO',
    'ALUGUEL_SOCIAL',
    'BOLSA_ATLETA',
    'AUXILIO_COMPETICAO',
    'DIARIA',
    'BLOCOS_CARNAVALESCOS',
)


def preencher_grupo(apps, schema_editor):
    """Histórico importado vinha com grupo vazio e o analista não via."""
    Linha = apps.get_model('processos_app', 'LinhaControleRelatorio')
    Linha.objects.filter(grupo='', sequencia__in=SEQUENCIAS).update(
        grupo='LIQUIDACOES')


def reverter(apps, schema_editor):
    Linha = apps.get_model('processos_app', 'LinhaControleRelatorio')
    Linha.objects.filter(
        grupo='LIQUIDACOES',
    ).exclude(sequencia='LIQUIDACOES').exclude(sequencia='').update(grupo='')


class Migration(migrations.Migration):

    dependencies = [
        ('processos_app', '0036_prioridade_palavras_chave'),
    ]

    operations = [
        migrations.RunPython(preencher_grupo, reverter),
    ]
