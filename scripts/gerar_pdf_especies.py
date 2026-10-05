"""Gera PDF com espécies, grupos de análise e sequências de relatório."""

from collections import defaultdict
from datetime import date
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle, KeepTogether,
)

# Fonte: migrations/0016 + 0029 Contabilidade
ESPECIES_POR_GRUPO = {
    'LIQUIDACOES': {
        'rotulo': 'Liquidações',
        'descricao': 'Fila de análise de Liquidações. Podem gerar número de relatório.',
        'especies': [
            'Pagamento Geral',
            'Concessão Aux. Bolsa Atleta',
            'P.C. Bolsa Atleta',
            'Concessão Aux. Aluguel Social',
            'Concessão Adiantamento',
            'P.C. Adiantamento',
            'Subvenção Social - Concessão',
            'Subvenção Social - Pagamento',
            'Subvenção Social - Prestação de Contas',
            'Subvenção Social - P.C. Anual',
            'Subvenção Social - Renovação',
            'Subvenção Bloco Carnaval',
            'P.C. Subvenção Bloco Carnaval',
            'Concessão Diária',
            'P.C. Patrocínio',
            'Reanálise',
        ],
    },
    'LICITACOES_E_CONTRATOS': {
        'rotulo': 'Licitações e Contratos',
        'descricao': 'Fila de análise de Licitações e Contratos. Não geram número de relatório.',
        'especies': [
            'Análise Fase Inicial',
            'Análise Fase Externa',
            'Dispensa - Análise Fase Externa',
            'Inexigibilidade',
            'Adesão de Ata',
            'Concessão Patrocínio',
            'Análise Aditivo',
            'Reanálise',
        ],
    },
    'CONTABILIDADE': {
        'rotulo': 'Contabilidade',
        'descricao': 'Fora das filas de analistas. Processos vão para a aba Processos CGM.',
        'especies': [
            'Contabilidade',
        ],
    },
}

# Fonte: processos_app/services/relatorios.py (SEQUENCIAS)
SEQUENCIAS = [
    {
        'nome': 'Liquidação',
        'codigo': 'LIQUIDACOES',
        'especies': ['Pagamento Geral', 'Reanálise'],
    },
    {
        'nome': 'Adiantamento',
        'codigo': 'ADIANTAMENTO',
        'especies': ['Concessão Adiantamento', 'P.C. Adiantamento'],
    },
    {
        'nome': 'Cota Patrocínio',
        'codigo': 'COTA_PATROCINIO',
        'especies': ['Concessão Patrocínio', 'P.C. Patrocínio'],
    },
    {
        'nome': 'Subvenção',
        'codigo': 'SUBVENCAO',
        'especies': [
            'Subvenção Social - Concessão',
            'Subvenção Social - Pagamento',
            'Subvenção Social - Prestação de Contas',
            'Subvenção Social - P.C. Anual',
            'Subvenção Social - Renovação',
        ],
    },
    {
        'nome': 'Aluguel Social',
        'codigo': 'ALUGUEL_SOCIAL',
        'especies': ['Concessão Aux. Aluguel Social'],
    },
    {
        'nome': 'Bolsa Atleta',
        'codigo': 'BOLSA_ATLETA',
        'especies': ['Concessão Aux. Bolsa Atleta', 'P.C. Bolsa Atleta'],
    },
    {
        'nome': 'Auxílio Competição',
        'codigo': 'AUXILIO_COMPETICAO',
        'especies': [
            'Concessão Aux. Competição',
            'P.C. Aux. Competição',
        ],
    },
    {
        'nome': 'Diária',
        'codigo': 'DIARIA',
        'especies': ['Concessão Diária'],
    },
    {
        'nome': 'Blocos carnavalescos',
        'codigo': 'BLOCOS_CARNAVALESCOS',
        'especies': ['Subvenção Bloco Carnaval', 'P.C. Subvenção Bloco Carnaval'],
    },
]

