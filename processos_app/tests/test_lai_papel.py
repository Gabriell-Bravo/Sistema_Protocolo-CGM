"""Papel (tipo de usuário) LAI: conta dedicada ao módulo de Acesso à Informação.

Rodar com:  python manage.py test processos_app.tests.test_lai_papel
"""
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from lai.models import Operador
from processos_app.models import Profile
from processos_app.services import permissions as perm
from processos_app.tests.base import criar_usuario

LINK_DO_MENU = 'href="/lai/falabr/pendentes/"'


class PapelLaiTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.lai = criar_usuario('pessoa_lai', 'LAI')
        cls.gestao = criar_usuario('gestora', 'GESTAO')

    def test_papel_lai_aparece_nas_opcoes_de_cadastro(self):
        self.assertIn('LAI', [codigo for codigo, _ in Profile.PAPEL_CHOICES])

    def test_conta_lai_cai_direto_na_aba_lai(self):
        self.client.force_login(self.lai)
        resp = self.client.get('/')
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp['Location'], reverse('lai:pendentes'))

    def test_conta_lai_abre_o_modulo_e_ve_o_item_no_menu(self):
        self.client.force_login(self.lai)
        resp = self.client.get(reverse('lai:dashboard'))
        self.assertEqual(resp.status_code, 200)
        self.assertIn(LINK_DO_MENU, resp.content.decode())
        self.assertEqual(self.client.get(reverse('lai:pendentes')).status_code, 200)
        self.assertEqual(self.client.get(reverse('lai:extensao')).status_code, 200)

    def test_cadastro_de_operador_nasce_sozinho_sem_competencia_recursal(self):
        self.client.force_login(self.lai)
        self.client.get(reverse('lai:dashboard'))
        operador = Operador.objects.get(usuario=self.lai)
        self.assertEqual(operador.cargo, 'Operador LAI')
        self.assertTrue(operador.acesso_global)
        self.assertFalse(operador.autoridade_recursal)

    def test_recebe_permissoes_de_operar_mas_nao_de_cadastros_nem_decisao(self):
        usuario = User.objects.get(pk=self.lai.pk)
        self.assertTrue(usuario.has_perm('lai.operar'))
        self.assertTrue(usuario.has_perm('lai.expedir'))
        self.assertTrue(usuario.has_perm('lai.view_demanda'))
        self.assertFalse(usuario.has_perm('lai.cadastrar'))
        self.assertFalse(usuario.has_perm('lai.decidir'))
        self.client.force_login(self.lai)
        self.assertEqual(self.client.get(reverse('lai:cadastros')).status_code, 403)

    def test_conta_lai_nao_entra_nas_telas_dos_processos(self):
        self.client.force_login(self.lai)
        for rota in ('gestao_dashboard', 'gestao_processos', 'area_analista'):
            with self.subTest(rota=rota):
                # Barrado: 403 direto ou redirecionamento do user_passes_test; nunca 200.
                self.assertIn(self.client.get(reverse(rota)).status_code, (302, 403))

    def test_papel_lai_nao_enxerga_o_menu_dos_processos(self):
        self.client.force_login(self.lai)
        texto = self.client.get(reverse('lai:dashboard')).content.decode()
        self.assertNotIn(reverse('gestao_dashboard'), texto)
        self.assertNotIn(reverse('area_analista'), texto)

    def test_outros_papeis_continuam_barrados(self):
        self.client.force_login(self.gestao)
        self.assertEqual(self.client.get(reverse('lai:dashboard')).status_code, 403)

    def test_trocar_o_papel_liga_e_desliga_as_permissoes(self):
        gestora = User.objects.get(pk=self.gestao.pk)
        self.assertFalse(gestora.has_perm('lai.operar'))
        gestora.profile.papel = 'LAI'
        gestora.profile.save(update_fields=['papel'])
        self.assertTrue(User.objects.get(pk=gestora.pk).has_perm('lai.operar'))
        gestora.profile.papel = 'GESTAO'
        gestora.profile.save(update_fields=['papel'])
        self.assertFalse(User.objects.get(pk=gestora.pk).has_perm('lai.operar'))
        self.client.force_login(gestora)
        self.assertEqual(self.client.get(reverse('lai:dashboard')).status_code, 403)

    def test_conta_lai_desativada_nao_entra(self):
        self.client.force_login(self.lai)
        User.objects.filter(pk=self.lai.pk).update(is_active=False)
        self.assertNotEqual(self.client.get(reverse('lai:dashboard')).status_code, 200)

    def test_flags_de_permissao(self):
        self.assertTrue(perm.is_lai(self.lai))
        self.assertFalse(perm.is_lai(self.gestao))
        self.assertFalse(perm.is_gestao(self.lai))
        self.assertFalse(perm.is_analista(self.lai))
        self.assertFalse(perm.is_protocolo(self.lai))
