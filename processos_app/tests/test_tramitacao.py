from django.core.exceptions import PermissionDenied

from processos_app.models import EventoProcesso, Prioridade, Processo
from processos_app.services import tramitacao
from processos_app.services.tramitacao import TransicaoInvalida

from .base import LIQ, BaseProcessoTestCase


class AssumirTest(BaseProcessoTestCase):

    def test_assumir(self):
        processo = self.novo_processo()
        tramitacao.assumir(processo.id, self.analista_lic)
        processo.refresh_from_db()
        self.assertEqual(processo.situacao_tramite, 'EM_ANALISE')
        self.assertEqual(processo.analista_responsavel, self.analista_lic)
        self.assertEqual(processo.situacao_exibicao,
                         f'Em análise por {processo.nome_analista}')

    def test_segundo_analista_nao_assume(self):
        """Concorrência (item 39), em sequência — ver alerta no relatório."""
        processo = self.novo_processo()
        tramitacao.assumir(processo.id, self.analista_lic)
        with self.assertRaises(TransicaoInvalida):
            tramitacao.assumir(processo.id, self.analista_lic2)
        processo.refresh_from_db()
        self.assertEqual(processo.analista_responsavel, self.analista_lic)

    def test_assumir_idempotente(self):
        processo = self.novo_processo()
        tramitacao.assumir(processo.id, self.analista_lic)
        tramitacao.assumir(processo.id, self.analista_lic)
        self.assertEqual(EventoProcesso.objects.filter(
            processo=processo, tipo='PROCESSO_ASSUMIDO').count(), 1)

    def test_outro_grupo_e_gestao_nao_assumem(self):
        processo = self.novo_processo()
        for usuario in (self.analista_liq, self.gestao, self.protocolo):
            with self.assertRaises(PermissionDenied):
                tramitacao.assumir(processo.id, usuario)

    def test_liquidacao_gera_numero_relatorio(self):
        processo = self.novo_processo(self.especie_liq)
        tramitacao.assumir(processo.id, self.analista_liq)
        processo.refresh_from_db()
        self.assertTrue(processo.numero_relatorio)

    def test_numeros_de_relatorio_nao_repetem(self):
        p1 = self.novo_processo(self.especie_liq, numero_processo='1/2026')
        p2 = self.novo_processo(self.especie_liq, numero_processo='2/2026')
        tramitacao.assumir(p1.id, self.analista_liq)
        tramitacao.assumir(p2.id, self.analista_liq)
        p1.refresh_from_db()
        p2.refresh_from_db()
        self.assertNotEqual(p1.numero_relatorio, p2.numero_relatorio)


class DeclinarAnaliseTest(BaseProcessoTestCase):

    def test_analista_devolve_a_fila(self):
        processo = self.processo_em_analise()
        tramitacao.declinar_analise(processo.id, self.analista_lic, 'Assumi por engano')
        processo.refresh_from_db()
        self.assertEqual(processo.situacao_tramite, 'DISPONIVEL')
        self.assertIsNone(processo.analista_responsavel)
        self.assertFalse(processo.observacao)
        self.assertEqual(processo.status_analise, 'NAO_APLICAVEL')
        self.assertTrue(EventoProcesso.objects.filter(
            processo=processo, tipo='ANALISE_DECLINADA').exists())

    def test_gestao_tambem_devolve(self):
        processo = self.processo_em_analise()
        tramitacao.declinar_analise(processo.id, self.gestao, 'Teste da Priscila')
        processo.refresh_from_db()
        self.assertEqual(processo.situacao_tramite, 'DISPONIVEL')
        self.assertIsNone(processo.analista_responsavel)

    def test_outro_analista_e_protocolo_nao_declinam(self):
        processo = self.processo_em_analise()
        for usuario in (self.analista_lic2, self.protocolo):
            with self.assertRaises(PermissionDenied):
                tramitacao.declinar_analise(processo.id, usuario, 'Não')

    def test_exige_motivo_e_so_em_analise(self):
        processo = self.processo_em_analise()
        with self.assertRaises(TransicaoInvalida):
            tramitacao.declinar_analise(processo.id, self.analista_lic, '')
        tramitacao.liberar_assinatura(processo.id, self.analista_lic)
        with self.assertRaises(TransicaoInvalida):
            tramitacao.declinar_analise(processo.id, self.analista_lic, 'Tarde demais')

    def test_cancela_pendencias_abertas(self):
        from processos_app.services import pendencias
        processo = self.processo_em_analise()
        p = pendencias.criar(processo.id, self.analista_lic, 'Tentativa de teste')
        tramitacao.declinar_analise(processo.id, self.analista_lic, 'Desfazer teste')
        p.refresh_from_db()
        self.assertEqual(p.status, 'CANCELADA')


