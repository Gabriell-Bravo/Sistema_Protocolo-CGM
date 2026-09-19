# processos_app/views_gestao.py
"""
Telas exclusivas da Gestão: cadastros parametrizáveis (itens 19 a 22),
Gestão de Pessoas CGM (itens 23 e 24) e Dashboard (itens 47 a 50).

Views tratam HTTP; as regras ficam nos services. Acesso por PAPEL, nunca
por nome de pessoa (item 3).
"""

import logging
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import (EspecieProcesso, Prioridade, Profile,
                     TipoIndisponibilidade, UnidadeAdministrativa)
from .services import gestao_pessoas, indicadores, prazos
from .services import permissions as perm

logger = logging.getLogger(__name__)

APENAS_GESTAO = 'Área exclusiva da Gestão.'


# --------------------------------------------------------------------------
# Cadastros parametrizáveis
# --------------------------------------------------------------------------
# Um cadastro usado historicamente não é excluído: é inativado (item 19).
# Por isso não existe botão de excluir.

CADASTROS = {
    'unidades': {
        'modelo': UnidadeAdministrativa,
        'titulo': 'Unidades Administrativas',
        'subtitulo': 'Usadas como Secretaria de origem e como destino.',
        'campos': [('nome', 'Nome', 'texto'), ('sigla', 'Sigla', 'texto'),
                   ('ordem', 'Ordem', 'numero')],
        'obrigatorios': ['nome'],
        'relacionados': ['processos_origem', 'processos_destino'],
    },
    'especies': {
        'modelo': EspecieProcesso,
        'titulo': 'Espécies de Processo',
        'subtitulo': 'A espécie define o grupo do processo e a periodicidade do monitoramento.',
        'campos': [('nome', 'Nome', 'texto'), ('grupo', 'Grupo', 'escolha'),
                   ('ordem', 'Ordem', 'numero'),
                   ('tipo_monitoramento', 'Monitoramento', 'escolha'),
                   ('encerra_monitoramento_anterior', 'Encerra monitoramento anterior', 'bool'),
                   ('gera_relatorio', 'Gera nº de relatório', 'bool'),
                   ('exige_contratada', 'Exige contratada', 'bool'),
                   ('exige_valor', 'Exige valor', 'bool')],
        'escolhas': {'grupo': EspecieProcesso.GRUPO_CHOICES,
                     'tipo_monitoramento': EspecieProcesso.TIPO_MONITORAMENTO_CHOICES},
        'obrigatorios': ['nome', 'grupo'],
        'relacionados': ['processos'],
        # Mudar o grupo de espécie já usada deixaria os processos antigos
        # com grupo derivado diferente do gravado.
        'travados_se_usado': ['grupo'],
    },
    'prioridades': {
        'modelo': Prioridade,
        'titulo': 'Prioridades',
        'subtitulo': ('Prazo em dias de cada prioridade. A política de contagem '
                      '(dias corridos ou úteis) segue pendente de definição administrativa.'),
        'campos': [('codigo', 'Código', 'texto'), ('nome', 'Nome', 'texto'),
                   ('prazo_dias', 'Prazo (dias)', 'numero'), ('ordem', 'Ordem', 'numero')],
        'obrigatorios': ['codigo', 'nome', 'prazo_dias'],
        'relacionados': ['processos'],
        'travados_se_usado': ['codigo'],
    },
    'tipos-indisponibilidade': {
        'modelo': TipoIndisponibilidade,
        'titulo': 'Tipos de Indisponibilidade',
        'subtitulo': 'Usados no módulo Gestão de Pessoas CGM.',
        'campos': [('nome', 'Nome', 'texto'), ('ordem', 'Ordem', 'numero')],
        'obrigatorios': ['nome'],
        'relacionados': ['registros'],
    },
}


def _config(slug):
    if slug not in CADASTROS:
        raise PermissionDenied('Cadastro desconhecido.')
    return CADASTROS[slug]


def _em_uso(registro, config):
    return any(getattr(registro, rel).exists() for rel in config.get('relacionados', []))


