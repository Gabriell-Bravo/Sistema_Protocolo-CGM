# processos_app/services/processos.py
"""
Criação e edição de Processo (itens 17, 18, 21 e 51).

  - Criação centralizada: salvar_processo (JSON do formulário) e
    cadastrar_processo (POST de formulário) passam pela MESMA função.
    Não há regra diferente conforme a tela (item 18).
  - Edição por WHITELIST por papel (item 51): campo fora da lista do papel
    não é gravado, mesmo que venha na requisição — e a resposta informa o
    que foi recusado.
  - Campos de tramitação (situacao_tramite, analista_responsavel,
    liberado_assinatura_*, saida_concluida_*, cancelado_*)
    não estão em whitelist nenhuma: só mudam pelos endpoints próprios de
    services/tramitacao.py (item 52). A prioridade na entrada é do Protocolo;
    a Gestão continua podendo alterá-la depois.
"""

from datetime import date, datetime, time

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from ..models import Processo, UrgenciaRecorrente
from . import cadastros, monitoramento, prazos
from . import permissions as perm
from .eventos import registrar_diff, registrar_evento

# --------------------------------------------------------------------------
# Whitelists (item 51)
# --------------------------------------------------------------------------

# Dados de protocolo: o que o Protocolo registra na entrada e pode corrigir.
CAMPOS_PROTOCOLO = (
    'numero_processo', 'volume', 'secretaria', 'data_entrada', 'hora_entrada',
    'genero', 'especie', 'objeto', 'contratada', 'recorrente', 'prioridade',
    'observacao_protocolo',
)

# Dados da análise: o que o analista responsável alimenta.
CAMPOS_ANALISTA = (
    'valor', 'destino', 'periodo', 'data_analise', 'numero_despacho',
    'status_analise', 'observacao',
)

# A Gestão não pratica ato técnico nem edita dado de protocolo (item 2).
# Prioridade e cancelamento têm endpoints próprios.
CAMPOS_GESTAO = ()

OBRIGATORIOS_PROTOCOLO = {
    'numero_processo': 'Número do processo',
    'volume': 'Volume',
    'secretaria': 'Secretaria',
    'objeto': 'Objeto',
    'data_entrada': 'Data de entrada',
    'hora_entrada': 'Hora de entrada',
}


class DadosInvalidos(ValidationError):
    """Dados de processo recusados pela validação de backend."""


def campos_editaveis(usuario, processo=None):
    """Campos que este usuário pode gravar neste processo."""
    if perm.is_protocolo(usuario):
        return set(CAMPOS_PROTOCOLO)
    if perm.is_analista(usuario):
        if processo is None:
            return set(CAMPOS_ANALISTA)
        if (processo.situacao_tramite == 'EM_ANALISE'
                and processo.analista_responsavel_id == usuario.id):
            return set(CAMPOS_ANALISTA)
        if (processo.numero_relatorio
                and perm.pode_editar_linha_relatorio(usuario, processo)):
            return set(CAMPOS_ANALISTA)
        return set()
    if perm.is_gestao(usuario):
        return set(CAMPOS_GESTAO)
    return set()


def filtrar_payload(usuario, processo, dados):
    """(permitidos, recusados) a partir do que veio na requisição."""
    permitidos_papel = campos_editaveis(usuario, processo)
    permitidos, recusados = {}, []
    for campo, valor in (dados or {}).items():
        if campo in permitidos_papel:
            permitidos[campo] = valor
        else:
            recusados.append(campo)
    return permitidos, sorted(recusados)


# --------------------------------------------------------------------------
# Conversões
# --------------------------------------------------------------------------

def texto(valor):
    return '' if valor is None else str(valor).strip()


