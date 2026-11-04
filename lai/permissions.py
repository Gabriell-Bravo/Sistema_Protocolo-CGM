from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from .models import Demanda

PAPEL_LAI = 'LAI'

# Permissões que a conta com papel LAI recebe sozinha. Ficam de fora: `cadastrar` (operadores,
# secretarias e regras de prazo) e `decidir` (ato recursal, que precisa ser concedido de propósito
# pelo administrador), além de qualquer exclusão.
PERMISSOES_FORA_DO_PAPEL = {'cadastrar', 'decidir'}


def papel_lai(user):
    """A conta é do tipo (papel) LAI no sistema hospedeiro."""
    profile = getattr(user, 'profile', None)
    return getattr(profile, 'papel', None) == PAPEL_LAI


def usuario_do_modulo(user):
    """Quem entra no módulo quando ele é restrito (LAI_SOMENTE_ADMIN): administrador ou papel LAI."""
    return bool(getattr(user, 'is_authenticated', False) and user.is_active
                and (user.is_superuser or papel_lai(user)))


def sincronizar_permissoes_do_papel(user, ativo):
    """Dá (ativo) ou tira as permissões do módulo de uma conta que entrou/saiu do papel LAI."""
    from django.contrib.auth.models import Permission
    permissoes = [
        p for p in Permission.objects.filter(content_type__app_label='lai')
        if p.codename not in PERMISSOES_FORA_DO_PAPEL and not p.codename.startswith('delete_')
    ]
    if ativo:
        user.user_permissions.add(*permissoes)
    else:
        user.user_permissions.remove(*permissoes)


def _operador_automatico(user):
    """Cria o cadastro de Operador na primeira vez que o administrador ou a conta LAI abre a aba.

    Só quando o módulo é restrito (LAI_SOMENTE_ADMIN). O cadastro nasce com acesso a todas as
    secretarias, mas SEM competência recursal: decidir recurso é um ato jurídico que precisa ser
    concedido de propósito em Cadastros.
    """
    existente = getattr(user, 'operador', None)
    if existente is not None:
        return existente
    from .models import Operador
    operador, _ = Operador.objects.get_or_create(usuario=user, defaults={
        'nome': user.get_full_name() or user.get_username(),
        'cargo': 'Administrador do sistema' if user.is_superuser else 'Operador LAI',
        'email': user.email or 'administrador@invalid.example',
        'acesso_global': True,
        'autoridade_recursal': False,
    })
    return operador


def perfil(user):
    if usuario_do_modulo(user) and getattr(settings, 'LAI_SOMENTE_ADMIN', False):
        _operador_automatico(user)
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
