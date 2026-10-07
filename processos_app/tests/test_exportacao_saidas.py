"""Exportação/impressão de saídas: períodos, grupo, sequência e Excel."""

import datetime

from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from processos_app.models import EspecieProcesso
from processos_app.services import exportacao_saidas as svc
from processos_app.services import tramitacao

from .base import LIQ, BaseProcessoTestCase

STATIC = {'STORAGES': {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
}}


@override_settings(**STATIC)
class ExportacaoSaidasTest(BaseProcessoTestCase):

    def _saida(self, especie=None, numero='exp-1/2026', data_saida=None):
        especie = especie or self.especie_liq
        processo = self.novo_processo(especie, numero_processo=numero)
        tramitacao.assumir(processo.id, self.analista_liq)
        processo.refresh_from_db()
        self.preencher_analise(processo)
        tramitacao.liberar_assinatura(processo.id, self.analista_liq)
        tramitacao.disponibilizar_retirada(processo.id, self.protocolo)
        tramitacao.registrar_saida([processo.id], self.protocolo)
        processo.refresh_from_db()
        if data_saida is not None:
            processo.data_saida = data_saida
            processo.save(update_fields=['data_saida'])
            processo.refresh_from_db()
        return processo

    def test_resolver_periodo_hoje_semana_mes_todas(self):
        hoje = datetime.date(2026, 10, 7)  # terça
        self.assertEqual(
            svc.resolver_periodo('hoje', hoje=hoje), (hoje, hoje))
        ini, fim = svc.resolver_periodo('semana', hoje=hoje)
        self.assertEqual(ini, datetime.date(2026, 10, 5))  # segunda
        self.assertEqual(fim, datetime.date(2026, 10, 11))
        ini_m, fim_m = svc.resolver_periodo('mes', hoje=hoje)
        self.assertEqual(ini_m, datetime.date(2026, 10, 1))
        self.assertEqual(fim_m, datetime.date(2026, 10, 31))
        self.assertEqual(svc.resolver_periodo('todas', hoje=hoje), (None, None))

    def test_tela_exportar_periodo_hoje_e_preview(self):
        hoje = timezone.localdate()
        p = self._saida(numero='exp-hoje/2026', data_saida=hoje)
        antigo = self._saida(
            numero='exp-antigo/2026',
            data_saida=hoje - datetime.timedelta(days=10))

        self.client.force_login(self.protocolo)
        pagina = self.client.get(
            reverse('exportar_saidas') + '?periodo=hoje')
        self.assertEqual(pagina.status_code, 200)
        self.assertContains(pagina, 'id="folhaSaidas"')
        self.assertContains(pagina, 'Preview da impressão')
        self.assertContains(pagina, p.numero_processo)
        self.assertNotContains(pagina, antigo.numero_processo)
        self.assertContains(pagina, 'Imprimir')
        self.assertContains(pagina, 'Baixar Excel')

    def test_filtro_liquidacoes_bolsa_atleta(self):
        bolsa, _ = EspecieProcesso.objects.get_or_create(
            nome='Concessão Aux. Bolsa Atleta',
            grupo=LIQ,
            defaults={
                'ativo': True,
                'gera_relatorio': True,
                'sequencia_numeracao': 'BOLSA_ATLETA',
            },
        )
        if bolsa.sequencia_numeracao != 'BOLSA_ATLETA' or not bolsa.ativo:
            bolsa.sequencia_numeracao = 'BOLSA_ATLETA'
            bolsa.ativo = True
            bolsa.gera_relatorio = True
            bolsa.save()
        pagamento = self.especie_liq
        p_bolsa = self._saida(especie=bolsa, numero='bolsa-1/2026')
        p_pag = self._saida(especie=pagamento, numero='pag-1/2026')

        self.client.force_login(self.gestao)
        pagina = self.client.get(
            reverse('exportar_saidas')
            + '?periodo=todas&genero=LIQUIDACOES&sequencia=BOLSA_ATLETA')
        self.assertEqual(pagina.status_code, 200)
        self.assertContains(pagina, p_bolsa.numero_processo)
        self.assertNotContains(pagina, p_pag.numero_processo)
        self.assertContains(pagina, 'Bolsa Atleta')

    def test_analista_nao_exporta(self):
        self.client.force_login(self.analista_liq)
        resp = self.client.get(reverse('exportar_saidas'))
        self.assertEqual(resp.status_code, 403)
        resp_x = self.client.get(reverse('exportar_finalizados_excel'))
        self.assertEqual(resp_x.status_code, 403)

    def test_excel_mesmos_filtros_incluindo_todas(self):
        import io
        import zipfile

        p = self._saida(numero='excel-1/2026')
        self.client.force_login(self.protocolo)
        resp = self.client.get(
            reverse('exportar_finalizados_excel') + '?periodo=todas')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('spreadsheet', resp['Content-Type'])
        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            xml = b''.join(zf.read(name) for name in zf.namelist()
                           if name.endswith('.xml'))
        self.assertIn(b'excel-1/2026', xml)

        data = p.data_saida.isoformat()
        resp2 = self.client.get(
            reverse('exportar_finalizados_excel')
            + f'?periodo=personalizado&data_inicial={data}&data_final={data}')
        self.assertEqual(resp2.status_code, 200)
        self.assertIn('spreadsheet', resp2['Content-Type'])

    def test_personalizado_sem_datas_mostra_aviso(self):
        self.client.force_login(self.gestao)
        pagina = self.client.get(
            reverse('exportar_saidas') + '?periodo=personalizado')
        self.assertEqual(pagina.status_code, 200)
        self.assertContains(pagina, 'Informe a data inicial')
