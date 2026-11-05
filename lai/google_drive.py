"""Envio das pastas dos pedidos para o Google Drive, com uma conta de serviço.

Configuração (no servidor, fora do repositório):

    LAI_DRIVE_CREDENCIAIS  caminho do arquivo JSON da conta de serviço
    LAI_DRIVE_PASTA_ID     ID da pasta do Drive que vai receber as pastas dos NUPs

A pasta do Drive precisa estar compartilhada, como Editor, com o e-mail da conta de serviço
(campo "client_email" do JSON). Para cada pedido o sistema cria, dentro dela, uma pasta com o
mesmo nome da pasta do servidor e envia os arquivos. Reenviar não duplica: arquivo que já está
lá com o mesmo tamanho é pulado, e o que mudou de tamanho é atualizado.
"""
import json
import logging
import mimetypes
from pathlib import Path

from django.conf import settings

log = logging.getLogger(__name__)

API = 'https://www.googleapis.com/drive/v3'
UPLOAD = 'https://www.googleapis.com/upload/drive/v3'
ESCOPOS = ['https://www.googleapis.com/auth/drive']
TIPO_PASTA = 'application/vnd.google-apps.folder'
LIMITE_ARQUIVO = 200 * 1024 * 1024
TEMPO_LIMITE = (15, 300)  # (conexão, resposta) em segundos


class DriveError(Exception):
    """Mensagem já pronta para mostrar ao usuário."""


def _credenciais():
    return str(getattr(settings, 'LAI_DRIVE_CREDENCIAIS', '') or '').strip()


def _pasta_raiz():
    return str(getattr(settings, 'LAI_DRIVE_PASTA_ID', '') or '').strip()


def configurado():
    return bool(_pasta_raiz() and _credenciais() and Path(_credenciais()).is_file())


def _email_da_conta():
    try:
        return json.loads(Path(_credenciais()).read_text(encoding='utf-8')).get('client_email', '')
    except (OSError, ValueError):
        return ''


def explicar_configuracao():
    """Texto do que falta configurar, ou '' se estiver tudo certo."""
    if not _pasta_raiz() or not _credenciais():
        return ('O envio ao Google Drive ainda não foi configurado no servidor '
                '(faltam LAI_DRIVE_CREDENCIAIS e LAI_DRIVE_PASTA_ID).')
    if not Path(_credenciais()).is_file():
        return 'O arquivo de credenciais do Google Drive não foi encontrado no servidor.'
    return ''


def _sessao():
    try:
        from google.auth.transport.requests import AuthorizedSession
        from google.oauth2 import service_account
        credenciais = service_account.Credentials.from_service_account_file(_credenciais(), scopes=ESCOPOS)
    except ImportError as exc:
        raise DriveError('As bibliotecas do Google não estão instaladas no servidor (google-auth e requests).') from exc
    except (OSError, ValueError) as exc:
        raise DriveError('O arquivo de credenciais do Google Drive é inválido.') from exc
    return AuthorizedSession(credenciais)


def _aspas(texto):
    return str(texto).replace('\\', '\\\\').replace("'", "\\'")


def _resposta(r, o_que):
    if r.status_code < 300:
        return r
    if r.status_code in (401, 403):
        raise DriveError(f'O Google Drive recusou o acesso ({o_que}). Confira se a pasta foi compartilhada como '
                         f'Editor com {_email_da_conta() or "a conta de serviço"}.')
    if r.status_code == 404:
        raise DriveError(f'Pasta do Google Drive não encontrada ({o_que}). Confira o ID da pasta e o compartilhamento '
                         f'com {_email_da_conta() or "a conta de serviço"}.')
    raise DriveError(f'O Google Drive respondeu com erro {r.status_code} ({o_que}).')


