# linia01-price

Разбор прайс-листа «Линия 01» для России (https://lbnsk.ru/prices/, файл `PriceRF.pdf`) в JSON.

- `parse_price_pdf.py` — разбор PDF по координатам текста (PyMuPDF): колонки «Наименование | Изм. | опт 1 | опт 2», цены в объединённых ячейках.
- `fetch_and_parse.py` — находит ссылку и дату на странице, при новой дате скачивает PDF и пишет `data/linia01.json`.
- `verify_pdf_parse.py` — сверка результата с самим PDF (потерянные и выдуманные цены).
- `.github/workflows/price.yml` — GitHub Action раз в сутки.
- `data/linia01.json` — результат: `price_date`, `rows[{perechen, name, key, unit, price1..price4, page}]`.

Стабильный адрес файла: https://raw.githubusercontent.com/InterVictor/linia01-price/main/data/linia01.json

Версия PyMuPDF закреплена в `requirements.txt`: результат зависит от версии библиотеки, проверять с ней же (`pip install -r requirements.txt`).
Не разобраны стр. 15 (матрица размеров) и стр. 18 (мотопомпы, все «по запросу»); «по запросу» и позиции без цены в JSON не попадают.
