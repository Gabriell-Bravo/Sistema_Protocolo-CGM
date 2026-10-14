"""Importação da planilha CONTROLE DE PENDÊNCIAS na tela de Diligências."""

from datetime import date
from io import BytesIO

from django.core.exceptions import PermissionDenied
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from openpyxl import Workbook

from processos_app.models import Pendencia, Processo
from processos_app.services import importar_diligencias as svc
from processos_app.services.tramitacao import TransicaoInvalida

from .base import BaseProcessoTestCase, LIQ


def _xlsx(linhas):
    wb = Workbook()
    ws = wb.active
    for linha in linhas:
        ws.append(linha)
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return SimpleUploadedFile(
        'controle_pendencias.xlsx',
        buf.read(),
        content_type=(
            'application/vnd.openxmlformats-officedocument'
            '.spreadsheetml.sheet'),
    )


CABECALHO = [
    'Processo origem', 'Processo Pagamento', 'Secretaria', 'Objeto',
    'Pendência', 'Data da pendência', 'Envio para Simone', 'Data de Saneamento',
]


class ImportarDiligenciasTest(BaseProcessoTestCase):

    def test_normalizar_numero_e_descricao(self):
        self.assertEqual(svc.normalizar_numero('24.273/2025'), '24273/2025')
        self.assertEqual(svc.normalizar_numero(' 24273/2025 '), '24273/2025')
        self.assertEqual(
            svc.normalizar_descricao('  Falta   certidão  '),
            'falta certidão')

    def test_importa_nova_e_ignora_duplicata(self):
        processo = self.novo_processo(
            self.especie_liq,
            numero_processo='24273/2025',
            processo_pagamento='1000/2024',
        )
        Pendencia.objects.create(
            processo=processo,
            descricao='Falta certidão',
            criada_por=self.gestao,
            status='AGUARDANDO_ATENDIMENTO',
        )

        arquivo = _xlsx([
            CABECALHO,
            [
                '1.000/2024', '24.273/2025', 'SESA', 'Objeto X',
                'Falta certidão', date(2025, 1, 10), None, None,
            ],
            [
                '1000/2024', '24273/2025', 'SESA', 'Objeto X',
                'Falta NF', date(2025, 2, 1), None, None,
            ],
            [
                '1000/2024', '24273/2025', 'SESA', 'Objeto X',
                'falta  nf', date(2025, 2, 2), None, None,
            ],
        ])

        resultado = svc.importar_planilha(self.gestao, arquivo)
        self.assertEqual(resultado['criadas'], 1)
        self.assertEqual(resultado['ignoradas'], 2)
        self.assertEqual(resultado['processos_novos'], 0)
        self.assertEqual(resultado['lidas'], 3)
        self.assertEqual(
            Pendencia.objects.filter(processo=processo)
            .exclude(status='CANCELADA').count(),
            2)
        nova = Pendencia.objects.get(processo=processo, descricao='Falta NF')
        self.assertEqual(nova.status, 'AGUARDANDO_ATENDIMENTO')

    def test_cria_stub_quando_processo_nao_existe(self):
        arquivo = _xlsx([
            CABECALHO,
            [
                '99.001/2024', '88.002/2025', 'SMS', 'Contrato Y',
                'Pedir esclarecimento', date(2025, 3, 1), None, None,
            ],
        ])
        resultado = svc.importar_planilha(self.gestao, arquivo)
        self.assertEqual(resultado['criadas'], 1)
        self.assertEqual(resultado['processos_novos'], 1)
        processo = Processo.objects.get(numero_processo='88002/2025')
        self.assertEqual(processo.genero, LIQ)
        self.assertEqual(processo.processo_pagamento, '99001/2024')
        self.assertTrue(
            Pendencia.objects.filter(
                processo=processo,
                descricao='Pedir esclarecimento').exists())

    def test_saneada_vem_como_resolvida(self):
        arquivo = _xlsx([
            CABECALHO,
            [
                '', '77001/2025', 'SEFIN', 'Obj',
                'Já sanada na planilha', date(2025, 1, 1), None,
                date(2025, 4, 15),
            ],
        ])
        resultado = svc.importar_planilha(self.gestao, arquivo)
        self.assertEqual(resultado['criadas'], 1)
        self.assertEqual(resultado['saneadas'], 1)
        p = Pendencia.objects.get(descricao='Já sanada na planilha')
        self.assertEqual(p.status, 'RESOLVIDA')
        self.assertIsNotNone(p.resolvida_em)

    def test_analista_nao_importa(self):
        arquivo = _xlsx([CABECALHO, ['1/2024', '2/2025', 'X', 'Y', 'Z', None, None, None]])
        with self.assertRaises(PermissionDenied):
            svc.importar_planilha(self.analista_liq, arquivo)

    def test_view_upload_gestao(self):
        self.client.force_login(self.gestao)
        pagina = self.client.get(reverse('gestao_diligencias'))
        self.assertContains(pagina, 'Importar Excel')
        self.assertContains(pagina, reverse('gestao_diligencias_importar'))

        arquivo = _xlsx([
            CABECALHO,
            [
                '10/2024', '20/2025', 'SESA', 'Obj',
                'Diligência via upload', None, None, None,
            ],
        ])
        resp = self.client.post(
            reverse('gestao_diligencias_importar'),
            {'planilha': arquivo},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(
            Pendencia.objects.filter(
                descricao='Diligência via upload').exists())

    def test_view_analista_nao_ve_botao_e_post_falha(self):
        self.client.force_login(self.analista_lic)
        pagina = self.client.get(reverse('gestao_diligencias'))
        self.assertNotContains(pagina, 'Importar Excel')

        arquivo = _xlsx([
            CABECALHO,
            ['1/2024', '2/2025', 'X', 'Y', 'Bloqueada', None, None, None],
        ])
        antes = Pendencia.objects.count()
        resp = self.client.post(
            reverse('gestao_diligencias_importar'),
            {'planilha': arquivo},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(Pendencia.objects.count(), antes)

    def test_planilha_sem_cabecalho_valido(self):
        arquivo = _xlsx([['A', 'B'], ['1', '2']])
        with self.assertRaises(TransicaoInvalida):
            svc.importar_planilha(self.gestao, arquivo)
