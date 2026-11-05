"""Envio das pastas dos pedidos ao Google Drive (sem falar com o Google: a sessão é simulada)."""
import json
from pathlib import Path
from unittest import mock

from django.test import override_settings
from django.urls import reverse

from lai import google_drive
from lai.models import ManifestacaoFalabr
from lai.tests.test_extensao import _Base


class _Resp:
    def __init__(self, status=200, corpo=None, cabecalhos=None):
        self.status_code = status
        self._corpo = corpo or {}
        self.headers = cabecalhos or {}

    def json(self):
        return self._corpo


class _DriveFalso:
    """Imita o mínimo do Drive v3: pastas, listagem por pai e envio resumível."""

    def __init__(self, existentes=None, status_listar=200):
        self.arquivos = {}      # id -> dict(name, parents, size, mimeType)
        self.chamadas = []
        self.status_listar = status_listar
        self._n = 0
        for item in existentes or []:
            self._criar(**item)

    def _criar(self, name, parents, size=None, mimeType=''):
        self._n += 1
        ident = f'id{self._n}'
        self.arquivos[ident] = {'id': ident, 'name': name, 'parents': parents, 'size': size,
                                'mimeType': mimeType, 'webViewLink': f'https://drive.example/{ident}'}
        return ident

    def get(self, url, params=None, **_):
        self.chamadas.append(('GET', url))
        if self.status_listar != 200:
            return _Resp(self.status_listar)
        q = params['q']
        pai = q.split("'")[1]
        achados = [a for a in self.arquivos.values() if pai in a['parents']]
        if " and name = '" in q:
            nome = q.split(" and name = '")[1].split("'")[0]
            achados = [a for a in achados if a['name'] == nome]
        if 'mimeType' in q:
            achados = [a for a in achados if a['mimeType'] == google_drive.TIPO_PASTA]
        return _Resp(200, {'files': achados})

    def post(self, url, params=None, json=None, headers=None, **_):
        self.chamadas.append(('POST', url))
        if 'uploadType' in (params or {}):
            ident = self._criar(json['name'], json['parents'])
            return _Resp(200, cabecalhos={'Location': f'https://upload.example/{ident}'})
        ident = self._criar(json['name'], json['parents'], mimeType=json['mimeType'])
        return _Resp(200, {'id': ident, 'webViewLink': f'https://drive.example/{ident}'})

    def patch(self, url, params=None, json=None, headers=None, **_):
        self.chamadas.append(('PATCH', url))
        ident = url.rsplit('/', 1)[1]
        return _Resp(200, cabecalhos={'Location': f'https://upload.example/{ident}'})

    def put(self, destino, data=None, **_):
        self.chamadas.append(('PUT', destino))
        ident = destino.rsplit('/', 1)[1]
        self.arquivos[ident]['size'] = str(len(data.read()))
        return _Resp(200, {'id': ident})


class _ComDrive(_Base):
    def setUp(self):
        super().setUp()
        credenciais = Path(self._tmp.name) / 'conta.json'
        credenciais.write_text(json.dumps({'client_email': 'robo@projeto.iam.gserviceaccount.com'}), encoding='utf-8')
        ajustes = override_settings(LAI_DRIVE_CREDENCIAIS=str(credenciais), LAI_DRIVE_PASTA_ID='RAIZ')
        ajustes.enable()
        self.addCleanup(ajustes.disable)

    def pasta_do_pedido(self, nome='1 - 03996.2026.000936-10 - QUADRO DE CARGOS', arquivos=None):
        base = Path(self._tmp.name) / 'pedidos' / '2026'
        pasta = base / nome
        pasta.mkdir(parents=True)
        for arq, conteudo in (arquivos or {'DetalhesNUP_03996202600093610.pdf': b'%PDF-1 pdf', 'anexo.pdf': b'anexo'}).items():
            (pasta / arq).write_bytes(conteudo)
        return pasta


