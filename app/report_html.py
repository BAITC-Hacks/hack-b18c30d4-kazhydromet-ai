"""Self-contained, printable presentation of the canonical Markdown report."""

import hashlib
import html
import re

from .report import build_report


def _text(value: str) -> str:
    # Markdown cells may already contain escaped HTML. They always remain text.
    return html.escape(html.unescape(value), quote=True)


def _inline(value: str) -> str:
    parts, position = [], 0
    pattern = r"(`[^`]*`|\*\*[^*]+\*\*|\[README\]\(\.\./README\.md\))"
    for match in re.finditer(pattern, value):
        parts.append(_text(value[position:match.start()]))
        token = match.group()
        if token.startswith("`"):
            tag = '<code class="gid">' if re.fullmatch(r"\d{18}", token[1:-1]) else "<code>"
            parts.append(tag + _text(token[1:-1]) + "</code>")
        elif token.startswith("**"):
            parts.append("<strong>" + _inline(token[2:-2]) + "</strong>")
        else:
            parts.append('<a href="https://github.com/BAITC-Hacks/hack-b18c30d4-kazhydromet-ai/blob/main/README.md" '
                         'rel="noopener noreferrer">README проекта</a>')
        position = match.end()
    parts.append(_text(value[position:]))
    return "".join(parts)


def _cells(line: str) -> list[str]:
    return [cell.strip().replace(r"\|", "|")
            for cell in re.split(r"(?<!\\)\|", line.strip().strip("|"))]


def _render_markdown(markdown: str) -> str:
    """Render only the headings, paragraphs, lists and tables emitted by report.py."""
    lines = markdown.splitlines()
    blocks, index, section = [], 0, False
    while index < len(lines):
        line = lines[index].strip()
        if not line:
            index += 1
            continue
        heading = re.match(r"^(#{1,3}) (.+)$", line)
        if heading:
            level, title = len(heading[1]), heading[2]
            if level == 2:
                if section:
                    blocks.append("</section>")
                kind = "node-sheet" if title.startswith("Узел ") else "report-section"
                blocks.append(f'<section class="{kind}">')
                section = True
            blocks.append(f"<h{level}>" + _inline(title) + f"</h{level}>")
            index += 1
        elif line.startswith("|"):
            table = []
            while index < len(lines) and lines[index].strip().startswith("|"):
                table.append(_cells(lines[index]))
                index += 1
            if len(table) > 1 and all(re.fullmatch(r":?-+:?", c) for c in table[1]):
                table.pop(1)
            headers, *rows = table
            blocks.append('<div class="table-scroll" tabindex="0" aria-label="Таблица отчёта; можно прокрутить по горизонтали"><table><thead><tr>'+
                          "".join('<th scope="col">'+_inline(cell)+"</th>" for cell in headers)+
                          "</tr></thead><tbody>"+
                          "".join("<tr>"+"".join("<td>"+_inline(cell)+"</td>" for cell in row)+"</tr>" for row in rows)+
                          "</tbody></table></div>")
        elif re.match(r"^(?:- |\d+\. )", line):
            ordered = bool(re.match(r"^\d+\. ", line))
            tag = "ol" if ordered else "ul"
            items = []
            while index < len(lines):
                match = re.match(r"^\d+\. (.+)$" if ordered else r"^- (.+)$", lines[index].strip())
                if not match:
                    break
                items.append("<li>"+_inline(match[1])+"</li>")
                index += 1
            blocks.append(f"<{tag}>"+"".join(items)+f"</{tag}>")
        else:
            paragraph = []
            while index < len(lines) and lines[index].strip():
                if re.match(r"^(?:#{1,3} |\||- |\d+\. )", lines[index].strip()):
                    break
                paragraph.append(lines[index].strip())
                index += 1
            blocks.append("<p>"+_inline(" ".join(paragraph))+"</p>")
    if section:
        blocks.append("</section>")
    return "\n".join(blocks)


