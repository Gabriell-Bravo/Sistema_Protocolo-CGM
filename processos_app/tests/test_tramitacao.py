from django.core.exceptions import PermissionDenied
from django.urls import reverse

from processos_app.models import EventoProcesso, Prioridade, Processo
from processos_app.services import processos as svc_processos
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

    def test_liquidacao_gera_numero_relatorio_ao_salvar(self):
        processo = self.novo_processo(self.especie_liq)
        tramitacao.assumir(processo.id, self.analista_liq)
        processo.refresh_from_db()
        self.assertFalse(processo.numero_relatorio)
        svc_processos.aplicar_analise(processo, {
            'destino': 'Unidade de Teste',
            'status_analise': 'PROSSEGUIMENTO_SEM_RESSALVA',
        }, self.analista_liq)
        processo.refresh_from_db()
        self.assertTrue(processo.numero_relatorio)
        numero = processo.numero_relatorio
        tramitacao.liberar_assinatura(processo.id, self.analista_liq)
        processo.refresh_from_db()
        self.assertEqual(processo.numero_relatorio, numero)

    def test_numeros_de_relatorio_nao_repetem(self):
        p1 = self.novo_processo(self.especie_liq, numero_processo='1/2026')
        p2 = self.novo_processo(self.especie_liq, numero_processo='2/2026')
        tramitacao.assumir(p1.id, self.analista_liq)
        tramitacao.assumir(p2.id, self.analista_liq)
        p1.refresh_from_db()
        p2.refresh_from_db()
        svc_processos.aplicar_analise(p1, {
            'destino': 'Unidade de Teste',
            'status_analise': 'PROSSEGUIMENTO_SEM_RESSALVA',
        }, self.analista_liq)
        svc_processos.aplicar_analise(p2, {
            'destino': 'Unidade de Teste',
            'status_analise': 'PROSSEGUIMENTO_SEM_RESSALVA',
        }, self.analista_liq)
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


class DesfazerTramiteAdminTest(BaseProcessoTestCase):

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        from .base import criar_usuario
        cls.admin = criar_usuario('admin_desfazer', 'PROTOCOLO', is_superuser=True)

    def test_admin_desfaz_analise(self):
        processo = self.processo_em_analise()
        tramitacao.desfazer_tramite(processo.id, self.admin, 'Corrigir')
        processo.refresh_from_db()
        self.assertEqual(processo.situacao_tramite, 'DISPONIVEL')
        self.assertIsNone(processo.analista_responsavel)
        self.assertTrue(EventoProcesso.objects.filter(
            processo=processo, tipo='ANALISE_DECLINADA').exists())

    def test_admin_desfaz_encaminhamento_ao_controlador(self):
        processo = self.processo_em_analise()
        tramitacao.liberar_assinatura(processo.id, self.analista_lic)
        tramitacao.desfazer_tramite(processo.id, self.admin)
        processo.refresh_from_db()
        self.assertEqual(processo.situacao_tramite, 'EM_ANALISE')
        self.assertEqual(processo.analista_responsavel, self.analista_lic)
        self.assertIsNone(processo.liberado_assinatura_por)
        self.assertTrue(EventoProcesso.objects.filter(
            processo=processo, tipo='TRAMITE_DESFEITO').exists())

    def test_admin_desfaz_retirada_e_saida(self):
        processo = self.processo_disponivel_retirada()
        tramitacao.desfazer_tramite(processo.id, self.admin)
        processo.refresh_from_db()
        self.assertEqual(processo.situacao_tramite, 'AGUARDANDO_ASSINATURA')

        tramitacao.disponibilizar_retirada(processo.id, self.protocolo)
        tramitacao.registrar_saida([processo.id], self.protocolo)
        tramitacao.desfazer_tramite(processo.id, self.admin)
        processo.refresh_from_db()
        self.assertEqual(processo.situacao_tramite, 'DISPONIVEL_RETIRADA')
        self.assertIsNone(processo.data_saida)

    def test_gestao_e_analista_nao_desfazem_encaminhamento(self):
        processo = self.processo_em_analise()
        tramitacao.liberar_assinatura(processo.id, self.analista_lic)
        for usuario in (self.gestao, self.analista_lic, self.protocolo):
            with self.assertRaises(PermissionDenied):
                tramitacao.desfazer_tramite(processo.id, usuario)


