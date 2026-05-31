"""Generate a LinkedIn-friendly carousel PDF for the Nexus framework.

Square 1080x1080 pages, dark palette with a single accent color, one
scannable idea per page. Output: docs/nexus-linkedin-post.pdf
"""

from __future__ import annotations

from pathlib import Path

from reportlab.lib.colors import Color, HexColor
from reportlab.pdfgen.canvas import Canvas

# ---------- design tokens ----------

PAGE = 1080  # square page in points

BG = HexColor("#0B1220")            # deep slate
SURFACE = HexColor("#111B2E")       # raised surface
PRIMARY = HexColor("#F8FAFC")       # near-white text
SECONDARY = HexColor("#94A3B8")     # muted text
ACCENT = HexColor("#22D3EE")        # cyan accent
ACCENT_SOFT = HexColor("#0E7490")   # darker cyan
INDIGO = HexColor("#818CF8")        # secondary accent
DIVIDER = HexColor("#1E293B")

BRAND = "Nexus"
HANDLE = "github.com/<your-org>/nexus"
TOTAL_PAGES = 9

OUTPUT = Path(__file__).resolve().parent / "nexus-linkedin-post.pdf"


# ---------- helpers ----------

def fill_bg(c: Canvas) -> None:
    c.setFillColor(BG)
    c.rect(0, 0, PAGE, PAGE, fill=1, stroke=0)


def accent_bar(c: Canvas, x: float, y: float, w: float = 80, h: float = 6) -> None:
    c.setFillColor(ACCENT)
    c.rect(x, y, w, h, fill=1, stroke=0)


def header(c: Canvas, label: str) -> None:
    """Small label at top-left, e.g. '01 · The problem'."""
    c.setFillColor(ACCENT)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(80, PAGE - 90, label.upper())


def footer(c: Canvas, page_num: int) -> None:
    c.setFillColor(SECONDARY)
    c.setFont("Helvetica", 14)
    c.drawString(80, 60, BRAND)
    c.drawRightString(PAGE - 80, 60, f"{page_num} / {TOTAL_PAGES}")
    # thin divider
    c.setStrokeColor(DIVIDER)
    c.setLineWidth(1)
    c.line(80, 90, PAGE - 80, 90)


def wrap_lines(text: str, max_chars: int) -> list[str]:
    """Naive word-wrap that respects a max character count per line."""
    words = text.split()
    lines: list[str] = []
    current: list[str] = []
    length = 0
    for word in words:
        added = len(word) + (1 if current else 0)
        if length + added > max_chars and current:
            lines.append(" ".join(current))
            current = [word]
            length = len(word)
        else:
            current.append(word)
            length += added
    if current:
        lines.append(" ".join(current))
    return lines


def draw_paragraph(
    c: Canvas,
    text: str,
    x: float,
    y: float,
    font: str = "Helvetica",
    size: int = 26,
    color: Color = PRIMARY,
    line_spacing: float = 1.35,
    max_chars: int = 38,
) -> float:
    """Draw a wrapped paragraph; return the y of the last baseline."""
    c.setFont(font, size)
    c.setFillColor(color)
    line_height = size * line_spacing
    current_y = y
    for line in wrap_lines(text, max_chars):
        c.drawString(x, current_y, line)
        current_y -= line_height
    return current_y


def draw_bullets(
    c: Canvas,
    items: list[str],
    x: float,
    y: float,
    size: int = 24,
    gap: int = 22,
    color: Color = PRIMARY,
    bullet_color: Color = ACCENT,
    max_chars: int = 44,
) -> float:
    c.setFont("Helvetica", size)
    current_y = y
    line_height = size * 1.3
    for item in items:
        # bullet square
        c.setFillColor(bullet_color)
        c.rect(x, current_y - 4, 10, 10, fill=1, stroke=0)
        # text (wrapped)
        c.setFillColor(color)
        c.setFont("Helvetica", size)
        for index, line in enumerate(wrap_lines(item, max_chars)):
            c.drawString(x + 28, current_y - index * line_height, line)
        wrapped_lines = max(1, len(wrap_lines(item, max_chars)))
        current_y -= line_height * wrapped_lines + gap
    return current_y


