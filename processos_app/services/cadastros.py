# processos_app/services/cadastros.py
"""
Acesso aos cadastros parametrizáveis (itens 19 a 22).

Ponto único para transformar o texto que vem das telas em cadastro e para
entregar às telas as listas que antes estavam fixas no HTML e no
JavaScript. Somente registros ATIVOS aparecem nas listas de seleção; os
inativos continuam vinculados aos processos antigos.
"""

from ..models import EspecieProcesso, Prioridade, UnidadeAdministrativa

GRUPOS_ANALISE = ('LICITACOES_E_CONTRATOS', 'LIQUIDACOES')
GRUPO_OUTROS = 'OUTROS_GENERO'


def _chave(texto):
    return (texto or '').strip().casefold()


# --------------------------------------------------------------------------
# Resolução texto -> cadastro
# --------------------------------------------------------------------------

def resolver_unidade(texto):
    """Unidade com o mesmo nome (sem diferenciar maiúsculas), ou None."""
    chave = _chave(texto)
    if not chave:
        return None
    for unidade in UnidadeAdministrativa.objects.all():
        if _chave(unidade.nome) == chave:
            return unidade
    return None


def resolver_especie(nome=None, grupo=None, especie_id=None):
    """Espécie cadastrada pelo id ou pelo nome (+ grupo).

    Sem grupo, só resolve se o nome for único — "Reanálise", por exemplo,
    existe nos dois grupos e exige o grupo para ser identificada.
    """
    if especie_id:
        try:
            return EspecieProcesso.objects.filter(id=int(especie_id)).first()
        except (TypeError, ValueError):
            return None
    chave = _chave(nome)
    if not chave:
        return None
    candidatos = [e for e in EspecieProcesso.objects.all() if _chave(e.nome) == chave]
    if grupo:
        candidatos = [e for e in candidatos if e.grupo == grupo]
    if len(candidatos) == 1:
        return candidatos[0]
    ativos = [e for e in candidatos if e.ativo]
    return ativos[0] if len(ativos) == 1 else None


def resolver_prioridade(codigo):
    codigo = (codigo or '').strip().upper()
    codigo = {'SIM': 'PRIORITARIO', 'NAO': 'NORMAL', 'NÃO': 'NORMAL'}.get(codigo, codigo)
    return Prioridade.objects.filter(codigo=codigo).first() if codigo else None


# --------------------------------------------------------------------------
# Listas para as telas
# --------------------------------------------------------------------------

def unidades_ativas():
    return UnidadeAdministrativa.objects.filter(ativo=True).order_by('ordem', 'nome')


def especies_ativas(grupo=None):
    consulta = EspecieProcesso.objects.filter(ativo=True)
    if grupo:
        consulta = consulta.filter(grupo=grupo)
    return consulta.order_by('grupo', 'ordem', 'nome')


def prioridades_ativas():
    return Prioridade.objects.filter(ativo=True).order_by('ordem', 'codigo')


def opcoes_prioridade():
    """[(codigo, nome)] para selects. Cai para as opções fixas do model se
    o cadastro ainda não tiver sido semeado."""
    from ..models import Processo
    opcoes = [(p.codigo, p.nome) for p in prioridades_ativas()]
    return opcoes or list(Processo.PRIORIDADE_CHOICES)


def dados_para_formulario():
    """Estrutura serializável (json_script) usada pelos formulários de
    entrada e de edição. Substitui as listas fixas do JavaScript."""
    return {
        'unidades': [u.nome for u in unidades_ativas()],
        'especies': [
            {
                'id': e.id,
                'nome': e.nome,
                'grupo': e.grupo,
                'grupo_display': e.get_grupo_display(),
                'monitoramento': e.get_tipo_monitoramento_display(),
                'exige_contratada': e.exige_contratada,
            }
            for e in especies_ativas()
        ],
        'grupos': [
            {'valor': valor, 'rotulo': rotulo}
            for valor, rotulo in EspecieProcesso.GRUPO_CHOICES
        ] + [{'valor': GRUPO_OUTROS, 'rotulo': 'Outros (fora das filas de análise)'}],
    }
