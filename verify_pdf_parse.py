#!/usr/bin/env python3
"""Сверка разбора с самим PDF: python verify_pdf_parse.py PriceRF.pdf data/linia01.json
1) ни одна цена из PDF не потеряна и ни одна цена в JSON не выдумана (по страницам, мультимножества значений);
2) выборочно 60 позиций: название и цены стоят на одной строке в `pdftotext -layout` (если pdftotext установлен)."""
import collections, json, random, re, shutil, subprocess, sys
import pymupdf
from parse_price_pdf import PR, price_int, spans_of

pdf, js = sys.argv[1], sys.argv[2]
d = json.load(open(js, encoding='utf-8'))
rows = d['rows']
doc = pymupdf.open(pdf)
lost = extra = 0
for pn, page in enumerate(doc, 1):
    if pn in d.get('skipped_pages', []):
        continue
    sv = collections.Counter(price_int(s['t']) for s in spans_of(page) if PR.match(s['t']))
    rv = collections.Counter()
    for r in rows:
        if r['page'] == pn:
            for k in ('price1', 'price2', 'price3', 'price4'):
                if r.get(k) is not None:
                    rv[r[k]] += 1
    lost += sum(max(0, c - rv[v]) for v, c in sv.items())
    extra += sum(c for v, c in rv.items() if sv[v] == 0)
print('потеряно цен из PDF:', lost, '| выдумано цен:', extra)
if shutil.which('pdftotext'):
    random.seed(7)
    fmt = lambda v: f'{v:,}'.replace(',', ' ') + 'р.'
    ok = 0
    sample = random.sample(rows, min(60, len(rows)))
    for r in sample:
        txt = subprocess.run(['pdftotext', '-layout', '-f', str(r['page']), '-l', str(r['page']), pdf, '-'],
                             capture_output=True, text=True).stdout
        frag = re.sub(r'\s+', '', r['name'])[:18]
        ok += any(frag in re.sub(r'\s+', '', ln) and fmt(r['price1']) in ln for ln in txt.splitlines())
    print('выборка на одной строке с названием: %d из %d (остальные — цены в объединённых ячейках)' % (ok, len(sample)))
sys.exit(1 if lost or extra else 0)