@login_required
@perm.exige(perm.pode_editar_cadastros, APENAS_GESTAO)
def cadastros(request, slug='unidades'):
    config = _config(slug)
    consulta = config['modelo'].objects.all()
    pagina = Paginator(consulta, 50).get_page(request.GET.get('page'))
    escolhas = config.get('escolhas', {})

    colunas = [{'campo': c, 'rotulo': r, 'tipo': t, 'opcoes': escolhas.get(c, [])}
               for c, r, t in config['campos']]
    linhas = []
    for registro in pagina:
        linhas.append({
            'obj': registro,
            'em_uso': _em_uso(registro, config),
            'celulas': [dict(coluna, valor=getattr(registro, coluna['campo'])) for coluna in colunas],
        })

    return render(request, 'gestao/cadastros.html', {
        'slug': slug,
        'titulo': config['titulo'],
        'subtitulo': config['subtitulo'],
        'colunas': colunas,
        'linhas': linhas,
        'pagina': pagina,
        'abas': [(chave, dados['titulo']) for chave, dados in CADASTROS.items()],
        'total': consulta.count(),
        'total_ativos': consulta.filter(ativo=True).count(),
        'travados': config.get('travados_se_usado', []),
    })


@login_required
@require_POST
@perm.exige(perm.pode_editar_cadastros, APENAS_GESTAO)
def cadastro_salvar(request, slug):
    config = _config(slug)
    modelo = config['modelo']
    registro = None
    if request.POST.get('id'):
        registro = get_object_or_404(modelo, id=request.POST.get('id'))

    dados = {}
    for campo, rotulo, tipo in config['campos']:
        if tipo == 'bool':
            dados[campo] = request.POST.get(campo) == 'on'
            continue
        valor = (request.POST.get(campo) or '').strip()
        if tipo == 'numero':
            if not valor:
                valor = 100 if campo == 'ordem' else None
            else:
                try:
                    valor = int(valor)
                    if valor < 0:
                        raise ValueError
                except ValueError:
                    messages.error(request, f'{rotulo}: informe um número inteiro positivo.')
                    return redirect('gestao_cadastros', slug=slug)
        elif tipo == 'escolha':
            validas = [v for v, _ in config['escolhas'][campo]]
            if valor not in validas:
                messages.error(request, f'{rotulo}: opção inválida.')
                return redirect('gestao_cadastros', slug=slug)
        if campo == 'codigo' and isinstance(valor, str):
            valor = valor.upper()
        dados[campo] = valor

    rotulos = {c: r for c, r, _ in config['campos']}
    faltando = [rotulos[c] for c in config['obrigatorios'] if dados.get(c) in (None, '')]
    if faltando:
        messages.error(request, 'Obrigatório: ' + ', '.join(faltando) + '.')
        return redirect('gestao_cadastros', slug=slug)

    if registro is not None and _em_uso(registro, config):
        for campo in config.get('travados_se_usado', []):
            if str(getattr(registro, campo)) != str(dados[campo]):
                messages.error(
                    request,
                    f'"{rotulos[campo]}" não pode mudar: o cadastro já está '
                    f'vinculado a processos. Crie um novo e inative este.')
                return redirect('gestao_cadastros', slug=slug)

    try:
        if registro is None:
            modelo.objects.create(**dados)
            messages.success(request, 'Cadastro criado.')
        else:
            for campo, valor in dados.items():
                setattr(registro, campo, valor)
            registro.save()
            messages.success(request, 'Cadastro atualizado.')
    except IntegrityError:
        messages.error(request, 'Já existe um cadastro com esse nome ou código.')
    except Exception:
        # item 53: não expor exceção interna ao usuário.
        logger.exception('Falha ao salvar cadastro %s', slug)
        messages.error(request, 'Não foi possível salvar o cadastro.')

    if modelo is Prioridade:
        prazos.limpar_cache()
    return redirect('gestao_cadastros', slug=slug)


@login_required
@require_POST
@perm.exige(perm.pode_editar_cadastros, APENAS_GESTAO)
def cadastro_alternar(request, slug, registro_id):
    """Inativa ou reativa. Nunca exclui (item 19)."""
    config = _config(slug)
    registro = get_object_or_404(config['modelo'], id=registro_id)
    registro.ativo = not registro.ativo
    registro.save(update_fields=['ativo'])
    if config['modelo'] is Prioridade:
        prazos.limpar_cache()
    messages.success(request, f'"{registro}" foi {"reativado" if registro.ativo else "inativado"}.')
    return redirect('gestao_cadastros', slug=slug)


# --------------------------------------------------------------------------
# Gestão de Pessoas CGM (itens 23 e 24)
# --------------------------------------------------------------------------

