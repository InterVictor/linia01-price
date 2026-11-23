#!/usr/bin/env python3
"""Разбор прайса Линия01 (lbnsk.ru, PriceRF.pdf) по координатам текста.

Прайс — PDF из Excel: страницы в 2-3 колонки «Наименование | Изм. | опт 1 | опт 2», у части позиций цена стоит в
объединённой ячейке между строками (текст по тексту без координат привязать нельзя). Поэтому разбор по геометрии (PyMuPDF).

Использование:  python parse_price_pdf.py PriceRF.pdf out.json
Выход: {source, price_date, rows:[{perechen, section, name, unit, price1, price2, page}], stats, skipped_pages}
Строки «по запросу» (без цены) в rows не попадают, их число — в stats.
"""
import json, re, sys, collections
import pymupdf as fitz

PR = re.compile(r'^\d[\d\s]*р\.?$')
ZAP = re.compile(r'^по\s*запросу$', re.I)
STOP = {'и', 'на', 'для', 'из', 'с', 'по', 'в', 'от', 'до', 'или'}
MONTHS = {'января': 1, 'февраля': 2, 'марта': 3, 'апреля': 4, 'мая': 5, 'июня': 6, 'июля': 7, 'августа': 8,
          'сентября': 9, 'октября': 10, 'ноября': 11, 'декабря': 12}


def is_unit(t):
    return (2 <= len(t) <= 8 and re.fullmatch(r'[а-яё./]+', t) is not None and t not in STOP
            and not ZAP.match(t))


def spans_of(page):
    out = []
    for b in page.get_text('dict')['blocks']:
        for ln in b.get('lines', []):
            for s in ln['spans']:
                t = s['text'].replace(' ', ' ').strip()
                if t:
                    out.append(dict(t=t, x0=s['bbox'][0], x1=s['bbox'][2], yc=(s['bbox'][1] + s['bbox'][3]) / 2))
    return out


def lines_of(spans, tol=1.6):
    lines = []
    for s in sorted(spans, key=lambda s: s['yc']):
        if lines and abs(lines[-1]['y'] - s['yc']) <= tol:
            lines[-1]['s'].append(s)
            lines[-1]['y'] = sum(x['yc'] for x in lines[-1]['s']) / len(lines[-1]['s'])
        else:
            lines.append(dict(y=s['yc'], s=[s]))
    for ln in lines:
        ln['s'].sort(key=lambda s: s['x0'])
    return lines


def merge_line(S):
    out = []
    for s in S:
        if out and s['x0'] - out[-1]['x1'] < 0.9 and not PR.match(s['t']) and not PR.match(out[-1]['t']):
            out[-1] = dict(t=out[-1]['t'] + s['t'], x0=out[-1]['x0'], x1=s['x1'], yc=out[-1]['yc'])
        else:
            out.append(dict(s))
    return out


def block_id(x0, opt1):
    best = None
    for i, o in enumerate(opt1):
        if o - 48 <= x0 <= o + 6 and (best is None or abs(x0 - o) < abs(x0 - opt1[best])):
            best = i
    return best


def price_int(t):
    return int(re.sub(r'\D', '', t))