def draw_code_block(c: Canvas, lines: list[str], x: float, y: float, width: float) -> float:
    line_height = 26
    padding = 24
    height = padding * 2 + line_height * len(lines)
    # panel
    c.setFillColor(SURFACE)
    c.roundRect(x, y - height, width, height, 16, fill=1, stroke=0)
    # code text
    c.setFillColor(PRIMARY)
    c.setFont("Courier-Bold", 18)
    for index, line in enumerate(lines):
        c.drawString(x + padding, y - padding - line_height * (index + 1) + 18, line)
    return y - height


# ---------- pages ----------

def page_cover(c: Canvas) -> None:
    fill_bg(c)
    accent_bar(c, 80, PAGE - 90, w=100, h=6)

    # tag
    c.setFillColor(ACCENT)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(80, PAGE - 140, "NOW OPEN-SOURCE")

    # big wordmark
    c.setFillColor(PRIMARY)
    c.setFont("Helvetica-Bold", 200)
    c.drawString(80, PAGE / 2 + 40, "NEXUS")

    # subtitle
    c.setFillColor(PRIMARY)
    c.setFont("Helvetica-Bold", 44)
    c.drawString(80, PAGE / 2 - 40, "An enterprise AI framework")

    c.setFillColor(SECONDARY)
    c.setFont("Helvetica", 30)
    c.drawString(80, PAGE / 2 - 90, "for secure, grounded, context-aware intelligence.")

    # bottom handle
    c.setFillColor(SECONDARY)
    c.setFont("Helvetica", 18)
    c.drawString(80, 120, HANDLE)
    c.drawRightString(PAGE - 80, 120, "Swipe →")

    accent_bar(c, 80, 90, w=PAGE - 160, h=2)


def page_problem(c: Canvas) -> None:
    fill_bg(c)
    header(c, "01 · The problem")

    c.setFillColor(PRIMARY)
    c.setFont("Helvetica-Bold", 110)
    c.drawString(80, PAGE - 280, "Data-rich.")

    c.setFillColor(ACCENT)
    c.setFont("Helvetica-Bold", 110)
    c.drawString(80, PAGE - 400, "Insight-poor.")

    body = (
        "Enterprises sit on terabytes of fragmented data, "
        "yet most AI prototypes never reach production. "
        "Teams reinvent ingestion, retrieval, guardrails, "
        "RBAC, and audit logging for every new use case."
    )
    draw_paragraph(c, body, 80, PAGE - 520, size=28, color=SECONDARY, max_chars=42)

    footer(c, 2)


def page_what_it_is(c: Canvas) -> None:
    fill_bg(c)
    header(c, "02 · What Nexus is")

    c.setFillColor(PRIMARY)
    c.setFont("Helvetica-Bold", 84)
    c.drawString(80, PAGE - 240, "7 layers.")
    c.setFillColor(ACCENT)
    c.drawString(80, PAGE - 330, "One front door.")

    body = (
        "A layered Python framework built so each layer is "
        "independently installable, replaceable, and deployable. "
        "The root nexus package is the only entry point and never "
        "imports child-layer code."
    )
    draw_paragraph(c, body, 80, PAGE - 410, size=26, color=SECONDARY, max_chars=44)

    # cards row
    cards = ["Library", "CLI", "REST API"]
    card_w = (PAGE - 160 - 40) / 3
    for index, name in enumerate(cards):
        x = 80 + index * (card_w + 20)
        y = 200
        c.setFillColor(SURFACE)
        c.roundRect(x, y, card_w, 120, 16, fill=1, stroke=0)
        c.setFillColor(ACCENT)
        c.rect(x + 20, y + 95, 30, 4, fill=1, stroke=0)
        c.setFillColor(PRIMARY)
        c.setFont("Helvetica-Bold", 28)
        c.drawString(x + 20, y + 50, name)
        c.setFillColor(SECONDARY)
        c.setFont("Helvetica", 16)
        sub = {"Library": "from nexus import …", "CLI": "$ nexus …", "REST API": "POST /v1/ask"}[name]
        c.drawString(x + 20, y + 22, sub)

    footer(c, 3)


