# Ativa Auxílio Competição: espécies + sequência de numeração própria.

from django.db import migrations


ESPECIES = (
    {
        'nome': 'Concessão Aux. Competição',
        'ordem': 55,
        'tipo_monitoramento': 'TRIMESTRAL',
        'encerra_monitoramento_anterior': True,
    },
    {
        'nome': 'P.C. Aux. Competição',
        'ordem': 56,
        'tipo_monitoramento': 'TRIMESTRAL',
        'encerra_monitoramento_anterior': True,
    },
)


def criar_especies(apps, schema_editor):
    EspecieProcesso = apps.get_model('processos_app', 'EspecieProcesso')
    for dados in ESPECIES:
        esp, criada = EspecieProcesso.objects.get_or_create(
            nome=dados['nome'],
            grupo='LIQUIDACOES',
            defaults={
                'ativo': True,
                'ordem': dados['ordem'],
                'exige_contratada': True,
                'exige_valor': True,
                'gera_relatorio': True,
                'sequencia_numeracao': 'AUXILIO_COMPETICAO',
                'tipo_monitoramento': dados['tipo_monitoramento'],
                'encerra_monitoramento_anterior': dados[
                    'encerra_monitoramento_anterior'],
            },
        )
        if criada:
            continue
        campos = []
        if not esp.ativo:
            esp.ativo = True
            campos.append('ativo')
        if not esp.gera_relatorio:
            esp.gera_relatorio = True
            campos.append('gera_relatorio')
        if (esp.sequencia_numeracao or '').strip() != 'AUXILIO_COMPETICAO':
            esp.sequencia_numeracao = 'AUXILIO_COMPETICAO'
            campos.append('sequencia_numeracao')
        if campos:
            esp.save(update_fields=campos)


def reverter(apps, schema_editor):
    EspecieProcesso = apps.get_model('processos_app', 'EspecieProcesso')
    EspecieProcesso.objects.filter(
        grupo='LIQUIDACOES',
        nome__in=[item['nome'] for item in ESPECIES],
    ).update(ativo=False, sequencia_numeracao='')


class Migration(migrations.Migration):

    dependencies = [
        ('processos_app', '0034_linha_situacao_historica'),
    ]

    operations = [
        migrations.RunPython(criar_especies, reverter),
    ]
