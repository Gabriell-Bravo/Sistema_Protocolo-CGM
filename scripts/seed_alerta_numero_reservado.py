"""Cenário local: processo sem número + linha histórica na planilha.

Abra a tela do analista e veja o alerta amarelo do número reaproveitável.
Depois clique em Gerar número — deve puxar o 1918, não um sequencial novo.

Uso (com o venv ativo / python do projeto):

    .\\.venv\\Scripts\\python.exe scripts\\seed_alerta_numero_reservado.py

Login: analista_liq / teste123
"""
import os
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'protocolo_project.settings')

import django

django.setup()

from django.contrib.auth.models import User

from processos_app.models import (
    EspecieProcesso, LinhaControleRelatorio, Processo, UnidadeAdministrativa,
)
from processos_app.services import processos as svc_processos
from processos_app.services import relatorios, tramitacao

SENHA = 'teste123'
NUMERO_PROCESSO = '7992-DEMO/2026'
NUMERO_RELATORIO = '1918'


def garantir_usuario(username, papel, **extra):
    u, criado = User.objects.get_or_create(
        username=username, defaults={'first_name': username})
    u.set_password(SENHA)
    if extra.get('is_superuser'):
        u.is_superuser = True
        u.is_staff = True
    u.save()
    u.profile.papel = papel
    u.profile.save()
    return u, criado


def main():
    protocolo, _ = garantir_usuario('protocolo', 'PROTOCOLO')
    analista, _ = garantir_usuario('analista_liq', 'ANALISTA_LIQUIDACOES')
    admin = User.objects.filter(is_superuser=True).first()
    if admin is None:
        admin, _ = garantir_usuario('admin', 'GESTAO', is_superuser=True)
    admin.set_password(SENHA)
    admin.is_superuser = True
    admin.is_staff = True
    admin.save()

    especie = EspecieProcesso.objects.filter(
        grupo='LIQUIDACOES', gera_relatorio=True, ativo=True,
    ).order_by('id').first()
    if especie is None:
        especie = EspecieProcesso.objects.create(
            nome='Pagamento Geral',
            grupo='LIQUIDACOES',
            ativo=True,
            gera_relatorio=True,
            sequencia_numeracao='LIQUIDACOES',
        )

    unidade = (
        UnidadeAdministrativa.objects.filter(ativo=True)
        .exclude(nome__icontains='Controladoria')
        .first()
        or UnidadeAdministrativa.objects.filter(ativo=True).first()
    )
    secretaria = unidade.nome if unidade else (
        'Educação, Cultura, Inclusão, Ciência e Tecnologia'
    )

    # Limpa cenário anterior.
    Processo.objects.filter(numero_processo=NUMERO_PROCESSO).delete()
    LinhaControleRelatorio.objects.filter(
        numero_processo=NUMERO_PROCESSO).delete()
    LinhaControleRelatorio.objects.filter(
        numero_relatorio=NUMERO_RELATORIO,
        situacao_linha__in=['HISTORICA', 'RESERVADA'],
    ).delete()

    relatorios.definir_ultimo_numero(admin, 1950, 'LIQUIDACOES')

    processo = svc_processos.criar_processo({
        'numero_processo': NUMERO_PROCESSO,
        'volume': '1',
        'secretaria': secretaria,
        'data_entrada': '2026-10-02',
        'hora_entrada': '10:00',
        'especie': especie.nome,
        'especie_id': str(especie.id),
        'genero': especie.grupo,
        'objeto': 'DEMO alerta — número histórico na planilha (não gerar novo)',
        'contratada': 'Empresa Demo Alerta',
        'recorrente': 'NAO',
    }, protocolo)

    if processo.situacao_tramite != 'EM_ANALISE':
        tramitacao.assumir(processo.id, analista)
        processo.refresh_from_db()

    LinhaControleRelatorio.objects.create(
        processo=None,
        numero_relatorio=NUMERO_RELATORIO,
        numero_processo=NUMERO_PROCESSO,
        data_relatorio=date(2026, 10, 2),
        secretaria=secretaria,
        contratada='Empresa Demo Alerta',
        objeto='Número histórico reservado para teste do alerta',
        situacao_linha='HISTORICA',
        sem_relatorio=True,
        grupo='LIQUIDACOES',
        sequencia='LIQUIDACOES',
        observacao='Seed local — alerta de número reaproveitável',
    )

    aviso = relatorios.aviso_numero_reaproveitavel(processo)
    url = f'http://127.0.0.1:8000/analista/processo/{processo.id}/'

    print('=== DEMO ALERTA NÚMERO RESERVADO ===')
    print(f'Login: analista_liq / {SENHA}')
    print(f'Processo: {NUMERO_PROCESSO}')
    print(f'Histórico na planilha: relatório {NUMERO_RELATORIO}')
    print(f'Aviso detectado: {aviso}')
    print('')
    print(f'1) Abra: {url}')
    print('2) Veja o alerta amarelo no topo da análise.')
    print('3) Clique em Gerar número — deve gravar 1918 (não 1951).')
    print('')
    print('Controle: http://127.0.0.1:8000/controle-relatorio/?termo=7992-DEMO')


if __name__ == '__main__':
    main()