def page_architecture(c: Canvas) -> None:
    fill_bg(c)
    header(c, "03 · Architecture")

    c.setFillColor(PRIMARY)
    c.setFont("Helvetica-Bold", 56)
    c.drawString(80, PAGE - 200, "Loose coupling,")
    c.setFillColor(ACCENT)
    c.drawString(80, PAGE - 260, "end to end.")

    # 7 layered cards
    labels = [
        ("1", "Enterprise Data Pipeline", "API · batch · stream · CDC"),
        ("2", "Processing & Enrichment", "ETL · chunking · metadata"),
        ("3", "Embedding & Retrieval", "vector · lexical · hybrid · graph"),
        ("4", "Orchestration & Guardrails", "PII · prompt safety · grounded RAG"),
        ("5", "Experience API", "REST · SDK · assistant · web · mobile"),
        ("6", "Security & Governance", "RBAC · tenant isolation · AEAD · audit"),
        ("7", "Observability", "metrics · logs · traces · alerts"),
    ]
    top = PAGE - 320
    row_h = 70
    for index, (num, title, sub) in enumerate(labels):
        y = top - index * row_h
        # card
        c.setFillColor(SURFACE)
        c.roundRect(80, y - row_h + 10, PAGE - 160, row_h - 14, 12, fill=1, stroke=0)
        # number badge
        c.setFillColor(ACCENT)
        c.circle(120, y - 17, 18, fill=1, stroke=0)
        c.setFillColor(BG)
        c.setFont("Helvetica-Bold", 22)
        c.drawCentredString(120, y - 25, num)
        # title
        c.setFillColor(PRIMARY)
        c.setFont("Helvetica-Bold", 22)
        c.drawString(160, y - 12, title)
        # subtitle
        c.setFillColor(SECONDARY)
        c.setFont("Helvetica", 16)
        c.drawString(160, y - 36, sub)

    footer(c, 4)


def page_features(c: Canvas) -> None:
    fill_bg(c)
    header(c, "04 · What you get")

    c.setFillColor(PRIMARY)
    c.setFont("Helvetica-Bold", 72)
    c.drawString(80, PAGE - 240, "Capabilities")

    items = [
        "Connectors for REST, batch, streaming, CDC",
        "Document chunking + metadata enrichment",
        "Hybrid vector + lexical + graph retrieval",
        "Grounded RAG with citations and confidence",
        "PII masking, prompt safety, policy engine",
        "REST API, Python SDK, CLI, assistant channels",
        "RBAC, tenant isolation, authenticated encryption",
        "Metrics, logs, traces, AI events, alerts",
    ]
    draw_bullets(c, items, 80, PAGE - 320, size=22, gap=14, max_chars=48)

    footer(c, 5)


def page_security(c: Canvas) -> None:
    fill_bg(c)
    header(c, "05 · Security-first")

    c.setFillColor(PRIMARY)
    c.setFont("Helvetica-Bold", 80)
    c.drawString(80, PAGE - 240, "Hardened")
    c.setFillColor(ACCENT)
    c.drawString(80, PAGE - 320, "by default.")

    items = [
        "Fernet AEAD (AES-128-CBC + HMAC-SHA256), fail-closed key handling",
        "API-key auth with constant-time compare; pluggable RBAC hook",
        "Session ownership enforced; spoofable user_id removed",
        "SSRF and bearer-token leak defense in API connectors",
        "Subprocess argv + path-traversal hardened end to end",
        "NFKC-normalized guardrails; Luhn-validated PII",
    ]
    draw_bullets(c, items, 80, PAGE - 400, size=21, gap=10, max_chars=52)

    footer(c, 6)