def formatar_valor(bruto):
    """Valor em real: R$ 40.000.000,00. Vazio continua vazio."""
    limpo = texto(bruto).replace('R$', '').replace(' ', '')
    if not limpo:
        return ''
    if ',' in limpo:
        inteiro, _, decimal = limpo.partition(',')
        inteiro = inteiro.replace('.', '')
        decimal = ''.join(c for c in decimal if c.isdigit())[:2].ljust(2, '0')
    elif limpo.count('.') == 1 and len(limpo.rsplit('.', 1)[-1]) in (1, 2):
        inteiro, decimal = limpo.split('.')
        decimal = ''.join(c for c in decimal if c.isdigit()).ljust(2, '0')
    else:
        inteiro = limpo.replace('.', '')
        decimal = '00'
    inteiro = ''.join(c for c in inteiro if c.isdigit()).lstrip('0') or '0'
    grupos = []
    while inteiro:
        grupos.append(inteiro[-3:])
        inteiro = inteiro[:-3]
    return 'R$ ' + '.'.join(reversed(grupos)) + ',' + decimal


def converter_data(valor):
    if isinstance(valor, date):
        return valor
    valor = texto(valor)
    if not valor:
        return None
    try:
        return datetime.strptime(valor, '%Y-%m-%d').date()
    except ValueError:
        raise DadosInvalidos(f'Data inválida: {valor}. Use AAAA-MM-DD.')


def converter_hora(valor):
    if isinstance(valor, time):
        return valor
    valor = texto(valor)
    if not valor:
        return None
    for formato in ('%H:%M', '%H:%M:%S'):
        try:
            return datetime.strptime(valor, formato).time()
        except ValueError:
            continue
    raise DadosInvalidos(f'Hora inválida: {valor}. Use HH:MM.')


def normalizar_recorrente(valor):
    """item 54: valor interno sempre SIM/NAO, sem acento."""
    return 'SIM' if texto(valor).upper() in ('SIM', 'S', 'TRUE', '1') else 'NAO'


def _para_historico(campo, valor):
    if valor is None or valor == '':
        return ''
    if campo == 'status_analise':
        return dict(Processo.STATUS_ANALISE_CHOICES).get(valor, valor)
    if isinstance(valor, date):
        return valor.strftime('%Y-%m-%d')
    if isinstance(valor, time):
        return valor.strftime('%H:%M')
    return str(valor)


def _definir_especie(processo, nome, grupo_enviado, especie_id=None):
    """item 21: o grupo é DERIVADO da espécie cadastrada. O grupo mandado
    pelo navegador só vale quando a espécie não está no cadastro
    (opção "Outros")."""
    especie = cadastros.resolver_especie(nome=nome, grupo=grupo_enviado or None,
                                         especie_id=especie_id)
    if especie is None and not especie_id:
        especie = cadastros.resolver_especie(nome=nome)
    if especie is not None:
        processo.especie_fk = especie
        processo.especie = especie.nome
        processo.genero = especie.grupo
        return especie
    processo.especie_fk = None
    processo.especie = texto(nome)
    processo.genero = texto(grupo_enviado)
    return None


# --------------------------------------------------------------------------
# Criação (itens 17 e 18)
# --------------------------------------------------------------------------

