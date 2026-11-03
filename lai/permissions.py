from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from .models import Demanda

def _operador_do_administrador(user):
    """Cria o cadastro de Operador do superusuário na primeira vez que ele abre a aba LAI.

    Só quando o módulo é exclusivo do administrador (LAI_SOMENTE_ADMIN). O cadastro nasce com
    acesso a todas as secretarias, mas SEM competência recursal: decidir recurso é um ato jurídico
    que precisa ser concedido de propósito em Cadastros.
    """
    existente = getattr(user, 'operador', None)
    if existente is not None:
        return existente
    from .models import Operador
    operador, _ = Operador.objects.get_or_create(usuario=user, defaults={
        'nome': user.get_full_name() or user.get_username(),
        'cargo': 'Administrador do sistema',
        'email': user.email or 'administrador@invalid.example',
        'acesso_global': True,
        'autoridade_recursal': False,
    })
    return operador


def perfil(user):
    if (getattr(user, 'is_authenticated', False) and user.is_active and user.is_superuser
            and getattr(settings, 'LAI_SOMENTE_ADMIN', False)):
        _operador_do_administrador(user)
    op = getattr(user, 'operador', None)
    if not user.is_authenticated or not user.is_active or not op or not op.ativo:
        raise PermissionDenied('Perfil LAI ativo necessário.')
    return op

def exigir(user, acao, demanda=None):
    if not getattr(settings, 'LAI_ENABLED', True): raise PermissionDenied('Módulo desabilitado.')
    op = perfil(user)
    if not user.has_perm('lai.' + acao): raise PermissionDenied('Sem permissão para esta operação.')
    if acao == 'decidir' and not op.autoridade_recursal:
        raise PermissionDenied('Competência recursal não cadastrada.')
    if demanda and not (op.acesso_global or demanda.operador_id == op.pk or op.secretarias.filter(pk=demanda.secretaria_id).exists()):
        raise PermissionDenied('Demanda fora de sua unidade.')
    return op

def visiveis(user):
    op = exigir(user, 'view_demanda')
    qs = Demanda.objects.select_related('secretaria', 'operador', 'politica')
    return qs if op.acesso_global else qs.filter(Q(operador=op) | Q(secretaria__in=op.secretarias.all())).distinct()
