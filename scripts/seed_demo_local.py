"""Gera processos DEMO só no SQLite local. Não usar em produção.

Padrão: 5 com número de relatório + 3 sem número (para testar Gerar /
vincular / cancelar).

Uso: python manage.py shell < scripts/seed_demo_local.py
  ou: python scripts/seed_demo_local.py (com DJANGO_SETTINGS_MODULE)
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'protocolo_project.settings')
django.setup()

from django.contrib.auth.models import User
from processos_app.models import (
    EspecieProcesso, UnidadeAdministrativa, Processo,
    SequenciaRelatorio, LinhaControleRelatorio,
)
from processos_app.services import processos as svc_processos
from processos_app.services import relatorios, tramitacao

SENHA = 'teste123'

TEMAS = [
    'Pagamento de serviços de limpeza predial — contrato 12/2025',
    'Liquidação de diárias de viagem a serviço — Out/2026',
    'Pagamento de material de consumo — almoxarifado',
    'Prestação de serviços de TI — suporte técnico',
    'Auxílio bolsa-atleta — parcela Outubro/2026',
    'Reembolso de despesas com locomoção',
    'Pagamento de energia elétrica — unidade administrativa',
    'Contrato de vigilância patrimonial — mensalidade',
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


def main():
    protocolo = user('protocolo', 'PROTOCOLO')
    analista = user('analista_liq', 'ANALISTA_LIQUIDACOES')
    user('gestao', 'GESTAO')
    admin = User.objects.filter(is_superuser=True).first()
    if admin is None:
        admin = user('admin', 'GESTAO', is_superuser=True)
        admin.set_password(SENHA)
        admin.save()

    especie = EspecieProcesso.objects.filter(
        grupo='LIQUIDACOES', gera_relatorio=True, nome='Pagamento Geral').first()
    if especie is None:
        especie = EspecieProcesso.objects.filter(
            grupo='LIQUIDACOES', gera_relatorio=True).first()
    unidade = (
        UnidadeAdministrativa.objects
        .filter(ativo=True)
        .exclude(nome__icontains='Controladoria')
        .exclude(nome__icontains='CGM')
        .first()
    )
    if unidade is None:
        unidade = UnidadeAdministrativa.objects.filter(ativo=True).first()
    print('Unidade usada:', unidade.nome)

    # Limpa demos anteriores (processos 1..N e linhas 9xxx).
    Processo.objects.filter(numero_processo__regex=r'^\d+$').delete()
    LinhaControleRelatorio.objects.filter(
        sequencia='LIQUIDACOES',
        numero_relatorio__regex=r'^9\d{3}$',
    ).delete()
    LinhaControleRelatorio.objects.filter(
        numero_processo__regex=r'^\d+$').delete()

    relatorios.definir_ultimo_numero(admin, 9000, 'LIQUIDACOES')

    def tema(i):
        return TEMAS[i % len(TEMAS)]

    def criar(numero_proc, indice_tema):
        return svc_processos.criar_processo({
            'numero_processo': str(numero_proc),
            'volume': '1',
            'secretaria': unidade.nome,
            'data_entrada': '2026-10-02',
            'hora_entrada': '10:00',
            'especie': especie.nome,
            'especie_id': str(especie.id),
            'genero': especie.grupo,
            'objeto': tema(indice_tema),
            'contratada': 'Empresa Teste Local LTDA',
            'recorrente': 'NAO',
        }, protocolo)

    def analisar(p, *, gerar_numero=False, observacao='DEMO LOCAL'):
        if p.situacao_tramite != 'EM_ANALISE':
            tramitacao.assumir(p.id, analista)
            p.refresh_from_db()
        dados = {
            'destino': unidade.nome,
            'valor': '1500,00',
            'periodo': 'Out/2026',
            'status_analise': 'PROSSEGUIMENTO_SEM_RESSALVA',
            'observacao': observacao,
        }
        if gerar_numero:
            dados['gerar_numero'] = '1'
        svc_processos.aplicar_analise(p, dados, analista)
        p.refresh_from_db()
        return p

    criados = []
    n = 1

    # 5 com número de relatório (ativos na planilha)
    for idx in range(5):
        p = analisar(
            criar(n, idx),
            gerar_numero=True,
            observacao=f'DEMO — com número ({idx + 1}/5)',
        )
        criados.append((
            p.numero_processo,
            p.numero_relatorio,
            'COM Nº',
            p.objeto[:42],
        ))
        n += 1

    # 3 sem número (análise salva; pode Gerar número ou vincular no Controle)
    for idx in range(3):
        p = analisar(
            criar(n, 5 + idx),
            gerar_numero=False,
            observacao=f'DEMO — sem número ({idx + 1}/3)',
        )
        criados.append((
            p.numero_processo,
            '(sem)',
            'SEM Nº',
            p.objeto[:42],
        ))
        n += 1

    prox = SequenciaRelatorio.objects.get(grupo='LIQUIDACOES').proximo_numero
    print('=== DEMO LOCAL (SQLite) ===')
    print(f'Usuarios: protocolo | analista_liq | gestao   senha: {SENHA}')
    print(f'Admin: {admin.username} (use a senha dele)')
    print(f'Proximo automatico Liquidacoes: {prox}')
    print('Padrão: 5 com número + 3 sem número')
    print('Processos:')
    for num, rel, sit, obj in criados:
        print(f'  {num:6}  rel={str(rel):8}  [{sit}]  {obj}')
    print(f'Linhas no Controle: {LinhaControleRelatorio.objects.count()}')
    print('Abra /controle-relatorio/ ou a análise dos processos 6–8 (sem nº)')


if __name__ == '__main__':
    main()
