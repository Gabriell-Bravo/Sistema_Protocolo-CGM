"""Gera processos DEMO só no SQLite local. Não usar em produção.

Um processo por grupo de numeração, com campos no estilo da planilha
Controle Relatórios 2026, para testar o formulário do analista.

Uso: python manage.py shell < scripts/seed_demo_local.py
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'protocolo_project.settings')
django.setup()

from django.contrib.auth.models import User
from processos_app.models import (
    EspecieProcesso, UnidadeAdministrativa, Processo,
    LinhaControleRelatorio,
)
from processos_app.services import processos as svc_processos
from processos_app.services import relatorios, tramitacao

SENHA = 'teste123'

# Um caso por grupo: sequência, espécie, dados cadastrais + análise (planilha).
DEMOS = [
    {
        'sequencia': 'LIQUIDACOES',
        'especie': 'Pagamento Geral',
        'ultimo': 9000,
        'cadastro': {
            'objeto': 'Pagamento de serviços de limpeza predial — contrato 12/2025',
            'contratada': 'Limpeza Total Serviços LTDA',
        },
        'analise': {
            'valor': '12500,00',
            'periodo': 'Set/2026',
            'destino': None,  # unidade padrão
            'observacao': 'DEMO Liquidação — planilha clássica',
        },
        'gerar_numero': True,
    },
    {
        'sequencia': 'ADIANTAMENTO',
        'especie': 'Concessão Adiantamento',
        'ultimo': 100,
        'cadastro': {
            'objeto': 'Concessão',  # Assunto na planilha
            'contratada': 'Neusa de Oliveira Santos',  # Servidor
        },
        'analise': {
            'valor': '3000,00',
            'destino': 'Finanças',
            'observacao': 'DEMO Adiantamento',
        },
        'gerar_numero': True,
    },
    {
        'sequencia': 'COTA_PATROCINIO',
        'especie': 'Concessão Patrocínio',
        'ultimo': 200,
        'cadastro': {
            'objeto': 'SAQUAREMA INTERNATIONAL CUP 2026',  # Evento
            'contratada': 'Federação de Jiu-Jitsu do RJ',  # Interessado
        },
        'analise': {
            'valor': '119820,00',
            'periodo': 'Prestação de Contas',  # Assunto
            'destino': 'Sec. De Esporte, Lazer e Turismo',
            'observacao': 'DEMO Cota Patrocínio',
        },
        'gerar_numero': True,
    },
    {
        'sequencia': 'SUBVENCAO',
        'especie': 'Subvenção Social - Concessão',
        'ultimo': 300,
        'cadastro': {
            'objeto': 'Renovação para o ano de 2026',  # Necessidade
            'contratada': 'Lar das crianças especiais — Laces',  # Entidade
        },
        'analise': {
            'valor': '197400,00',
            'periodo': 'Renovação',  # Assunto
            'destino': 'PGM',
            'observacao': 'DEMO Subvenção',
        },
        'gerar_numero': True,
    },
    {
        'sequencia': 'ALUGUEL_SOCIAL',
        'especie': 'Concessão Aux. Aluguel Social',
        'ultimo': 400,
        'cadastro': {
            'objeto': 'Aluguel Social',
            'contratada': 'Katia Marins de Vasconcelos',  # Beneficiário
        },
        'analise': {
            'valor': '7200,00',
            'periodo': '1ª parcela: R$ 600,00',  # Parcelas
            'destino': 'Desenvolvimento Social',
            'observacao': 'DEMO Aluguel Social',
        },
        'gerar_numero': True,
    },
    {
        'sequencia': 'BOLSA_ATLETA',
        'especie': 'Concessão Aux. Bolsa Atleta',
        'ultimo': 500,
        'cadastro': {
            'objeto': 'Prestação 2º semestre 2025 — Jiu-Jitsu',  # Assunto/Modalidade
            'contratada': 'Laura Silva Crispim de Carvalho',  # Atleta
        },
        'analise': {
            'valor': '3000,00',
            'periodo': 'Aline Jorge Silva Crispim de Carvalho',  # Responsável
            'destino': 'Esporte, Lazer e Turismo',
            'observacao': 'DEMO Bolsa Atleta · Processo concessão: 22.950/2024',
        },
        'gerar_numero': True,
    },
    {
        'sequencia': 'AUXILIO_COMPETICAO',
        'especie': 'Concessão Aux. Competição',
        'ultimo': 90,
        'cadastro': {
            'objeto': 'Concessão — Jiu-Jitsu',
            'contratada': 'Bernardo Rosalba de Menezes',
        },
        'analise': {
            'valor': '3000,00',
            'periodo': 'ATLETA MAIOR',
            'destino': 'Finanças',
            'observacao': 'DEMO Auxílio Competição',
        },
        'gerar_numero': True,
    },
    {
        'sequencia': 'DIARIA',
        'especie': 'Concessão Diária',
        'ultimo': 600,
        'cadastro': {
            'objeto': 'Concessão Diária',
            'contratada': 'Beatriz Ferreira de O. Correia e outros',  # Servidor(es)
            'secretaria': 'Sec. Municipal de Desenvolvimento Social',
        },
        'analise': {
            'valor': '6300,00',
            'periodo': '3',  # Quantidade
            'destino': 'Gabinete',
            'observacao': 'DEMO Diária',
        },
        'gerar_numero': True,
    },
    {
        'sequencia': 'BLOCOS_CARNAVALESCOS',
        'especie': 'Subvenção Bloco Carnaval',
        'ultimo': 700,
        'cadastro': {
            'objeto': 'Prestação de Contas 2025',
            'contratada': 'Virgens de Itauna',  # Bloco
        },
        'analise': {
            'valor': '7000,00',
            'destino': 'Esporte',
            'observacao': 'DEMO Blocos · Apto',
        },
        'gerar_numero': True,
    },
]


def user(username, papel, **extra):
    u, created = User.objects.get_or_create(
        username=username,
        defaults={'first_name': username.replace('_', ' ').title()},
    )
    if created:
        u.set_password(SENHA)
        u.save()
    if extra.get('is_superuser'):
        u.is_superuser = True
        u.is_staff = True
        u.save()
    u.profile.papel = papel
    u.profile.save()
    return u


def especie_do_grupo(nome, sequencia):
    esp, _ = EspecieProcesso.objects.get_or_create(
        nome=nome,
        grupo='LIQUIDACOES',
        defaults={
            'ativo': True,
            'gera_relatorio': True,
            'sequencia_numeracao': sequencia,
        },
    )
    campos = []
    if not esp.ativo:
        esp.ativo = True
        campos.append('ativo')
    if not esp.gera_relatorio:
        esp.gera_relatorio = True
        campos.append('gera_relatorio')
    if (esp.sequencia_numeracao or '').strip() != sequencia:
        esp.sequencia_numeracao = sequencia
        campos.append('sequencia_numeracao')
    if campos:
        esp.save(update_fields=campos)
    return esp


def main():
    protocolo = user('protocolo', 'PROTOCOLO')
    analista = user('analista_liq', 'ANALISTA_LIQUIDACOES')
    user('gestao', 'GESTAO')
    admin = User.objects.filter(is_superuser=True).first()
    if admin is None:
        admin = user('admin', 'GESTAO', is_superuser=True)
    admin.set_password(SENHA)
    admin.is_superuser = True
    admin.is_staff = True
    admin.save()
    admin.profile.papel = 'GESTAO'
    admin.profile.save()

    unidade = (
        UnidadeAdministrativa.objects
        .filter(ativo=True)
        .exclude(nome__icontains='Controladoria')
        .exclude(nome__icontains='CGM')
        .first()
    )
    if unidade is None:
        unidade = UnidadeAdministrativa.objects.filter(ativo=True).first()
    print('Unidade padrão:', unidade.nome if unidade else '(nenhuma)')

    # Limpa demos anteriores (números simples 1..N).
    Processo.objects.filter(numero_processo__regex=r'^\d+$').delete()
    LinhaControleRelatorio.objects.filter(
        numero_processo__regex=r'^\d+$').delete()

    for demo in DEMOS:
        relatorios.definir_ultimo_numero(
            admin, demo['ultimo'], demo['sequencia'])

    criados = []
    for i, demo in enumerate(DEMOS, start=1):
        sequencia = demo['sequencia']
        especie = especie_do_grupo(demo['especie'], sequencia)
        cad = demo['cadastro']
        secretaria = cad.get('secretaria') or (unidade.nome if unidade else 'Sec. Teste')
        p = svc_processos.criar_processo({
            'numero_processo': str(i),
            'volume': '1',
            'secretaria': secretaria,
            'data_entrada': '2026-10-02',
            'hora_entrada': '10:00',
            'especie': especie.nome,
            'especie_id': str(especie.id),
            'genero': especie.grupo,
            'objeto': cad['objeto'],
            'contratada': cad['contratada'],
            'recorrente': 'NAO',
        }, protocolo)

        if p.situacao_tramite != 'EM_ANALISE':
            tramitacao.assumir(p.id, analista)
            p.refresh_from_db()

        analise = dict(demo['analise'])
        destino = analise.pop('destino', None) or (unidade.nome if unidade else '')
        dados = {
            'contratada': cad['contratada'],
            'secretaria': secretaria,
            'objeto': cad['objeto'],
            'destino': destino,
            'valor': analise.get('valor', ''),
            'periodo': analise.get('periodo', ''),
            'status_analise': 'PROSSEGUIMENTO_SEM_RESSALVA',
            'observacao': analise.get('observacao', f'DEMO {sequencia}'),
        }
        if demo.get('gerar_numero'):
            dados['gerar_numero'] = '1'
        svc_processos.aplicar_analise(p, dados, analista)
        p.refresh_from_db()

        info = relatorios.info_sequencia(sequencia)
        layout = relatorios.layout_planilha(sequencia)
        criados.append({
            'num': p.numero_processo,
            'grupo': info['nome'],
            'rel': p.numero_relatorio or '(sem)',
            'titulo': layout['titulo'],
            'url': f'/analista/processo/{p.id}/',
        })

    print('=== DEMO LOCAL — 1 processo por grupo ===')
    print(f'Login analista: analista_liq / {SENHA}')
    print(f'Login admin:    admin / {SENHA}')
    print('')
    print('Abra cada processo para ver o formulário igual à planilha:')
    for item in criados:
        print(
            f"  #{item['num']}  {item['grupo']:22}  "
            f"rel={str(item['rel']):6}  {item['url']}"
        )
        print(f"         -> {item['titulo']}")
    print('')
    print(f'Total: {len(criados)} processos · '
          f'{LinhaControleRelatorio.objects.count()} linhas no Controle')
    print('Fila: http://127.0.0.1:8000/analista/')
    print('Controle: http://127.0.0.1:8000/controle-relatorio/?secao=analises')


if __name__ == '__main__':
    main()
