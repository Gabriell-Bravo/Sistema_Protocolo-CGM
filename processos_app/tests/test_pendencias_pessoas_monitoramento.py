import datetime

from django.core.exceptions import PermissionDenied

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
        self.assertEqual(processo.situacao_tramite, 'ASSINATURA_DIRECIONADA')


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
