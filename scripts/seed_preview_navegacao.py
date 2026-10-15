"""Seed rico no preview.sqlite3 para navegar Gestão/Admin/Analista.

Uso:
  $env:DJANGO_SETTINGS_MODULE='protocolo_project.settings_preview'
  .\\.venv\\Scripts\\python.exe scripts\\seed_preview_navegacao.py
"""
import datetime
import os
import runpy
import sys

import django

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'protocolo_project.settings_preview')
django.setup()

from django.contrib.auth.models import User

from processos_app.models import (
    AnexoProcesso, EspecieProcesso, Pendencia, Processo, UnidadeAdministrativa,
)
from processos_app.services import pendencias, processos as svc_processos
from processos_app.services import tramitacao

SENHA = 'teste123'


def garantir_usuarios():
    runpy.run_path(
        os.path.join(BASE, 'scripts', 'seed_demo_local.py'),
        run_name='__main__',
    )
    for username in (
        'admin', 'gestao', 'protocolo', 'analista_liq', 'analista_lic',
    ):
        u = User.objects.filter(username=username).first()
        if u:
            u.set_password(SENHA)
            u.save()


def extras_navegacao():
    protocolo = User.objects.get(username='protocolo')
    analista_lic = User.objects.get(username='analista_lic')
    analista_liq = User.objects.get(username='analista_liq')
    gestao = User.objects.get(username='gestao')

    unidade = (
        UnidadeAdministrativa.objects.filter(ativo=True)
        .exclude(nome__icontains='Controladoria')
        .first()
        or UnidadeAdministrativa.objects.filter(ativo=True).first()
    )
    secretaria = unidade.nome if unidade else 'Sec. Teste'

    esp_lic, _ = EspecieProcesso.objects.get_or_create(
        nome='Pregão Eletrônico',
        grupo='LICITACOES_E_CONTRATOS',
        defaults={'ativo': True, 'gera_relatorio': False},
    )
    esp_liq, _ = EspecieProcesso.objects.get_or_create(
        nome='Pagamento Geral',
        grupo='LIQUIDACOES',
        defaults={
            'ativo': True,
            'gera_relatorio': True,
            'sequencia_numeracao': 'LIQUIDACOES',
        },
    )

    # Limpa cenários extras anteriores.
    Processo.objects.filter(
        numero_processo__startswith='NAV-').delete()
    Processo.objects.filter(
        numero_processo__in=(
            '18640/2023', '18.640/2023', '1122/2026', '18245/2025',
            'ORIGEM-NAV/2026', 'PAG-NAV/2026',
        )).delete()

    def criar(num, especie, **extra):
        dados = {
            'numero_processo': num,
            'volume': '1',
            'secretaria': secretaria,
            'data_entrada': '2026-10-14',
            'hora_entrada': '09:30',
            'especie': especie.nome,
            'especie_id': str(especie.id),
            'genero': especie.grupo,
            'objeto': extra.pop('objeto', f'DEMO navegação {num}'),
            'contratada': extra.pop('contratada', 'Empresa Nav LTDA'),
            'recorrente': 'NAO',
            'prioridade': extra.pop('prioridade', 'NORMAL'),
        }
        dados.update(extra)
        return svc_processos.criar_processo(dados, protocolo)

    # 1) Licitação com diligência (origem) — número sem ponto.
    lic = criar(
        '18245/2025', esp_lic,
        objeto='DEMO origem com pendência (sem ponto no nº)',
        prioridade='URGENTE',
    )
    tramitacao.assumir(lic.id, analista_lic)
    pendencias.criar(
        lic.id, analista_lic,
        '1- Regularizar assinaturas; 2- Juntar portaria; 3- Atualizar FGTS',
    )
    # Libera para "Com o Controlador" (aparecer no filtro da Gestão).
    Processo.objects.filter(id=lic.id).update(
        status_analise='PROSSEGUIMENTO_COM_RESSALVA',
        numero_despacho='NAV-1/2026',
        destino=secretaria,
    )
    AnexoProcesso.objects.get_or_create(
        processo=lic,
        defaults={
            'arquivo': 'anexos/nav-demo.pdf',
            'nome_original': 'parecer-nav.pdf',
            'tamanho': 4,
            'enviado_por': analista_lic,
        },
    )
    try:
        tramitacao.liberar_assinatura(lic.id, analista_lic)
    except Exception as exc:
        print('Aviso liberar 18245/2025:', exc)

    # 2) Liquidação com origem COM ponto (18.245/2025) — aviso deve achar a pendência.
    #    Campos "corretos": pagamento = PAG, origem = 18.245/2025
    liq = criar(
        'PAG-NAV/2026', esp_liq,
        objeto='DEMO Liquidação — origem com ponto; pendência na Licitação',
        contratada='Fornecedor Dupla LTDA',
    )
    Processo.objects.filter(id=liq.id).update(
        processo_pagamento='18.245/2025')
    # Deixa DISPONÍVEL para analista_liq assumir e ver o aviso.
    # (criar_processo já deixa DISPONIVEL)

    # 3) Outra Liquidação com campos INVERTIDOS (como no print do relatório).
    liq_inv = criar(
        '18640/2023', esp_liq,
        objeto='DEMO campos invertidos origem↔pagamento',
    )
    Processo.objects.filter(id=liq_inv.id).update(
        processo_pagamento='1122/2026')
    tramitacao.assumir(liq_inv.id, analista_liq)
    # Pendência nesta passagem (para a próxima com dupla invertida achar).
    pendencias.criar(
        liq_inv.id, analista_liq,
        '1- Pendência da dupla origem/pagamento invertível',
    )

    # 4) Passagem "irmã" com a dupla invertida (número 1122, origem 18640).
    liq_irma = criar(
        '1122/2026', esp_liq,
        objeto='DEMO irmã — campos invertidos em relação a 18640/2023',
    )
    Processo.objects.filter(id=liq_irma.id).update(
        processo_pagamento='18640/2023')

    # 5) Vários disponíveis / urgentes / em análise para encher filas.
    for i in range(1, 5):
        criar(
            f'NAV-DISP-{i:02d}/2026', esp_lic,
            objeto=f'DEMO disponível Licitações #{i}',
            prioridade='PRIORITARIO' if i == 1 else 'NORMAL',
        )
    for i in range(1, 4):
        p = criar(
            f'NAV-ANA-{i:02d}/2026', esp_liq,
            objeto=f'DEMO em análise Liquidação #{i}',
        )
        tramitacao.assumir(p.id, analista_liq)

    # 6) Mais um com controlador (Liquidação) para o card da Gestão.
    p_ctrl = criar(
        'NAV-CTRL/2026', esp_liq,
        objeto='DEMO Com o Controlador — Liquidação',
        prioridade='URGENTE',
    )
    tramitacao.assumir(p_ctrl.id, analista_liq)
    Processo.objects.filter(id=p_ctrl.id).update(
        status_analise='PROSSEGUIMENTO_SEM_RESSALVA',
        numero_relatorio='9101',
        destino=secretaria,
        data_analise=datetime.date(2026, 10, 14),
    )
    p_ctrl.refresh_from_db()
    try:
        tramitacao.liberar_assinatura(p_ctrl.id, analista_liq)
    except Exception as exc:
        print('Aviso liberar NAV-CTRL:', exc)

    # 7) Diligência aberta “só Liquidação” para a tela Diligências.
    p_dil = criar(
        'NAV-DIL/2026', esp_liq,
        objeto='DEMO diligência na tela Gestão → Diligências',
    )
    tramitacao.assumir(p_dil.id, analista_liq)
    pendencias.criar(
        p_dil.id, analista_liq,
        '1- Falta NF; 2- Falta certidão; 3- Atualizar cadastro',
    )

    print('')
    print('=== EXTRAS NAVEGAÇÃO ===')
    print(f'Pendências abertas: {Pendencia.objects.filter(status__in=Pendencia.STATUS_ABERTOS).count()}')
    print(f'Processos totais:   {Processo.objects.count()}')
    print('')
    print('Cenários para testar:')
    print('  · Gestão menu enxuto: login gestao / teste123 → Dashboard')
    print('  · Processos → filtro Com o Controlador (18245/2025, NAV-CTRL…)')
    print('  · Diligências (NAV-DIL e 18245)')
    print('  · Analista Liq assume PAG-NAV/2026 (origem 18.245) → aviso pendência')
    print('  · Analista Liq assume 1122/2026 → vê pendência da dupla invertida')
    print('  · Nº processo clicável nas listas')
    print('')
    print(f'Senha de todos: {SENHA}')
    print('  admin / gestao / protocolo / analista_liq / analista_lic')


if __name__ == '__main__':
    garantir_usuarios()
    extras_navegacao()
    print('')
    print('Pronto. Suba: http://127.0.0.1:8765/')
