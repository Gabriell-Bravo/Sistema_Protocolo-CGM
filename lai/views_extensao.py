"""Entradas que a extensão do navegador usa para entregar ao sistema o que leu no Fala.BR.

Não usam o login por cookie: cada chamada traz o código da extensão (Authorization: Bearer ...),
gerado para o usuário que baixou a extensão. Só o administrador (ou quem tem perfil LAI de
operador, quando o módulo não é exclusivo do administrador) é aceito.
"""
import json
from functools import wraps

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from . import ponte_extensao
from .permissions import exigir


def _recusa(mensagem, status):
    return JsonResponse({'ok': False, 'erro': mensagem}, status=status)


def api(view):
    @csrf_exempt
    @require_POST
    @wraps(view)
    def embrulhada(request, *args, **kwargs):
        cabecalho = request.META.get('HTTP_AUTHORIZATION', '')
        token = cabecalho[7:].strip() if cabecalho.lower().startswith('bearer ') else ''
        usuario = ponte_extensao.usuario_do_token(token)
        if usuario is None:
            return _recusa('Código da extensão inválido ou vencido. Baixe a extensão de novo na aba LAI.', 401)
        if getattr(settings, 'LAI_SOMENTE_ADMIN', False) and not usuario.is_superuser:
            return _recusa('A aba LAI é exclusiva do administrador.', 403)
        try:
            exigir(usuario, 'operar')
        except PermissionDenied as exc:
            return _recusa(str(exc) or 'Sem permissão.', 403)
        request.user = usuario
        try:
            resposta = view(request, *args, **kwargs)
        except ponte_extensao.ExtensaoError as exc:
            return _recusa(str(exc), 409)
        except ValueError as exc:
            return _recusa(str(exc), 400)
        resposta['Cache-Control'] = 'no-store'
        return resposta
    return embrulhada


def _json(request):
    try:
        dados = json.loads(request.body.decode('utf-8') or '{}')
    except (UnicodeDecodeError, ValueError):
        raise ValueError('O corpo da chamada não é um JSON válido.')
    if not isinstance(dados, dict):
        raise ValueError('O corpo da chamada deve ser um objeto JSON.')
    return dados


@api
def ping(request):
    return JsonResponse({'ok': True, 'usuario': request.user.get_username(), 'versao': ponte_extensao.VERSAO})


@api
def leitura(request):
    aviso = ponte_extensao.receber_leitura(_json(request))
    return JsonResponse({'ok': True, 'resumo': aviso})


@api
def progresso(request):
    continuar = ponte_extensao.progresso(_json(request))
    return JsonResponse({'ok': True, 'continuar': continuar})


@api
def pedido(request):
    nup = (request.POST.get('nup') or '').strip()
    arquivo = request.FILES.get('pdf')
    if not nup or arquivo is None:
        raise ValueError('Faltam o NUP ou o PDF.')
    anexos = [(f.name, f.read()) for f in request.FILES.getlist('anexo')]
    resultado = ponte_extensao.receber_pedido(nup, arquivo.read(), anexos)
    return JsonResponse({'ok': True, 'pasta': resultado['pasta'], 'anexos': resultado['anexos']})


@api
def falha(request):
    dados = _json(request)
    ponte_extensao.registrar_falha(dados.get('nup'), dados.get('erro'))
    return JsonResponse({'ok': True})


@api
def concluir(request):
    ponte_extensao.concluir()
    return JsonResponse({'ok': True})