class LiberacaoTest(BaseProcessoTestCase):

    def test_licitacao_exige_anexo_e_nao_os_campos(self):
        processo = self.processo_em_analise(completo=False)
        with self.assertRaises(TransicaoInvalida):
            tramitacao.liberar_assinatura(processo.id, self.analista_lic)
        self.anexar_teste(processo)
        tramitacao.liberar_assinatura(processo.id, self.analista_lic)
        processo.refresh_from_db()
        self.assertEqual(processo.situacao_tramite, 'AGUARDANDO_ASSINATURA')
        self.assertEqual(processo.status_analise, 'NAO_APLICAVEL')
        self.assertFalse(processo.numero_despacho)
        self.assertFalse(processo.destino)

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

    def test_especie_que_exige_valor_so_em_liquidacao(self):
        """Licitações encaminha só com anexo; Liquidações ainda exige valor."""
        self.especie_lic.exige_valor = True
        self.especie_lic.save()
        processo = self.processo_em_analise(completo=False)
        self.anexar_teste(processo)
        tramitacao.liberar_assinatura(processo.id, self.analista_lic)
        processo.refresh_from_db()
        self.assertEqual(processo.situacao_tramite, 'AGUARDANDO_ASSINATURA')

        self.especie_liq.exige_valor = True
        self.especie_liq.save()
        liquidacao = self.novo_processo(self.especie_liq, numero_processo='8/2026')
        tramitacao.assumir(liquidacao.id, self.analista_liq)
        liquidacao.refresh_from_db()
        self.preencher_analise(liquidacao, numero_despacho=None)
        with self.assertRaises(TransicaoInvalida):
            tramitacao.liberar_assinatura(liquidacao.id, self.analista_liq)


