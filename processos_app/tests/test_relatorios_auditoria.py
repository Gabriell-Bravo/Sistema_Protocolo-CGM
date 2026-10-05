"""Auditoria de numeração/cancelamento — casos-limite para achar falhas.

Roda com:
  python manage.py test processos_app.tests.test_relatorios_auditoria -v 2
"""

from django.core.exceptions import PermissionDenied
from django.urls import reverse

from processos_app.models import LinhaControleRelatorio, SequenciaRelatorio
from processos_app.services import processos as svc_processos
from processos_app.services import relatorios, tramitacao

from .base import BaseProcessoTestCase, criar_usuario


class AuditoriaNumeracaoTest(BaseProcessoTestCase):
    """Cada método isola um risco: número perdido, duplicado, contador errado."""

    def setUp(self):
        self.admin = criar_usuario(
            f'adm_{self._testMethodName[:20]}', 'GESTAO', is_superuser=True)

    def _salvar(self, processo, analista=None):
        analista = analista or self.analista_liq
        if processo.situacao_tramite != 'EM_ANALISE':
            tramitacao.assumir(processo.id, analista)
            processo.refresh_from_db()
        svc_processos.aplicar_analise(processo, {
            'destino': 'Unidade de Teste',
            'valor': '1000',
            'status_analise': 'PROSSEGUIMENTO_SEM_RESSALVA',
            'gerar_numero': '1',
        }, analista)
        processo.refresh_from_db()
        return processo

    def _proximo(self, grupo='LIQUIDACOES'):
        return SequenciaRelatorio.objects.get(grupo=grupo).proximo_numero

    def test_01_cancelar_nao_reemite_no_proximo_automatico(self):
        """Cancelado (vermelho): próximo automático segue o contador."""
        relatorios.definir_ultimo_numero(self.admin, 100)
        a = self._salvar(self.novo_processo(self.especie_liq, numero_processo='a1/26'))
        self.assertEqual(a.numero_relatorio, '101')
        linha = LinhaControleRelatorio.objects.get(processo=a)
        relatorios.cancelar_linha(self.admin, linha.id)
        self.assertNotIn(101, relatorios.numeros_usados('LIQUIDACOES'))
        b = self._salvar(self.novo_processo(self.especie_liq, numero_processo='a2/26'))
        self.assertEqual(b.numero_relatorio, '102')
        self.assertEqual(
            LinhaControleRelatorio.objects.filter(numero_relatorio='101').count(), 1)

    def test_02_cancelar_excluir_nao_reemite_automatico(self):
        """Vermelho: número fora da sequência não volta no próximo automático."""
        relatorios.definir_ultimo_numero(self.admin, 200)
        a = self._salvar(self.novo_processo(self.especie_liq, numero_processo='b1/26'))
        self.assertEqual(a.numero_relatorio, '201')
        linha = LinhaControleRelatorio.objects.get(processo=a)
        relatorios.cancelar_linha(self.admin, linha.id, 'excluir')
        self.assertNotIn(201, relatorios.numeros_usados('LIQUIDACOES'))
        b = self._salvar(self.novo_processo(self.especie_liq, numero_processo='b2/26'))
        self.assertEqual(b.numero_relatorio, '202')
        self.assertEqual(
            LinhaControleRelatorio.objects.filter(numero_relatorio='201').count(), 1)

    def test_03_reativar_vermelho_mesmo_numero(self):
        relatorios.definir_ultimo_numero(self.admin, 300)
        a = self._salvar(self.novo_processo(self.especie_liq, numero_processo='c1/26'))
        linha = LinhaControleRelatorio.objects.get(processo=a)
        relatorios.cancelar_linha(self.admin, linha.id)
        novo = self.novo_processo(self.especie_liq, numero_processo='c2/26')
        tramitacao.assumir(novo.id, self.analista_liq)
        relatorios.alterar_numero(self.analista_liq, novo.id, 301, '2026-10-02')
        linha.refresh_from_db()
        self.assertEqual(linha.situacao_linha, 'ATIVA')
        self.assertEqual(linha.processo_id, novo.id)

        relatorios.cancelar_linha(self.admin, linha.id)
        outro = self.novo_processo(self.especie_liq, numero_processo='c3/26')
        tramitacao.assumir(outro.id, self.analista_liq)
        relatorios.alterar_numero(self.analista_liq, outro.id, 301, '2026-10-03')
        linha.refresh_from_db()
        self.assertEqual(linha.situacao_linha, 'ATIVA')
        self.assertEqual(linha.processo_id, outro.id)
        self.assertEqual(
            LinhaControleRelatorio.objects.filter(numero_relatorio='301').count(), 1)

    def test_04_dois_processos_mesmo_numero_manual_ambos_ativos(self):
        """Ao pegar número já ativo, o processo antigo é desvinculado."""
        relatorios.definir_ultimo_numero(self.admin, 400)
        a = self._salvar(self.novo_processo(self.especie_liq, numero_processo='d1/26'))
        b = self.novo_processo(self.especie_liq, numero_processo='d2/26')
        tramitacao.assumir(b.id, self.analista_liq)
        relatorios.alterar_numero(self.analista_liq, b.id, int(a.numero_relatorio), '2026-10-02')
        a.refresh_from_db()
        b.refresh_from_db()
        self.assertEqual(b.numero_relatorio, '401')
        self.assertFalse(a.numero_relatorio)
        ativos = LinhaControleRelatorio.objects.filter(
            numero_relatorio='401', situacao_linha='ATIVA')
        self.assertEqual(ativos.count(), 1)
        self.assertEqual(ativos.get().processo_id, b.id)
    def test_05_cancelar_e_salvar_analise_de_novo_gera_numero_novo(self):
        """Após cancelar, Gerar número de novo recebe o próximo sequencial."""
        relatorios.definir_ultimo_numero(self.admin, 500)
        p = self._salvar(self.novo_processo(self.especie_liq, numero_processo='e1/26'))
        n1 = p.numero_relatorio
        linha = LinhaControleRelatorio.objects.get(processo=p)
        relatorios.cancelar_linha(self.admin, linha.id)
        p.refresh_from_db()
        self.assertFalse(p.numero_relatorio)
        self._salvar(p)
        p.refresh_from_db()
        self.assertTrue(p.numero_relatorio)
        self.assertNotEqual(p.numero_relatorio, n1)
        self.assertEqual(p.numero_relatorio, '502')

    def test_06_apagar_linha_ativa_some_e_limpa_processo(self):
        relatorios.definir_ultimo_numero(self.admin, 600)
        p = self._salvar(self.novo_processo(self.especie_liq, numero_processo='f1/26'))
        linha = LinhaControleRelatorio.objects.get(processo=p)
        info = relatorios.apagar_linha(self.admin, linha.id)
        self.assertEqual(info['numero_relatorio'], '601')
        self.assertFalse(LinhaControleRelatorio.objects.filter(id=linha.id).exists())
        p.refresh_from_db()
        self.assertFalse(p.numero_relatorio)

    def test_07_apagar_linha_vermelha_some_sem_voltar_contador(self):
        relatorios.definir_ultimo_numero(self.admin, 700)
        a = self._salvar(self.novo_processo(self.especie_liq, numero_processo='g1/26'))
        b = self._salvar(self.novo_processo(self.especie_liq, numero_processo='g2/26'))
        self.assertEqual(self._proximo(), 703)
        linha_a = LinhaControleRelatorio.objects.get(processo=a)
        relatorios.cancelar_linha(self.admin, linha_a.id, 'excluir')
        linha_a.refresh_from_db()
        relatorios.apagar_linha(self.admin, linha_a.id)
        self.assertFalse(
            LinhaControleRelatorio.objects.filter(numero_relatorio='701').exists())
        # Contador não deve voltar por apagar vermelha do meio.
        self.assertEqual(self._proximo(), 703)
        b.refresh_from_db()
        self.assertEqual(b.numero_relatorio, '702')

    def test_08_apagar_ultima_ativa_volta_contador(self):
        relatorios.definir_ultimo_numero(self.admin, 800)
        p = self._salvar(self.novo_processo(self.especie_liq, numero_processo='h1/26'))
        self.assertEqual(self._proximo(), 802)
        linha = LinhaControleRelatorio.objects.get(processo=p)
        relatorios.apagar_linha(self.admin, linha.id)
        self.assertEqual(self._proximo(), 801)
        q = self._salvar(self.novo_processo(self.especie_liq, numero_processo='h2/26'))
        self.assertEqual(q.numero_relatorio, '801')

    def test_09_gestao_nao_apaga_analista_liq_nao_apaga(self):
        relatorios.definir_ultimo_numero(self.admin, 900)
        p = self._salvar(self.novo_processo(self.especie_liq, numero_processo='i1/26'))
        linha = LinhaControleRelatorio.objects.get(processo=p)
        with self.assertRaises(PermissionDenied):
            relatorios.apagar_linha(self.gestao, linha.id)
        with self.assertRaises(PermissionDenied):
            relatorios.apagar_linha(self.analista_liq, linha.id)
        self.assertTrue(LinhaControleRelatorio.objects.filter(id=linha.id).exists())

    def test_10_troca_sequencia_libera_origem_e_pega_destino(self):
        relatorios.definir_ultimo_numero(self.admin, 1000, 'LIQUIDACOES')
        relatorios.definir_ultimo_numero(self.admin, 50, 'BOLSA_ATLETA')
        p = self._salvar(self.novo_processo(self.especie_liq, numero_processo='j1/26'))
        antigo = p.numero_relatorio
        relatorios.alterar_sequencia(self.admin, p.id, 'BOLSA_ATLETA')
        p.refresh_from_db()
        self.assertEqual(p.numero_relatorio, '51')
        linha = LinhaControleRelatorio.objects.get(processo=p)
        self.assertEqual(linha.sequencia, 'BOLSA_ATLETA')
        # Número antigo da liquidação não deve ficar preso como ATIVO.
        self.assertFalse(
            LinhaControleRelatorio.objects.filter(
                numero_relatorio=antigo, situacao_linha='ATIVA',
                processo__isnull=False).exclude(processo=p).exists())

    def test_11_cancelar_sem_relatorio_backend_aceita_ui_esconde(self):
        """Linha 'sem relatório' existe; cancelar no backend funciona, UI só mostra se tiver número."""
        p = self.novo_processo(self.especie_liq, numero_processo='k1/26')
        tramitacao.assumir(p.id, self.analista_liq)
        p.refresh_from_db()
        svc_processos.aplicar_analise(p, {
            'destino': 'Unidade de Teste',
            'valor': '1000',
            'status_analise': 'PROSSEGUIMENTO_SEM_RESSALVA',
            'sem_relatorio': '1',
        }, self.analista_liq)
        p.refresh_from_db()
        linha = LinhaControleRelatorio.objects.get(processo=p)
        self.assertTrue(linha.sem_relatorio)
        # Backend permite cancelar linha sem número se for sem_relatorio.
        relatorios.cancelar_linha(self.admin, linha.id, 'excluir')
        linha.refresh_from_db()
        self.assertEqual(linha.situacao_linha, 'CANCELADA')
        self.assertIsNone(linha.processo_id)
        # Na tela, o botão cancelar exige numero_relatorio — só admin apaga.
        self.client.force_login(self.admin)
        pagina = self.client.get(reverse('controle_relatorio'))
        self.assertContains(pagina, 'data-apagar-linha')

    def test_12_reativar_numero_nao_deve_criar_segunda_linha(self):
        relatorios.definir_ultimo_numero(self.admin, 1100)
        a = self._salvar(self.novo_processo(self.especie_liq, numero_processo='l1/26'))
        linha = LinhaControleRelatorio.objects.get(processo=a)
        relatorios.cancelar_linha(self.admin, linha.id, 'excluir')
        # Processo A ainda existe sem número; se salvar de novo gera 1102.
        # Novo processo pega 1101 manualmente.
        novo = self.novo_processo(self.especie_liq, numero_processo='l2/26')
        tramitacao.assumir(novo.id, self.analista_liq)
        relatorios.alterar_numero(self.analista_liq, novo.id, 1101, '2026-10-02')
        self.assertEqual(
            LinhaControleRelatorio.objects.filter(numero_relatorio='1101').count(), 1)
        a.refresh_from_db()
        self._salvar(a)
        a.refresh_from_db()
        self.assertEqual(a.numero_relatorio, '1102')
        self.assertEqual(
            LinhaControleRelatorio.objects.filter(numero_relatorio='1101').count(), 1)

    def test_13_alterar_numero_para_outro_ativo_nao_deve_sobrescrever_silencioso(self):
        """Se B pega o número de A ativo, A perde o número e a linha fica só com B."""
        relatorios.definir_ultimo_numero(self.admin, 1200)
        a = self._salvar(self.novo_processo(self.especie_liq, numero_processo='m1/26'))
        b = self._salvar(self.novo_processo(self.especie_liq, numero_processo='m2/26'))
        num_a = int(a.numero_relatorio)
        resultado = relatorios.alterar_numero(
            self.analista_liq, b.id, num_a, '2026-10-02')
        a.refresh_from_db()
        b.refresh_from_db()
        self.assertEqual(b.numero_relatorio, str(num_a))
        self.assertFalse(a.numero_relatorio)
        self.assertEqual(
            LinhaControleRelatorio.objects.filter(
                numero_relatorio=str(num_a), situacao_linha='ATIVA').count(), 1)
        self.assertIn('m1/26', getattr(resultado, '_numeros_desvinculados', []))
        liberado = LinhaControleRelatorio.objects.get(numero_relatorio='1202')
        self.assertEqual(liberado.situacao_linha, 'CANCELADA')
        self.assertIsNone(liberado.processo_id)

    def test_14_contador_nao_volta_ao_cancelar_ultimo(self):
        """Cancelar NÃO deve rebobinar o contador — só apagar."""
        relatorios.definir_ultimo_numero(self.admin, 1300)
        p = self._salvar(self.novo_processo(self.especie_liq, numero_processo='n1/26'))
        self.assertEqual(self._proximo(), 1302)
        linha = LinhaControleRelatorio.objects.get(processo=p)
        relatorios.cancelar_linha(self.admin, linha.id, 'excluir')
        self.assertEqual(self._proximo(), 1302)
        q = self._salvar(self.novo_processo(self.especie_liq, numero_processo='n2/26'))
        self.assertEqual(q.numero_relatorio, '1302')

    def test_15_declinar_analise_deixa_numero_verde_para_reuso(self):
        relatorios.definir_ultimo_numero(self.admin, 1400)
        p = self._salvar(self.novo_processo(self.especie_liq, numero_processo='o1/26'))
        self.assertEqual(p.numero_relatorio, '1401')
        tramitacao.declinar_analise(p.id, self.analista_liq, 'desistiu do relatório')
        p.refresh_from_db()
        self.assertFalse(p.numero_relatorio)
        liberado = LinhaControleRelatorio.objects.get(numero_relatorio='1401')
        self.assertIsNone(liberado.processo_id)
        self.assertEqual(liberado.situacao_linha, 'RESERVADA')
        # Contador não regride: o reuso vem da linha verde no mesmo dia.
        self.assertEqual(self._proximo(), 1402)
        q = self._salvar(self.novo_processo(self.especie_liq, numero_processo='o2/26'))
        self.assertEqual(q.numero_relatorio, '1401')

    def test_17_trocar_numero_preserva_antigo_na_planilha(self):
        """Trocar 9003→9004 não some com o 9003: fica vermelho com data."""
        relatorios.definir_ultimo_numero(self.admin, 1600)
        p = self._salvar(self.novo_processo(self.especie_liq, numero_processo='t1/26'))
        self.assertEqual(p.numero_relatorio, '1601')
        data_antiga = LinhaControleRelatorio.objects.get(processo=p).data_relatorio
        relatorios.alterar_numero(self.analista_liq, p.id, 1605, '2026-10-05')
        p.refresh_from_db()
        self.assertEqual(p.numero_relatorio, '1605')
        liberado = LinhaControleRelatorio.objects.get(numero_relatorio='1601')
        self.assertEqual(liberado.situacao_linha, 'CANCELADA')
        self.assertIsNone(liberado.processo_id)
        self.assertEqual(liberado.data_relatorio, data_antiga)
        ativo = LinhaControleRelatorio.objects.get(processo=p)
        self.assertEqual(ativo.numero_relatorio, '1605')
        self.assertEqual(str(ativo.data_relatorio), '2026-10-05')
        # Reuso do número específico reativa a linha vermelha.
        outro = self.novo_processo(self.especie_liq, numero_processo='t2/26')
        tramitacao.assumir(outro.id, self.analista_liq)
        relatorios.alterar_numero(self.analista_liq, outro.id, 1601, '2026-10-06')
        liberado.refresh_from_db()
        self.assertEqual(liberado.situacao_linha, 'ATIVA')
        self.assertEqual(liberado.processo_id, outro.id)

    def test_16_http_apagar_e_cancelar_fluxo_completo(self):
        relatorios.definir_ultimo_numero(self.admin, 1500)
        p = self._salvar(self.novo_processo(self.especie_liq, numero_processo='p1/26'))
        linha = LinhaControleRelatorio.objects.get(processo=p)
        self.client.force_login(self.admin)
        r1 = self.client.post(
            reverse('controle_relatorio_cancelar_linha', args=[linha.id]), {
                'destino_numero': 'excluir', 'grupo': 'LIQUIDACOES',
            })
        self.assertEqual(r1.status_code, 302)
        linha.refresh_from_db()
        self.assertEqual(linha.situacao_linha, 'CANCELADA')
        r2 = self.client.post(
            reverse('controle_relatorio_apagar_linha', args=[linha.id]), {
                'grupo': 'LIQUIDACOES',
            })
        self.assertEqual(r2.status_code, 302)
        self.assertFalse(LinhaControleRelatorio.objects.filter(id=linha.id).exists())