def page_install(c: Canvas) -> None:
    fill_bg(c)
    header(c, "06 · How to use")

    c.setFillColor(PRIMARY)
    c.setFont("Helvetica-Bold", 72)
    c.drawString(80, PAGE - 240, "Install in")
    c.setFillColor(ACCENT)
    c.drawString(80, PAGE - 320, "seconds.")

    code_lines = [
        "$ pip install -e nexus",
        "$ nexus validate-platform configs/nexus.yaml",
        "$ nexus prepare-demo configs/nexus.yaml",
        "$ nexus ask configs/nexus.yaml \"What is MFA?\"",
    ]
    draw_code_block(c, code_lines, 80, PAGE - 380, PAGE - 160)

    py_lines = [
        "from nexus import NexusPlatform",
        "platform = NexusPlatform.from_config(path)",
        "print(platform.ask(\"What is MFA?\"))",
    ]
    draw_code_block(c, py_lines, 80, 360, PAGE - 160)

    footer(c, 7)


def page_benefits(c: Canvas) -> None:
    fill_bg(c)
    header(c, "07 · Benefits")

    c.setFillColor(PRIMARY)
    c.setFont("Helvetica-Bold", 80)
    c.drawString(80, PAGE - 240, "Why teams")
    c.setFillColor(ACCENT)
    c.drawString(80, PAGE - 320, "adopt it.")

    items = [
        "Drop-in Python library — no side effects at import",
        "Loose coupling — swap any layer without touching others",
        "Security built in, not bolted on",
        "Deterministic local dev — no required cloud services",
        "181 tests across 8 suites, deterministic and offline",
        "Vendor-neutral — wire in your own LLM, vector DB, KMS, SIEM",
    ]
    draw_bullets(c, items, 80, PAGE - 400, size=21, gap=12, max_chars=52)

    footer(c, 8)


def page_cta(c: Canvas) -> None:
    fill_bg(c)
    accent_bar(c, 80, PAGE - 90, w=100, h=6)

    c.setFillColor(ACCENT)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(80, PAGE - 140, "GET STARTED")

    c.setFillColor(PRIMARY)
    c.setFont("Helvetica-Bold", 140)
    c.drawString(80, PAGE / 2 + 60, "Try")
    c.setFillColor(ACCENT)
    c.drawString(330, PAGE / 2 + 60, "Nexus.")

    c.setFillColor(SECONDARY)
    c.setFont("Helvetica", 30)
    c.drawString(80, PAGE / 2 - 20, "Read the full integrator guide:")
    c.setFillColor(PRIMARY)
    c.setFont("Helvetica-Bold", 30)
    c.drawString(80, PAGE / 2 - 70, "docs/USING_NEXUS.md")

    # pills
    pills = ["Star ★", "Fork", "Contribute"]
    x = 80
    for label in pills:
        text_w = 24 + 12 * len(label)
        c.setFillColor(SURFACE)
        c.roundRect(x, 200, text_w, 60, 30, fill=1, stroke=0)
        c.setFillColor(PRIMARY)
        c.setFont("Helvetica-Bold", 22)
        c.drawString(x + 18, 220, label)
        x += text_w + 16

    c.setFillColor(SECONDARY)
    c.setFont("Helvetica", 22)
    c.drawString(80, 130, HANDLE)
    accent_bar(c, 80, 100, w=PAGE - 160, h=2)


# ---------- entry point ----------

def build() -> Path:
    c = Canvas(str(OUTPUT), pagesize=(PAGE, PAGE))
    c.setTitle("Nexus — Open-source enterprise AI framework")
    c.setAuthor("Nexus")
    c.setSubject("LinkedIn announcement carousel")

    for builder in (
        page_cover,
        page_problem,
        page_what_it_is,
        page_architecture,
        page_features,
        page_security,
        page_install,
        page_benefits,
        page_cta,
    ):
        builder(c)
        c.showPage()

    c.save()
    return OUTPUT


if __name__ == "__main__":
    path = build()
    print(f"Wrote {path}")
