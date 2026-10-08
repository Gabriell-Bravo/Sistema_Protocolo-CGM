# processos_app/services/exportacao_saidas.py
"""Consulta e títulos para exportação/impressão de processos com saída."""

from datetime import datetime, timedelta
from urllib.parse import urlencode

from django.db.models import Q
from django.utils import timezone

from . import permissions as perm
from . import relatorios
from . import tramitacao

PERIODOS = (
    ('hoje', 'Saídas do dia'),
    ('semana', 'Saídas da semana'),
    ('mes', 'Saídas do mês'),
    ('todas', 'Todas as saídas'),
    ('personalizado', 'Período personalizado'),
)

GRUPOS = (
    ('', 'Todos os grupos'),
    ('LICITACOES_E_CONTRATOS', 'Licitações e Contratos'),
    ('LIQUIDACOES', 'Liquidações'),
    ('CONTABILIDADE', 'Contabilidade'),
    ('OUTROS_GENERO', 'Outros'),
)


class ExportacaoInvalida(ValueError):
    pass


def pode_exportar(usuario):
    return (
        perm.eh_administrador(usuario)
        or perm.is_protocolo(usuario)
        or perm.is_gestao(usuario)
    )


def periodos_disponiveis():
    return [{'codigo': c, 'nome': n} for c, n in PERIODOS]


def grupos_disponiveis(usuario):
    itens = []
    for codigo, nome in GRUPOS:
        if codigo and not perm.pode_ver_grupo(usuario, codigo):
            continue
        itens.append({'codigo': codigo, 'nome': nome})
    return itens


def subgrupos_liquidacoes():
    return [
        {'codigo': item['codigo'], 'nome': item['nome']}
        for item in relatorios.sequencias_disponiveis()
        if relatorios.sequencia_ativa(item['codigo'])
    ]


def _parse_data(texto):
    if not texto:
        return None
    try:
        return datetime.strptime(str(texto).strip(), '%Y-%m-%d').date()
    except (TypeError, ValueError):
        raise ExportacaoInvalida('Formato de data inválido. Use AAAA-MM-DD.')


