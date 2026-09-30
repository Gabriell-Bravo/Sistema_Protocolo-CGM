from django.core.exceptions import PermissionDenied
from django.urls import reverse

from processos_app.models import LinhaControleRelatorio
from processos_app.services import processos as svc_processos
from processos_app.services import relatorios, tramitacao

from .base import BaseProcessoTestCase, criar_usuario


class ControleRelatorioTest(BaseProcessoTestCase):

    def _encaminhar_liquidacao(self, processo, analista=None):
        analista = analista or self.analista_liq
        if processo.situacao_tramite != 'EM_ANALISE':
            tramitacao.assumir(processo.id, analista)
            processo.refresh_from_db()
        self.preencher_analise(processo, numero_despacho=None)
        tramitacao.liberar_assinatura(processo.id, analista)
        processo.refresh_from_db()
        return processo

    def test_admin_define_ultimo_e_proximo_encaminhado_continua(self):
        admin = criar_usuario('admin_rel', 'GESTAO', is_superuser=True)
        relatorios.definir_ultimo_numero(admin, 2000)
        estado = relatorios.estado_sequencia()
        self.assertEqual(estado['ultimo'], 2000)
        self.assertEqual(estado['proximo'], 2001)

        processo = self.novo_processo(self.especie_liq, numero_processo='9/2026')
        tramitacao.assumir(processo.id, self.analista_liq)
        processo.refresh_from_db()
        self.assertFalse(processo.numero_relatorio)
        self.assertFalse(LinhaControleRelatorio.objects.filter(processo=processo).exists())

        self._encaminhar_liquidacao(processo)
        self.assertEqual(processo.numero_relatorio, '2001')
        linha = LinhaControleRelatorio.objects.get(processo=processo)
        self.assertEqual(linha.numero_processo, '9/2026')
        self.assertEqual(linha.numero_relatorio, '2001')
        self.assertEqual(linha.analista, processo.nome_analista)

    def test_analista_nao_define_ultimo(self):
        with self.assertRaises(PermissionDenied):
            relatorios.definir_ultimo_numero(self.analista_liq, 10)

    def test_salvar_analise_atualiza_planilha_depois_do_encaminhamento(self):
        processo = self.novo_processo(self.especie_liq, numero_processo='10/2026')
        tramitacao.assumir(processo.id, self.analista_liq)
        processo.refresh_from_db()
        svc_processos.aplicar_analise(processo, {
            'destino': 'Unidade de Teste',
            'valor': '1000',
            'status_analise': 'PROSSEGUIMENTO_SEM_RESSALVA',
        }, self.analista_liq)
        self.assertFalse(LinhaControleRelatorio.objects.filter(processo=processo).exists())
        tramitacao.liberar_assinatura(processo.id, self.analista_liq)
        linha = LinhaControleRelatorio.objects.get(processo=processo)
        self.assertEqual(linha.destino, 'Unidade de Teste')
        self.assertEqual(linha.valor, '1000')
        self.assertEqual(linha.status_analise, 'PROSSEGUIMENTO_SEM_RESSALVA')

    def test_declinar_nao_reutiliza_numero(self):
        admin = criar_usuario('admin_gasto', 'GESTAO', is_superuser=True)
        relatorios.definir_ultimo_numero(admin, 2000)
        primeiro = self.novo_processo(self.especie_liq, numero_processo='11/2026')
        self._encaminhar_liquidacao(primeiro)
        self.assertEqual(primeiro.numero_relatorio, '2001')
        tramitacao.desfazer_tramite(primeiro.id, admin)
        tramitacao.declinar_analise(primeiro.id, self.analista_liq, 'Teste')
        self.assertFalse(LinhaControleRelatorio.objects.filter(
            processo=primeiro).exists())

        segundo = self.novo_processo(self.especie_liq, numero_processo='11b/2026')
        self._encaminhar_liquidacao(segundo)
        self.assertNotEqual(segundo.numero_relatorio, '2001')

    def test_dois_analistas_nao_recebem_o_mesmo_numero(self):
        outro = criar_usuario('dana_liq', 'ANALISTA_LIQUIDACOES')
        p1 = self.novo_processo(self.especie_liq, numero_processo='14/2026')
        p2 = self.novo_processo(self.especie_liq, numero_processo='15/2026')
        self._encaminhar_liquidacao(p1, self.analista_liq)
        self._encaminhar_liquidacao(p2, outro)
        self.assertTrue(p1.numero_relatorio)
        self.assertTrue(p2.numero_relatorio)
        self.assertNotEqual(p1.numero_relatorio, p2.numero_relatorio)

    def test_admin_corrige_numero_de_analise_ja_feita(self):
        admin = criar_usuario('admin_edit', 'GESTAO', is_superuser=True)
        processo = self.novo_processo(self.especie_liq, numero_processo='16/2026')
        tramitacao.assumir(processo.id, self.analista_liq)
        with self.assertRaises(relatorios.RelatorioInvalido):
            relatorios.alterar_numero(admin, processo.id, 3300)

        self._encaminhar_liquidacao(processo)
        relatorios.alterar_numero(admin, processo.id, 3300)
        processo.refresh_from_db()
        self.assertEqual(processo.numero_relatorio, '3300')
        linha = LinhaControleRelatorio.objects.get(processo=processo)
        self.assertEqual(linha.numero_relatorio, '3300')
        self.assertEqual(relatorios.estado_sequencia()['proximo'], 3301)

        with self.assertRaises(PermissionDenied):
            relatorios.alterar_numero(self.analista_liq, processo.id, 3301)

        outro = self.novo_processo(self.especie_liq, numero_processo='17/2026')
        self._encaminhar_liquidacao(outro)
        with self.assertRaises(relatorios.RelatorioInvalido):
            relatorios.alterar_numero(admin, outro.id, 3300)

    def test_tela_analista_ve_planilha_admin_define_ultimo(self):
        processo = self.novo_processo(self.especie_liq, numero_processo='12/2026')
        self._encaminhar_liquidacao(processo)

        self.client.force_login(self.analista_liq)
        pagina = self.client.get(reverse('controle_relatorio'))
        self.assertEqual(pagina.status_code, 200)
        self.assertContains(pagina, 'Planilha de relatórios')
        self.assertNotContains(pagina, 'Último número já usado')
        self.assertContains(pagina, processo.numero_relatorio)
        self.assertContains(pagina, '12/2026')
        self.assertNotContains(pagina, 'name="numero_relatorio"')

        admin = criar_usuario('admin_rel2', 'GESTAO', is_superuser=True)
        self.client.force_login(admin)
        pagina = self.client.get(reverse('controle_relatorio'))
        self.assertContains(pagina, 'Último número já usado')
        self.assertContains(pagina, '12/2026')
        self.assertContains(pagina, 'name="numero_relatorio"')

    def test_protocolo_nao_acessa(self):
        self.client.force_login(self.protocolo)
        self.assertEqual(
            self.client.get(reverse('controle_relatorio')).status_code, 403)

    def test_analista_de_licitacoes_nao_ve_linha_de_liquidacao(self):
        processo = self.novo_processo(self.especie_liq, numero_processo='13/2026')
        self._encaminhar_liquidacao(processo)
        self.client.force_login(self.analista_lic)
        pagina = self.client.get(reverse('controle_relatorio'))
        self.assertEqual(pagina.status_code, 200)
        self.assertNotContains(pagina, '13/2026')
