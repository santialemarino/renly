from datetime import date
from decimal import Decimal

import httpx
import pytest

from app.services import price_providers

# The BYMA CEDEAR ratio PDF, read end to end through `fetch_byma_ratios` — the one place the API parses a
# PDF. It pins what the parser extracts, so a pdfplumber or pdfminer bump that changes `extract_text()`
# shows up here rather than as silently wrong ratios. (Pillow, which pdfplumber pulls in, is only loaded
# for `to_image`, so text extraction never touches it.)
#
# The PDF is built in the test, not committed: BYMA's own file carries no licence to redistribute. It
# copies the live file's layout (checked against the 2026-09-16 edition): Letter pages, one row per CEDEAR
# with the name, ticker, market and "N:N" ratio in four columns, a header drawn four times with a small
# offset (the fake bold that makes pdfplumber read "RRRRaaaattttiiiioooo"), and a two-line footer on every
# page. The rows are real ones chosen for the cases the parser handles: a fractional ratio, a two-word
# market, a dotted ticker, a ticker ending in a digit and a zero-padded ratio. More carry the tickers and
# markets of live rows an earlier parser got wrong (their names and ratios are stand-ins): the "New York"
# and "OTC US" markets (read as tickers YORK and US), a ticker that is itself a market word (GS), the
# CBOE, NASDAQ CM and BOVESPA markets, and the six live rows whose market cell is EMPTY — which as one line
# of text look exactly like a row on a one-word market, so only the column gap tells them apart. A row
# with a fifth cell is a layout the parser does not know, and is skipped by name.
#
# The PDF's filename carries the edition's date, which the live file puts FIRST; an older edition put it
# last. Both must yield it.
_PDF_FILENAMES = {
    "the live shape, date first": ("y_2026-09-16-BYMA-CEDEARs.pdf", date(2026, 9, 16)),
    "the older shape, date last": ("y_BYMA-CEDEARs-2026-02-03.pdf", date(2026, 2, 3)),
}

_PAGES = [
    [
        ("Apple Inc.", "AAPL", "NASDAQ", "20:1"),
        ("Ambev S.A.", "ABEV", "NASDAQ", "1:3"),
        ("Ambev S.A.", "ABEV3", "B3", "1:1"),
        ("Airbnb Inc", "ABNB", "NASDAQ GS", "15:1"),
        ("Embotelladora Andina S.A.", "AKO.B", "NYSE", "1:1"),
        ("ARK INNOVATION", "ARKK", "NYSE Arca", "10:1"),
        ("Bank Of America Corporation", "BA.C", "NYSE", "4:1"),
    ],
    [
        ("Basf SE", "BAS", "FRANKFURT", "2:1"),
        ("Adidas AG", "ADS", "XETRA", "22:1"),
        ("State Street SPDR S&P Metals & Mining ETF", "XME", "NYSE ARCA", "30:1"),
        ("XP Inc", "XP", "NASDAQ", "04:01"),
        ("Amazon.Com, Inc.", "AMZN", "NYSE", "144:1"),
        ("Banco Santander S.A.", "SAN", "New York", "1:4"),
        ("Grupo Supervielle S.A.", "SUPV", "OTC US", "1:2"),
        ("The Goldman Sachs Group, Inc.", "GS", "NYSE", "13:1"),
        ("Toyota Motor Corporation", "TM", "Tokyo", "5:1"),
    ],
    [
        ("Stand-in BBAX", "BBAX", "CBOE", "10:1"),
        ("Stand-in BBCA", "BBCA", "CBOE", "10:1"),
        ("Stand-in ITA", "ITA", "CBOE", "20:1"),
        ("Stand-in VXX", "VXX", "CBOE", "5:1"),
        ("Stand-in ONDS", "ONDS", "NASDAQ CM", "1:1"),
        ("Stand-in RGTI", "RGTI", "NASDAQ CM", "2:1"),
        ("Stand-in RCTB4", "RCTB4", "BOVESPA", "1:1"),
        ("Stand-in ATAD", "ATAD", "", "1:1"),
        ("Stand-in HHPD", "HHPD", "", "1:1"),
        ("Stand-in LKOD", "LKOD", "", "1:1"),
        ("Stand-in NLM", "NLM", "", "1:1"),
        ("Stand-in OGZD", "OGZD", "", "1:1"),
        ("Stand-in SMSN", "SMSN", "", "1:1"),
        ("Odd Layout Co", "ODD", "NYSE", "note", "1:1"),
    ],
]

_EXPECTED = [
    ("AAPL.BA", "AAPL", Decimal(20)),
    ("ABEV.BA", "ABEV", Decimal(1) / Decimal(3)),
    ("ABEV3.BA", "ABEV3", Decimal(1)),
    ("ABNB.BA", "ABNB", Decimal(15)),
    ("AKO.B.BA", "AKO.B", Decimal(1)),
    ("ARKK.BA", "ARKK", Decimal(10)),
    ("BA.C.BA", "BA.C", Decimal(4)),
    ("BAS.BA", "BAS", Decimal(2)),
    ("ADS.BA", "ADS", Decimal(22)),
    ("XME.BA", "XME", Decimal(30)),
    ("XP.BA", "XP", Decimal(4)),
    ("AMZN.BA", "AMZN", Decimal(144)),
    ("SAN.BA", "SAN", Decimal(1) / Decimal(4)),
    ("SUPV.BA", "SUPV", Decimal(1) / Decimal(2)),
    ("GS.BA", "GS", Decimal(13)),
    ("TM.BA", "TM", Decimal(5)),
    ("BBAX.BA", "BBAX", Decimal(10)),
    ("BBCA.BA", "BBCA", Decimal(10)),
    ("ITA.BA", "ITA", Decimal(20)),
    ("VXX.BA", "VXX", Decimal(5)),
    ("ONDS.BA", "ONDS", Decimal(1)),
    ("RGTI.BA", "RGTI", Decimal(2)),
    ("RCTB4.BA", "RCTB4", Decimal(1)),
    ("ATAD.BA", "ATAD", Decimal(1)),
    ("HHPD.BA", "HHPD", Decimal(1)),
    ("LKOD.BA", "LKOD", Decimal(1)),
    ("NLM.BA", "NLM", Decimal(1)),
    ("OGZD.BA", "OGZD", Decimal(1)),
    ("SMSN.BA", "SMSN", Decimal(1)),
]