STYLE = """
:root{font-family:'Segoe UI',Arial,sans-serif;color:#16313e;background:#eaf0f3;font-size:15px;line-height:1.6}
*{box-sizing:border-box}body{margin:0}a{color:#087a68}button{font:inherit;cursor:pointer}
.toolbar{position:sticky;top:0;display:flex;align-items:center;justify-content:space-between;gap:14px;padding:12px max(24px,calc((100% - 980px)/2));background:#102632;color:#d9e9ed;z-index:2;font-size:13px}
.toolbar button{background:#bcebdc;color:#0c4537;border:0;border-radius:6px;padding:9px 15px;font-weight:650;white-space:nowrap}
.document{max-width:980px;background:white;margin:28px auto;padding:44px 52px 38px;border:1px solid #d5e0e6;box-shadow:0 10px 40px #20374709}
.brand{display:flex;justify-content:space-between;gap:20px;color:#557480;font-size:11px;letter-spacing:1.5px;text-transform:uppercase;padding-bottom:17px;border-bottom:2px solid #16856f;margin-bottom:28px}
h1{font-size:34px;line-height:1.15;letter-spacing:-1.2px;max-width:740px;font-weight:650;margin:0 0 18px}
h2{font-size:22px;line-height:1.35;letter-spacing:-.5px;margin:0 0 12px;color:#123e49}h3{font-size:15px;margin:24px 0 9px;color:#19564f}
p{margin:9px 0 15px;color:#425d69}ul,ol{padding-left:22px;margin:10px 0 16px}li{padding-left:4px;margin:5px 0;color:#425d69}strong{color:#173d48;font-weight:650}
.report-section,.node-sheet{margin-top:30px;padding-top:24px;border-top:1px solid #dce5e8}.node-sheet h2{background:#ecf7f2;border-left:3px solid #16856f;padding:12px 15px;font-size:21px}
code{font-family:Consolas,monospace;font-size:.92em;white-space:nowrap;color:#174a56}table{width:100%;border-collapse:collapse;font-size:12px;line-height:1.5;margin:8px 0 18px}th{background:#eef4f5;color:#2d535e;text-align:left;font-weight:650;padding:10px 9px;border-bottom:1px solid #bfcfd5}td{vertical-align:top;padding:9px;border-bottom:1px solid #e2e9ec}tr:nth-child(even) td{background:#fafcfc}thead{display:table-header-group}.table-scroll{overflow-x:auto}.table-scroll:focus-visible{outline:2px solid #16856f;outline-offset:3px}
.report-footer{margin-top:35px;padding-top:15px;border-top:2px solid #16856f;font-size:11px;color:#617e87}.report-footer code{display:inline-block;max-width:100%;font-size:11px;white-space:normal;overflow-wrap:anywhere;word-break:break-word}.print-note{font-size:12px;color:#52707a;background:#f1f7f6;padding:10px 13px;margin-top:18px}
@media(max-width:700px){.document{margin:0;padding:25px 20px;border:0}h1{font-size:29px}.brand{flex-wrap:wrap;gap:4px}.toolbar{padding:10px 16px}.toolbar span{font-size:11px;max-width:50%}.toolbar button{font-size:12px}.node-sheet h2{font-size:17px;overflow-wrap:anywhere}.node-sheet h2 code{white-space:normal}table{min-width:540px}.report-footer{overflow-wrap:anywhere}}
@page{size:A4;margin:16mm 14mm 18mm}
@media print{html,body{background:#fff;color:#162d36;font-size:10pt;line-height:1.45}.toolbar,.print-note{display:none}.document{max-width:none;border:0;margin:0;padding:0;box-shadow:none}.brand{font-size:8pt;margin-bottom:18px}h1{font-size:25pt}h2{font-size:16pt}h3{font-size:11pt}p,li{color:#263f49}table{font-size:8pt;line-height:1.35;min-width:0}.table-scroll{overflow:visible}th,td{padding:6px 7px}td{overflow-wrap:anywhere}code{font-size:.9em;white-space:normal;overflow-wrap:anywhere}code.gid{white-space:nowrap;overflow-wrap:normal}h1,h2,h3{break-after:avoid}tr{break-inside:avoid}.node-sheet{break-before:page;border:0;padding-top:0}.report-section{margin-top:20px;padding-top:16px}.node-sheet h2{font-size:16pt}.report-footer{font-size:8pt;break-inside:avoid}.brand,th,.node-sheet h2{-webkit-print-color-adjust:exact;print-color-adjust:exact}a{color:inherit;text-decoration:none}}
"""


def build_html_report(gids: list[str] | None = None, top: int = 10) -> str:
    markdown = build_report(gids=gids, top=top)
    digest = hashlib.sha256(markdown.encode("utf-8")).hexdigest()
    return ('<!doctype html><html lang="ru"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>Перечень на проверку · Граф денег</title><style>'+STYLE+'</style></head><body>'
            '<div class="toolbar"><span>Документ аналитика · гипотезы для проверки</span>'
            '<button type="button" onclick="window.print()">Печать / сохранить PDF</button></div>'
            '<main class="document"><header class="brand"><strong>Граф денег / Kazhydromet AI</strong>'
            '<span>Freedom · HackAlem AI · 2026</span></header>'+_render_markdown(markdown)+
            '<div class="print-note">Для передачи сохраните этот документ через печать браузера в PDF. '
            'Проверьте выбранные страницы и поля в предварительном просмотре.</div>'
            '<footer class="report-footer">Контрольная сумма исходного Markdown (SHA-256):<br>'
            '<code>'+digest+'</code><br>Позволяет сверить содержимое отчёта; не является электронной подписью.'
            '</footer></main></body></html>')