class EnviarPastaTest(_ComDrive):
    def test_cria_a_pasta_e_envia_os_arquivos(self):
        pasta = self.pasta_do_pedido()
        drive = _DriveFalso()
        resumo = google_drive.enviar_pasta(pasta, sessao=drive)
        self.assertEqual((resumo['enviados'], resumo['ja_existiam'], resumo['total']), (2, 0, 2))
        pastas = [a for a in drive.arquivos.values() if a['mimeType'] == google_drive.TIPO_PASTA]
        self.assertEqual([(p['name'], p['parents']) for p in pastas], [(pasta.name, ['RAIZ'])])
        nomes = sorted(a['name'] for a in drive.arquivos.values() if a['mimeType'] != google_drive.TIPO_PASTA)
        self.assertEqual(nomes, ['DetalhesNUP_03996202600093610.pdf', 'anexo.pdf'])
        self.assertTrue(resumo['link'].startswith('https://drive.example/'))

    def test_reenviar_nao_duplica(self):
        pasta = self.pasta_do_pedido()
        drive = _DriveFalso()
        google_drive.enviar_pasta(pasta, sessao=drive)
        total = len(drive.arquivos)
        resumo = google_drive.enviar_pasta(pasta, sessao=drive)
        self.assertEqual((resumo['enviados'], resumo['ja_existiam']), (0, 2))
        self.assertEqual(len(drive.arquivos), total)

    def test_arquivo_que_mudou_de_tamanho_e_atualizado_no_lugar(self):
        pasta = self.pasta_do_pedido()
        drive = _DriveFalso()
        google_drive.enviar_pasta(pasta, sessao=drive)
        (pasta / 'anexo.pdf').write_bytes(b'anexo bem maior que o anterior')
        total = len(drive.arquivos)
        resumo = google_drive.enviar_pasta(pasta, sessao=drive)
        self.assertEqual((resumo['enviados'], resumo['ja_existiam']), (1, 1))
        self.assertEqual(len(drive.arquivos), total)
        self.assertIn('PATCH', [c[0] for c in drive.chamadas])

    def test_pasta_vazia_ou_inexistente(self):
        vazia = Path(self._tmp.name) / 'vazia'
        vazia.mkdir()
        with self.assertRaisesRegex(google_drive.DriveError, 'vazia'):
            google_drive.enviar_pasta(vazia, sessao=_DriveFalso())
        with self.assertRaisesRegex(google_drive.DriveError, 'não existe'):
            google_drive.enviar_pasta(vazia / 'nada', sessao=_DriveFalso())

    def test_sem_acesso_diz_com_quem_compartilhar(self):
        pasta = self.pasta_do_pedido()
        for status in (403, 404):
            with self.subTest(status=status):
                with self.assertRaisesRegex(google_drive.DriveError, 'robo@projeto.iam.gserviceaccount.com'):
                    google_drive.enviar_pasta(pasta, sessao=_DriveFalso(status_listar=status))

    def test_falha_de_rede_vira_mensagem_amigavel(self):
        pasta = self.pasta_do_pedido()
        drive = _DriveFalso()
        drive.get = mock.Mock(side_effect=OSError('sem rede'))
        with self.assertRaisesRegex(google_drive.DriveError, 'Não foi possível falar com o Google Drive'):
            google_drive.enviar_pasta(pasta, sessao=drive)

    def test_sem_configuracao(self):
        pasta = self.pasta_do_pedido()
        with override_settings(LAI_DRIVE_PASTA_ID=''):
            self.assertFalse(google_drive.configurado())
            with self.assertRaisesRegex(google_drive.DriveError, 'não foi configurado'):
                google_drive.enviar_pasta(pasta, sessao=_DriveFalso())
        with override_settings(LAI_DRIVE_CREDENCIAIS='/nao/existe.json'):
            self.assertFalse(google_drive.configurado())
            self.assertIn('não foi encontrado', google_drive.explicar_configuracao())

    def test_nome_com_aspas_nao_quebra_a_consulta(self):
        self.assertEqual(google_drive._aspas("a'b\\c"), "a\\'b\\\\c")


class EnviarPelaTelaTest(_ComDrive):
    def _post(self, pk):
        return self.client.post(reverse('lai:drive_enviar'), {'pk': pk})

    def test_envia_e_guarda_o_link(self):
        registro = self.registro()
        pasta = self.pasta_do_pedido()
        ManifestacaoFalabr.objects.filter(pk=registro.pk).update(pasta=pasta.name)
        drive = _DriveFalso()
        with mock.patch.object(google_drive, '_sessao', return_value=drive):
            resp = self._post(registro.pk)
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json()['enviados'], 2)
        registro.refresh_from_db()
        self.assertIsNotNone(registro.drive_em)
        self.assertTrue(registro.drive_link.startswith('https://drive.example/'))
        pagina = self.client.get(reverse('lai:pendentes'))
        self.assertContains(pagina, 'No Google Drive desde')
        self.assertContains(pagina, 'id="btn-drive"')

    def test_pedido_sem_pasta_e_pasta_sumida_e_sem_configuracao(self):
        registro = self.registro()
        resp = self._post(registro.pk)
        self.assertEqual(resp.status_code, 409)
        self.assertIn('Automatizar pastas', resp.json()['erro'])
        ManifestacaoFalabr.objects.filter(pk=registro.pk).update(pasta='99 - sumiu')
        self.assertEqual(self._post(registro.pk).status_code, 404)
        pasta = self.pasta_do_pedido()
        ManifestacaoFalabr.objects.filter(pk=registro.pk).update(pasta=pasta.name)
        with override_settings(LAI_DRIVE_PASTA_ID=''):
            resp = self._post(registro.pk)
        self.assertEqual(resp.status_code, 409)
        self.assertIn('não foi configurado', resp.json()['erro'])
        registro.refresh_from_db()
        self.assertIsNone(registro.drive_em)

    def test_erro_do_drive_nao_marca_como_enviado(self):
        registro = self.registro()
        pasta = self.pasta_do_pedido()
        ManifestacaoFalabr.objects.filter(pk=registro.pk).update(pasta=pasta.name)
        with mock.patch.object(google_drive, '_sessao', return_value=_DriveFalso(status_listar=403)):
            resp = self._post(registro.pk)
        self.assertEqual(resp.status_code, 502)
        self.assertIn('Editor', resp.json()['erro'])
        registro.refresh_from_db()
        self.assertIsNone(registro.drive_em)

    def test_nao_sai_da_pasta_dos_pedidos(self):
        registro = self.registro()
        ManifestacaoFalabr.objects.filter(pk=registro.pk).update(pasta='..')
        self.assertEqual(self._post(registro.pk).status_code, 404)

    def test_metodo_e_pk_invalidos(self):
        self.assertEqual(self.client.get(reverse('lai:drive_enviar')).status_code, 405)
        self.assertEqual(self._post('abc').status_code, 404)
        self.assertEqual(self._post('999999').status_code, 404)
