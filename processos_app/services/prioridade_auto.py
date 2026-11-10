# processos_app/services/prioridade_auto.py
"""Detecta prioridade na entrada por palavras-chave (listas da CGM)."""

import re
import unicodedata

from django.db import DatabaseError

from .prazos import SO_DESTA_ENTRADA

# Ordem de precedência: urgente > obras > recorrente > normal.
PRECEDENCIA = ('URGENTE', 'PRIORITARIO', 'RECORRENTE', 'NORMAL')


def _normalizar(texto):
    bruto = unicodedata.normalize('NFKD', str(texto or ''))
    sem_acento = ''.join(c for c in bruto if not unicodedata.combining(c))
    return re.sub(r'\s+', ' ', sem_acento.casefold()).strip()


def _termos(bloco):
    """[(termo_normalizado, texto_original), ...] — longos primeiro."""
    pares = []
    for linha in str(bloco or '').splitlines():
        original = linha.strip()
        termo = _normalizar(original)
        if termo:
            pares.append((termo, original))
    pares.sort(key=lambda item: len(item[0]), reverse=True)
    return pares


def _contem(haystack, termo):
    if not haystack or not termo:
        return False
    # Termos curtos (siglas) exigem limite de palavra.
    if len(termo) <= 3:
        return re.search(
            rf'(^|[^a-z0-9]){re.escape(termo)}([^a-z0-9]|$)', haystack
        ) is not None
    return termo in haystack


def texto_do_processo(dados):
    """Campos da entrada usados na detecção."""
    partes = [
        dados.get('contratada'),
        dados.get('objeto'),
        dados.get('secretaria'),
        dados.get('numero_processo'),
    ]
    return _normalizar(' '.join(str(p or '') for p in partes))


def _mapa_palavras():
    """{codigo: [(termo, original), ...]} das prioridades ativas."""
    try:
        from ..models import Prioridade
        linhas = Prioridade.objects.filter(ativo=True).values_list(
            'codigo', 'palavras_chave')
    except DatabaseError:
        return {}
    return {
        codigo: _termos(palavras)
        for codigo, palavras in linhas
        if (palavras or '').strip()
    }


def detectar_codigo(dados):
    """Devolve o código da prioridade detectada, ou None."""
    achado = sugerir(dados)
    return achado['codigo'] if achado else None


def sugerir(dados):
    """Devolve {codigo, nome, termo, prazo_dias} ou None."""
    haystack = texto_do_processo(dados)
    if not haystack:
        return None
    try:
        from ..models import Prioridade
        prioridades = {
            p.codigo: p
            for p in Prioridade.objects.filter(ativo=True)
        }
    except DatabaseError:
        prioridades = {}
    mapa = {
        codigo: _termos(getattr(prio, 'palavras_chave', ''))
        for codigo, prio in prioridades.items()
        if (getattr(prio, 'palavras_chave', None) or '').strip()
    }
    for codigo in PRECEDENCIA:
        if codigo in SO_DESTA_ENTRADA:
            continue
        for termo, original in mapa.get(codigo, ()):
            if not _contem(haystack, termo):
                continue
            prio = prioridades.get(codigo)
            return {
                'codigo': codigo,
                'nome': prio.nome if prio else codigo,
                'termo': original,
                'prazo_dias': prio.prazo_dias if prio else None,
            }
    return None


# Ordem do PDF: urgente, obras e recorrentes (as que entram automático).
SECOES_EMPRESAS = (
    ('URGENTE', 'Urgente'),
    ('PRIORITARIO', 'Prioridade de obras'),
    ('RECORRENTE', 'Prioridade recorrente'),
)


def _chave_empresa(termo):
    """Junta variantes do mesmo nome (ex.: M. COSTA e M COSTA)."""
    return re.sub(r'[^a-z0-9]+', ' ', termo).strip()


def _empresas_unicas(bloco):
    """Lista limpa: uma empresa por termo, sem variantes iguais (acento/espaço)."""
    unicas = {}
    for termo, original in _termos(bloco):
        chave = _chave_empresa(termo)
        if not chave:
            continue
        atual = unicas.get(chave)
        # Prefere a grafia mais completa (com ponto/acento).
        if atual is None or len(original) > len(atual[1]):
            unicas[chave] = (chave, original)
    return [item[1] for item in sorted(unicas.values(), key=lambda item: item[0])]