class LiberacaoTest(BaseProcessoTestCase):

    def test_exige_analise_completa(self):
        processo = self.processo_em_analise(completo=False)
        with self.assertRaises(TransicaoInvalida):
            tramitacao.liberar_assinatura(processo.id, self.analista_lic)

    def test_liberar_fluxo_normal(self):
        processo = self.processo_em_analise()
        tramitacao.liberar_assinatura(processo.id, self.analista_lic)
        processo.refresh_from_db()
        self.assertEqual(processo.situacao_tramite, 'AGUARDANDO_ASSINATURA')
        self.assertEqual(processo.liberado_assinatura_por, self.analista_lic)

    def test_liquidacao_libera_sem_numero_despacho(self):
        """Correção: antes Liquidações exigia despacho e nunca liberava."""
        processo = self.novo_processo(self.especie_liq)
        tramitacao.assumir(processo.id, self.analista_liq)
        processo.refresh_from_db()
        self.preencher_analise(processo, numero_despacho=None)
        tramitacao.liberar_assinatura(processo.id, self.analista_liq)
        processo.refresh_from_db()
        self.assertEqual(processo.situacao_tramite, 'AGUARDANDO_ASSINATURA')

    def test_especie_que_exige_valor(self):
        self.especie_lic.exige_valor = True
        self.especie_lic.save()
        processo = self.processo_em_analise()
        with self.assertRaises(TransicaoInvalida):
            tramitacao.liberar_assinatura(processo.id, self.analista_lic)


class DirecionamentoTest(BaseProcessoTestCase):

    def test_direcionar_e_assinatura_substitutiva(self):
        processo = self.processo_em_analise()
        tramitacao.direcionar_assinatura(processo.id, self.analista_lic, self.analista_liq.id)
        processo.refresh_from_db()
        self.assertEqual(processo.situacao_tramite, 'ASSINATURA_DIRECIONADA')
        # Item 8: pode ser de outro grupo.
        self.assertEqual(processo.assinatura_direcionada_para, self.analista_liq)

        # Só o destinatário libera.
        with self.assertRaises(TransicaoInvalida):
            tramitacao.liberar_assinatura(processo.id, self.analista_lic)
        tramitacao.liberar_assinatura(processo.id, self.analista_liq)
        processo.refresh_from_db()
        self.assertEqual(processo.situacao_tramite, 'AGUARDANDO_ASSINATURA')
        # Item 7: quem analisou continua sendo quem analisou.
        self.assertEqual(processo.analista_responsavel, self.analista_lic)
        evento = EventoProcesso.objects.get(processo=processo, tipo='LIBERADO_ASSINATURA')
        self.assertTrue(evento.dados.get('assinatura_substitutiva'))

    def test_redirecionar_preserva_historico(self):
        processo = self.processo_em_analise()
        tramitacao.direcionar_assinatura(processo.id, self.analista_lic, self.analista_liq.id)
        tramitacao.direcionar_assinatura(processo.id, self.analista_lic, self.analista_lic2.id)
        self.assertTrue(EventoProcesso.objects.filter(
            processo=processo, tipo='ASSINATURA_REDIRECIONADA').exists())

    def test_seletor_vazio_nao_gera_erro_500(self):
        processo = self.processo_em_analise()
        with self.assertRaises(TransicaoInvalida):
            tramitacao.direcionar_assinatura(processo.id, self.analista_lic, '')

    def test_nao_direciona_para_si(self):
        processo = self.processo_em_analise()
        with self.assertRaises(TransicaoInvalida):
            tramitacao.direcionar_assinatura(processo.id, self.analista_lic, self.analista_lic.id)

    def test_nao_direciona_para_gestao(self):
        processo = self.processo_em_analise()
        with self.assertRaises(TransicaoInvalida):
            tramitacao.direcionar_assinatura(processo.id, self.analista_lic, self.gestao.id)

    def test_direcionar_exige_analise_completa(self):
        processo = self.processo_em_analise(completo=False)
        with self.assertRaises(TransicaoInvalida):
            tramitacao.direcionar_assinatura(processo.id, self.analista_lic, self.analista_liq.id)