# One text draw in PDF coordinates; `top` is measured from the top edge, as pdfplumber reports it.
def _text(x: float, top: float, size: float, text: str) -> str:
    escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    return f"BT /F1 {size} Tf {x:.2f} {792 - top - size:.2f} Td ({escaped}) Tj ET"


# The header, drawn four times a fraction of a point apart, the way the live file's fake bold is.
def _bold(x: float, top: float, size: float, text: str) -> list[str]:
    return [_text(x + i * 0.15, top, size, text) for i in range(4)]


# One page's content stream: header, rows, footer.
def _page_stream(rows: list[tuple[str, ...]], number: int) -> bytes:
    ops = [
        *_bold(57, 72, 8.5, "CEDEARs Negociables en BYMA"),
        *_bold(281, 92, 5.6, "Código Mercado donde"),
        *_bold(118, 99, 5.6, "Nombre de la Compañía"),
        *_bold(406, 99, 5.6, "Ratio (*)"),
        *_bold(281, 106, 5.6, "BYMA Cotiza"),
    ]
    for index, (name, ticker, market, ratio, *extra) in enumerate(rows):
        top = 170 + index * 12.7
        ops += [
            _text(57, top, 6.4, name),
            _text(283, top, 6.4, ticker),
            *([_text(349, top, 6.4, market)] if market else []),
            _text(412, top - 0.4, 7.1, ratio),
            *[_text(470, top, 6.4, cell) for cell in extra],
        ]
    ops += [
        _text(57, 740, 5.6, "Bolsas y Mercados Argentinos S.A. Actualizado 16/09/2026"),
        _text(57, 750, 5.6, f"Mercado registrado bajo el N° 639 de la CNV (*) Relación CEDEAR Subyacente Página {number}"),
    ]
    return "\n".join(ops).encode("latin-1")


# A minimal valid PDF (catalog, page tree, one Helvetica font, one page + stream per page, xref table).
def _build_pdf() -> bytes:
    page_count = len(_PAGES)
    font_id = 3
    page_ids = [4 + 2 * i for i in range(page_count)]
    objects = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        2: f"<< /Type /Pages /Kids [{' '.join(f'{p} 0 R' for p in page_ids)}] /Count {page_count} >>".encode(),
        font_id: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
    }
    for i, rows in enumerate(_PAGES):
        stream = _page_stream(rows, i + 1)
        objects[page_ids[i]] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 {font_id} 0 R >> >> /Contents {page_ids[i] + 1} 0 R >>"
        ).encode()
        objects[page_ids[i] + 1] = b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream"

    out = bytearray(b"%PDF-1.4\n")
    offsets = {}
    for object_id in sorted(objects):
        offsets[object_id] = len(out)
        out += b"%d 0 obj\n" % object_id + objects[object_id] + b"\nendobj\n"
    xref = len(out)
    size = max(objects) + 1
    out += b"xref\n0 %d\n0000000000 65535 f \n" % size
    for object_id in range(1, size):
        out += b"%010d 00000 n \n" % offsets[object_id]
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (size, xref)
    return bytes(out)


# A fake httpx.AsyncClient serving the BYMA page (with a link to the PDF under `filename`) and then the
# PDF itself.
def _fake_client(pdf: bytes, filename: str):
    page_html = f'<a href="https://cdn.prod.website-files.com/x/{filename}">PDF</a>'

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def get(self, url, **kwargs):
            request = httpx.Request("GET", url)
            if url == price_providers.BYMA_CEDEARS_PAGE_URL:
                return httpx.Response(200, request=request, text=page_html)
            return httpx.Response(200, request=request, content=pdf)

    return _Client


class TestTheBYMAPdfParses:
    @pytest.mark.asyncio
    async def test_every_row_yields_its_ticker_and_ratio_and_nothing_else_does(self, monkeypatch, caplog):
        monkeypatch.setattr(price_providers.httpx, "AsyncClient", _fake_client(_build_pdf(), _PDF_FILENAMES["the live shape, date first"][0]))

        result = await price_providers.fetch_byma_ratios()

        assert result.ratios == _EXPECTED
        # The one row it could not read is named, so a layout change reads as a list of rows, not a count.
        assert [r.getMessage() for r in caplog.records if r.levelname == "WARNING"] == [
            "BYMA CEDEAR PDF: skipped 1 rows whose cells do not read as a CEDEAR row: ['Odd Layout Co | ODD | NYSE | note | 1:1']"
        ]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("shape", sorted(_PDF_FILENAMES))
    async def test_the_editions_date_is_read_from_its_filename(self, monkeypatch, shape):
        filename, expected = _PDF_FILENAMES[shape]
        monkeypatch.setattr(price_providers.httpx, "AsyncClient", _fake_client(_build_pdf(), filename))

        result = await price_providers.fetch_byma_ratios()

        assert result.source_date == expected