def listar_empresas_automaticas():
    """Empresas/termos que disparam prioridade automática na entrada."""
    try:
        from ..models import Prioridade
        por_codigo = {
            p.codigo: p
            for p in Prioridade.objects.filter(
                codigo__in=[codigo for codigo, _ in SECOES_EMPRESAS],
                ativo=True,
            )
        }
    except DatabaseError:
        return []

    secoes = []
    for codigo, rotulo in SECOES_EMPRESAS:
        prio = por_codigo.get(codigo)
        if not prio:
            continue
        secoes.append({
            'codigo': codigo,
            'nome': prio.nome or rotulo,
            'prazo_dias': prio.prazo_dias,
            'empresas': _empresas_unicas(prio.palavras_chave),
        })
    return secoes


def _periodo_do_processo(processo):
    """Período gravado na análise do processo (campo do processo ou da planilha)."""
    from django.core.exceptions import ObjectDoesNotExist

    periodo = (processo.periodo or '').strip()
    if periodo:
        return periodo
    try:
        linha = processo.linha_relatorio
    except ObjectDoesNotExist:
        return ''
    return (linha.periodo or '').strip()


def _score_ultima_analise(processo):
    """Ordena pelo processo com análise mais recente daquela empresa."""
    from datetime import date
    tem_periodo = 1 if _periodo_do_processo(processo) else 0
    return (
        tem_periodo,
        processo.data_analise or date.min,
        processo.data_entrada or date.min,
        processo.id or 0,
    )


def _candidatos_empresas():
    try:
        from ..models import Processo
        return list(
            Processo.objects
            .filter(cancelado_em__isnull=True)
            .exclude(contratada='')
            .select_related('linha_relatorio')
            .only(
                'id', 'numero_processo', 'contratada', 'prioridade', 'periodo',
                'data_analise', 'data_entrada',
                'linha_relatorio__periodo',
            )
        )
    except DatabaseError:
        return []


def _processo_da_empresa(empresa, candidatos):
    termo = _normalizar(empresa)
    if not termo:
        return None
    matches = [
        processo for processo in candidatos
        if _contem(_normalizar(processo.contratada), termo)
    ]
    if not matches:
        return None
    return max(matches, key=_score_ultima_analise)


def listar_empresas_com_ultima_analise():
    """Por empresa automática: último processo encontrado e o período da análise."""
    candidatos = _candidatos_empresas()
    secoes = []
    for secao in listar_empresas_automaticas():
        linhas = []
        for empresa in secao['empresas']:
            processo = _processo_da_empresa(empresa, candidatos)
            if processo is None:
                linhas.append({
                    'empresa': empresa,
                    'numero_processo': '',
                    'contratada': empresa,
                    'prioridade': secao['nome'],
                    'periodo': '',
                    'rotulo': (
                        f'{empresa} — {secao["nome"]} — '
                        'sem processo encontrado'
                    ),
                })
                continue
            periodo = _periodo_do_processo(processo)
            contratada = (processo.contratada or empresa).strip() or empresa
            periodo_txt = periodo or 'sem período na última análise'
            linhas.append({
                'empresa': empresa,
                'numero_processo': processo.numero_processo,
                'contratada': contratada,
                'prioridade': secao['nome'],
                'periodo': periodo,
                'rotulo': (
                    f'{processo.numero_processo} — {contratada} — '
                    f'{secao["nome"]} — {periodo_txt}'
                ),
            })
        secoes.append({
            **secao,
            'linhas': linhas,
        })
    return secoes


