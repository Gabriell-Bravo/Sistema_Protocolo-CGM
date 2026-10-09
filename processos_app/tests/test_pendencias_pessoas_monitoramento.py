import datetime

from django.core.exceptions import PermissionDenied
from django.urls import reverse

from processos_app.models import Pendencia, Processo, TipoIndisponibilidade
from processos_app.services import gestao_pessoas, monitoramento, pendencias, prazos
from processos_app.services.tramitacao import TransicaoInvalida

from .base import BaseProcessoTestCase


class PendenciasTest(BaseProcessoTestCase):

    def test_ciclo_completo(self):
        processo = self.processo_em_analise()
        p = pendencias.criar(processo.id, self.analista_lic, 'Falta certidão')
        self.assertEqual(p.responsavel_tecnico, self.analista_lic)
        self.assertTrue(processo.tem_pendencia_aberta)

        with self.assertRaises(PermissionDenied):
            pendencias.indicar_atendimento(p.id, self.analista_lic)
        pendencias.indicar_atendimento(p.id, self.gestao)

        with self.assertRaises(TransicaoInvalida):
            pendencias.atendimento_insuficiente(p.id, self.analista_lic, '')
        pendencias.atendimento_insuficiente(p.id, self.analista_lic, 'Certidão vencida')
        p.refresh_from_db()
        self.assertEqual(p.status, 'AGUARDANDO_ATENDIMENTO')

        pendencias.indicar_atendimento(p.id, self.gestao)
        with self.assertRaises(PermissionDenied):
            pendencias.confirmar_resolucao(p.id, self.analista_lic2)
        pendencias.confirmar_resolucao(p.id, self.analista_lic)
        p.refresh_from_db()
        self.assertEqual(p.status, 'RESOLVIDA')
        self.assertFalse(processo.tem_pendencia_aberta)

    def test_so_responsavel_cria(self):
        processo = self.processo_em_analise()
        for usuario in (self.analista_lic2, self.gestao, self.protocolo):
            with self.assertRaises(PermissionDenied):
                pendencias.criar(processo.id, usuario, 'x')

    def test_cancelar_exige_motivo_e_preserva(self):
        processo = self.processo_em_analise()
        p = pendencias.criar(processo.id, self.analista_lic, 'Indevida')
        with self.assertRaises(TransicaoInvalida):
            pendencias.cancelar(p.id, self.gestao, '')
        pendencias.cancelar(p.id, self.gestao, 'Lançada por engano')
        self.assertEqual(Pendencia.objects.get(id=p.id).status, 'CANCELADA')

    def test_admin_cancela_e_edita_diligencia_de_outro(self):
        from processos_app.tests.base import criar_usuario

        admin = criar_usuario('admin_dil', 'GESTAO', is_superuser=True)
        processo = self.processo_em_analise()
        p = pendencias.criar(processo.id, self.analista_lic, 'Texto original')

        pendencias.editar_descricao(p.id, admin, 'Texto corrigido pelo admin')
        p.refresh_from_db()
        self.assertEqual(p.descricao, 'Texto corrigido pelo admin')

        self.client.force_login(admin)
        pagina = self.client.get(reverse('analista_processo', args=[processo.id]))
        self.assertContains(pagina, 'Texto corrigido pelo admin')
        self.assertContains(pagina, 'Salvar texto')
        self.assertContains(pagina, '/pendencias/')
        self.assertContains(pagina, '/editar/')

        resp = self.client.post(
            reverse('remover_pendencia', args=[p.id]),
            {'motivo': 'Cadastrada indevidamente'},
        )
        self.assertEqual(resp.status_code, 302)
        p.refresh_from_db()
        self.assertEqual(p.status, 'CANCELADA')

        resp_edit = self.client.post(
            reverse('pend_editar', args=[p.id]),
            {'descricao': 'Não pode editar cancelada'},
        )
        self.assertEqual(resp_edit.status_code, 302)
        p.refresh_from_db()
        self.assertEqual(p.descricao, 'Texto corrigido pelo admin')

    def test_adicionar_pendencia_grava_analise_ja_preenchida(self):
        processo = self.processo_em_analise(completo=False)
        self.client.force_login(self.analista_lic)
        resposta = self.client.post(
            reverse('adicionar_pendencia', args=[processo.id]),
            {
                'descricao': 'Falta certidão',
                'valor': '1500',
                'destino': 'Secretaria Nova',
                'periodo': 'Jan/2026',
                'observacao': 'Obs da análise',
                'status_analise': 'PROSSEGUIMENTO_COM_RESSALVA',
            },
        )
        self.assertEqual(resposta.status_code, 302)
        processo.refresh_from_db()
        self.assertEqual(processo.valor, 'R$ 1.500,00')
        self.assertEqual(processo.destino, 'Secretaria Nova')
        self.assertEqual(processo.periodo, 'Jan/2026')
        self.assertEqual(processo.observacao, 'Obs da análise')
        self.assertEqual(processo.status_analise, 'PROSSEGUIMENTO_COM_RESSALVA')
        self.assertTrue(
            processo.pendencias.filter(descricao='Falta certidão').exists())

    def test_adicionar_pendencia_sem_campos_de_analise_nao_apaga_o_que_ja_estava(self):
        processo = self.processo_em_analise()
        destino = processo.destino
        status = processo.status_analise
        self.client.force_login(self.analista_lic)
        self.client.post(
            reverse('adicionar_pendencia', args=[processo.id]),
            {'descricao': 'Falta nota'},
        )
        processo.refresh_from_db()
        self.assertEqual(processo.destino, destino)
        self.assertEqual(processo.status_analise, status)
        self.assertTrue(processo.pendencias.filter(descricao='Falta nota').exists())

    def test_fila_de_diligencias(self):
        processo = self.processo_em_analise()
        p = pendencias.criar(processo.id, self.analista_lic, 'Falta nota')
        self.assertIn(p, list(pendencias.fila_diligencias()))
        pendencias.indicar_atendimento(p.id, self.gestao)
        self.assertEqual(pendencias.total_atendimentos_indicados(self.analista_lic), 1)


