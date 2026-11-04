"""Compara ativos do sistema x controle do Protocolo.

Só considera o mesmo processo quando coincidem:
nº do processo + volume + data de entrada.
"""
from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from datetime import date, datetime, time
from pathlib import Path

import openpyxl

SYS = Path(r'c:\Users\LENOVO\Downloads\processos_ativos_2026-10-08.xlsx')
PROT = Path(r'c:\Users\LENOVO\Downloads\2026 - CONTROLE PROCESSUAL - PARA PROTOCOLO.xlsx')
OUT_TXT = Path(r'c:\Users\LENOVO\Downloads\divergencias_ativos_ja_sairam.txt')
OUT_XLSX = Path(r'c:\Users\LENOVO\Downloads\divergencias_ativos_ja_sairam.xlsx')


def _sem_acento(texto: str) -> str:
    bruto = unicodedata.normalize('NFKD', texto)
    return ''.join(c for c in bruto if not unicodedata.combining(c))


def norm_proc(v) -> str:
    if v is None:
        return ''
    if isinstance(v, float) and v.is_integer():
        s = str(int(v))
    else:
        s = str(v).strip()
    return s.upper().replace(' ', '')


def parse_data(v) -> date | None:
    if v is None or v == '':
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    if isinstance(v, (int, float)):
        # serial Excel inválido / lixo
        return None
    s = str(v).strip()
    for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y', '%d/%m/%y'):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _expandir_trecho(trecho: str) -> set[str]:
    """Converte '1', '1AO5', '4E5', '6494/2022' em tokens normalizados."""
    trecho = trecho.strip()
    if not trecho:
        return set()
    if trecho in {'UNICO', 'U'}:
        return {'UNICO'}
    # faixa: 1AO5 / 1A5
    m = re.fullmatch(r'(\d+)\s*A(?:O)?\s*(\d+)', trecho)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        if a > b:
            a, b = b, a
        if b - a > 40:
            return {trecho}
        return {str(n) for n in range(a, b + 1)}
    # número puro / com zero à esquerda
    if re.fullmatch(r'\d+', trecho):
        return {str(int(trecho))}
    return {trecho}


def norm_vol_chave(v) -> frozenset[str]:
    """Chave comparável de volume (conjunto de partes)."""
    if v is None or str(v).strip() == '':
        return frozenset()
    if isinstance(v, float) and v.is_integer():
        texto = str(int(v))
    elif isinstance(v, int):
        texto = str(v)
    else:
        texto = str(v).strip()
    texto = _sem_acento(texto).upper()
    texto = texto.replace('+', ' ')
    # "APENSO", etc. removidos do match de volume numérico
    texto = re.sub(r'\bAPENSO\b', ' ', texto)
    texto = re.sub(r'\s+', ' ', texto).strip()
    if texto in {'UNICO', 'VOLUME UNICO', 'VOL UNICO'}:
        return frozenset({'UNICO'})
    # separadores: e / E / , / ; / -
    partes = re.split(r'\s*(?:E|,|;|/|\s+E\s+)\s*', texto)
    # também "1 AO 5" pode ter ficado inteiro se não tinha "E"
    tokens: set[str] = set()
    for parte in partes:
        parte = parte.strip()
        if not parte:
            continue
        # "1 AO 5" com espaços
        m = re.fullmatch(r'(\d+)\s+A(?:O)?\s+(\d+)', parte)
        if m:
            tokens |= _expandir_trecho(f'{m.group(1)}AO{m.group(2)}')
            continue
        # "1AO5" colado
        tokens |= _expandir_trecho(parte.replace(' ', ''))
    # volumes tipo processo origem "6494/2022" — se split por / quebrou, remontar
    if '/' in str(v) and not any('/' in t for t in tokens):
        # reconstituir se era um único token tipo A/B
        bruto = _sem_acento(str(v)).upper().replace(' ', '')
        if re.fullmatch(r'\d+/\d+', bruto):
            return frozenset({bruto})
    return frozenset(tokens)


def vols_iguais(a, b) -> bool:
    ka, kb = norm_vol_chave(a), norm_vol_chave(b)
    if not ka or not kb:
        return False
    return ka == kb


def saida_preenchida(v) -> bool:
    if v is None:
        return False
    if isinstance(v, (datetime, date, time)):
        return True
    s = str(v).strip()
    if not s or s in ('-', '—', 'N/A', 'NA'):
        return False
    if s.startswith('#'):
        return False
    # datas texto
    if parse_data(s) is not None:
        return True
    return bool(re.search(r'\d', s))