def gerar_pdf_empresas_automaticas(referencia=None):
    """PDF com empresas de Urgente, Obras e Recorrentes + período da última análise."""
    from io import BytesIO
    from xml.sax.saxutils import escape

    from django.utils import timezone
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.platypus import (
        Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
    )

    hoje = referencia or timezone.localdate()
    secoes = listar_empresas_com_ultima_analise()
    stream = BytesIO()
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name='CabecalhoPrio', fontName='Helvetica-Bold', fontSize=11,
        alignment=TA_CENTER, textColor=colors.HexColor('#0f2a5c'),
        spaceAfter=6, leading=14,
    ))
    styles.add(ParagraphStyle(
        name='TituloPrio', fontName='Helvetica-Bold', fontSize=14,
        alignment=TA_CENTER, textColor=colors.HexColor('#0f172a'),
        spaceBefore=8, spaceAfter=10, leading=18,
    ))
    styles.add(ParagraphStyle(
        name='IntroPrio', fontName='Helvetica', fontSize=9,
        alignment=TA_JUSTIFY, textColor=colors.HexColor('#334155'),
        spaceAfter=14, leading=13,
    ))
    styles.add(ParagraphStyle(
        name='SecaoPrio', fontName='Helvetica-Bold', fontSize=11,
        textColor=colors.HexColor('#0f2a5c'), spaceBefore=12,
        spaceAfter=6, leading=14,
    ))
    styles.add(ParagraphStyle(
        name='ItemPrio', fontName='Helvetica', fontSize=9,
        textColor=colors.HexColor('#0f172a'), leading=12,
    ))
    styles.add(ParagraphStyle(
        name='VazioPrio', fontName='Helvetica-Oblique', fontSize=9,
        textColor=colors.HexColor('#64748b'), spaceAfter=6, leading=12,
    ))

    story = [
        Paragraph(
            'PREFEITURA MUNICIPAL DE SAQUAREMA<br/>'
            'CONTROLADORIA-GERAL DO MUNICÍPIO',
            styles['CabecalhoPrio'],
        ),
        Paragraph(
            'Empresas com prioridade automática na entrada',
            styles['TituloPrio'],
        ),
        Paragraph(
            f'Emitido em {hoje:%d/%m/%Y}. Documento restrito ao administrador. '
            'Para cada empresa cadastrada em Prioridades aparece o processo '
            'mais recente encontrado e o <b>período da última análise</b> '
            '(nº do processo — contratada — prioridade — período).',
            styles['IntroPrio'],
        ),
    ]

    total = 0
    com_processo = 0
    for secao in secoes:
        prazo = secao['prazo_dias']
        prazo_txt = f' — prazo de {prazo} dia{"s" if prazo != 1 else ""}'
        story.append(Paragraph(
            f'{escape(secao["nome"])}{prazo_txt} '
            f'({len(secao["linhas"])} empresa'
            f'{"s" if len(secao["linhas"]) != 1 else ""})',
            styles['SecaoPrio'],
        ))
        if not secao['linhas']:
            story.append(Paragraph(
                'Nenhuma empresa cadastrada nesta prioridade.',
                styles['VazioPrio'],
            ))
            continue
        total += len(secao['linhas'])
        com_processo += sum(1 for linha in secao['linhas'] if linha['numero_processo'])
        linhas = [[
            Paragraph(f'{indice}.', styles['ItemPrio']),
            Paragraph(escape(linha['rotulo']), styles['ItemPrio']),
        ] for indice, linha in enumerate(secao['linhas'], start=1)]
        tabela = Table(linhas, colWidths=[28, 460])
        tabela.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
            ('TOPPADDING', (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
            ('LINEBELOW', (0, 0), (-1, -2), 0.25, colors.HexColor('#e2e8f0')),
        ]))
        story.append(tabela)

    story.append(Spacer(1, 16))
    story.append(Paragraph(
        f'Total: {total} empresa{"s" if total != 1 else ""} '
        f'({com_processo} com processo localizado). '
        'A lista de empresas segue o cadastro em Cadastros → Prioridades.',
        styles['IntroPrio'],
    ))

    def rodape(canvas, doc):
        canvas.setFont('Helvetica', 8)
        canvas.setFillColor(colors.HexColor('#64748b'))
        canvas.drawString(
            42, 26,
            'CGM Saquarema · Prioridades automáticas · uso do administrador')
        canvas.drawRightString(A4[0] - 42, 26, f'Página {doc.page}')

    SimpleDocTemplate(
        stream, pagesize=A4,
        rightMargin=42, leftMargin=42, topMargin=40, bottomMargin=48,
    ).build(story, onFirstPage=rodape, onLaterPages=rodape)
    return stream.getvalue()