MONITORAMENTO = {
    'P.C. Bolsa Atleta': 'Semestral',
    'P.C. Adiantamento': 'Trimestral',
    'Subvenção Social - Prestação de Contas': 'Quadrimestral',
    'Subvenção Social - P.C. Anual': 'Anual',
    'P.C. Subvenção Bloco Carnaval': 'Trimestral',
    'P.C. Patrocínio': 'Trimestral',
    'Concessão Aux. Bolsa Atleta': 'Trimestral',
    'Concessão Aux. Aluguel Social': 'Trimestral',
    'Concessão Adiantamento': 'Trimestral',
    'Subvenção Social - Concessão': 'Trimestral',
    'Concessão Diária': 'Trimestral',
    'Concessão Patrocínio': 'Trimestral',
}


def _styles():
    base = getSampleStyleSheet()
    return {
        'titulo': ParagraphStyle(
            'Titulo', parent=base['Heading1'], fontSize=16,
            alignment=TA_CENTER, spaceAfter=6, textColor=colors.HexColor('#0f172a')),
        'subtitulo': ParagraphStyle(
            'Subtitulo', parent=base['Normal'], fontSize=9,
            alignment=TA_CENTER, textColor=colors.HexColor('#64748b'), spaceAfter=16),
        'h2': ParagraphStyle(
            'H2', parent=base['Heading2'], fontSize=12,
            textColor=colors.HexColor('#1e3a5f'), spaceBefore=14, spaceAfter=6),
        'h3': ParagraphStyle(
            'H3', parent=base['Heading3'], fontSize=10,
            textColor=colors.HexColor('#334155'), spaceBefore=8, spaceAfter=4),
        'corpo': ParagraphStyle(
            'Corpo', parent=base['Normal'], fontSize=9,
            textColor=colors.HexColor('#334155'), leading=12, spaceAfter=4),
        'celula': ParagraphStyle(
            'Celula', parent=base['Normal'], fontSize=8.5,
            textColor=colors.HexColor('#1e293b'), leading=11),
        'rodape': ParagraphStyle(
            'Rodape', parent=base['Normal'], fontSize=8,
            alignment=TA_CENTER, textColor=colors.HexColor('#94a3b8')),
    }


def _tabela(cabecalho, linhas, col_widths):
    data = [cabecalho] + linhas
    tabela = Table(data, colWidths=col_widths, repeatRows=1)
    tabela.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e3a5f')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 8.5),
        ('FONTSIZE', (0, 1), (-1, -1), 8.5),
        ('BACKGROUND', (0, 1), (-1, -1), colors.white),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1),
         [colors.white, colors.HexColor('#f8fafc')]),
        ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#cbd5e1')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    return tabela


def mapa_especie_para_sequencia():
    mapa = {}
    for seq in SEQUENCIAS:
        for nome in seq['especies']:
            mapa[nome] = seq['nome']
    return mapa


