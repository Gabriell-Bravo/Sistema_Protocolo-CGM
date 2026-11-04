"""Trava de acesso do módulo LAI quando ele é uma aba exclusiva do administrador.

Vale para TODAS as rotas do namespace `lai`, inclusive downloads e chamadas
JSON, mesmo que uma view nova esqueça de conferir. Esconder o item do menu é
só conforto: a decisão de verdade é esta.

Com `LAI_SOMENTE_ADMIN = False` (ex.: execução independente do módulo) a trava
não faz nada e valem somente as permissões `lai.*` e o cadastro de Operador.
"""
from django.conf import settings
from django.core.exceptions import PermissionDenied

from .permissions import usuario_do_modulo


class SomenteAdministrador:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        if not getattr(settings, 'LAI_SOMENTE_ADMIN', False):
            return None
        match = request.resolver_match
        if match is None or match.namespace != 'lai':
            return None
        usuario = request.user
        if not usuario.is_authenticated:
            # Quem não entrou segue para a tela de login (decorator das views).
            return None
        if not usuario_do_modulo(usuario):
            raise PermissionDenied('A aba LAI é exclusiva do administrador e do perfil LAI.')
        return None