class GestaoPessoasTest(BaseProcessoTestCase):

    def setUp(self):
        self.tipo = TipoIndisponibilidade.objects.filter(ativo=True).first()

    def test_periodo(self):
        hoje = self.hoje()
        gestao_pessoas.registrar(self.gestao, self.analista_lic.id, self.tipo.id,
                                 data_inicio=hoje, data_fim=hoje + datetime.timedelta(days=5))
        self.assertFalse(gestao_pessoas.esta_disponivel(self.analista_lic, hoje))
        self.assertTrue(gestao_pessoas.esta_disponivel(
            self.analista_lic, hoje + datetime.timedelta(days=6)))

    def test_recorrente_com_vigencia(self):
        segunda = datetime.date(2026, 9, 21)   # segunda-feira
        gestao_pessoas.registrar(self.gestao, self.analista_lic.id, self.tipo.id,
                                 recorrente=True, dia_semana=0,
                                 vigencia_inicio=segunda,
                                 vigencia_fim=segunda + datetime.timedelta(days=14))
        self.assertFalse(gestao_pessoas.esta_disponivel(self.analista_lic, segunda))
        self.assertTrue(gestao_pessoas.esta_disponivel(
            self.analista_lic, segunda + datetime.timedelta(days=1)))
        self.assertTrue(gestao_pessoas.esta_disponivel(
            self.analista_lic, segunda + datetime.timedelta(days=21)))

    def test_validacoes_e_permissao(self):
        hoje = self.hoje()
        with self.assertRaises(gestao_pessoas.RegistroInvalido):
            gestao_pessoas.registrar(self.gestao, self.analista_lic.id, self.tipo.id,
                                     data_inicio=hoje, data_fim=hoje - datetime.timedelta(days=1))
        with self.assertRaises(PermissionDenied):
            gestao_pessoas.registrar(self.analista_lic, self.analista_lic.id, self.tipo.id,
                                     data_inicio=hoje)

    def test_indisponivel_ainda_recebe_direcionamento(self):
        """Item 9: indisponibilidade informa, não bloqueia."""
        gestao_pessoas.registrar(self.gestao, self.analista_liq.id, self.tipo.id,
                                 data_inicio=self.hoje())
        from processos_app.services import tramitacao
        processo = self.processo_em_analise()
        tramitacao.direcionar_assinatura(processo.id, self.analista_lic, self.analista_liq.id)
        processo.refresh_from_db()
        self.assertEqual(processo.situacao_tramite, 'EM_ANALISE')
        self.assertEqual(processo.analista_responsavel, self.analista_liq)