def parse_page(page):
    sp = spans_of(page)
    opt1 = sorted({round(s['x0']) for s in sp if re.fullmatch(r'опт\s*1', s['t'])})
    if not opt1:
        return None
    # левая граница блока k = правый край колонок «Изм./опт» блока k-1 (так заголовки левого блока не липнут к правому)
    left = [-1e9]
    for k in range(1, len(opt1)):
        xs = [s['x1'] for s in sp if opt1[k - 1] - 8 <= s['x0'] <= opt1[k - 1] + 62
              and (PR.match(s['t']) or ZAP.match(s['t']))]
        left.append((max(xs) if xs else opt1[k - 1] + 58) + 0.3)

    def blk(x0):
        b = 0
        for k, lb in enumerate(left):
            if x0 >= lb:
                b = k
        return b

    rows, lone, heads = [], [], []
    for ln in lines_of(sp):
        groups = collections.defaultdict(list)
        for s in merge_line(ln['s']):
            groups[blk(s['x0'])].append(s)
        for b, S in groups.items():
            buf, i = [], 0
            while i < len(S):
                s = S[i]
                t = s['t']
                is_u = is_unit(t) and opt1[b] - 48 <= s['x0'] <= opt1[b] + 6
                inline = PR.match(t) or ZAP.match(t)
                if is_u or inline:
                    if not is_u and not buf:  # одинокая цена (объединённая ячейка)
                        lone.append(dict(y=ln['y'], b=b, t=t))
                        i += 1
                        continue
                    r = dict(name=' '.join(x['t'] for x in buf), unit=t if is_u else '', y=ln['y'], b=b, prices=[], zap=False)
                    if is_u:
                        i += 1
                    buf = []
                    while i < len(S) and (PR.match(S[i]['t']) or ZAP.match(S[i]['t'])):
                        if ZAP.match(S[i]['t']):
                            r['zap'] = True
                        else:
                            r['prices'].append(price_int(S[i]['t']))
                        i += 1
                    rows.append(r)
                    continue
                buf.append(s)
                i += 1
            if buf:
                heads.append(dict(y=ln['y'], b=b, t=' '.join(x['t'] for x in buf)))
    cells = []
    for p in sorted(lone, key=lambda p: (p['b'], -p['y'])):
        if cells and cells[-1]['b'] == p['b'] and abs(cells[-1]['y'] - p['y']) < 1.6 and not cells[-1]['zap'] and not ZAP.match(p['t']):
            cells[-1]['v'].append(p['t'])
        else:
            cells.append(dict(b=p['b'], y=p['y'], v=[p['t']], zap=bool(ZAP.match(p['t']))))
    for r in rows:  # строка с ценой, но без названия на своей линии: берём ближайший текст этого же блока
        if not r['name']:
            near = [h for h in heads if h['b'] == r['b'] and abs(h['y'] - r['y']) <= 9]
            if near:
                r['name'] = min(near, key=lambda h: (abs(h['y'] - r['y']), h['y'] > r['y']))['t']
    rows = [r for r in rows if r['name']]
    waiting = [r for r in rows if not r['prices'] and not r['zap'] and r['unit']]
    for r in waiting:
        cs = [c for c in cells if c['b'] == r['b']]
        if not cs:
            continue
        c = min(cs, key=lambda c: abs(c['y'] - r['y']))
        if abs(c['y'] - r['y']) <= 9:
            c['used'] = True
            if c['zap']:
                r['zap'] = True
            else:
                r['prices'] = [price_int(v) for v in c['v']]
    unused = [c for c in cells if not c.get('used')]
    return opt1, rows, unused


UNIT_TAIL = re.compile(r'(?<=\S)(шт\.?|компл\.?|скат|пара|кг\.?|меш\.?|м\.п\.)$')


def clean_row(name, unit):
    """Название в едином виде + ключ без пробелов (не зависит от версии библиотеки), прилипшая к названию единица отделяется."""
    name = re.sub(r'\s+', ' ', name).strip()
    if not unit:
        m = UNIT_TAIL.search(name)
        if m:
            unit, name = m.group(1), name[:m.start()].rstrip()
    return name, re.sub(r'\s+', '', name), unit


def parse_pdf(path):
    doc = fitz.open(path)
    rows_out, stats, skipped = [], collections.Counter(), []
    perechen, last_num, seq = '', None, collections.Counter()
    price_date, price_date_text = None, None
    noprice = []
    for pi, page in enumerate(doc, 1):
        txt = page.get_text()
        m = re.search(r'(\d{1,2})\s*(' + '|'.join(MONTHS) + r')\s*(\d{4})', txt.replace('\n', ' '))
        if m and not price_date and m.group(2) in MONTHS:
            price_date = '%s-%02d-%02d' % (m.group(3), MONTHS[m.group(2)], int(m.group(1)))
            price_date_text = m.group(0)
        mp = re.search(r'Перечень\s*№\s*(\d+)', txt)
        if mp:
            n = mp.group(1)
            if n != last_num:
                seq[n] += 1
                last_num = n
            perechen = 'Перечень № %s' % n + (' (часть %d)' % seq[n] if seq[n] > 1 else '')
        res = parse_page(page)
        if res is None:
            skipped.append(pi)
            continue
        opt1, rows, unused = res
        stats['unused_price_cells'] += len(unused)
        for r in rows:
            stats['rows'] += 1
            if r['prices']:
                stats['priced'] += 1
                p = (r['prices'] + [None] * 4)[:4]
                name, key, unit = clean_row(r['name'], r['unit'])
                rows_out.append(dict(perechen=perechen, name=name, key=key, unit=unit, price1=p[0], price2=p[1],
                                     price3=p[2], price4=p[3], page=pi))
            elif r['zap']:
                stats['po_zaprosu'] += 1
            else:
                stats['no_price'] += 1
                noprice.append((pi, r['name'][:60]))
    return dict(source='linia01', price_date=price_date, price_date_text=price_date_text, pages=len(doc),
                skipped_pages=skipped, stats=dict(stats), no_price_sample=noprice[:40], rows=rows_out)


if __name__ == '__main__':
    data = parse_pdf(sys.argv[1])
    with open(sys.argv[2], 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    print(json.dumps({k: v for k, v in data.items() if k != 'rows'}, ensure_ascii=False), 'rows:', len(data['rows']))
