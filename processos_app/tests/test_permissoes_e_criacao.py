from django.core.exceptions import PermissionDenied

from processos_app.models import EventoProcesso, Processo
from processos_app.services import permissions as perm
from processos_app.services import processos as svc_processos

from .base import LIC, LIQ, BaseProcessoTestCase, criar_usuario


class PapeisTest(BaseProcessoTestCase):

    def test_papeis_basicos(self):
        self.assertTrue(perm.is_protocolo(self.protocolo))
        self.assertTrue(perm.is_analista(self.analista_lic))
        self.assertTrue(perm.is_gestao(self.gestao))
        self.assertEqual(perm.grupo_do_analista(self.analista_liq), LIQ)

    def test_superusuario_nao_ganha_papel_automaticamente(self):
        """Superusuário deixou de ter atalho de permissão: vale o papel."""
        su = criar_usuario('su', 'PROTOCOLO', is_superuser=True, is_staff=True)
        self.assertTrue(perm.is_protocolo(su))
        self.assertFalse(perm.is_gestao(su))

    def test_nivel_legado_quando_papel_vazio(self):
        u = criar_usuario('legado', 'GESTAO')
        u.profile.papel = ''
        u.profile.level = '1'
        u.profile.save()
        self.assertEqual(perm.get_papel(u), 'ANALISTA_LICITACOES')

    def test_gestao_so_visualiza(self):
        processo = self.novo_processo()
        self.assertFalse(perm.pode_assumir_processo(self.gestao, processo))
        self.assertTrue(perm.pode_consultar_processo(self.gestao, processo))
        self.assertTrue(perm.pode_cancelar_processo(self.gestao))
        self.assertFalse(perm.pode_cancelar_processo(self.protocolo))

    def test_analista_nao_ve_outro_grupo(self):
        processo = self.novo_processo(self.especie_liq)
        self.assertFalse(perm.pode_consultar_processo(self.analista_lic, processo))
        self.assertTrue(perm.pode_consultar_processo(self.analista_liq, processo))

    def test_rota_inicial(self):
        self.assertEqual(perm.rota_inicial(self.gestao), 'gestao_dashboard')


class CriacaoTest(BaseProcessoTestCase):

    def test_so_protocolo_cria(self):
        for usuario in (self.analista_lic, self.gestao):
            with self.assertRaises(PermissionDenied):
                svc_processos.criar_processo(self.dados_protocolo(), usuario)

    def test_criacao_ignora_campos_de_analise(self):
        processo = self.novo_processo(
            tecnico='Fulano', numero_despacho='99', observacao='x',
            prioridade='URGENTE', data_saida='2026-09-02', destino='Outro')
        self.assertEqual(processo.situacao_tramite, 'DISPONIVEL')
        self.assertEqual(processo.prioridade, 'NORMAL')
        self.assertIsNone(processo.analista_responsavel)
        self.assertFalse(processo.numero_despacho)
        self.assertIsNone(processo.data_saida)
        self.assertIsNone(processo.destino)

    def test_grupo_vem_da_especie(self):
        dados = self.dados_protocolo(self.especie_liq)
        dados['genero'] = LIC  # navegador mandou grupo errado
        processo = svc_processos.criar_processo(dados, self.protocolo)
        self.assertEqual(processo.genero, LIQ)
        self.assertEqual(processo.especie_fk, self.especie_liq)

    def test_vincula_secretaria_e_evento(self):
        processo = self.novo_processo()
        self.assertEqual(processo.secretaria_fk, self.unidade)
        self.assertTrue(EventoProcesso.objects.filter(
            processo=processo, tipo='PROCESSO_CADASTRADO').exists())

    def test_obrigatorios(self):
        dados = self.dados_protocolo(objeto='')
        with self.assertRaises(svc_processos.DadosInvalidos):
            svc_processos.criar_processo(dados, self.protocolo)
        self.assertFalse(Processo.objects.exists())

    def test_recorrente_normalizado(self):
        processo = self.novo_processo(recorrente='Sim')
        self.assertEqual(processo.recorrente, 'SIM')


class WhitelistEdicaoTest(BaseProcessoTestCase):

    def test_protocolo_nao_grava_campo_de_analise(self):
        processo = self.novo_processo()
        alteracoes, recusados = svc_processos.aplicar_edicao(
            processo, {'objeto': 'Novo objeto', 'numero_despacho': '1/2026',
                       'status_analise': 'NAO_PROSSEGUIMENTO'}, self.protocolo)
        processo.refresh_from_db()
        self.assertEqual(processo.objeto, 'Novo objeto')
        self.assertIn('numero_despacho', recusados)
        self.assertIn('status_analise', recusados)
        self.assertFalse(processo.numero_despacho)

    def test_gestao_nao_edita_nada(self):
        processo = self.novo_processo()
        self.assertEqual(svc_processos.campos_editaveis(self.gestao, processo), set())

    def test_analista_so_edita_quando_responsavel(self):
        processo = self.processo_em_analise(completo=False)
        self.assertTrue(svc_processos.campos_editaveis(self.analista_lic, processo))
        self.assertEqual(svc_processos.campos_editaveis(self.analista_lic2, processo), set())

    def test_aplicar_analise_status_invalido(self):
        processo = self.processo_em_analise(completo=False)
        with self.assertRaises(svc_processos.DadosInvalidos):
            svc_processos.aplicar_analise(
                processo, {'status_analise': 'INVENTADO'}, self.analista_lic)