class RetiradaESaidaTest(BaseProcessoTestCase):

    def test_fluxo_completo(self):
        processo = self.processo_disponivel_retirada()
        self.assertEqual(processo.situacao_tramite, 'DISPONIVEL_RETIRADA')
        tramitacao.registrar_saida([processo.id], self.protocolo)
        processo.refresh_from_db()
        self.assertEqual(processo.situacao_tramite, 'SAIDA_CONCLUIDA')
        self.assertIsNotNone(processo.data_saida)
        self.assertFalse(tramitacao.ativos().filter(id=processo.id).exists())
        self.assertTrue(tramitacao.finalizados().filter(id=processo.id).exists())

    def test_saida_em_lote_tudo_ou_nada(self):
        pronto = self.processo_disponivel_retirada()
        em_analise = self.processo_em_analise()
        with self.assertRaises(TransicaoInvalida):
            tramitacao.registrar_saida([pronto.id, em_analise.id], self.protocolo)
        pronto.refresh_from_db()
        self.assertEqual(pronto.situacao_tramite, 'DISPONIVEL_RETIRADA')

    def test_so_protocolo_registra_saida(self):
        processo = self.processo_disponivel_retirada()
        with self.assertRaises(PermissionDenied):
            tramitacao.registrar_saida([processo.id], self.gestao)

    def test_disponibilizar_exige_liberado(self):
        processo = self.processo_em_analise()
        with self.assertRaises(TransicaoInvalida):
            tramitacao.disponibilizar_retirada(processo.id, self.protocolo)


class LegadoTest(BaseProcessoTestCase):

    def _processo_legado(self):
        """Processo como os cadastrados antes da nova tramitação: sem evento."""
        processo = self.novo_processo()
        EventoProcesso.objects.filter(processo=processo).delete()
        return processo

    def test_saida_legado(self):
        processo = self._processo_legado()
        self.assertTrue(tramitacao.eh_legado(processo))
        tramitacao.registrar_saida_legado(processo.id, self.protocolo)
        processo.refresh_from_db()
        self.assertEqual(processo.situacao_tramite, 'SAIDA_CONCLUIDA')
        evento = EventoProcesso.objects.get(processo=processo, tipo='SAIDA_CONCLUIDA')
        self.assertTrue(evento.dados.get('legado'))

    def test_processo_novo_nao_usa_via_legado(self):
        processo = self.novo_processo()
        self.assertFalse(tramitacao.eh_legado(processo))
        with self.assertRaises(TransicaoInvalida):
            tramitacao.registrar_saida_legado(processo.id, self.protocolo)


class DestinoPrioridadeCancelamentoTest(BaseProcessoTestCase):

    def test_alterar_destino_exige_autorizacao(self):
        processo = self.processo_disponivel_retirada()
        with self.assertRaises(TransicaoInvalida):
            tramitacao.alterar_destino(processo.id, self.protocolo, 'Unidade de Teste', '')
        tramitacao.alterar_destino(processo.id, self.protocolo, 'Outro destino', 'Controlador')
        processo.refresh_from_db()
        self.assertEqual(processo.destino, 'Outro destino')
        self.assertTrue(EventoProcesso.objects.filter(
            processo=processo, tipo='DESTINO_ALTERADO').exists())

    def test_prioridade_do_cadastro(self):
        processo = self.novo_processo()
        tramitacao.alterar_prioridade(processo.id, self.gestao, 'URGENTE')
        processo.refresh_from_db()
        self.assertEqual(processo.prioridade, 'URGENTE')
        self.assertEqual(processo.prazo_dias, Prioridade.objects.get(codigo='URGENTE').prazo_dias)

    def test_prioridade_inexistente_ou_por_protocolo(self):
        processo = self.novo_processo()
        with self.assertRaises(TransicaoInvalida):
            tramitacao.alterar_prioridade(processo.id, self.gestao, 'INVENTADA')
        with self.assertRaises(PermissionDenied):
            tramitacao.alterar_prioridade(processo.id, self.protocolo, 'URGENTE')

    def test_cancelar_preserva_registro(self):
        processo = self.novo_processo()
        with self.assertRaises(TransicaoInvalida):
            tramitacao.cancelar_processo(processo.id, self.gestao, '')
        tramitacao.cancelar_processo(processo.id, self.gestao, 'Cadastro duplicado')
        self.assertTrue(Processo.objects.filter(id=processo.id).exists())
        self.assertFalse(tramitacao.ativos().filter(id=processo.id).exists())
        self.assertFalse(tramitacao.finalizados().filter(id=processo.id).exists())