class DirecionamentoTest(BaseProcessoTestCase):

    def test_encaminhar_passa_a_ser_do_colega(self):
        processo = self.processo_em_analise()
        tramitacao.direcionar_assinatura(processo.id, self.analista_lic, self.analista_liq.id)
        processo.refresh_from_db()
        self.assertEqual(processo.situacao_tramite, 'EM_ANALISE')
        self.assertEqual(processo.analista_responsavel, self.analista_liq)
        self.assertIsNone(processo.assinatura_direcionada_para)

        with self.assertRaises(PermissionDenied):
            tramitacao.liberar_assinatura(processo.id, self.analista_lic)
        tramitacao.liberar_assinatura(processo.id, self.analista_liq)
        processo.refresh_from_db()
        self.assertEqual(processo.situacao_tramite, 'AGUARDANDO_ASSINATURA')
        self.assertEqual(processo.analista_responsavel, self.analista_liq)
        evento = EventoProcesso.objects.get(processo=processo, tipo='LIBERADO_ASSINATURA')
        self.assertFalse(evento.dados.get('assinatura_substitutiva'))

    def test_so_o_novo_responsavel_reencaminha(self):
        processo = self.processo_em_analise()
        tramitacao.direcionar_assinatura(processo.id, self.analista_lic, self.analista_liq.id)
        with self.assertRaises(PermissionDenied):
            tramitacao.direcionar_assinatura(
                processo.id, self.analista_lic, self.analista_lic2.id)
        tramitacao.direcionar_assinatura(
            processo.id, self.analista_liq, self.analista_lic2.id)
        processo.refresh_from_db()
        self.assertEqual(processo.analista_responsavel, self.analista_lic2)
        self.assertTrue(EventoProcesso.objects.filter(
            processo=processo, tipo='ASSINATURA_DIRECIONADA').exists())

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

    def test_direcionar_licitacao_exige_anexo(self):
        processo = self.processo_em_analise(completo=False)
        with self.assertRaises(TransicaoInvalida):
            tramitacao.direcionar_assinatura(
                processo.id, self.analista_lic, self.analista_liq.id)
        self.anexar_teste(processo)
        tramitacao.direcionar_assinatura(
            processo.id, self.analista_lic, self.analista_liq.id)
        processo.refresh_from_db()
        self.assertEqual(processo.situacao_tramite, 'EM_ANALISE')
        self.assertEqual(processo.analista_responsavel, self.analista_liq)


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

    def test_protocolo_da_saida_de_processo_novo_sem_analise(self):
        processo = self.novo_processo()
        self.assertFalse(tramitacao.eh_legado(processo))
        tramitacao.registrar_saida_direta(processo.id, self.protocolo)
        processo.refresh_from_db()
        self.assertEqual(processo.situacao_tramite, 'SAIDA_CONCLUIDA')
        evento = EventoProcesso.objects.get(processo=processo, tipo='SAIDA_CONCLUIDA')
        self.assertTrue(evento.dados.get('saida_direta'))

    def test_gestao_nao_da_saida_direta(self):
        processo = self.novo_processo()
        with self.assertRaises(PermissionDenied):
            tramitacao.registrar_saida_direta(processo.id, self.gestao)

    def test_administrador_registra_saida(self):
        from .base import criar_usuario
        admin = criar_usuario('admin_saida', 'GESTAO', is_superuser=True)
        processo = self.novo_processo()
        tramitacao.registrar_saida_direta(processo.id, admin)
        processo.refresh_from_db()
        self.assertEqual(processo.situacao_tramite, 'SAIDA_CONCLUIDA')
        self.assertIsNotNone(processo.data_saida)
        self.assertIsNotNone(processo.hora_saida)


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

    def test_urgencia_recorrente_nas_proximas_entradas(self):
        processo = self.novo_processo(numero_processo='777/2026')
        tramitacao.alterar_prioridade(
            processo.id, self.gestao, 'URGENTE', recorrente=True)
        seguinte = self.novo_processo(numero_processo='777/2026', volume='2')
        self.assertEqual(seguinte.prioridade, 'URGENTE')

    def test_urgencia_so_desta_entrada(self):
        processo = self.novo_processo(numero_processo='778/2026')
        tramitacao.alterar_prioridade(
            processo.id, self.gestao, 'URGENTE', recorrente=False)
        processo.refresh_from_db()
        self.assertEqual(processo.prioridade, 'URGENTE')
        seguinte = self.novo_processo(numero_processo='778/2026', volume='2')
        self.assertEqual(seguinte.prioridade, 'NORMAL')

    def test_nao_recorrente_desfaz_a_preferencia(self):
        processo = self.novo_processo(numero_processo='779/2026')
        tramitacao.alterar_prioridade(
            processo.id, self.gestao, 'URGENTE', recorrente=True)
        tramitacao.alterar_prioridade(processo.id, self.gestao, 'NORMAL')
        tramitacao.alterar_prioridade(
            processo.id, self.gestao, 'URGENTE', recorrente=False)
        seguinte = self.novo_processo(numero_processo='779/2026', volume='2')
        self.assertEqual(seguinte.prioridade, 'NORMAL')

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


