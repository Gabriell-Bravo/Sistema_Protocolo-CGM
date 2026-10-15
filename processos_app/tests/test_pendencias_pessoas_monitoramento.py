import datetime

from django.core.exceptions import PermissionDenied
from django.urls import reverse

from processos_app.models import Pendencia, Processo, TipoIndisponibilidade
from processos_app.services import gestao_pessoas, monitoramento, pendencias, prazos
from processos_app.services.tramitacao import TransicaoInvalida

from .base import BaseProcessoTestCase


class PendenciasTest(BaseProcessoTestCase):

    def test_ciclo_completo(self):
        from processos_app.tests.base import criar_usuario

        processo = self.processo_em_analise()
        p = pendencias.criar(processo.id, self.analista_lic, 'Falta certidão')
        self.assertEqual(p.responsavel_tecnico, self.analista_lic)
        self.assertTrue(processo.tem_pendencia_aberta)

        with self.assertRaises(PermissionDenied):
            pendencias.concluir(p.id, self.analista_lic)
        pendencias.concluir(p.id, self.gestao)
        p.refresh_from_db()
        self.assertEqual(p.status, 'RESOLVIDA')
        self.assertFalse(processo.tem_pendencia_aberta)

        outra = pendencias.criar(processo.id, self.analista_lic, 'Falta anexo')
        admin = criar_usuario('admin_conclui', 'PROTOCOLO', is_superuser=True)
        pendencias.concluir(outra.id, admin)
        outra.refresh_from_db()
        self.assertEqual(outra.status, 'RESOLVIDA')

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

    def test_admin_desfaz_indicacao_legado_e_conclui_direto(self):
        from processos_app.tests.base import criar_usuario

        admin = criar_usuario('admin_desfaz_ind', 'GESTAO', is_superuser=True)
        processo = self.processo_em_analise()
        p = pendencias.criar(processo.id, self.analista_lic, 'Falta certidão')
        # Caminho legado ainda grava ATENDIMENTO_INDICADO no service.
        pendencias.indicar_atendimento(p.id, self.gestao)
        p.refresh_from_db()
        self.assertEqual(p.status, 'ATENDIMENTO_INDICADO')

        with self.assertRaises(PermissionDenied):
            pendencias.desfazer_indicacao(p.id, self.gestao)
        with self.assertRaises(PermissionDenied):
            pendencias.desfazer_indicacao(p.id, self.analista_lic)

        # Na lista unificada, legado aparece como aberta com Concluir diligência.
        self.client.force_login(admin)
        fila = self.client.get(reverse('gestao_diligencias'))
        self.assertContains(fila, 'Concluir diligência')
        self.assertContains(fila, 'Falta certidão')

        tela = self.client.get(reverse('analista_processo', args=[processo.id]))
        self.assertContains(tela, 'Desfazer indicação')

        resp = self.client.post(reverse('pend_desfazer_indicacao', args=[p.id]))
        self.assertEqual(resp.status_code, 302)
        p.refresh_from_db()
        self.assertEqual(p.status, 'AGUARDANDO_ATENDIMENTO')

        pendencias.concluir(p.id, admin)
        p.refresh_from_db()
        self.assertEqual(p.status, 'RESOLVIDA')
        with self.assertRaises(TransicaoInvalida):
            pendencias.desfazer_indicacao(p.id, admin)

    def test_aba_finalizados_so_quando_todas_completas(self):
        processo = self.processo_em_analise()
        aberta = pendencias.criar(processo.id, self.analista_lic, 'Ainda aberta')
        confirmada = pendencias.criar(processo.id, self.analista_lic, 'Já confirmada')
        pendencias.concluir(confirmada.id, self.gestao)

        self.client.force_login(self.gestao)
        padrao = self.client.get(reverse('gestao_diligencias'))
        self.assertEqual(padrao.context['status_atual'], 'AGUARDANDO_ATENDIMENTO')
        self.assertContains(padrao, 'Aguardando atendimento')
        self.assertContains(padrao, 'Finalizados')
        self.assertContains(padrao, 'Ainda aberta')
        self.assertContains(padrao, '1/2 diligências')
        self.assertNotContains(padrao, 'Já confirmada')
        rotulos = [rotulo for _, rotulo, _ in padrao.context['abas_diligencia']]
        self.assertEqual(rotulos, ['Aguardando atendimento', 'Finalizados'])

        # Com parcial, Finalizados ainda não lista o processo.
        fim = self.client.get(reverse('gestao_diligencias') + '?status=RESOLVIDA')
        self.assertEqual(fim.context['titulo_aba'], 'Finalizados')
        self.assertNotContains(fim, 'Já confirmada')
        self.assertEqual(fim.context['total'], 0)

        pendencias.concluir(aberta.id, self.gestao)
        fim = self.client.get(reverse('gestao_diligencias') + '?status=RESOLVIDA')
        self.assertContains(fim, 'Já confirmada')
        self.assertContains(fim, 'Ainda aberta')
        self.assertContains(fim, 'Concluída')
        self.assertContains(fim, 'Concluída por')
        self.assertContains(fim, self.gestao.get_full_name() or self.gestao.username)
        self.assertContains(fim, 'Histórico')
        self.assertContains(fim, 'Resolvida')
        self.assertEqual(fim.context['total'], 2)

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

    def test_aviso_ao_assumir_e_checklist_de_correcao(self):
        from django.contrib.messages import get_messages

        from processos_app.services.diligencia_texto import separar_itens

        passagem = self.processo_em_analise()
        texto = (
            '1- Regularizar assinaturas; '
            '2- Juntar portaria; '
            '3- Atualizar FGTS')
        antiga = pendencias.criar(passagem.id, self.analista_lic, texto)
        itens = separar_itens(texto)
        self.assertEqual(len(itens), 3)

        reentrada = self.novo_processo(numero_processo=passagem.numero_processo)
        aviso = pendencias.mensagem_aviso_ao_assumir(reentrada)
        self.assertIn('diligências em aberto', aviso.casefold())
        self.assertNotIn('1 pendência', aviso.casefold())
        self.assertNotIn('tela de diligências', aviso.casefold())

        self.client.force_login(self.analista_lic)
        resp = self.client.post(
            reverse('assumir_processo', args=[reentrada.id]), follow=True)
        self.assertEqual(resp.status_code, 200)
        msgs = [m.message for m in get_messages(resp.wsgi_request)]
        self.assertTrue(any('diligências em aberto' in m.casefold() for m in msgs))
        self.assertContains(resp, 'Diligências da passagem anterior')
        self.assertContains(resp, 'Salvar verificação')
        self.assertContains(resp, 'Regularizar assinaturas')

        # Parcial 2/3: permanece aberta e na análise; não vai a Finalizados.
        parcial = self.client.post(
            reverse('pend_verificar_correcao', args=[antiga.id]),
            {
                'processo_atual': reentrada.id,
                'itens_concluidos': itens[:2],
                'next': reverse('analista_processo', args=[reentrada.id]),
            },
            follow=True,
        )
        antiga.refresh_from_db()
        self.assertEqual(antiga.status, 'AGUARDANDO_ATENDIMENTO')
        self.assertEqual(set(antiga.itens_concluidos), set(itens[:2]))
        self.assertContains(parcial, 'Salvar verificação')
        self.assertContains(parcial, itens[2])
        fim = self.client.get(reverse('gestao_diligencias') + '?status=RESOLVIDA')
        self.assertNotContains(fim, 'Regularizar assinaturas')
        abertas = self.client.get(reverse('gestao_diligencias'))
        self.assertContains(abertas, 'Regularizar assinaturas')

        # Completa 3/3: conclui, mas continua listada na análise.
        ok = self.client.post(
            reverse('pend_verificar_correcao', args=[antiga.id]),
            {
                'processo_atual': reentrada.id,
                'itens_concluidos': itens,
                'next': reverse('analista_processo', args=[reentrada.id]),
            },
            follow=True,
        )
        antiga.refresh_from_db()
        self.assertEqual(antiga.status, 'RESOLVIDA')
        self.assertEqual(set(antiga.itens_concluidos), set(itens))
        self.assertContains(ok, 'Resolvida')
        self.assertContains(ok, 'Regularizar assinaturas')

    def test_outro_analista_nao_verifica_correcao(self):
        from processos_app.services import tramitacao

        passagem = self.processo_em_analise()
        antiga = pendencias.criar(passagem.id, self.analista_lic, 'Falta NF')
        reentrada = self.novo_processo(numero_processo=passagem.numero_processo)
        tramitacao.assumir(reentrada.id, self.analista_lic)

        with self.assertRaises(PermissionDenied):
            pendencias.verificar_correcao(
                antiga.id, self.analista_lic2, reentrada.id)

    def test_aviso_e_checklist_via_processo_origem(self):
        """Liquidação com nº de pagamento diferente vê pendência da Licitação."""
        from django.contrib.messages import get_messages

        from processos_app.services.diligencia_texto import separar_itens

        lic = self.processo_em_analise(especie=self.especie_lic)
        Processo.objects.filter(id=lic.id).update(
            numero_processo='ORIGEM-100/2026')
        lic.refresh_from_db()
        texto = '1- Regularizar doc da Licitação'
        antiga = pendencias.criar(lic.id, self.analista_lic, texto)
        itens = separar_itens(texto)

        liq_sem_origem = self.novo_processo(
            self.especie_liq, numero_processo='PAG-201/2026')
        self.assertIsNone(
            pendencias.mensagem_aviso_ao_assumir(liq_sem_origem))

        liq = self.novo_processo(
            self.especie_liq, numero_processo='PAG-200/2026')
        # Origem é campo de análise (não entra no cadastro do Protocolo).
        Processo.objects.filter(id=liq.id).update(
            processo_pagamento='ORIGEM-100/2026')
        liq.refresh_from_db()
        aviso = pendencias.mensagem_aviso_ao_assumir(liq)
        self.assertIsNotNone(aviso)
        self.assertIn('diligências em aberto', aviso.casefold())
        self.assertIn(
            antiga,
            list(pendencias.pendencias_de_passagens_anteriores(liq)))

        self.client.force_login(self.analista_liq)
        resp = self.client.post(
            reverse('assumir_processo', args=[liq.id]), follow=True)
        self.assertEqual(resp.status_code, 200)
        msgs = [m.message for m in get_messages(resp.wsgi_request)]
        self.assertTrue(
            any('diligências em aberto' in m.casefold() for m in msgs))
        self.assertContains(resp, 'Diligências da passagem anterior')
        self.assertContains(resp, 'Regularizar doc da Licitação')
        self.assertContains(resp, 'Salvar verificação')

        ok = self.client.post(
            reverse('pend_verificar_correcao', args=[antiga.id]),
            {
                'processo_atual': liq.id,
                'itens_concluidos': itens,
                'next': reverse('analista_processo', args=[liq.id]),
            },
            follow=True,
        )
        antiga.refresh_from_db()
        self.assertEqual(antiga.status, 'RESOLVIDA')
        self.assertContains(ok, 'Resolvida')
        self.assertContains(ok, 'Regularizar doc da Licitação')

        # Pendência já resolvida: outra Liquidação com a mesma origem não avisa.
        liq2 = self.novo_processo(
            self.especie_liq, numero_processo='PAG-202/2026')
        Processo.objects.filter(id=liq2.id).update(
            processo_pagamento='ORIGEM-100/2026')
        liq2.refresh_from_db()
        self.assertIsNone(pendencias.mensagem_aviso_ao_assumir(liq2))

    def test_aviso_via_origem_ignora_ponto_no_numero(self):
        """18.245/2025 e 18245/2025 são o mesmo nº na ligação origem ↔ pendência."""
        from processos_app.services import tramitacao
        from processos_app.services.diligencia_texto import separar_itens

        lic = self.processo_em_analise(especie=self.especie_lic)
        Processo.objects.filter(id=lic.id).update(
            numero_processo='18245/2025')
        lic.refresh_from_db()
        texto = '1- Falta documento com ponto no número'
        antiga = pendencias.criar(lic.id, self.analista_lic, texto)
        itens = separar_itens(texto)

        liq = self.novo_processo(
            self.especie_liq, numero_processo='99.001/2026')
        Processo.objects.filter(id=liq.id).update(
            processo_pagamento='18.245/2025')
        liq.refresh_from_db()

        self.assertEqual(
            pendencias.numeros_vinculados_pendencia(liq),
            ['99001/2026', '18245/2025'])
        aviso = pendencias.mensagem_aviso_ao_assumir(liq)
        self.assertIsNotNone(aviso)
        self.assertIn(
            antiga,
            list(pendencias.pendencias_de_passagens_anteriores(liq)))

        self.client.force_login(self.analista_liq)
        tramitacao.assumir(liq.id, self.analista_liq)
        ok = self.client.post(
            reverse('pend_verificar_correcao', args=[antiga.id]),
            {
                'processo_atual': liq.id,
                'itens_concluidos': itens,
                'next': reverse('analista_processo', args=[liq.id]),
            },
            follow=True,
        )
        antiga.refresh_from_db()
        self.assertEqual(antiga.status, 'RESOLVIDA')
        self.assertContains(ok, 'Resolvida')

    def test_aviso_trata_origem_e_pagamento_como_dupla_invertivel(self):
        """Campos invertidos (origem↔pagamento) ainda ligam à mesma pendência."""
        from processos_app.services import tramitacao
        from processos_app.services.diligencia_texto import separar_itens

        # Passagem com a dupla “correta”: pagamento 1122, origem 18640.
        anterior = self.processo_em_analise(
            analista=self.analista_liq, especie=self.especie_liq)
        Processo.objects.filter(id=anterior.id).update(
            numero_processo='1122/2026',
            processo_pagamento='18640/2023',
        )
        anterior.refresh_from_db()
        texto = '1- Pendência da dupla origem/pagamento'
        antiga = pendencias.criar(anterior.id, self.analista_liq, texto)
        itens = separar_itens(texto)

        # Nova passagem com os campos invertidos (como no controle de relatório).
        atual = self.novo_processo(
            self.especie_liq, numero_processo='18640/2023')
        Processo.objects.filter(id=atual.id).update(
            processo_pagamento='1122/2026')
        atual.refresh_from_db()

        self.assertEqual(
            set(pendencias.numeros_vinculados_pendencia(atual)),
            {'18640/2023', '1122/2026'})
        self.assertIsNotNone(pendencias.mensagem_aviso_ao_assumir(atual))
        self.assertIn(
            antiga,
            list(pendencias.pendencias_de_passagens_anteriores(atual)))

        self.client.force_login(self.analista_liq)
        tramitacao.assumir(atual.id, self.analista_liq)
        ok = self.client.post(
            reverse('pend_verificar_correcao', args=[antiga.id]),
            {
                'processo_atual': atual.id,
                'itens_concluidos': itens,
                'next': reverse('analista_processo', args=[atual.id]),
            },
            follow=True,
        )
        antiga.refresh_from_db()
        self.assertEqual(antiga.status, 'RESOLVIDA')
        self.assertContains(ok, 'Resolvida')


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

    def test_dias_na_cgm_congelam_na_saida(self):
        """Com saída, a contagem para — não segue até hoje."""
        from datetime import timedelta
        from django.utils import timezone

        hoje = timezone.localdate()
        processo = self.novo_processo(
            self.especie_liq, numero_processo='prazo-saida/2026')
        processo.data_entrada = hoje - timedelta(days=100)
        processo.save(update_fields=['data_entrada'])

        # Ainda na CGM: conta até hoje.
        self.assertEqual(prazos.dias_na_cgm(processo, hoje), 100)

        # Saiu há 90 dias (ficou 10 dias na CGM).
        processo.data_saida = hoje - timedelta(days=90)
        processo.hora_saida = timezone.localtime().time().replace(microsecond=0)
        processo.situacao_tramite = 'SAIDA_CONCLUIDA'
        processo.save(update_fields=[
            'data_saida', 'hora_saida', 'situacao_tramite'])

        self.assertEqual(prazos.dias_na_cgm(processo, hoje), 10)
        prazos.anotar(processo, hoje)
        self.assertEqual(processo.dias_na_cgm, 10)
        self.assertEqual(processo.prazo_formatado, '10 dias Na CGM')
        self.assertEqual(processo.prazo_status, 'saido')
        # Não marca atraso vermelho depois da saída.
        self.assertIsNone(processo.dias_restantes)
