"""Export completed tasks as CSV, JSON or PDF using only the standard library."""
import csv
import io
import json
from datetime import datetime

FIELDS = ["id", "name", "description", "contact", "due", "priority", "tags",
          "created_at", "done_at", "completed_late"]
LABELS = {"id": "ID", "name": "Name", "description": "Description", "contact": "Stakeholder",
          "due": "Due", "priority": "Priority", "tags": "Tags", "created_at": "Created",
          "done_at": "Completed", "completed_late": "Completed late"}


def completed_rows(tasks, start=None, end=None):
    """Done tasks, newest first, with derived fields. start/end are inclusive YYYY-MM-DD dates."""
    rows = []
    for t in tasks:
        if t.get("bucket") != "Done" or not t.get("done_at"):
            continue
        day = t["done_at"][:10]
        if (start and day < start) or (end and day > end):
            continue
        r = {k: t.get(k) for k in FIELDS}
        r["tags"] = list(t.get("tags") or [])
        r["created_at"] = t.get("created_at") or ""
        r["completed_late"] = ("Yes" if day > t["due"] else "No") if t.get("due") else ""
        rows.append(r)
    rows.sort(key=lambda r: (r["done_at"], r["id"]), reverse=True)
    return rows


def _safe_cell(v):
    """Neutralise spreadsheet formula injection (=, +, -, @ at the start of a cell)."""
    s = "" if v is None else str(v)
    return "'" + s if s[:1] in ("=", "+", "-", "@", "\t", "\r") else s


def to_csv(rows):
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\r\n")
    w.writerow([LABELS[f] for f in FIELDS])
    for r in rows:
        w.writerow([_safe_cell("; ".join(r[f]) if f == "tags" else r[f]) for f in FIELDS])
    return ("﻿" + buf.getvalue()).encode("utf-8")  # BOM so Excel reads UTF-8


def to_json(rows):
    doc = {"exported_at": datetime.now().isoformat(timespec="seconds"), "count": len(rows), "tasks": rows}
    return json.dumps(doc, indent=2, ensure_ascii=False).encode("utf-8")


# ---- minimal PDF writer (Helvetica, WinAnsi) -------------------------------------------------
_W = dict(zip(" !\"#$%&'()*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ[\\]^_`abcdefghijklmnopqrstuvwxyz{|}~",
              [278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584, 278, 333, 278, 278] + [556] * 10
              + [278, 278, 584, 584, 584, 556, 1015,
                 667, 667, 722, 722, 667, 611, 778, 722, 278, 500, 667, 556, 833, 722, 778, 667, 778, 722,
                 667, 611, 722, 667, 944, 667, 667, 611, 278, 278, 278, 469, 556, 333,
                 556, 556, 500, 556, 556, 278, 556, 556, 222, 222, 500, 222, 833, 556, 556, 556, 556,
                 333, 500, 278, 556, 500, 722, 500, 500, 500, 334, 260, 334, 584]))


def _width(s, size, bold=False):
    return sum(_W.get(c, 556) for c in s) * size / 1000.0 * (1.06 if bold else 1.0)


def _wrap(text, size, max_w, bold=False):
    """Word-wrap `text` (may contain newlines) to max_w points."""
    out = []
    for para in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = ""
        for word in para.split(" "):
            while _width(word, size, bold) > max_w:  # hard-split very long tokens
                n = max(1, int(len(word) * max_w / _width(word, size, bold)))
                if line:
                    out.append(line)
                    line = ""
                out.append(word[:n])
                word = word[n:]
            trial = (line + " " + word) if line else word
            if _width(trial, size, bold) <= max_w:
                line = trial
            else:
                out.append(line)
                line = word
        out.append(line)
    return out


def _esc(s):
    b = s.encode("cp1252", "replace")
    return b.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")


