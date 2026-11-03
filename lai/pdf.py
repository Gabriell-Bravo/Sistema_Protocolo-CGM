from io import BytesIO
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

def gerar_memorando(m):
    stream = BytesIO()
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='TextoLAI', fontName='Helvetica', fontSize=11, leading=17, spaceAfter=10))
    styles.add(ParagraphStyle(name='CabecalhoLAI', fontSize=12, alignment=TA_CENTER, textColor=colors.HexColor('#13534d'), spaceAfter=10))
    story = [Paragraph('PREFEITURA MUNICIPAL DE SAQUAREMA<br/>CONTROLADORIA-GERAL DO MUNICÍPIO', styles['CabecalhoLAI']),
        Spacer(1, 18), Paragraph(f'Memorando nº {m}', styles['Heading2']),
        Paragraph(f'Data: {m.criado_em:%d/%m/%Y}<br/>Destinatário: {escape(m.destinatario)}', styles['TextoLAI'])]
    if m.cancelado: story.append(Paragraph('DOCUMENTO CANCELADO', styles['Heading2']))
    for par in m.texto.split('\n'):
        story.append(Paragraph(escape(par) or '&#160;', styles['TextoLAI']))
    story += [Spacer(1, 24), Paragraph(escape(m.signatario).replace('\n','<br/>'), styles['TextoLAI']),
        Paragraph('Identificação do responsável. Este arquivo não contém assinatura digital certificada.', styles['Normal'])]
    def rodape(canvas, doc):
        canvas.setFont('Helvetica', 8)
        canvas.drawString(42, 26, 'LAI / CGM • Documento de tramitação interna')
        canvas.drawRightString(A4[0]-42, 26, f'Página {doc.page}')
    SimpleDocTemplate(stream, pagesize=A4, rightMargin=48, leftMargin=48, topMargin=45, bottomMargin=48).build(story, onFirstPage=rodape, onLaterPages=rodape)
    return stream.getvalue()