class ApagarProcessoTest(BaseProcessoTestCase):

    def setUp(self):
        super().setUp()
        self.admin = self.gestao
        self.admin.is_superuser = True
        self.admin.save(update_fields=['is_superuser'])

    def test_admin_exclui_processo_ativo_e_libera_o_relatorio(self):
        from processos_app.models import LinhaControleRelatorio
        from processos_app.services.relatorios import registrar

        processo = self.novo_processo(
            self.especie_liq, numero_processo='3001/2026')
        tramitacao.assumir(processo.id, self.analista_liq)
        processo.numero_relatorio = '1898'
        processo.save(update_fields=['numero_relatorio'])
        registrar(processo)

        numero = tramitacao.apagar_processo(processo.id, self.admin)
        self.assertEqual(numero, '3001/2026')
        self.assertFalse(Processo.objects.filter(id=processo.id).exists())
        self.assertFalse(EventoProcesso.objects.filter(processo_id=processo.id).exists())
        linha = LinhaControleRelatorio.objects.get(numero_relatorio='1898')
        self.assertIsNone(linha.processo)

    def test_gestao_e_processo_finalizado_nao_excluem(self):
        self.admin.is_superuser = False
        self.admin.save(update_fields=['is_superuser'])
        processo = self.novo_processo(numero_processo='3002/2026')
        with self.assertRaises(PermissionDenied):
            tramitacao.apagar_processo(processo.id, self.gestao)

        self.admin.is_superuser = True
        self.admin.save(update_fields=['is_superuser'])
        tramitacao.registrar_saida_direta(processo.id, self.protocolo)
        with self.assertRaises(TransicaoInvalida):
            tramitacao.apagar_processo(processo.id, self.admin)
        self.assertTrue(Processo.objects.filter(id=processo.id).exists())


class DevolverAssinaturaGestaoTest(BaseProcessoTestCase):

    def _no_controlador(self):
        processo = self.processo_em_analise()
        processo.valor = 'R$ 10,00'
        processo.destino = 'Unidade de Teste'
        processo.save(update_fields=['valor', 'destino'])
        tramitacao.liberar_assinatura(processo.id, self.analista_lic)
        processo.refresh_from_db()
        return processo

    def test_gestao_devolve_a_fila_e_mantem_a_analise(self):
        processo = self._no_controlador()
        tramitacao.devolver_da_assinatura(
            processo.id, self.gestao, 'Destino errado')
        processo.refresh_from_db()
        self.assertEqual(processo.situacao_tramite, 'DISPONIVEL')
        self.assertEqual(processo.destino, 'Unidade de Teste')
        self.assertEqual(processo.valor, 'R$ 10,00')
        self.assertIsNone(processo.analista_responsavel)
        tramitacao.assumir(processo.id, self.analista_lic)
        self.client.force_login(self.analista_lic)
        pagina = self.client.get(reverse('analista_processo', args=[processo.id]))
        self.assertContains(pagina, 'Motivo: Destino errado')
        self.assertContains(pagina, 'A Gestão devolveu este processo')
        tramitacao.liberar_assinatura(processo.id, self.analista_lic)
        self.assertIsNone(tramitacao.aviso_devolucao_gestao(processo))

    def test_gestao_devolve_para_um_analista(self):
        processo = self._no_controlador()
        tramitacao.devolver_da_assinatura(
            processo.id, self.gestao, 'Ajustar o destino', self.analista_lic2.id)
        processo.refresh_from_db()
        self.assertEqual(processo.situacao_tramite, 'EM_ANALISE')
        self.assertEqual(processo.analista_responsavel, self.analista_lic2)
        self.assertEqual(processo.destino, 'Unidade de Teste')
        self.client.force_login(self.analista_lic2)
        pagina = self.client.get(reverse('analista_processo', args=[processo.id]))
        self.assertContains(pagina, 'Ajustar o destino')

    def test_analista_nao_devolve_do_controlador(self):
        processo = self._no_controlador()
        with self.assertRaises(PermissionDenied):
            tramitacao.devolver_da_assinatura(
                processo.id, self.analista_lic, 'Não')
        with self.assertRaises(TransicaoInvalida):
            tramitacao.devolver_da_assinatura(processo.id, self.gestao, '  ')

    def test_tela_para_assinar_mostra_devolver_para_gestao(self):
        self._no_controlador()
        self.client.force_login(self.gestao)
        pagina = self.client.get(reverse('gestao_liberados_assinatura'))
        self.assertContains(pagina, 'Devolver')
        self.assertContains(pagina, 'Fila do grupo')
        self.client.force_login(self.analista_lic)
        consulta = self.client.get(reverse('gestao_liberados_assinatura'))
        self.assertNotContains(consulta, 'modalDevolver')