def gerar(destino: Path):
    styles = _styles()
    doc = SimpleDocTemplate(
        str(destino),
        pagesize=A4,
        leftMargin=1.6 * cm,
        rightMargin=1.6 * cm,
        topMargin=1.4 * cm,
        bottomMargin=1.4 * cm,
        title='Espécies e grupos — Sistema Protocolo CGM',
    )
    story = []
    hoje = date.today().strftime('%d/%m/%Y')

    story.append(Paragraph('Sistema Protocolo CGM', styles['titulo']))
    story.append(Paragraph(
        f'Relação de espécies, grupos de análise e sequências de relatório · {hoje}',
        styles['subtitulo']))

    story.append(Paragraph('1. Grupos de análise', styles['h2']))
    story.append(Paragraph(
        'Cada espécie pertence a um grupo. O grupo define a fila do analista '
        '(ou o isolamento na aba Processos CGM, no caso de Contabilidade).',
        styles['corpo']))

    especie_seq = mapa_especie_para_sequencia()
    total = 0
    for codigo, info in ESPECIES_POR_GRUPO.items():
        bloco = []
        bloco.append(Paragraph(
            f"{info['rotulo']} <font color='#64748b'>({codigo})</font>",
            styles['h3']))
        bloco.append(Paragraph(info['descricao'], styles['corpo']))
        linhas = []
        for i, nome in enumerate(info['especies'], 1):
            total += 1
            mon = MONITORAMENTO.get(nome, '—')
            seq = especie_seq.get(nome, '—') if codigo == 'LIQUIDACOES' else 'Não se aplica'
            if codigo == 'LICITACOES_E_CONTRATOS' and nome == 'Concessão Patrocínio':
                seq = 'Cota Patrocínio (quando houver relatório)'
            linhas.append([
                str(i),
                Paragraph(nome, styles['celula']),
                Paragraph(mon, styles['celula']),
                Paragraph(seq, styles['celula']),
            ])
        bloco.append(_tabela(
            ['#', 'Espécie', 'Monitoramento', 'Sequência de relatório'],
            linhas,
            [0.8 * cm, 8.2 * cm, 3.2 * cm, 5.0 * cm],
        ))
        story.append(KeepTogether(bloco))

    story.append(Paragraph('2. Sequências de numeração de relatório', styles['h2']))
    story.append(Paragraph(
        'Dentro de Liquidações, a espécie determina a sequência numérica '
        'usada no Controle de relatório. O administrador pode ajustar a '
        'sequência de um processo pontualmente.',
        styles['corpo']))

    linhas_seq = []
    for seq in SEQUENCIAS:
        especies = ', '.join(seq['especies']) if seq['especies'] else (seq.get('obs') or '—')
        linhas_seq.append([
            Paragraph(seq['nome'], styles['celula']),
            Paragraph(seq['codigo'], styles['celula']),
            Paragraph(especies, styles['celula']),
        ])
    story.append(_tabela(
        ['Sequência', 'Código', 'Espécies vinculadas'],
        linhas_seq,
        [3.8 * cm, 4.0 * cm, 9.4 * cm],
    ))

    # Resumo inverso: espécie -> grupo + sequência
    story.append(Paragraph('3. Índice por espécie', styles['h2']))
    story.append(Paragraph(
        'Visão consolidada: para cada espécie, o grupo de análise e, quando '
        'couber, a sequência de relatório.',
        styles['corpo']))

    indice = []
    for codigo, info in ESPECIES_POR_GRUPO.items():
        for nome in info['especies']:
            indice.append((nome, info['rotulo'], codigo))
    indice.sort(key=lambda x: x[0].casefold())

    linhas_idx = []
    for i, (nome, grupo_rotulo, codigo) in enumerate(indice, 1):
        seq = especie_seq.get(nome, '—')
        if codigo != 'LIQUIDACOES':
            seq = '—'
        linhas_idx.append([
            str(i),
            Paragraph(nome, styles['celula']),
            Paragraph(grupo_rotulo, styles['celula']),
            Paragraph(seq, styles['celula']),
        ])
    story.append(_tabela(
        ['#', 'Espécie', 'Grupo de análise', 'Sequência de relatório'],
        linhas_idx,
        [0.8 * cm, 8.0 * cm, 4.2 * cm, 4.2 * cm],
    ))

    story.append(Spacer(1, 16))
    story.append(Paragraph(
        f'Total de espécies: {total} · Documento gerado a partir do cadastro do sistema.',
        styles['rodape']))

    doc.build(story)
    return destino


if __name__ == '__main__':
    saida = Path(__file__).resolve().parents[1] / 'especies_e_grupos.pdf'
    # Prefer Desktop if available
    desktop = Path.home() / 'Desktop' / 'especies_e_grupos_protocolo_cgm.pdf'
    destino = desktop if desktop.parent.exists() else saida
    path = gerar(destino)
    print(path)