@transaction.atomic
def criar_processo(dados, usuario):
    """Única porta de criação de Processo.

    A entrada registra informação de protocolo, inclusive a prioridade e
    a observação do Protocolo. Técnico, despacho, observação da análise e
    dados de saída NÃO são aceitos aqui, mesmo que venham na requisição.
    """
    perm.assert_permissao(perm.pode_cadastrar_processo(usuario),
                          'Somente o Protocolo cadastra processos.')
    dados = dict(dados or {})
    erros = []

    processo = Processo(
        numero_processo=texto(dados.get('numero_processo')),
        volume=texto(dados.get('volume')),
        secretaria=texto(dados.get('secretaria')),
        objeto=texto(dados.get('objeto')),
        contratada=texto(dados.get('contratada')) or None,
        recorrente=normalizar_recorrente(dados.get('recorrente')),
        observacao_protocolo=texto(dados.get('observacao_protocolo')),
        situacao_tramite='DISPONIVEL',
        status_analise='NAO_APLICAVEL',
        destino=None,
    )

    # item 1: o que o sistema sabe, o sistema preenche.
    processo.data_entrada = converter_data(dados.get('data_entrada')) or timezone.localdate()
    processo.hora_entrada = (converter_hora(dados.get('hora_entrada'))
                             or timezone.localtime().time().replace(microsecond=0))

    especie = _definir_especie(processo, dados.get('especie'),
                               dados.get('genero'), dados.get('especie_id'))

    for campo, rotulo in OBRIGATORIOS_PROTOCOLO.items():
        if not getattr(processo, campo):
            erros.append(f'{rotulo} é obrigatório.')
    if not processo.especie:
        erros.append('Espécie é obrigatória.')
    if not processo.genero:
        erros.append('Informe o grupo da espécie digitada em "Outros".')
    if especie is not None and especie.exige_contratada and not processo.contratada:
        erros.append(f'A espécie "{especie.nome}" exige Contratada / Favorecido / Interessado.')
    if erros:
        raise DadosInvalidos(erros)

    processo.secretaria_fk = cadastros.resolver_unidade(processo.secretaria)

    # Prioridade informada na entrada. Se o número está marcado como
    # urgência recorrente pela Gestão, nasce Urgente de qualquer forma.
    codigo_prioridade = prazos.normalizar_prioridade(dados.get('prioridade'))
    if UrgenciaRecorrente.vale_para(processo.numero_processo):
        codigo_prioridade = 'URGENTE'
    cadastro_prio = cadastros.resolver_prioridade(codigo_prioridade)
    if cadastro_prio is None or not cadastro_prio.ativo:
        codigo_prioridade = 'NORMAL'
        cadastro_prio = cadastros.resolver_prioridade(codigo_prioridade)
    processo.prioridade = codigo_prioridade
    processo.prioridade_fk = cadastro_prio
    processo.prazo_dias = (
        cadastro_prio.prazo_dias if cadastro_prio
        else prazos.dias_por_prioridade(codigo_prioridade))

    monitoramento.definir_inicial(processo)
    processo.save()
    monitoramento.encerrar_ciclos_anteriores(processo, usuario)

    registrar_evento(
        processo, 'PROCESSO_CADASTRADO', usuario,
        descricao=f'Processo cadastrado por {perm.nome_usuario(usuario)}.',
        especie=processo.especie, grupo=processo.genero,
        prioridade=processo.prioridade)
    return processo


# --------------------------------------------------------------------------
# Edição de dados de protocolo (item 51)
# --------------------------------------------------------------------------

@transaction.atomic
def aplicar_edicao(processo, dados, usuario):
    """Aplica a edição permitida ao papel. Devolve (alteracoes, recusados).

    `alteracoes` é {campo: (anterior, novo)}; `recusados` lista os campos
    que vieram na requisição e não são editáveis por este papel.
    """
    permitidos, recusados = filtrar_payload(usuario, processo, dados)
    alteracoes = {}

    if 'especie' in permitidos or 'genero' in permitidos:
        antes = (processo.especie, processo.genero)
        _definir_especie(processo,
                         permitidos.get('especie', processo.especie),
                         permitidos.get('genero', processo.genero))
        if not processo.especie or not processo.genero:
            raise DadosInvalidos('Espécie e grupo são obrigatórios.')
        if antes[0] != processo.especie:
            alteracoes['especie'] = (antes[0], processo.especie)
        if antes[1] != processo.genero:
            alteracoes['genero'] = (antes[1], processo.genero)

    for campo, bruto in permitidos.items():
        if campo in ('especie', 'genero'):
            continue
        if campo == 'data_entrada':
            novo = converter_data(bruto)
        elif campo == 'hora_entrada':
            novo = converter_hora(bruto)
        elif campo == 'recorrente':
            novo = normalizar_recorrente(bruto)
        elif campo == 'prioridade':
            codigo = prazos.normalizar_prioridade(bruto)
            cadastro = cadastros.resolver_prioridade(codigo)
            if cadastro is None or not cadastro.ativo:
                raise DadosInvalidos('Prioridade inválida ou inativa.')
            novo = cadastro.codigo
            atual = processo.prioridade
            if atual == novo:
                continue
            processo.prioridade = novo
            processo.prioridade_fk = cadastro
            processo.prazo_dias = cadastro.prazo_dias
            alteracoes['prioridade'] = (atual, novo)
            continue
        else:
            novo = texto(bruto) or None
        if campo in OBRIGATORIOS_PROTOCOLO and not novo:
            raise DadosInvalidos(f'{OBRIGATORIOS_PROTOCOLO[campo]} é obrigatório.')
        atual = getattr(processo, campo)
        if _para_historico(campo, atual) == _para_historico(campo, novo):
            continue
        setattr(processo, campo, novo)
        alteracoes[campo] = (atual, novo)

    if not alteracoes:
        return alteracoes, recusados

    if 'secretaria' in alteracoes:
        processo.secretaria_fk = cadastros.resolver_unidade(processo.secretaria)
    monitoramento.recalcular_apos_edicao(processo, alteracoes.keys())
    processo.save()
    for campo, (anterior, novo) in alteracoes.items():
        registrar_diff(processo, campo, _para_historico(campo, anterior),
                       _para_historico(campo, novo), usuario)
    return alteracoes, recusados


