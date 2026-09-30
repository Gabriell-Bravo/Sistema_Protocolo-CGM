"""Anexos de Licitações e Contratos: quem envia, quem baixa, o que é recusado."""

import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse

from processos_app.models import AnexoProcesso, EventoProcesso
from processos_app.services import tramitacao

from .base import BaseProcessoTestCase

_PASTA_MEDIA = tempfile.mkdtemp()
STATIC = {'STORAGES': {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
}}


def _pdf(nome='parecer.pdf', conteudo=b'%PDF-1.4 teste'):
    return SimpleUploadedFile(nome, conteudo, content_type='application/pdf')


@override_settings(MEDIA_ROOT=_PASTA_MEDIA, **STATIC)
class AnexoProcessoTest(BaseProcessoTestCase):

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(_PASTA_MEDIA, ignore_errors=True)

    def setUp(self):
        self.processo = self.novo_processo()
        self.liquidacao = self.novo_processo(self.especie_liq, numero_processo='9/2026')

    def _post_anexo(self, usuario, processo, arquivo):
        self.client.force_login(usuario)
        return self.client.post(
            reverse('anexar_arquivo', args=[processo.id]),
            {'arquivos': arquivo},
        )

    def test_analista_anexa_sem_assumir_nem_preencher_analise(self):
        resposta = self._post_anexo(self.analista_lic, self.processo, _pdf())
        self.assertEqual(resposta.status_code, 302)
        anexo = AnexoProcesso.objects.get(processo=self.processo)
        self.assertEqual(anexo.nome_original, 'parecer.pdf')
        self.assertEqual(anexo.enviado_por, self.analista_lic)
        self.assertTrue(EventoProcesso.objects.filter(
            processo=self.processo, tipo='ARQUIVO_ANEXADO').exists())
        self.processo.refresh_from_db()
        self.assertEqual(self.processo.situacao_tramite, 'DISPONIVEL')
        self.assertIsNone(self.processo.analista_responsavel)

    def test_tela_mostra_anexo_e_outros_papeis_baixam(self):
        self._post_anexo(self.analista_lic, self.processo, _pdf())
        anexo = AnexoProcesso.objects.get()

        self.client.force_login(self.analista_lic)
        pagina = self.client.get(reverse('analista_processo', args=[self.processo.id]))
        self.assertContains(pagina, 'Escolher arquivos')
        self.assertContains(pagina, 'parecer.pdf')
        self.assertContains(pagina, 'não são obrigatórios')

        self.client.force_login(self.gestao)
        consulta = self.client.get(reverse('analista_processo', args=[self.processo.id]))
        self.assertContains(consulta, 'parecer.pdf')
        self.assertNotContains(consulta, 'Escolher arquivos')

        for usuario in (self.gestao, self.protocolo, self.analista_lic2):
            self.client.force_login(usuario)
            baixa = self.client.get(reverse('baixar_anexo', args=[anexo.id]))
            self.assertEqual(baixa.status_code, 200, usuario.username)
            self.assertIn(b'%PDF', b''.join(baixa.streaming_content))

        self.client.force_login(self.protocolo)
        historico = self.client.get(reverse('ver_historico_processo', args=[self.processo.id]))
        self.assertContains(historico, 'parecer.pdf')
        self.assertNotContains(historico, 'Escolher arquivos')

    def test_liquidacao_nao_anexa_e_outro_grupo_nao_baixa(self):
        resposta = self._post_anexo(self.analista_liq, self.processo, _pdf())
        self.assertEqual(resposta.status_code, 302)
        self.assertFalse(AnexoProcesso.objects.exists())

        pagina_liq = self._post_anexo(self.analista_liq, self.liquidacao, _pdf('liq.pdf'))
        self.assertEqual(pagina_liq.status_code, 302)
        self.assertFalse(AnexoProcesso.objects.filter(processo=self.liquidacao).exists())

        self.client.force_login(self.analista_liq)
        tela = self.client.get(reverse('analista_processo', args=[self.liquidacao.id]))
        self.assertNotContains(tela, 'Escolher arquivos')

        self._post_anexo(self.analista_lic, self.processo, _pdf())
        anexo = AnexoProcesso.objects.get()
        self.client.force_login(self.analista_liq)
        self.assertEqual(
            self.client.get(reverse('baixar_anexo', args=[anexo.id])).status_code, 403)
        self.client.force_login(self.gestao)
        self.assertEqual(
            self.client.post(reverse('remover_anexo', args=[anexo.id])).status_code, 302)
        self.assertTrue(AnexoProcesso.objects.filter(id=anexo.id).exists())

    def test_recusa_tipo_e_tamanho(self):
        resposta = self._post_anexo(
            self.analista_lic, self.processo,
            SimpleUploadedFile('virus.exe', b'MZ', content_type='application/octet-stream'))
        self.assertEqual(resposta.status_code, 302)
        self.assertFalse(AnexoProcesso.objects.exists())

        grande = SimpleUploadedFile('longo.pdf', b'x' * (15 * 1024 * 1024 + 1),
                                     content_type='application/pdf')
        self._post_anexo(self.analista_lic, self.processo, grande)
        self.assertFalse(AnexoProcesso.objects.exists())

    def test_declinar_analise_preserva_arquivo(self):
        tramitacao.assumir(self.processo.id, self.analista_lic)
        self._post_anexo(self.analista_lic, self.processo, _pdf())
        tramitacao.declinar_analise(self.processo.id, self.analista_lic, 'Teste')
        self.assertTrue(AnexoProcesso.objects.filter(processo=self.processo).exists())

    def test_encaminha_para_assinatura_so_com_anexo(self):
        tramitacao.assumir(self.processo.id, self.analista_lic)
        self._post_anexo(self.analista_lic, self.processo, _pdf())
        self.client.force_login(self.analista_lic)
        pagina = self.client.get(reverse('analista_processo', args=[self.processo.id]))
        self.assertContains(pagina, 'O arquivo anexado segue para assinatura.')
        self.assertNotContains(pagina, 'anexe ao menos um arquivo')

        resposta = self.client.post(
            reverse('analista_processo', args=[self.processo.id]),
            {'acao': 'concluir'},
        )
        self.assertRedirects(resposta, reverse('area_analista'))
        self.processo.refresh_from_db()
        self.assertEqual(self.processo.situacao_tramite, 'AGUARDANDO_ASSINATURA')
        self.assertEqual(self.processo.status_analise, 'NAO_APLICAVEL')
        self.assertFalse(self.processo.numero_despacho)
        self.assertFalse(self.processo.destino)

    def test_sem_anexo_nao_encaminha_licitacao(self):
        tramitacao.assumir(self.processo.id, self.analista_lic)
        self.client.force_login(self.analista_lic)
        pagina = self.client.get(reverse('analista_processo', args=[self.processo.id]))
        self.assertContains(pagina, 'anexe ao menos um arquivo')
        resposta = self.client.post(
            reverse('analista_processo', args=[self.processo.id]),
            {'acao': 'concluir'},
        )
        self.assertEqual(resposta.status_code, 302)
        self.processo.refresh_from_db()
        self.assertEqual(self.processo.situacao_tramite, 'EM_ANALISE')

    def test_remover(self):
        self._post_anexo(self.analista_lic, self.processo, _pdf())
        anexo = AnexoProcesso.objects.get()
        self.client.force_login(self.analista_lic)
        resposta = self.client.post(reverse('remover_anexo', args=[anexo.id]))
        self.assertEqual(resposta.status_code, 302)
        self.assertFalse(AnexoProcesso.objects.exists())
        self.assertTrue(EventoProcesso.objects.filter(
            processo=self.processo, tipo='ARQUIVO_REMOVIDO').exists())