def fmt_saida(v) -> str:
    d = parse_data(v)
    if d:
        return d.strftime('%d/%m/%Y')
    if v is None:
        return ''
    return str(v).strip()


def fmt_hora(v) -> str:
    if v is None:
        return ''
    if isinstance(v, datetime):
        return v.strftime('%H:%M')
    if isinstance(v, time):
        return v.strftime('%H:%M')
    return str(v).strip()


def main():
    wb_s = openpyxl.load_workbook(SYS, data_only=True)
    ws_s = wb_s.active
    sistema = []
    for r in range(2, ws_s.max_row + 1):
        num = ws_s.cell(r, 1).value
        if not num:
            continue
        sistema.append({
            'num': norm_proc(num),
            'num_raw': str(num).strip(),
            'vol_raw': ws_s.cell(r, 2).value or '',
            'vol_key': norm_vol_chave(ws_s.cell(r, 2).value),
            'entrada': parse_data(ws_s.cell(r, 4).value),
            'entrada_raw': ws_s.cell(r, 4).value,
            'hora': ws_s.cell(r, 5).value or '',
            'situacao': ws_s.cell(r, 6).value or '',
            'analista': ws_s.cell(r, 7).value or '',
            'sec': ws_s.cell(r, 3).value or '',
            'especie': ws_s.cell(r, 10).value or '',
            'objeto': (ws_s.cell(r, 11).value or '')[:140],
        })

    wb_p = openpyxl.load_workbook(PROT, data_only=True)
    ws = wb_p['CONTROLE PROCESSUAL']
    prot_by_num = defaultdict(list)
    for r in range(3, ws.max_row + 1):
        num = ws.cell(r, 2).value
        if not num:
            continue
        if isinstance(num, float) and num.is_integer():
            num_raw = str(int(num))
        else:
            num_raw = str(num).strip()
        saida = ws.cell(r, 7).value
        item = {
            'row': r,
            'num': norm_proc(num),
            'num_raw': num_raw,
            'vol_raw': ws.cell(r, 3).value or '',
            'vol_key': norm_vol_chave(ws.cell(r, 3).value),
            'entrada': parse_data(ws.cell(r, 5).value),
            'entrada_raw': ws.cell(r, 5).value,
            'saida': saida,
            'saida_fmt': fmt_saida(saida),
            'hora_saida': fmt_hora(ws.cell(r, 8).value),
            'destino': ws.cell(r, 9).value or '',
            'tem_saida': saida_preenchida(saida),
        }
        prot_by_num[item['num']].append(item)

    certos = []  # num + vol + entrada + saida
    so_num_entrada = []  # num+entrada, vol diferente, com saida
    so_num_vol = []  # num+vol, entrada diferente, com saida
    sem_match = []
    ainda_abertos = []  # match completo sem saida
    sem_linha = []

    for s in sistema:
        if not s['entrada'] or not s['vol_key']:
            # sem chave completa no sistema — não afirma saída
            cands = prot_by_num.get(s['num'], [])
            if not cands:
                sem_linha.append(s)
            else:
                sem_match.append((s, 'sistema sem volume/data completa'))
            continue

        cands = prot_by_num.get(s['num'], [])
        if not cands:
            sem_linha.append(s)
            continue

        exatamente = [
            c for c in cands
            if c['entrada'] == s['entrada'] and c['vol_key'] == s['vol_key']
        ]
        if exatamente:
            com_saida = [c for c in exatamente if c['tem_saida']]
            if com_saida:
                # pega a saída mais recente se houver duplicata
                def sk(c):
                    d = parse_data(c['saida'])
                    return d or date.min
                certos.append((s, sorted(com_saida, key=sk, reverse=True)[0]))
            else:
                ainda_abertos.append((s, exatamente[0]))
            continue

        # diagnósticos (não contam como certeza)
        mesma_entrada = [
            c for c in cands
            if c['entrada'] == s['entrada'] and c['tem_saida']
        ]
        mesmo_vol = [
            c for c in cands
            if c['vol_key'] == s['vol_key'] and c['tem_saida']
        ]
        if mesma_entrada:
            so_num_entrada.append((s, mesma_entrada[0]))
        elif mesmo_vol:
            so_num_vol.append((s, mesmo_vol[0]))
        else:
            sem_match.append((s, 'sem linha com mesmo volume+entrada'))

    lines = [
        'PROCESSOS ATIVOS NO SISTEMA QUE JA SAIRAM NO PROTOCOLO',
        '(certeza = mesmo Nº + VOLUME + DATA DE ENTRADA)',
        '',
        f'Total ativos no sistema: {len(sistema)}',
        f'CERTEZA — já saíram no protocolo: {len(certos)}',
        f'Mesmo nº+entrada, volume diferente (não contados): {len(so_num_entrada)}',
        f'Mesmo nº+volume, entrada diferente (não contados): {len(so_num_vol)}',
        f'Match completo e ainda SEM saída no protocolo: {len(ainda_abertos)}',
        f'Sem linha no controle do protocolo: {len(sem_linha)}',
        f'Sem match utilizável: {len(sem_match)}',
        '=' * 110,
    ]
    for i, (s, p) in enumerate(sorted(certos, key=lambda x: (x[0]['entrada'] or date.min, x[0]['num'])), 1):
        ent = s['entrada'].strftime('%d/%m/%Y') if s['entrada'] else '?'
        lines.append(
            f"{i:3}. {s['num_raw']:16} vol={str(s['vol_raw'])[:14]:14} "
            f"entrada={ent} | sistema: {s['situacao'][:26]:26} "
            f"| SAÍDA protocolo={p['saida_fmt']:10} {p['hora_saida']:5} "
            f"→ {str(p['destino'])[:22]:22} | {s['objeto']}"
        )

    if so_num_entrada:
        lines += ['', '--- Mesmo nº e entrada, VOLUME diferente (revisar manual) ---']
        for s, p in so_num_entrada:
            ent = s['entrada'].strftime('%d/%m/%Y') if s['entrada'] else '?'
            lines.append(
                f"  · {s['num_raw']} entrada={ent} "
                f"vol sistema={s['vol_raw']!r} vs protocolo={p['vol_raw']!r} "
                f"saída={p['saida_fmt']}"
            )

    if so_num_vol:
        lines += ['', '--- Mesmo nº e volume, ENTRADA diferente (revisar manual) ---']
        for s, p in so_num_vol:
            ent_s = s['entrada'].strftime('%d/%m/%Y') if s['entrada'] else '?'
            ent_p = p['entrada'].strftime('%d/%m/%Y') if p['entrada'] else '?'
            lines.append(
                f"  · {s['num_raw']} vol={s['vol_raw']!r} "
                f"entrada sistema={ent_s} vs protocolo={ent_p} "
                f"saída={p['saida_fmt']}"
            )

    text = '\n'.join(lines)
    OUT_TXT.write_text(text, encoding='utf-8')
    print(text)
    print(f'\nArquivo texto: {OUT_TXT}')

    wb_out = openpyxl.Workbook()
    sheet = wb_out.active
    sheet.title = 'Certeza ja sairam'
    sheet.append([
        'Nº Processo', 'Volume', 'Data Entrada', 'Situação sistema', 'Analista',
        'Secretaria', 'Saída protocolo', 'Hora saída', 'Destino protocolo',
        'Espécie', 'Objeto', 'Linha protocolo',
    ])
    for s, p in sorted(certos, key=lambda x: (x[0]['entrada'] or date.min, x[0]['num'])):
        sheet.append([
            s['num_raw'], s['vol_raw'],
            s['entrada'].isoformat() if s['entrada'] else '',
            s['situacao'], s['analista'], s['sec'],
            p['saida_fmt'], p['hora_saida'], p['destino'],
            s['especie'], s['objeto'], p['row'],
        ])

    sheet2 = wb_out.create_sheet('Revisar volume')
    sheet2.append([
        'Nº Processo', 'Entrada', 'Volume sistema', 'Volume protocolo',
        'Saída protocolo', 'Destino',
    ])
    for s, p in so_num_entrada:
        sheet2.append([
            s['num_raw'],
            s['entrada'].isoformat() if s['entrada'] else '',
            s['vol_raw'], p['vol_raw'], p['saida_fmt'], p['destino'],
        ])

    sheet3 = wb_out.create_sheet('Revisar entrada')
    sheet3.append([
        'Nº Processo', 'Volume', 'Entrada sistema', 'Entrada protocolo',
        'Saída protocolo', 'Destino',
    ])
    for s, p in so_num_vol:
        sheet3.append([
            s['num_raw'], s['vol_raw'],
            s['entrada'].isoformat() if s['entrada'] else '',
            p['entrada'].isoformat() if p['entrada'] else '',
            p['saida_fmt'], p['destino'],
        ])

    wb_out.save(OUT_XLSX)
    print(f'Arquivo Excel: {OUT_XLSX}')


if __name__ == '__main__':
    main()