# --------------------------------------------------------------------------
# Edição da análise (tela do analista)
# --------------------------------------------------------------------------

@transaction.atomic
def aplicar_analise(processo, dados, usuario):
    """Grava os campos de análise enviados. Devolve quantos mudaram.

    Só o analista responsável (em análise) ou o analista do grupo
    corrigindo um relatório já gerado. Se vier número manual no POST,
    ele é gravado no mesmo Salvar análise.
    """
    permitidos, _ = filtrar_payload(
        usuario, processo, {k: dados.get(k) for k in CAMPOS_ANALISTA if k in dados})
    alteracoes = 0
    for campo, bruto in permitidos.items():
        if campo == 'data_analise':
            novo = converter_data(bruto)
        elif campo == 'status_analise':
            novo = texto(bruto) or 'NAO_APLICAVEL'
            if novo not in dict(Processo.STATUS_ANALISE_CHOICES):
                raise DadosInvalidos('Status da análise inválido.')
        elif campo == 'valor':
            novo = formatar_valor(bruto) or None
        else:
            novo = texto(bruto) or None
        atual = getattr(processo, campo)
        if _para_historico(campo, atual) == _para_historico(campo, novo):
            continue
        setattr(processo, campo, novo)
        registrar_diff(processo, campo, _para_historico(campo, atual),
                       _para_historico(campo, novo), usuario)
        alteracoes += 1
        if campo == 'destino':
            processo.destino_fk = cadastros.resolver_unidade(novo)
    from .relatorios import (
        alterar_numero, atribuir_se_preciso, registrar as registrar_relatorio,
    )
    if alteracoes:
        processo.save()

    numero_manual = texto(dados.get('numero_relatorio')) if dados else ''
    if (numero_manual
            and perm.pode_editar_numero_relatorio(usuario, processo)):
        anterior = processo.numero_relatorio or ''
        anterior_data = (
            processo.data_analise.isoformat() if processo.data_analise else '')
        alterar_numero(
            usuario, processo.id, numero_manual, dados.get('data_relatorio'))
        processo.refresh_from_db()
        if (processo.numero_relatorio or '') != anterior:
            alteracoes += 1
        nova_data = (
            processo.data_analise.isoformat() if processo.data_analise else '')
        if nova_data != anterior_data:
            alteracoes += 1
    elif campos_editaveis(usuario, processo) and atribuir_se_preciso(processo):
        processo.save(update_fields=['numero_relatorio'])
        alteracoes += 1
    elif processo.numero_relatorio:
        registrar_relatorio(processo)
    return alteracoes
