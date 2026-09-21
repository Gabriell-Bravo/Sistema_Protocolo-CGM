"""Smoke tests das telas por papel e regras de HTTP (GET não grava,
POST obrigatório, respostas de erro sem exceção interna)."""

import json

from django.test import override_settings
from django.urls import reverse

from processos_app.models import EventoProcesso, ProcessHistory, Processo
from processos_app.services import tramitacao

from .base import BaseProcessoTestCase

STATIC = {'STORAGES': {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
}}


@override_settings(**STATIC)
class TelasPorPapelTest(BaseProcessoTestCase):

    def setUp(self):
        self.processo = self.novo_processo()
        self.monitorado = self.novo_processo(self.especie_monit, numero_processo='55/2026')

    def _get(self, usuario, nome, *args, esperado=200, query=''):
        self.client.force_login(usuario)
        resposta = self.client.get(reverse(nome, args=args) + query)
        self.assertEqual(resposta.status_code, esperado,
                         f'{nome} com {usuario.username}: {resposta.status_code}')
        return resposta

    def test_protocolo(self):
        for nome in ('listar_processos', 'listar_finalizados', 'cadastrar_processo',
                     'processos_para_retirada'):
            self._get(self.protocolo, nome)
        self._get(self.protocolo, 'ver_historico_processo', self.processo.id)
        self._get(self.protocolo, 'listar_processos', query='?situacao=DISPONIVEL&page=1')

    def test_analista(self):
        self._get(self.analista_lic, 'area_analista')
        self._get(self.analista_lic, 'area_analista', query='?filtro=disponiveis')
        self._get(self.analista_lic, 'analista_processo', self.processo.id)
        self._get(self.analista_lic, 'meus_atendimentos')

    def test_gestao(self):
        for nome in ('gestao_dashboard', 'gestao_processos', 'gestao_diligencias',
                     'gestao_pessoas', 'gestao_cadastros_inicio',
                     'gestao_liberados_assinatura', 'listar_processos',
                     'listar_finalizados'):
            self._get(self.gestao, nome)
        for slug in ('unidades', 'especies', 'prioridades', 'tipos-indisponibilidade'):
            self._get(self.gestao, 'gestao_cadastros', slug)
        self._get(self.gestao, 'gestao_dashboard', query='?inicio=2026-01-01&fim=2026-12-31')
        # item 2: Gestão consulta a tela do processo sem praticar ato.
        self._get(self.gestao, 'analista_processo', self.processo.id)

    def test_acessos_negados(self):
        self._get(self.analista_lic, 'gestao_cadastros_inicio', esperado=403)
        self._get(self.protocolo, 'gestao_dashboard', esperado=403)
        self._get(self.gestao, 'cadastrar_processo', esperado=403)
        # analista de outro grupo não abre o processo
        self._get(self.analista_liq, 'analista_processo', self.processo.id, esperado=403)

    def test_get_nao_grava(self):
        antes = (ProcessHistory.objects.count(), EventoProcesso.objects.count(),
                 list(Processo.objects.values_list('status_monitoramento', flat=True)))
        self._get(self.gestao, 'listar_finalizados')
        self._get(self.gestao, 'listar_processos')
        self._get(self.gestao, 'gestao_dashboard')
        depois = (ProcessHistory.objects.count(), EventoProcesso.objects.count(),
                  list(Processo.objects.values_list('status_monitoramento', flat=True)))
        self.assertEqual(antes, depois)

    def test_exportar_excel(self):
        resposta = self._get(self.gestao, 'exportar_finalizados_excel')
        self.assertIn('spreadsheet', resposta['Content-Type'])