class MonitoramentoTest(BaseProcessoTestCase):

    def test_meses_de_calendario(self):
        self.assertEqual(monitoramento.somar_periodo(datetime.date(2026, 1, 31), 'TRIMESTRAL'),
                         datetime.date(2026, 4, 30))
        self.assertEqual(monitoramento.somar_periodo(datetime.date(2025, 11, 30), 'QUADRIMESTRAL'),
                         datetime.date(2026, 3, 30))
        self.assertIsNone(monitoramento.somar_periodo(datetime.date(2026, 1, 1), 'NENHUM'))

    def test_inicial_pela_especie(self):
        processo = self.novo_processo(self.especie_monit)
        self.assertEqual(processo.status_monitoramento, 'PENDENTE')
        self.assertEqual(processo.proxima_data_monitoramento, datetime.date(2026, 12, 1))

    def test_status_efetivo_nao_grava(self):
        processo = self.novo_processo(self.especie_monit)
        Processo.objects.filter(id=processo.id).update(
            proxima_data_monitoramento=self.hoje() - datetime.timedelta(days=1))
        processo.refresh_from_db()
        self.assertEqual(monitoramento.status_efetivo(processo), 'ATRASADO')
        self.assertEqual(processo.status_monitoramento, 'PENDENTE')
        self.assertTrue(Processo.objects.filter(
            monitoramento.filtro_status('ATRASADO'), id=processo.id).exists())

    def test_concluir_nao_da_saida(self):
        processo = self.novo_processo(self.especie_monit)
        monitoramento.concluir(processo.id, self.gestao)
        processo.refresh_from_db()
        self.assertEqual(processo.status_monitoramento, 'CONCLUIDO')
        self.assertIsNone(processo.data_saida)
        self.assertEqual(processo.situacao_tramite, 'DISPONIVEL')

    def test_editar_data_nao_reabre_concluido(self):
        processo = self.novo_processo(self.especie_monit)
        monitoramento.concluir(processo.id, self.gestao)
        processo.refresh_from_db()
        self.assertFalse(monitoramento.recalcular_apos_edicao(processo, ['data_entrada']))
        self.assertEqual(processo.status_monitoramento, 'CONCLUIDO')

    def test_persistir_status_igual_ao_calculado(self):
        processo = self.novo_processo(self.especie_monit)
        Processo.objects.filter(id=processo.id).update(
            proxima_data_monitoramento=self.hoje() - datetime.timedelta(days=3))
        processo.refresh_from_db()
        esperado = monitoramento.status_efetivo(processo)
        monitoramento.persistir_status()
        processo.refresh_from_db()
        self.assertEqual(processo.status_monitoramento, esperado)


class PrazosTest(BaseProcessoTestCase):

    def test_prazo_vem_do_cadastro(self):
        prazos.limpar_cache()
        self.assertEqual(prazos.dias_por_prioridade('URGENTE'), 1)
        self.assertEqual(prazos.dias_por_prioridade('NORMAL'), 7)

    def test_rotulos(self):
        self.assertEqual(prazos.status_do_prazo(-1), 'atrasado')
        self.assertEqual(prazos.status_do_prazo(0), 'hoje')
        self.assertEqual(prazos.formatar_dias_na_cgm(0), '0 dias Na CGM')
        self.assertEqual(prazos.formatar_dias_na_cgm(1), '1 dia Na CGM')
        self.assertEqual(prazos.formatar_dias_na_cgm(13), '13 dias Na CGM')

    def test_anotar_mostra_dias_na_cgm(self):
        from datetime import timedelta
        from django.utils import timezone

        processo = self.novo_processo(self.especie_liq)
        processo.data_entrada = timezone.localdate() - timedelta(days=5)
        processo.save(update_fields=['data_entrada'])
        prazos.anotar(processo)
        self.assertEqual(processo.dias_na_cgm, 5)
        self.assertEqual(processo.prazo_formatado, '5 dias Na CGM')
        self.assertIn(processo.prazo_status, {'atrasado', 'hoje', 'atencao', 'ok'})