def resolver_periodo(modelo, data_ini=None, data_fim=None, hoje=None):
    """Devolve (data_inicial, data_final) ou (None, None) para todas.

    Semana = segunda a domingo da semana corrente (locale).
    """
    hoje = hoje or timezone.localdate()
    modelo = (modelo or 'hoje').strip().lower()
    if modelo not in dict(PERIODOS):
        raise ExportacaoInvalida('Modelo de período inválido.')

    if modelo == 'todas':
        return None, None

    if modelo == 'hoje':
        return hoje, hoje

    if modelo == 'semana':
        inicio = hoje - timedelta(days=hoje.weekday())
        fim = inicio + timedelta(days=6)
        return inicio, fim

    if modelo == 'mes':
        inicio = hoje.replace(day=1)
        if inicio.month == 12:
            fim = inicio.replace(year=inicio.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            fim = inicio.replace(month=inicio.month + 1, day=1) - timedelta(days=1)
        return inicio, fim

    # personalizado
    ini = _parse_data(data_ini)
    fim = _parse_data(data_fim)
    if ini is None or fim is None:
        raise ExportacaoInvalida(
            'Informe a data inicial e a data final do período personalizado.')
    if ini > fim:
        raise ExportacaoInvalida(
            'A data inicial não pode ser maior que a data final.')
    return ini, fim


def _filtro_sequencia(codigo_sequencia):
    """Processos da sequência de Liquidações (ajuste, espécie ou mapa)."""
    codigo = (codigo_sequencia or '').strip()
    if not codigo or not relatorios.sequencia_valida(codigo):
        return Q()
    info = relatorios.info_sequencia(codigo)
    especies = list(info.get('especies') or ())
    filtro = (
        Q(sequencia_relatorio=codigo)
        | Q(especie_fk__sequencia_numeracao=codigo)
    )
    if especies:
        filtro |= Q(especie__in=especies) | Q(especie_fk__nome__in=especies)
    return filtro


def filtros_de_request(request):
    """Lê querystring e devolve dict normalizado + intervalo resolvido."""
    periodo = (request.GET.get('periodo') or '').strip().lower()
    genero = (request.GET.get('genero') or '').strip()
    if genero in ('', 'todas', 'todos'):
        genero = ''
    sequencia = (request.GET.get('sequencia') or '').strip()
    especie = (request.GET.get('especie') or '').strip()
    if especie in ('', 'todas', 'todos'):
        especie = ''
    termo = (request.GET.get('termo') or '').strip()
    data_inicial = (request.GET.get('data_inicial') or '').strip()
    data_final = (request.GET.get('data_final') or '').strip()

    # Vindo da lista de Finalizados com datas, sem modelo explícito.
    if not periodo or periodo not in dict(PERIODOS):
        if data_inicial and data_final:
            periodo = 'personalizado'
        else:
            periodo = 'hoje'

    if genero != 'LIQUIDACOES':
        sequencia = ''

    ini, fim = resolver_periodo(periodo, data_inicial, data_final)
    return {
        'periodo': periodo,
        'genero': genero,
        'sequencia': sequencia,
        'especie': especie,
        'termo': termo,
        'data_inicial': ini.isoformat() if ini else data_inicial,
        'data_final': fim.isoformat() if fim else data_final,
        'intervalo': (ini, fim),
    }


def consultar_saidas(usuario, filtros):
    """Queryset de saídas ordenado por data/hora de saída."""
    consulta = tramitacao.finalizados()
    consulta = perm.filtrar_por_grupo(usuario, consulta)

    ini, fim = filtros.get('intervalo') or (None, None)
    if ini is not None:
        consulta = consulta.filter(data_saida__gte=ini)
    if fim is not None:
        consulta = consulta.filter(data_saida__lte=fim)

    genero = (filtros.get('genero') or '').strip()
    if genero:
        if not perm.pode_ver_grupo(usuario, genero):
            return consulta.none()
        consulta = consulta.filter(genero=genero)

    sequencia = (filtros.get('sequencia') or '').strip()
    if sequencia and genero == 'LIQUIDACOES':
        consulta = consulta.filter(_filtro_sequencia(sequencia))

    especie = (filtros.get('especie') or '').strip()
    if especie:
        consulta = consulta.filter(
            Q(especie=especie) | Q(especie_fk__nome=especie))

    termo = (filtros.get('termo') or '').strip()
    if termo:
        consulta = consulta.filter(
            Q(numero_processo__icontains=termo)
            | Q(secretaria__icontains=termo)
            | Q(destino__icontains=termo)
            | Q(objeto__icontains=termo)
            | Q(contratada__icontains=termo)
            | Q(tecnico__icontains=termo)
            | Q(observacao__icontains=termo)
            | Q(observacao_protocolo__icontains=termo)
            | Q(valor__icontains=termo)
            | Q(periodo__icontains=termo)
        )

    return (
        consulta
        .select_related('especie_fk', 'analista_responsavel')
        .order_by('data_saida', 'hora_saida', 'id')
    )


def especies_do_conjunto(usuario, filtros):
    """Espécies distintas já restritas por período/grupo/subgrupo (sem espécie)."""
    base = dict(filtros)
    base['especie'] = ''
    nomes = (
        consultar_saidas(usuario, base)
        .exclude(especie='')
        .values_list('especie', flat=True)
        .distinct()
        .order_by('especie')
    )
    return [n for n in nomes if n]


def rotulo_periodo(filtros):
    periodo = filtros.get('periodo') or 'hoje'
    nome = dict(PERIODOS).get(periodo, periodo)
    ini, fim = filtros.get('intervalo') or (None, None)
    if periodo == 'todas':
        return nome
    if ini and fim:
        if ini == fim:
            return f'{nome} ({ini.strftime("%d/%m/%Y")})'
        return (
            f'{nome} ({ini.strftime("%d/%m/%Y")} a '
            f'{fim.strftime("%d/%m/%Y")})'
        )
    return nome


def titulo_relatorio(filtros):
    partes = [rotulo_periodo(filtros)]
    genero = (filtros.get('genero') or '').strip()
    if genero:
        partes.append(dict(GRUPOS).get(genero, genero))
    sequencia = (filtros.get('sequencia') or '').strip()
    if sequencia:
        partes.append(relatorios.info_sequencia(sequencia)['nome'])
    especie = (filtros.get('especie') or '').strip()
    if especie:
        partes.append(especie)
    return ' · '.join(partes)


def querystring_exportacao(filtros, **extra):
    """Monta querystring estável para links da tela / Excel."""
    params = {
        'periodo': filtros.get('periodo') or 'hoje',
    }
    if filtros.get('genero'):
        params['genero'] = filtros['genero']
    if filtros.get('sequencia'):
        params['sequencia'] = filtros['sequencia']
    if filtros.get('especie'):
        params['especie'] = filtros['especie']
    if filtros.get('termo'):
        params['termo'] = filtros['termo']
    if (filtros.get('periodo') or '') == 'personalizado':
        if filtros.get('data_inicial'):
            params['data_inicial'] = filtros['data_inicial']
        if filtros.get('data_final'):
            params['data_final'] = filtros['data_final']
    params.update({k: v for k, v in extra.items() if v not in (None, '')})
    return urlencode(params)