@override_settings(**STATIC)
class AcoesHttpTest(BaseProcessoTestCase):

    def _post_json(self, usuario, nome, args, dados):
        self.client.force_login(usuario)
        return self.client.post(reverse(nome, args=args), data=json.dumps(dados),
                                content_type='application/json')

    def test_salvar_processo_json(self):
        resposta = self._post_json(self.protocolo, 'salvar_processo', [],
                                   self.dados_protocolo())
        self.assertEqual(resposta.status_code, 200, resposta.content)
        self.assertTrue(resposta.json()['success'])

    def test_gestao_nao_cadastra(self):
        resposta = self._post_json(self.gestao, 'salvar_processo', [], self.dados_protocolo())
        self.assertEqual(resposta.status_code, 403)

    def test_endpoints_de_escrita_recusam_get(self):
        processo = self.novo_processo()
        self.client.force_login(self.gestao)
        for nome in ('deletar_processo', 'marcar_saida_processo', 'concluir_monitoramento',
                     'atualizar_processo'):
            resposta = self.client.get(reverse(nome, args=[processo.id]))
            self.assertEqual(resposta.status_code, 405, nome)

    def test_edicao_em_linha_recusa_campo_fora_do_papel(self):
        processo = self.novo_processo()
        resposta = self._post_json(self.protocolo, 'atualizar_processo', [processo.id],
                                   {'objeto': 'Alterado', 'numero_despacho': '7/2026'})
        self.assertEqual(resposta.status_code, 200, resposta.content)
        self.assertIn('numero_despacho', resposta.json()['recusados'])
        processo.refresh_from_db()
        self.assertEqual(processo.objeto, 'Alterado')
        self.assertFalse(processo.numero_despacho)

    def test_gestao_nao_edita_em_linha(self):
        processo = self.novo_processo()
        resposta = self._post_json(self.gestao, 'atualizar_processo', [processo.id],
                                   {'objeto': 'Alterado'})
        self.assertEqual(resposta.status_code, 403)

    def test_cancelar_pela_rota_antiga(self):
        processo = self.novo_processo()
        self.client.force_login(self.gestao)
        resposta = self.client.post(reverse('deletar_processo', args=[processo.id]),
                                    {'motivo': 'Duplicado'})
        self.assertEqual(resposta.status_code, 200, resposta.content)
        processo.refresh_from_db()
        self.assertIsNotNone(processo.cancelado_em)

    def test_saida_pelo_botao_so_no_estado_certo(self):
        processo = self.processo_em_analise()
        self.client.force_login(self.protocolo)
        resposta = self.client.post(reverse('marcar_saida_processo', args=[processo.id]))
        self.assertEqual(resposta.status_code, 400)
        processo.refresh_from_db()
        self.assertEqual(processo.situacao_tramite, 'EM_ANALISE')

    def test_gestao_nao_pratica_ato_na_tela_do_processo(self):
        processo = self.novo_processo()
        self.client.force_login(self.gestao)
        resposta = self.client.post(reverse('analista_processo', args=[processo.id]),
                                    {'status_analise': 'NAO_PROSSEGUIMENTO'})
        self.assertEqual(resposta.status_code, 403)

    def test_direcionar_seletor_vazio_nao_quebra(self):
        processo = self.processo_em_analise()
        self.client.force_login(self.analista_lic)
        resposta = self.client.post(
            reverse('tram_direcionar_assinatura', args=[processo.id]),
            {'destinatario': ''})
        self.assertLess(resposta.status_code, 500)
        processo.refresh_from_db()
        self.assertEqual(processo.situacao_tramite, 'EM_ANALISE')

    def test_desativar_usuario_nao_apaga(self):
        admin = self.gestao
        admin.is_staff = True
        admin.is_superuser = True
        admin.save()
        self.client.force_login(admin)
        self.client.post(reverse('delete_user', args=[self.analista_lic2.id]))
        self.analista_lic2.refresh_from_db()
        self.assertFalse(self.analista_lic2.is_active)

    def test_admin_redefine_senha_de_outro_usuario(self):
        admin = self.gestao
        admin.is_staff = True
        admin.is_superuser = True
        admin.save()
        self.client.force_login(admin)
        nova = 'SenhaTemp#2026a'
        resposta = self.client.post(
            reverse('reset_user_password', args=[self.analista_lic2.id]),
            {'new_password1': nova, 'new_password2': nova})
        self.assertRedirects(resposta, reverse('manage_users'))
        self.analista_lic2.refresh_from_db()
        self.assertTrue(self.analista_lic2.check_password(nova))
        self.assertFalse(self.analista_lic2.check_password('senha-teste-123'))

    def test_nao_admin_nao_redefine_senha(self):
        self.client.force_login(self.protocolo)
        resposta = self.client.get(
            reverse('reset_user_password', args=[self.analista_lic2.id]))
        self.assertEqual(resposta.status_code, 302)

    def test_admin_nao_redefine_a_propria_senha_por_essa_tela(self):
        admin = self.gestao
        admin.is_staff = True
        admin.is_superuser = True
        admin.save()
        self.client.force_login(admin)
        resposta = self.client.get(reverse('reset_user_password', args=[admin.id]))
        self.assertRedirects(resposta, reverse('password_change'))

    def test_fluxo_completo_por_http(self):
        processo = self.processo_em_analise()
        self.client.force_login(self.analista_lic)
        self.client.post(reverse('tram_liberar_assinatura', args=[processo.id]))
        self.client.force_login(self.protocolo)
        self.client.post(reverse('tram_disponibilizar_retirada', args=[processo.id]))
        self.client.post(reverse('tram_registrar_saida'), {'processos': [processo.id]})
        processo.refresh_from_db()
        self.assertEqual(processo.situacao_tramite, 'SAIDA_CONCLUIDA',
                         'verificar nome do campo do lote em views_tramitacao.registrar_saida')
        self.assertFalse(tramitacao.ativos().filter(id=processo.id).exists())
