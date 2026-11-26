"""A small .xlsx writer using only the standard library.

Supports what the export needs: several sheets, a bold header row that stays frozen, column
filters, column widths, number formats and formulas. Text is always written as text, so a
supplier name that starts with "=" is never run as a formula.
"""

from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass, field
from xml.sax.saxutils import escape, quoteattr

# style name -> index into cellXfs below
STYLES = {"text": 0, "header": 1, "money": 2, "int": 3, "pct": 4, "dec": 5, "input": 6,
          "bold": 7, "total": 8}

_ILLEGAL = re.compile("[^\t\n\r\x20-퟿-�\U00010000-\U0010ffff]")


@dataclass
class Cell:
    value: object = None
    style: str = "text"
    formula: str = ""         # without the leading "="; `value` is the cached result


@dataclass
class Sheet:
    name: str
    rows: list = field(default_factory=list)      # lists of Cell
    widths: list = field(default_factory=list)
    table: bool = True        # first row is a header: freeze it and add filters


def col_letter(i: int) -> str:
    """0 -> A, 25 -> Z, 26 -> AA."""
    s = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def _text(value) -> str:
    return escape(_ILLEGAL.sub("", str(value))[:32767])


def _cell(ref: str, c: Cell) -> str:
    s = STYLES[c.style]
    if c.formula:
        cached = "" if c.value is None else f"<v>{c.value!r}</v>"
        return f'<c r="{ref}" s="{s}"><f>{escape(c.formula)}</f>{cached}</c>'
    if c.value is None or c.value == "":
        return f'<c r="{ref}" s="{s}"/>'
    if isinstance(c.value, (int, float)) and not isinstance(c.value, bool):
        return f'<c r="{ref}" s="{s}"><v>{c.value!r}</v></c>'
    return f'<c r="{ref}" s="{s}" t="inlineStr"><is><t xml:space="preserve">{_text(c.value)}</t></is></c>'


def _sheet_xml(sh: Sheet) -> str:
    body = "".join(
        f'<row r="{n}">' + "".join(_cell(f"{col_letter(i)}{n}", c) for i, c in enumerate(row)) + "</row>"
        for n, row in enumerate(sh.rows, 1))
    pane = ('<pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>'
            if sh.table else "")
    cols = "".join(f'<col min="{i}" max="{i}" width="{w}" customWidth="1"/>'
                   for i, w in enumerate(sh.widths, 1))
    flt = ""
    if sh.table and len(sh.rows) > 1:
        flt = f'<autoFilter ref="A1:{col_letter(len(sh.rows[0]) - 1)}{len(sh.rows)}"/>'
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            f'<sheetViews><sheetView workbookViewId="0">{pane}</sheetView></sheetViews>'
            '<sheetFormatPr defaultRowHeight="15"/>'
            + (f"<cols>{cols}</cols>" if cols else "")
            + f"<sheetData>{body}</sheetData>{flt}</worksheet>")


_STYLES_XML = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
    '<numFmts count="2"><numFmt numFmtId="164" formatCode="0.0%"/>'
    '<numFmt numFmtId="165" formatCode="#,##0.00"/></numFmts>'
    '<fonts count="3"><font><sz val="11"/><name val="Calibri"/><family val="2"/></font>'
    '<font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Calibri"/><family val="2"/></font>'
    '<font><b/><sz val="11"/><name val="Calibri"/><family val="2"/></font></fonts>'
    '<fills count="4"><fill><patternFill patternType="none"/></fill>'
    '<fill><patternFill patternType="gray125"/></fill>'
    '<fill><patternFill patternType="solid"><fgColor rgb="FF16324F"/></patternFill></fill>'
    '<fill><patternFill patternType="solid"><fgColor rgb="FFFFF2CC"/></patternFill></fill></fills>'
    '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
    '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
    '<cellXfs count="9">'
    '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
    '<xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1"/>'
    '<xf numFmtId="165" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>'
    '<xf numFmtId="3" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>'
    '<xf numFmtId="164" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>'
    '<xf numFmtId="2" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>'
    '<xf numFmtId="164" fontId="0" fillId="3" borderId="0" xfId="0" applyNumberFormat="1" applyFill="1"/>'
    '<xf numFmtId="0" fontId="2" fillId="0" borderId="0" xfId="0" applyFont="1"/>'
    '<xf numFmtId="165" fontId="2" fillId="0" borderId="0" xfId="0" applyNumberFormat="1" applyFont="1"/>'
    '</cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
    '</styleSheet>')


def write_xlsx(path: str, sheets: list[Sheet]) -> None:
    main = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    rel = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    pkg = "http://schemas.openxmlformats.org/package/2006/relationships"
    ct = "application/vnd.openxmlformats-officedocument.spreadsheetml"
    head = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    n = len(sheets)
    types = (head + '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
             '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
             '<Default Extension="xml" ContentType="application/xml"/>'
             f'<Override PartName="/xl/workbook.xml" ContentType="{ct}.sheet.main+xml"/>'
             f'<Override PartName="/xl/styles.xml" ContentType="{ct}.styles+xml"/>'
             + "".join(f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="{ct}.worksheet+xml"/>'
                       for i in range(1, n + 1)) + "</Types>")
    root = (head + f'<Relationships xmlns="{pkg}"><Relationship Id="rId1" Type="{rel}/officeDocument" '
            'Target="xl/workbook.xml"/></Relationships>')
    filters = "".join(
        f'<definedName name="_xlnm._FilterDatabase" localSheetId="{i}" hidden="1">'
        f"{escape(chr(39) + s.name + chr(39))}!$A$1:${col_letter(len(s.rows[0]) - 1)}${len(s.rows)}</definedName>"
        for i, s in enumerate(sheets) if s.table and len(s.rows) > 1)
    book = (head + f'<workbook xmlns="{main}" xmlns:r="{rel}"><sheets>'
            + "".join(f'<sheet name={quoteattr(s.name)} sheetId="{i}" r:id="rId{i}"/>'
                      for i, s in enumerate(sheets, 1))
            + "</sheets>" + (f"<definedNames>{filters}</definedNames>" if filters else "")
            + '<calcPr fullCalcOnLoad="1"/></workbook>')
    book_rels = (head + f'<Relationships xmlns="{pkg}">'
                 + "".join(f'<Relationship Id="rId{i}" Type="{rel}/worksheet" Target="worksheets/sheet{i}.xml"/>'
                           for i in range(1, n + 1))
                 + f'<Relationship Id="rId{n + 1}" Type="{rel}/styles" Target="styles.xml"/></Relationships>')
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", types)
        z.writestr("_rels/.rels", root)
        z.writestr("xl/workbook.xml", book)
        z.writestr("xl/_rels/workbook.xml.rels", book_rels)
        z.writestr("xl/styles.xml", _STYLES_XML)
        for i, s in enumerate(sheets, 1):
            z.writestr(f"xl/worksheets/sheet{i}.xml", _sheet_xml(s))
