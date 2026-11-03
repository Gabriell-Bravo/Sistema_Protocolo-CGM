"""A aba LAI é exclusiva do administrador (superusuário).

A decisão é do servidor (lai.middleware): esconder o item do menu é só conforto,
então os testes tentam entrar pelas rotas, não só olham o menu.
Rodar com:  python manage.py test processos_app.tests.test_lai_admin
"""
from django.contrib.auth.models import Permission, User
from django.test import TestCase, override_settings
from django.urls import reverse

from lai.models import Operador
from processos_app.tests.base import criar_usuario

ROTAS_LAI = (
    'lai:dashboard', 'lai:pendentes', 'lai:importar', 'lai:nova', 'lai:gestao',
    'lai:cadastros', 'lai:exportar', 'lai:exportar_falabr', 'lai:falabr_sessao',
    'lai:automacao_estado',
)
LINK_DO_MENU = 'href="/lai/"'


class AbaLaiSomenteAdministradorTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser('chefe', 'chefe@example.invalid', 'senha-teste-123')
        cls.gestao = criar_usuario('gestora', 'GESTAO')
        cls.protocolo = criar_usuario('protocolo', 'PROTOCOLO')
        cls.analista = criar_usuario('ana_lic', 'ANALISTA_LICITACOES')
        cls.staff = criar_usuario('equipe', 'GESTAO', is_staff=True)

    def _pagina_do_protocolo(self):
        """Uma tela que qualquer perfil abre e que usa o layout com menu lateral."""
        return self.client.get(reverse('password_change'))

    # ---- o administrador entra ----------------------------------------------------------
    def test_admin_abre_a_aba_lai_no_layout_do_protocolo(self):
        self.client.force_login(self.admin)
        resp = self.client.get(reverse('lai:dashboard'))
        self.assertEqual(resp.status_code, 200)
        texto = resp.content.decode()
        self.assertIn('sidebar__nav', texto)            # menu lateral do protocolo
        self.assertIn('Lei de Acesso à Informação', texto)

    def test_admin_ve_o_item_lai_no_menu(self):
        self.client.force_login(self.admin)
        texto = self._pagina_do_protocolo().content.decode()
        self.assertIn(LINK_DO_MENU, texto)
        self.assertIn('nav-item__label">LAI<', texto)

    def test_admin_abre_todas_as_telas_do_modulo(self):
        self.client.force_login(self.admin)
        for rota in ROTAS_LAI:
            with self.subTest(rota=rota):
                self.assertEqual(self.client.get(reverse(rota)).status_code, 200)

    def test_cadastro_de_operador_do_admin_nasce_sozinho_e_sem_competencia_recursal(self):
        self.assertFalse(Operador.objects.filter(usuario=self.admin).exists())
        self.client.force_login(self.admin)
        self.client.get(reverse('lai:dashboard'))
        operador = Operador.objects.get(usuario=self.admin)
        self.assertTrue(operador.ativo)
        self.assertTrue(operador.acesso_global)
        self.assertFalse(operador.autoridade_recursal)
        self.client.get(reverse('lai:dashboard'))
        self.assertEqual(Operador.objects.filter(usuario=self.admin).count(), 1)

    def test_operador_desativado_do_admin_continua_bloqueado(self):
        Operador.objects.create(usuario=self.admin, nome='Chefe', cargo='Admin', email='c@example.invalid',
                                ativo=False)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse('lai:dashboard')).status_code, 403)

    # ---- quem não é administrador não entra --------------------------------------------
    def test_outros_perfis_recebem_403_em_todas_as_rotas(self):
        for usuario in (self.gestao, self.protocolo, self.analista, self.staff):
            self.client.force_login(usuario)
            for rota in ROTAS_LAI:
                with self.subTest(usuario=usuario.username, rota=rota):
                    self.assertEqual(self.client.get(reverse(rota)).status_code, 403)

    def test_outros_perfis_nao_ganham_cadastro_de_operador_ao_tentar(self):
        self.client.force_login(self.gestao)
        self.client.get(reverse('lai:dashboard'))
        self.assertFalse(Operador.objects.filter(usuario=self.gestao).exists())

    def test_post_e_downloads_tambem_sao_negados(self):
        self.client.force_login(self.gestao)
        self.assertEqual(self.client.post(reverse('lai:automacao_iniciar'), {'selecionados': ['1']}).status_code, 403)
        self.assertEqual(self.client.post(reverse('lai:pendentes'), {'acao': 'logar'}).status_code, 403)
        self.assertEqual(self.client.get(reverse('lai:detalhe', args=[1])).status_code, 403)

    def test_gestao_com_operador_e_todas_as_permissoes_lai_continua_barrada(self):
        """Ter cadastro e permissões LAI não basta: a aba é do administrador."""
        Operador.objects.create(usuario=self.gestao, nome='Gestora', cargo='Gestão',
                                email='g@example.invalid', acesso_global=True)
        self.gestao.user_permissions.set(Permission.objects.filter(content_type__app_label='lai'))
        self.client.force_login(self.gestao)
        self.assertEqual(self.client.get(reverse('lai:dashboard')).status_code, 403)

    def test_outros_perfis_nao_veem_o_item_no_menu(self):
        for usuario in (self.gestao, self.protocolo, self.analista, self.staff):
            self.client.force_login(usuario)
            with self.subTest(usuario=usuario.username):
                resp = self._pagina_do_protocolo()
                self.assertEqual(resp.status_code, 200)
                self.assertNotIn(LINK_DO_MENU, resp.content.decode())

    def test_quem_nao_entrou_vai_para_o_login(self):
        resp = self.client.get(reverse('lai:dashboard'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('login', resp['Location'])

    def test_admin_desativado_nao_entra(self):
        self.client.force_login(self.admin)
        User.objects.filter(pk=self.admin.pk).update(is_active=False)
        resp = self.client.get(reverse('lai:dashboard'))
        self.assertIn(resp.status_code, (302, 403))
        self.assertNotEqual(resp.status_code, 200)

    # ---- chave de liberação --------------------------------------------------------------
    @override_settings(LAI_SOMENTE_ADMIN=False)
    def test_com_a_trava_desligada_valem_so_as_permissoes_do_modulo(self):
        """Sem a trava (execução independente do módulo), perfil sem cadastro LAI segue barrado."""
        self.client.force_login(self.gestao)
        self.assertEqual(self.client.get(reverse('lai:dashboard')).status_code, 403)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse('lai:dashboard')).status_code, 403)  # sem Operador, sem cadastro automático

    def test_trava_ligada_por_padrao_no_sistema(self):
        from django.conf import settings
        self.assertTrue(settings.LAI_SOMENTE_ADMIN)
