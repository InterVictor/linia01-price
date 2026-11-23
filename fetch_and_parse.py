#!/usr/bin/env python3
"""Линия01: скачать прайс для России, разобрать и сохранить в JSON (если дата прайса изменилась).

Использование:  python fetch_and_parse.py data/linia01.json [--force]
Дата прайса берётся со страницы https://lbnsk.ru/prices/ (рядом со ссылкой PriceRF.pdf, «Прайс-лист от ДД.ММ.ГГГГ»),
PDF скачивается и разбирается только если дата новая. Если разбор подозрительно мал (меньше 1000 позиций или меньше 90% от
прошлого раза) — ошибка, старый файл не перезаписывается (в GitHub Actions задание упадёт и пришлёт письмо).
Код возврата 0 — успех (в том числе «изменений нет»).
"""
import json, os, re, sys, tempfile, urllib.request, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from parse_price_pdf import parse_pdf

PAGE = 'https://lbnsk.ru/prices/'
UA = {'User-Agent': 'Mozilla/5.0 (compatible; price-monitor)'}


def get(url, binary=False):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=120) as r:
        data = r.read()
    return data if binary else data.decode('utf-8', 'replace')


def find_rf(html):
    for m in re.finditer(r'<a\b[^>]*href="([^"]*PriceRF[^"]*\.pdf[^"]*)"[^>]*>(.*?)</a>', html, re.S | re.I):
        text = re.sub(r'<[^>]+>', ' ', m.group(2))
        d = re.search(r'(\d{2})\.(\d{2})\.(\d{4})', text)
        if not d:
            raise SystemExit('На странице нет даты рядом со ссылкой PriceRF.pdf: ' + re.sub(r'\s+', ' ', text)[:200])
        href = m.group(1).replace('&amp;', '&')
        if href.startswith('/'):
            href = 'https://lbnsk.ru' + href
        return href.replace(' ', '%20'), '%s-%s-%s' % (d.group(3), d.group(2), d.group(1)), re.sub(r'\s+', ' ', text).strip()
    raise SystemExit('Ссылка на PriceRF.pdf (прайс для России) не найдена на странице ' + PAGE)


def main():
    out = sys.argv[1]
    force = '--force' in sys.argv
    url, page_date, page_text = find_rf(get(PAGE))
    old = None
    if os.path.exists(out):
        with open(out, encoding='utf-8') as f:
            old = json.load(f)
        if not force and old.get('price_date') == page_date:
            print('Дата прайса не изменилась (%s), ничего не делаем' % page_date)
            return
    pdf = get(url, binary=True)
    with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as t:
        t.write(pdf)
        path = t.name
    data = parse_pdf(path)
    os.unlink(path)
    n = len(data['rows'])
    prev = len(old['rows']) if old else 0
    if n < 1000 or (prev and n < 0.9 * prev):
        raise SystemExit('Разбор подозрительно мал: %d позиций (было %d) — файл не обновляем' % (n, prev))
    if old and not force:  # защита от смены вёрстки/версии библиотеки: ключи позиций не должны массово меняться
        ok = {(r['perechen'], r['key']) for r in old['rows']}
        nk = {(r['perechen'], r['key']) for r in data['rows']}
        overlap = len(ok & nk) / max(1, len(ok))
        if overlap < 0.75:
            raise SystemExit('Совпадает только %.0f%% ключей позиций со старым файлом — вёрстка или разбор изменились. '
                             'Проверьте вручную и запустите с force.' % (overlap * 100))
    data['price_date'] = page_date  # дата со страницы; из PDF («Действителен с») — отдельно
    data['pdf_valid_from'] = data.pop('price_date_text', None)
    data['page_text'] = page_text
    data['source_url'] = url
    data['generated_at'] = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, separators=(',', ':'))
    print('Готово: дата %s, позиций %d (было %d), по запросу %s, без цены %s, пропущены страницы %s'
          % (page_date, n, prev, data['stats'].get('po_zaprosu'), data['stats'].get('no_price'), data['skipped_pages']))


if __name__ == '__main__':
    main()
