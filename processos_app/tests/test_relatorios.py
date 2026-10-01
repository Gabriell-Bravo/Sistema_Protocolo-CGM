from django.core.exceptions import PermissionDenied
from django.urls import reverse

from processos_app.models import LinhaControleRelatorio
from processos_app.services import processos as svc_processos
from processos_app.services import relatorios, tramitacao

from .base import BaseProcessoTestCase, criar_usuario


class ControleRelatorioTest(BaseProcessoTestCase):

    def _salvar_liquidacao(self, processo, analista=None):
        analista = analista or self.analista_liq
        if processo.situacao_tramite != 'EM_ANALISE':
            tramitacao.assumir(processo.id, analista)
            processo.refresh_from_db()
        svc_processos.aplicar_analise(processo, {
            'destino': 'Unidade de Teste',
            'valor': '1000',
            'status_analise': 'PROSSEGUIMENTO_SEM_RESSALVA',
        }, analista)
        processo.refresh_from_db()
        return processo

    def test_salvar_analise_sem_relatorio_aparece_no_controle(self):
        processo = self.novo_processo(self.especie_liq, numero_processo='sr-1/2026')
        tramitacao.assumir(processo.id, self.analista_liq)
        processo.refresh_from_db()
        svc_processos.aplicar_analise(processo, {
            'destino': 'Unidade de Teste',
            'valor': '1000',
            'status_analise': 'PROSSEGUIMENTO_SEM_RESSALVA',
            'sem_relatorio': '1',
        }, self.analista_liq)
        processo.refresh_from_db()
        self.assertTrue(processo.sem_relatorio)
        self.assertFalse(processo.numero_relatorio)
        linha = LinhaControleRelatorio.objects.get(processo=processo)
        self.assertTrue(linha.sem_relatorio)
        self.assertEqual(linha.numero_relatorio, '')
        self.assertEqual(linha.numero_processo, 'sr-1/2026')

        self.client.force_login(self.analista_liq)
        pagina = self.client.get(reverse('controle_relatorio'))
        self.assertContains(pagina, 'sr-1/2026')
        self.assertContains(pagina, 'Processo despachado sem relatório')
        self.assertContains(pagina, 'aviso-sem-relatorio')

        tela = self.client.get(reverse('analista_processo', args=[processo.id]))
        self.assertContains(tela, 'name="sem_relatorio"')
        self.assertContains(tela, 'Sem relatório')

    def test_admin_define_ultimo_e_proximo_salvo_continua(self):
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

        self._salvar_liquidacao(processo)
        self.assertEqual(processo.numero_relatorio, '2001')
        linha = LinhaControleRelatorio.objects.get(processo=processo)
        self.assertEqual(linha.numero_processo, '9/2026')
        self.assertEqual(linha.numero_relatorio, '2001')
        self.assertEqual(linha.analista, processo.nome_analista)

    def test_analista_nao_define_ultimo(self):
        with self.assertRaises(PermissionDenied):
            relatorios.definir_ultimo_numero(self.analista_liq, 10)

    def test_salvar_analise_gera_numero_e_planilha(self):
        processo = self.novo_processo(self.especie_liq, numero_processo='10/2026')
        tramitacao.assumir(processo.id, self.analista_liq)
        processo.refresh_from_db()
        self.assertFalse(processo.numero_relatorio)
        svc_processos.aplicar_analise(processo, {
            'destino': 'Unidade de Teste',
            'valor': '1000',
            'status_analise': 'PROSSEGUIMENTO_SEM_RESSALVA',
        }, self.analista_liq)
        processo.refresh_from_db()
        self.assertTrue(processo.numero_relatorio)
        linha = LinhaControleRelatorio.objects.get(processo=processo)
        self.assertEqual(linha.destino, 'Unidade de Teste')
        self.assertEqual(linha.valor, 'R$ 1.000,00')
        self.assertEqual(linha.status_analise, 'PROSSEGUIMENTO_SEM_RESSALVA')
        numero = processo.numero_relatorio
        tramitacao.liberar_assinatura(processo.id, self.analista_liq)
        processo.refresh_from_db()
        self.assertEqual(processo.numero_relatorio, numero)

    def test_declinar_devolve_o_numero_ao_proximo_analista(self):
        admin = criar_usuario('admin_gasto', 'GESTAO', is_superuser=True)
        relatorios.definir_ultimo_numero(admin, 2000)
        primeiro = self.novo_processo(self.especie_liq, numero_processo='11/2026')
        self._salvar_liquidacao(primeiro)
        self.assertEqual(primeiro.numero_relatorio, '2001')
        tramitacao.declinar_analise(primeiro.id, self.analista_liq, 'Teste')
        primeiro.refresh_from_db()
        self.assertFalse(primeiro.numero_relatorio)
        self.assertFalse(LinhaControleRelatorio.objects.filter(
            processo=primeiro).exists())

        segundo = self.novo_processo(self.especie_liq, numero_processo='11b/2026')
        self._salvar_liquidacao(segundo)
        self.assertEqual(segundo.numero_relatorio, '2001')

    def test_declinar_no_meio_devolve_so_o_numero_livre(self):
        admin = criar_usuario('admin_meio', 'GESTAO', is_superuser=True)
        relatorios.definir_ultimo_numero(admin, 2000)
        primeiro = self.novo_processo(self.especie_liq, numero_processo='11c/2026')
        segundo = self.novo_processo(self.especie_liq, numero_processo='11d/2026')
        self._salvar_liquidacao(primeiro)
        self._salvar_liquidacao(segundo)
        self.assertEqual(primeiro.numero_relatorio, '2001')
        self.assertEqual(segundo.numero_relatorio, '2002')
        tramitacao.declinar_analise(primeiro.id, self.analista_liq, 'Teste')

        terceiro = self.novo_processo(self.especie_liq, numero_processo='11e/2026')
        self._salvar_liquidacao(terceiro)
        self.assertEqual(terceiro.numero_relatorio, '2001')
        quarto = self.novo_processo(self.especie_liq, numero_processo='11f/2026')
        self._salvar_liquidacao(quarto)
        self.assertEqual(quarto.numero_relatorio, '2003')

    def test_buraco_de_numero_especifico_e_reaproveitado(self):
        admin = criar_usuario('admin_buraco', 'GESTAO', is_superuser=True)
        relatorios.definir_ultimo_numero(admin, 1900)
        primeiro = self.novo_processo(self.especie_liq, numero_processo='93a/2026')
        segundo = self.novo_processo(self.especie_liq, numero_processo='93b/2026')
        self._salvar_liquidacao(primeiro)
        self._salvar_liquidacao(segundo)
        self.assertEqual(primeiro.numero_relatorio, '1901')
        self.assertEqual(segundo.numero_relatorio, '1902')

        # Terceiro recebe número específico 1904 sem passar pelo 1903.
        terceiro = self.novo_processo(self.especie_liq, numero_processo='93c/2026')
        tramitacao.assumir(terceiro.id, self.analista_liq)
        relatorios.alterar_numero(self.analista_liq, terceiro.id, 1904, '2026-10-01')
        terceiro.refresh_from_db()
        self.assertEqual(terceiro.numero_relatorio, '1904')
        self.assertEqual(relatorios.estado_sequencia()['proximo'], 1905)

        quarto = self.novo_processo(self.especie_liq, numero_processo='93d/2026')
        self._salvar_liquidacao(quarto)
        self.assertEqual(quarto.numero_relatorio, '1903')

        quinto = self.novo_processo(self.especie_liq, numero_processo='93e/2026')
        self._salvar_liquidacao(quinto)
        self.assertEqual(quinto.numero_relatorio, '1905')

    def test_dois_analistas_nao_recebem_o_mesmo_numero(self):
        outro = criar_usuario('dana_liq', 'ANALISTA_LIQUIDACOES')
        p1 = self.novo_processo(self.especie_liq, numero_processo='14/2026')
        p2 = self.novo_processo(self.especie_liq, numero_processo='15/2026')
        self._salvar_liquidacao(p1, self.analista_liq)
        self._salvar_liquidacao(p2, outro)
        self.assertTrue(p1.numero_relatorio)
        self.assertTrue(p2.numero_relatorio)
        self.assertNotEqual(p1.numero_relatorio, p2.numero_relatorio)

    def test_admin_corrige_numero_de_analise_ja_feita(self):
        admin = criar_usuario('admin_edit', 'GESTAO', is_superuser=True)
        processo = self.novo_processo(self.especie_liq, numero_processo='16/2026')
        tramitacao.assumir(processo.id, self.analista_liq)
        relatorios.alterar_numero(admin, processo.id, 3300, '2026-03-15')
        processo.refresh_from_db()
        self.assertEqual(processo.numero_relatorio, '3300')

        self._salvar_liquidacao(processo)
        relatorios.alterar_numero(admin, processo.id, 3300, '2026-03-15')
        processo.refresh_from_db()
        self.assertEqual(processo.numero_relatorio, '3300')
        linha = LinhaControleRelatorio.objects.get(processo=processo)
        self.assertEqual(linha.numero_relatorio, '3300')
        self.assertEqual(relatorios.estado_sequencia()['proximo'], 3301)

        with self.assertRaises(PermissionDenied):
            relatorios.alterar_numero(self.analista_lic, processo.id, 3301)

        outro = self.novo_processo(self.especie_liq, numero_processo='17/2026')
        self._salvar_liquidacao(outro)
        relatorios.alterar_numero(admin, outro.id, 3300, '2026-03-16')
        outro.refresh_from_db()
        processo.refresh_from_db()
        self.assertEqual(outro.numero_relatorio, '3300')
        self.assertEqual(processo.numero_relatorio, '3300')

    def test_analista_informa_o_proprio_numero(self):
        processo = self.novo_processo(self.especie_liq, numero_processo='16b/2026')
        tramitacao.assumir(processo.id, self.analista_liq)
        processo.refresh_from_db()
        relatorios.alterar_numero(self.analista_liq, processo.id, 4400, '2026-04-10')
        processo.refresh_from_db()
        self.assertEqual(processo.numero_relatorio, '4400')
        self.assertEqual(str(processo.data_analise), '2026-04-10')
        self._salvar_liquidacao(processo)
        self.assertEqual(processo.numero_relatorio, '4400')
        relatorios.alterar_numero(self.analista_liq, processo.id, 4401, '2026-04-11')
        processo.refresh_from_db()
        self.assertEqual(processo.numero_relatorio, '4401')
        self.assertEqual(str(processo.data_analise), '2026-04-11')
        linha = LinhaControleRelatorio.objects.get(processo=processo)
        self.assertEqual(linha.numero_relatorio, '4401')
        self.assertEqual(str(linha.data_relatorio), '2026-04-11')

        with self.assertRaises(relatorios.RelatorioInvalido):
            relatorios.alterar_numero(self.analista_liq, processo.id, 4402)

        self.client.force_login(self.analista_liq)
        tela = self.client.get(reverse('analista_processo', args=[processo.id]))
        self.assertContains(tela, 'Informar número específico')
        self.assertContains(tela, 'Data deste número')
        self.assertContains(tela, 'Data do relatório')
        self.assertContains(tela, 'data_relatorio_exibicao')
        self.assertContains(tela, 'btnCancelarNumero')
        self.assertNotContains(tela, 'form="formNumeroRelatorio"')

    def test_salvar_analise_grava_numero_especifico_no_mesmo_botao(self):
        processo = self.novo_processo(self.especie_liq, numero_processo='16c/2026')
        tramitacao.assumir(processo.id, self.analista_liq)
        self.client.force_login(self.analista_liq)
        resposta = self.client.post(
            reverse('analista_processo', args=[processo.id]),
            {
                'acao': 'salvar',
                'destino': 'Unidade de Teste',
                'valor': '1000',
                'status_analise': 'PROSSEGUIMENTO_SEM_RESSALVA',
                'numero_relatorio': '5500',
                'data_relatorio': '2026-07-01',
            },
        )
        self.assertEqual(resposta.status_code, 302)
        processo.refresh_from_db()
        self.assertEqual(processo.numero_relatorio, '5500')
        self.assertEqual(str(processo.data_analise), '2026-07-01')

        resposta = self.client.post(
            reverse('analista_processo', args=[processo.id]),
            {
                'acao': 'salvar',
                'destino': 'Unidade de Teste',
                'valor': '1000',
                'status_analise': 'PROSSEGUIMENTO_SEM_RESSALVA',
            },
        )
        self.assertEqual(resposta.status_code, 302)
        processo.refresh_from_db()
        self.assertEqual(processo.numero_relatorio, '5500')

    def test_tela_analista_ve_planilha_admin_define_ultimo(self):
        processo = self.novo_processo(self.especie_liq, numero_processo='12/2026')
        self._salvar_liquidacao(processo)

        self.client.force_login(self.analista_liq)
        pagina = self.client.get(reverse('controle_relatorio'))
        self.assertEqual(pagina.status_code, 200)
        self.assertContains(pagina, 'Planilha — Liquidação')
        self.assertContains(pagina, 'Bolsa Atleta')
        self.assertContains(pagina, 'Inclui (Pagamento Geral; Reanálise).')
        self.assertNotContains(pagina, 'Último nº usado')
        self.assertNotContains(pagina, 'Início da numeração')
        self.assertContains(pagina, 'Números destinados')
        self.assertContains(pagina, 'Análises')
        self.assertNotContains(pagina, 'Do número')
        self.assertContains(pagina, processo.numero_relatorio)
        self.assertContains(pagina, '12/2026')
        self.assertContains(pagina, 'Editar análise')
        self.assertNotContains(pagina, 'name="valor"')
        self.assertNotContains(pagina, 'name="numero_relatorio"')

        admin = criar_usuario('admin_rel2', 'GESTAO', is_superuser=True)
        self.client.force_login(admin)
        pagina = self.client.get(reverse('controle_relatorio'))
        self.assertContains(pagina, 'Numeração')
        self.assertContains(pagina, '12/2026')
        self.assertContains(pagina, 'Editar análise')
        self.assertNotContains(pagina, 'name="numero_relatorio"')
        self.assertNotContains(pagina, 'name="valor"')

        numeracao = self.client.get(
            reverse('controle_relatorio') + '?secao=numeracao')
        self.assertContains(numeracao, 'Início da numeração por grupo')
        self.assertContains(numeracao, 'Último nº usado')
        self.assertContains(numeracao, 'Bolsa Atleta')
        self.assertContains(numeracao, 'Adiantamento')
        self.assertContains(numeracao, 'name="ultimo_numero"')
        resposta = self.client.post(reverse('controle_relatorio_ultimo'), {
            'grupo': 'BOLSA_ATLETA',
            'ultimo_numero': '50',
        })
        self.assertRedirects(
            resposta,
            reverse('controle_relatorio') + '?aba=BOLSA_ATLETA&secao=numeracao')
        self.assertEqual(
            relatorios.estado_sequencia('BOLSA_ATLETA')['proximo'], 51)

    def test_analista_corrige_pela_tela_da_analise(self):
        processo = self.novo_processo(self.especie_liq, numero_processo='18/2026')
        self._salvar_liquidacao(processo)
        tramitacao.liberar_assinatura(processo.id, self.analista_liq)
        processo.refresh_from_db()

        self.client.force_login(self.analista_liq)
        url = reverse('analista_processo', args=[processo.id])
        tela = self.client.get(f'{url}?next={reverse("controle_relatorio")}')
        self.assertEqual(tela.status_code, 200)
        self.assertContains(tela, 'Salvar análise')
        self.assertContains(tela, 'Voltar ao Controle de relatório')

        resposta = self.client.post(url, {
            'acao': 'salvar',
            'next': reverse('controle_relatorio'),
            'destino': 'Secretaria Nova',
            'valor': '2500',
            'periodo': 'Jan/2026',
            'observacao': 'Corrigido na tela da análise',
            'status_analise': 'PROSSEGUIMENTO_COM_RESSALVA',
        })
        self.assertRedirects(resposta, reverse('controle_relatorio'))
        processo.refresh_from_db()
        self.assertEqual(processo.destino, 'Secretaria Nova')
        self.assertEqual(processo.valor, 'R$ 2.500,00')
        self.assertEqual(processo.periodo, 'Jan/2026')
        self.assertEqual(processo.observacao, 'Corrigido na tela da análise')
        self.assertEqual(processo.status_analise, 'PROSSEGUIMENTO_COM_RESSALVA')
        linha = LinhaControleRelatorio.objects.get(processo=processo)
        self.assertEqual(linha.destino, 'Secretaria Nova')
        self.assertEqual(linha.valor, 'R$ 2.500,00')
        self.assertEqual(linha.observacao, 'Corrigido na tela da análise')

        self.assertEqual(
            svc_processos.campos_editaveis(self.analista_lic, processo), set())

    def test_destinar_numeros_e_usar_traz_a_data(self):
        relatorios.destinar_numeros(
            self.analista_liq, 5001, 5003, '2026-06-20')
        reservas = list(relatorios.reservas_abertas())
        self.assertEqual([r.numero for r in reservas], [5001, 5002, 5003])
        self.assertEqual(str(reservas[0].data), '2026-06-20')

        processo = self.novo_processo(self.especie_liq, numero_processo='40/2026')
        tramitacao.assumir(processo.id, self.analista_liq)
        relatorios.alterar_numero(self.analista_liq, processo.id, 5002)
        processo.refresh_from_db()
        self.assertEqual(processo.numero_relatorio, '5002')
        self.assertEqual(str(processo.data_analise), '2026-06-20')
        self.assertEqual(
            [r.numero for r in relatorios.reservas_abertas()], [5001, 5003])

        automatico = self.novo_processo(self.especie_liq, numero_processo='41/2026')
        self._salvar_liquidacao(automatico)
        self.assertNotEqual(automatico.numero_relatorio, '5001')
        self.assertNotEqual(automatico.numero_relatorio, '5003')

        with self.assertRaises(relatorios.RelatorioInvalido):
            relatorios.destinar_numeros(
                self.analista_liq, 5001, 5001, '2026-06-21')
        with self.assertRaises(PermissionDenied):
            relatorios.destinar_numeros(
                self.analista_lic, 6000, 6001, '2026-06-21')

        self.client.force_login(self.analista_liq)
        pagina = self.client.get(
            reverse('controle_relatorio') + '?aba=destinados')
        self.assertContains(pagina, '5001')
        self.assertContains(pagina, '20/06/2026')
        self.assertContains(pagina, 'Destinar números')
        self.assertContains(pagina, 'Grupo de numeração')
        self.assertContains(pagina, 'name="grupo"')
        self.assertContains(pagina, 'Bolsa Atleta')
        self.assertNotContains(pagina, 'Planilha — Liquidação')
        tela = self.client.get(reverse('analista_processo', args=[processo.id]))
        self.assertContains(tela, '"5001": "2026-06-20"')

        relatorios.destinar_numeros(
            self.analista_liq, 11, 12, '2026-08-01', grupo='BOLSA_ATLETA')
        aba_bolsa = self.client.get(
            reverse('controle_relatorio') + '?aba=BOLSA_ATLETA&secao=destinados')
        self.assertContains(aba_bolsa, '11')
        self.assertContains(aba_bolsa, '12')
        self.assertContains(aba_bolsa, '01/08/2026')
        self.assertContains(aba_bolsa, 'Reservados — Bolsa Atleta')
        self.assertNotContains(aba_bolsa, '5001')
        aba_liq = self.client.get(
            reverse('controle_relatorio') + '?aba=LIQUIDACOES&secao=destinados')
        self.assertContains(aba_liq, '5001')
        self.assertNotContains(aba_liq, '>11</strong>')

    def test_especies_ainda_usam_so_sequencia_liquidacao(self):
        """Outras sequências existem na tela, mas ainda não geram número próprio."""
        from processos_app.models import EspecieProcesso

        bolsa, _ = EspecieProcesso.objects.get_or_create(
            nome='Concessão Aux. Bolsa Atleta', grupo='LIQUIDACOES',
            defaults={'ativo': True, 'gera_relatorio': True})
        bolsa.gera_relatorio = True
        bolsa.ativo = True
        bolsa.save(update_fields=['gera_relatorio', 'ativo'])
        diaria, _ = EspecieProcesso.objects.get_or_create(
            nome='Concessão Diária', grupo='LIQUIDACOES',
            defaults={'ativo': True, 'gera_relatorio': True})
        diaria.gera_relatorio = True
        diaria.ativo = True
        diaria.save(update_fields=['gera_relatorio', 'ativo'])
        admin = criar_usuario('admin_seq', 'GESTAO', is_superuser=True)
        relatorios.definir_ultimo_numero(admin, 100, grupo='LIQUIDACOES')
        relatorios.definir_ultimo_numero(admin, 10, grupo='BOLSA_ATLETA')
        relatorios.definir_ultimo_numero(admin, 20, grupo='DIARIA')

        liquidacao = self.novo_processo(self.especie_liq, numero_processo='60/2026')
        processo_bolsa = self.novo_processo(bolsa, numero_processo='61/2026')
        processo_diaria = self.novo_processo(diaria, numero_processo='62/2026')
        self._salvar_liquidacao(liquidacao)
        self._salvar_liquidacao(processo_bolsa)
        self._salvar_liquidacao(processo_diaria)

        self.assertEqual(liquidacao.numero_relatorio, '101')
        self.assertEqual(processo_bolsa.numero_relatorio, '102')
        self.assertEqual(processo_diaria.numero_relatorio, '103')
        for processo in (liquidacao, processo_bolsa, processo_diaria):
            self.assertEqual(
                LinhaControleRelatorio.objects.get(processo=processo).sequencia,
                'LIQUIDACOES')

        self.assertEqual(relatorios.estado_sequencia('BOLSA_ATLETA')['proximo'], 11)
        self.assertEqual(relatorios.estado_sequencia('DIARIA')['proximo'], 21)

        self.client.force_login(self.analista_liq)
        aba_bolsa = self.client.get(
            reverse('controle_relatorio') + '?aba=BOLSA_ATLETA')
        self.assertContains(aba_bolsa, 'Bolsa Atleta')
        self.assertContains(
            aba_bolsa, 'Inclui (Concessão Aux. Bolsa Atleta; P.C. Bolsa Atleta).')
        self.assertNotContains(aba_bolsa, '61/2026')

        aba_liq = self.client.get(reverse('controle_relatorio'))
        self.assertContains(aba_liq, '60/2026')
        self.assertContains(aba_liq, '61/2026')
        self.assertContains(aba_liq, '62/2026')

    def test_planilha_ordena_por_numero_de_relatorio(self):
        admin = criar_usuario('admin_ord', 'GESTAO', is_superuser=True)
        primeiro = self.novo_processo(self.especie_liq, numero_processo='20/2026')
        segundo = self.novo_processo(self.especie_liq, numero_processo='21/2026')
        self._salvar_liquidacao(primeiro)
        self._salvar_liquidacao(segundo)
        relatorios.alterar_numero(admin, primeiro.id, 1895, '2026-05-01')
        relatorios.alterar_numero(admin, segundo.id, 1893, '2026-05-02')
        numeros = [linha.numero_relatorio for linha in relatorios.listar(self.analista_liq)]
        self.assertEqual(numeros, ['1893', '1895'])

    def test_tela_formata_valor_e_destino_e_lista_de_secretarias(self):
        self.assertEqual(svc_processos.formatar_valor('40000000'), 'R$ 40.000.000,00')
        self.assertEqual(svc_processos.formatar_valor('R$ 40.000.000,00'), 'R$ 40.000.000,00')
        processo = self.novo_processo(self.especie_liq, numero_processo='30/2026')
        tramitacao.assumir(processo.id, self.analista_liq)
        processo.valor = '40000000'
        processo.destino = 'Unidade de Teste'
        processo.save(update_fields=['valor', 'destino'])
        self.client.force_login(self.analista_liq)
        pagina = self.client.get(reverse('analista_processo', args=[processo.id]))
        self.assertContains(pagina, 'R$ 40.000.000,00')
        self.assertContains(pagina, 'name="destino"')
        self.assertContains(pagina, 'Selecione a secretaria')
        self.assertContains(pagina, 'Unidade de Teste')

    def test_protocolo_nao_acessa(self):
        self.client.force_login(self.protocolo)
        self.assertEqual(
            self.client.get(reverse('controle_relatorio')).status_code, 403)

    def test_analista_de_licitacoes_nao_ve_linha_de_liquidacao(self):
        processo = self.novo_processo(self.especie_liq, numero_processo='13/2026')
        self._salvar_liquidacao(processo)
        self.client.force_login(self.analista_lic)
        pagina = self.client.get(reverse('controle_relatorio'))
        self.assertEqual(pagina.status_code, 200)
        self.assertNotContains(pagina, '13/2026')