def _listar(sessao, pai, nome=None, so_pastas=False):
    consulta = f"'{_aspas(pai)}' in parents and trashed = false"
    if nome is not None:
        consulta += f" and name = '{_aspas(nome)}'"
    if so_pastas:
        consulta += f" and mimeType = '{TIPO_PASTA}'"
    r = sessao.get(f'{API}/files', params={
        'q': consulta, 'fields': 'files(id,name,size,webViewLink)', 'pageSize': 1000,
        'supportsAllDrives': 'true', 'includeItemsFromAllDrives': 'true'}, timeout=TEMPO_LIMITE)
    return _resposta(r, 'listar').json().get('files', [])


def _pasta_do_pedido(sessao, nome, pai):
    existentes = _listar(sessao, pai, nome, so_pastas=True)
    if existentes:
        return existentes[0]
    r = sessao.post(f'{API}/files', params={'supportsAllDrives': 'true', 'fields': 'id,webViewLink'}, json={
        'name': nome, 'mimeType': TIPO_PASTA, 'parents': [pai]}, timeout=TEMPO_LIMITE)
    return _resposta(r, 'criar a pasta').json()


def _enviar_arquivo(sessao, caminho, pai, existente_id=None):
    tipo = mimetypes.guess_type(caminho.name)[0] or 'application/octet-stream'
    cabecalho = {'X-Upload-Content-Type': tipo, 'X-Upload-Content-Length': str(caminho.stat().st_size)}
    if existente_id:
        r = sessao.patch(f'{UPLOAD}/files/{existente_id}', params={'uploadType': 'resumable', 'supportsAllDrives': 'true'},
                         json={}, headers=cabecalho, timeout=TEMPO_LIMITE)
    else:
        r = sessao.post(f'{UPLOAD}/files', params={'uploadType': 'resumable', 'supportsAllDrives': 'true'},
                        json={'name': caminho.name, 'parents': [pai]}, headers=cabecalho, timeout=TEMPO_LIMITE)
    destino = _resposta(r, f'enviar {caminho.name}').headers.get('Location')
    if not destino:
        raise DriveError(f'O Google Drive não aceitou o envio de {caminho.name}.')
    with open(caminho, 'rb') as arquivo:
        r = sessao.put(destino, data=arquivo, headers={'Content-Type': tipo}, timeout=TEMPO_LIMITE)
    _resposta(r, f'enviar {caminho.name}')


def enviar_pasta(pasta, sessao=None):
    """Envia os arquivos de `pasta` para dentro da pasta do Drive. Devolve um resumo."""
    pasta = Path(pasta)
    if not pasta.is_dir():
        raise DriveError('A pasta do pedido não existe mais no servidor.')
    problema = explicar_configuracao()
    if problema:
        raise DriveError(problema)
    arquivos = sorted(p for p in pasta.iterdir() if p.is_file())
    if not arquivos:
        raise DriveError('A pasta do pedido está vazia.')
    grandes = [p.name for p in arquivos if p.stat().st_size > LIMITE_ARQUIVO]
    if grandes:
        raise DriveError(f'Arquivo grande demais para enviar por aqui: {grandes[0]}.')
    try:
        sessao = sessao or _sessao()
        destino = _pasta_do_pedido(sessao, pasta.name, _pasta_raiz())
        no_drive = {f['name']: f for f in _listar(sessao, destino['id'])}
        enviados = ja_existiam = 0
        for arquivo in arquivos:
            atual = no_drive.get(arquivo.name)
            if atual and str(atual.get('size', '')) == str(arquivo.stat().st_size):
                ja_existiam += 1
                continue
            _enviar_arquivo(sessao, arquivo, destino['id'], atual['id'] if atual else None)
            enviados += 1
    except DriveError:
        raise
    except Exception as exc:  # falha de rede, certificado, tempo esgotado...
        log.warning('Falha ao falar com o Google Drive: %s', exc)
        raise DriveError('Não foi possível falar com o Google Drive agora. Tente de novo em instantes.') from exc
    return {'pasta_id': destino['id'], 'link': destino.get('webViewLink', ''), 'enviados': enviados,
            'ja_existiam': ja_existiam, 'total': len(arquivos)}
