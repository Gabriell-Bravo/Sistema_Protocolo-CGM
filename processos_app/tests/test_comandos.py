import datetime
from io import StringIO

from django.core.management import call_command

from processos_app.models import Processo

from .base import BaseProcessoTestCase


class SanearDadosTest(BaseProcessoTestCase):

    def _saida_so_em_data_saida(self):
        processo = self.novo_processo()
        Processo.objects.filter(id=processo.id).update(
            data_saida=datetime.date(2026, 9, 5), situacao_tramite='DISPONIVEL')
        return processo

    def test_relatorio_nao_grava(self):
        processo = self._saida_so_em_data_saida()
        call_command('sanear_dados', stdout=StringIO())
        processo.refresh_from_db()
        self.assertEqual(processo.situacao_tramite, 'DISPONIVEL')

    def test_aplicar_corrige_saida_legada(self):
        processo = self._saida_so_em_data_saida()
        call_command('sanear_dados', '--aplicar', stdout=StringIO())
        processo.refresh_from_db()
        self.assertEqual(processo.situacao_tramite, 'SAIDA_CONCLUIDA')
        self.assertIsNotNone(processo.saida_concluida_em)
        self.assertTrue(processo.eventos.filter(tipo='SAIDA_CONCLUIDA').exists())

    def test_status_monitoramento(self):
        processo = self.novo_processo(self.especie_monit)
        Processo.objects.filter(id=processo.id).update(
            proxima_data_monitoramento=datetime.date.today() - datetime.timedelta(days=2))
        call_command('atualizar_status_monitoramento', stdout=StringIO())
        processo.refresh_from_db()
        self.assertEqual(processo.status_monitoramento, 'ATRASADO')
