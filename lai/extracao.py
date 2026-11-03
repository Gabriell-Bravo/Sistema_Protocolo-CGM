"""Extrator determinístico, local; resultados sempre dependem de conferência."""
import re
from datetime import datetime
from pypdf import PdfReader

def extrair(arquivo):
    reader = PdfReader(arquivo)
    if reader.is_encrypted: raise ValueError('PDF protegido. Envie cópia acessível ou cadastre manualmente.')
    if len(reader.pages) > 100: raise ValueError('PDF excede 100 páginas.')
    textos = [p.extract_text(extraction_mode='layout') for p in reader.pages]
    texto = '\n'.join(textos)
    result = {'metodo': 'pypdf-layout-v1', 'paginas': len(textos), 'teor': texto, 'avisos': [], 'anexos_esperados': []}
    nup = re.search(r'\b\d{5}\.\d{4}\.\d{6}-\d{2}\b', texto)
    if nup: result['nup'] = nup.group()
    labels = [('tipo', 'Tipo de Manifestação'), ('cadastro_falabr', 'Data de Cadastro'), ('vencimento_original', 'Data limite para resposta')]
    for key, label in labels:
        match = re.search(re.escape(label) + r'\s*:\s*([^\n]+)', texto, re.I)
        if match:
            value = match.group(1).strip()
            if key != 'tipo':
                dm = re.search(r'\d{2}/\d{2}/\d{4}', value)
                if dm:
                    try: result[key] = datetime.strptime(dm.group(), '%d/%m/%Y').date().isoformat()
                    except ValueError: pass
            else: result[key] = value
    # Recupera teor pelo layout, mantendo o original completo no PDF armazenado.
    partes = []
    for page in textos:
        start = re.search(r'\bTeor:\s*', page)
        if start:
            trecho = page[start.end():]
            trecho = re.split(r'\n\s*(?:Anexos|Local:|Proposta de melhoria:|Plataforma Integrada)', trecho)[0]
            partes.append(trecho.strip())
        elif partes and not re.search(r'Dados das Respostas|Dados de Encaminhamento', page):
            trecho = re.split(r'\n\s*(?:Local:|Proposta de melhoria:|Plataforma Integrada)', page)[0]
            partes.append(trecho.strip())
    if partes: result['teor'] = '\n\n'.join(partes)
    resumo = re.search(r'\bResumo:\s*([^\n]+)', texto)
    valor = resumo.group(1).strip() if resumo else ''
    result['resumo'] = valor if valor not in ('', '-') else ''
    if not result['resumo']:
        result['avisos'].append('Resumo ausente: redija ou revise o trecho sugerido, sem IA.')
        trecho = re.search(r'ASSUNTO:\s*(.{1,400})', result['teor'], re.S)
        result['resumo'] = re.sub(r'\s+', ' ', trecho.group(1) if trecho else result['teor'][:350])[:350]
    result['anexos_esperados'] = sorted(set(re.findall(r'[\w.-]+\.(?:jpe?g|png|pdf|docx|xlsx)', texto, re.I)))
    for key in ('nup','tipo','cadastro_falabr','vencimento_original'):
        if not result.get(key): result['avisos'].append(f'Conferir/preencher: {key}.')
    if len(texto.strip()) < 30: result['avisos'].append('PDF sem texto. OCR não instalado: cadastro manual disponível.')
    result['avisos'].append('Confira datas, teor multipágina e secretaria antes de confirmar.')
    return result