@login_required
@perm.exige(perm.pode_gerir_pessoas, APENAS_GESTAO)
def pessoas(request):
    hoje = timezone.localdate()
    servidores = list(gestao_pessoas.servidores())
    disponibilidade = gestao_pessoas.mapa_disponibilidade(servidores, hoje)
    quadro = [{
        'nome': perm.nome_usuario(servidor),
        'papel': dict(Profile.PAPEL_CHOICES).get(perm.get_papel(servidor) or '', '—'),
        'disponibilidade': disponibilidade.get(servidor.id, gestao_pessoas.DISPONIVEL),
        'disponivel': disponibilidade.get(servidor.id) == gestao_pessoas.DISPONIVEL,
    } for servidor in servidores]

    return render(request, 'gestao/pessoas.html', {
        'quadro': quadro,
        'registros': Paginator(gestao_pessoas.registros(), 50).get_page(request.GET.get('page')),
        'tipos': TipoIndisponibilidade.objects.filter(ativo=True),
        'servidores': servidores,
        'dias_semana': [(0, 'Segunda-feira'), (1, 'Terça-feira'), (2, 'Quarta-feira'),
                        (3, 'Quinta-feira'), (4, 'Sexta-feira')],
        'hoje': hoje,
    })


@login_required
@require_POST
def pessoas_registrar(request):
    converter = gestao_pessoas.converter_data
    try:
        gestao_pessoas.registrar(
            request.user,
            request.POST.get('usuario'),
            request.POST.get('tipo'),
            data_inicio=converter(request.POST.get('data_inicio')),
            data_fim=converter(request.POST.get('data_fim')),
            recorrente=request.POST.get('recorrente') == 'on',
            dia_semana=request.POST.get('dia_semana'),
            vigencia_inicio=converter(request.POST.get('vigencia_inicio')),
            vigencia_fim=converter(request.POST.get('vigencia_fim')),
            observacao=request.POST.get('observacao', ''),
        )
        messages.success(request, 'Indisponibilidade registrada.')
    except (PermissionDenied, ValidationError) as exc:
        messages.error(request, '; '.join(getattr(exc, 'messages', [str(exc)])))
    return redirect('gestao_pessoas')


@login_required
@require_POST
def pessoas_desativar(request, registro_id):
    try:
        gestao_pessoas.desativar(request.user, registro_id)
        messages.success(request, 'Registro desativado. Ele continua no histórico.')
    except (PermissionDenied, ValidationError) as exc:
        messages.error(request, '; '.join(getattr(exc, 'messages', [str(exc)])))
    return redirect('gestao_pessoas')


# --------------------------------------------------------------------------
# Dashboard (itens 47 a 50)
# --------------------------------------------------------------------------

@login_required
@perm.exige(perm.pode_ver_dashboard, APENAS_GESTAO)
def dashboard(request):
    hoje = timezone.localdate()
    converter = gestao_pessoas.converter_data
    inicio = converter(request.GET.get('inicio')) or hoje.replace(day=1)
    fim = converter(request.GET.get('fim')) or hoje
    if fim < inicio:
        inicio, fim = fim, inicio

    filtros = {
        'grupo': request.GET.get('grupo') or None,
        'analista': request.GET.get('analista') or None,
        'secretaria': (request.GET.get('secretaria') or '').strip() or None,
        'especie': request.GET.get('especie') or None,
    }
    mes_anterior_fim = hoje.replace(day=1) - timedelta(days=1)

    return render(request, 'gestao/dashboard.html', {
        'cards': indicadores.cards(hoje),
        'equipe': indicadores.equipe(inicio, fim, hoje),
        'periodo': indicadores.periodo(inicio, fim, **filtros),
        'tempos': indicadores.tempos_medios(inicio, fim, **filtros),
        'inicio': inicio,
        'fim': fim,
        'filtros': filtros,
        'analistas': perm.analistas_ativos(),
        'grupos': EspecieProcesso.GRUPO_CHOICES,
        'especies': EspecieProcesso.objects.order_by('grupo', 'nome'),
        'hoje': hoje,
        'atalhos': [
            ('Este mês', hoje.replace(day=1), hoje),
            ('Mês anterior', mes_anterior_fim.replace(day=1), mes_anterior_fim),
            ('Últimos 30 dias', hoje - timedelta(days=29), hoje),
            ('Este ano', hoje.replace(month=1, day=1), hoje),
        ],
    })