def to_pdf(rows, title="Completed tasks"):
    PW, PH, M = 595, 842, 48  # A4 in points
    usable = PW - 2 * M
    pages, cur, y = [], [], PH - M

    def new_page():
        nonlocal cur, y
        if cur:
            pages.append(cur)
        cur, y = [], PH - M

    def line(text, size=9.5, bold=False, indent=0, gap=1.5, color="0.15 0.15 0.2"):
        nonlocal y
        h = size + gap
        if y - h < M + 14:
            new_page()
        y -= h
        cur.append(b"BT /%s %.1f Tf %s rg %.1f %.1f Td (" % (b"F2" if bold else b"F1", size,
                   color.encode(), M + indent, y) + _esc(text) + b") Tj ET")

    new_page()
    line(title, 18, True, gap=6)
    line("Exported %s  |  %d task%s" % (datetime.now().strftime("%Y-%m-%d %H:%M"), len(rows),
                                        "" if len(rows) == 1 else "s"), 9, color="0.4 0.4 0.45", gap=10)
    if not rows:
        line("No completed tasks.")
    for r in rows:
        if y < M + 90:
            new_page()
        for ln in _wrap(r["name"], 12, usable, True):
            line(ln, 12, True, gap=2)
        late = {"Yes": "  (late)", "No": "  (on time)"}.get(r["completed_late"], "")
        meta = [("Completed", (r["done_at"] or "").replace("T", " ") + late), ("Priority", r["priority"]),
                ("Stakeholder", r["contact"]), ("Due", r["due"]), ("Created", (r["created_at"] or "").replace("T", " ")),
                ("Tags", ", ".join(r["tags"])), ("ID", str(r["id"]))]
        for k, v in meta:
            if v and v.strip():
                for i, ln in enumerate(_wrap("%s: %s" % (k, v), 9.5, usable - 12)):
                    line(ln, 9.5, indent=12 if i == 0 else 24)
        if r["description"]:
            for ln in _wrap(r["description"], 9.5, usable - 12):
                line(ln, 9.5, indent=12, color="0.3 0.3 0.35")
        y -= 5
        cur.append(b"0.85 0.85 0.88 RG 0.5 w %d %.1f m %d %.1f l S" % (M, y, PW - M, y))
        y -= 7
    new_page()

    # Assemble objects: 1 catalog, 2 pages, 3/4 fonts, then (page, content) pairs.
    n = len(pages)
    objs = {1: b"<< /Type /Catalog /Pages 2 0 R >>",
            3: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
            4: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>"}
    kids = []
    for i, ops in enumerate(pages):
        pg, ct = 5 + 2 * i, 6 + 2 * i
        kids.append(b"%d 0 R" % pg)
        ops = ops + [b"BT /F1 8 Tf 0.5 0.5 0.55 rg %d 28 Td (Page %d of %d) Tj ET" % (PW - M - 50, i + 1, n)]
        stream = b"\n".join(ops)
        objs[ct] = b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream"
        objs[pg] = (b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %d %d] /Resources << /Font << /F1 3 0 R /F2 4 0 R >> >>"
                    b" /Contents %d 0 R >>" % (PW, PH, ct))
    objs[2] = b"<< /Type /Pages /Kids [" + b" ".join(kids) + b"] /Count %d >>" % n

    out = bytearray(b"%PDF-1.4\n")
    offsets = {}
    for num in sorted(objs):
        offsets[num] = len(out)
        out += b"%d 0 obj\n" % num + objs[num] + b"\nendobj\n"
    xref = len(out)
    size = max(objs) + 1
    out += b"xref\n0 %d\n0000000000 65535 f \n" % size
    for num in range(1, size):
        out += b"%010d 00000 n \n" % offsets[num]
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (size, xref)
    return bytes(out)


FORMATS = {
    "csv": ("text/csv; charset=utf-8", to_csv),
    "json": ("application/json; charset=utf-8", to_json),
    "pdf": ("application/pdf", to_pdf),
}
