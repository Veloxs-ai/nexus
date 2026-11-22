# Copyright 2026 Veloxs AI Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# SPDX-License-Identifier: Apache-2.0

"""Encodings, language ID, HTML implied end tags, Slack, JSON, code members, Mongo, ADF."""

from __future__ import annotations

import json
import time

import pytest

from nexus_processing.code import _looks_python, process_code, process_polyglot_source
from nexus_processing.json_table import flatten_json, json_table
from nexus_processing.language import detect_language
from nexus_processing.markup_adf import adf_to_markdown
from nexus_processing.markup_html import html_to_markdown
from nexus_processing.mongodb import flatten_mongo_document
from nexus_processing.slack_export import messages_to_chunks
from nexus_processing.text_decode import decode_text

LEGACY = [
    ("cp1251", "Компания представила результаты квартала и утвердила план."),
    ("cp1250", "Zażółć gęślą jaźń, Łódź i Kraków."),
    ("cp1253", "Η εταιρεία παρουσίασε τα αποτελέσματα του τριμήνου."),
    ("cp1256", "قدمت الشركة نتائج الربع ووافق مجلس الإدارة على الخطة."),
    ("cp1255", "החברה הציגה את תוצאות הרבעון והדירקטוריון אישר את התוכנית."),
    ("koi8_r", "Компания представила результаты квартала и утвердила план."),
    ("shift_jis", "会社は四半期の業績を発表し、取締役会は承認しました。"),
    ("euc_jp", "会社は四半期の業績を発表し、取締役会は承認しました。"),
    ("gb18030", "公司公布了季度业绩，董事会批准了新的年度投资计划。"),
    ("big5", "公司公佈了季度業績，董事會批准了新的年度投資計劃。"),
    ("euc-kr", "회사는 분기 실적을 발표했고 이사회는 승인했습니다."),
]
WESTERN = [
    "Résumé – naïve café, Zürich € 12,50",
    "Señora Muñoz pagó el depósito; ¿Cuándo llega? ¡Gracias!",
    "São João, Conceição, informações, não, então",
    "Æsir, Ørsted, Ålborg, fjörður",
    "Total: 12,50 € (incl. 19% MwSt.) – Lieferung ab Köln",
]


@pytest.mark.parametrize(("codec", "text"), LEGACY)
def test_legacy_code_pages_decode_exactly(codec, text):
    assert decode_text(text.encode(codec)).text == text


@pytest.mark.parametrize("text", WESTERN)
def test_western_text_stays_cp1252(text):
    decoded = decode_text(text.encode("cp1252"))
    assert decoded.text == text and decoded.encoding == "cp1252"


def test_every_cp1252_character_alone_stays_cp1252():
    for code in range(0x80, 0x100):
        if code in (0x81, 0x8D, 0x8F, 0x90, 0x9D):
            continue
        char = bytes([code]).decode("cp1252")
        for template in ("Price 12 {} ok", "{}", "word{}", "The caf{} is open"):
            text = template.format(char)
            assert decode_text(text.encode("cp1252")).text == text


def test_mostly_utf8_keeps_utf8_and_counts_broken_bytes():
    good = ("Résumé – naïve café Zürich € 12,50\n" * 20).encode()
    decoded = decode_text(good + b"\xff" + good)
    assert decoded.encoding == "utf-8" and decoded.replaced == 1
    assert decoded.text.count("Résumé") == 40


def test_two_unknown_bytes_fall_back_to_latin1():
    assert decode_text(bytes([0x81, 0x41])).encoding == "latin-1"


@pytest.mark.parametrize(
    ("lang", "text"),
    [
        ("uk", "Компанія представила результати кварталу, і рада директорів затвердила план."),
        ("bg", "Компанията представи резултатите и съветът одобри новия план за годината."),
        ("ru", "Компания представила результаты квартала, и совет утвердил новый план."),
        ("mr", "कंपनीने तिमाहीचे निकाल सादर केले आणि मंडळाने नवीन योजनेला मंजुरी दिली."),
        ("hi", "कंपनी ने तिमाही के परिणाम प्रस्तुत किए और बोर्ड ने योजना को मंजूरी दी।"),
        ("fa", "شرکت نتایج فصل را ارائه کرد و هیئت مدیره برنامه جدید را تصویب کرد."),
        ("ar", "قدمت الشركة نتائج الربع ووافق مجلس الإدارة على خطة الاستثمار الجديدة."),
        ("ja", "東京本社営業部第三課長代理山田太郎様宛請求書在中"),
        ("zh", "公司公布了季度业绩，董事会批准了新的年度投资计划。"),
        ("pl", "Firma przedstawiła wyniki kwartału, a zarząd zatwierdził nowy plan na rok."),
        ("en", "The board approved the annual budget and the new policy is in effect."),
        ("pt", "A empresa apresentou os resultados e o conselho aprovou o novo plano."),
        ("de", "Das Unternehmen hat die Ergebnisse vorgestellt und der Vorstand hat genehmigt."),
    ],
)
def test_language_identification(lang, text):
    assert detect_language(text)[0] == lang


def test_language_is_undetermined_without_stopword_evidence():
    words = " ".join(f"zork{i}" for i in range(40)) + " the"
    assert detect_language(words) == ("und", 0.0)


def test_html_implied_end_tags_keep_tables_and_lists():
    md = html_to_markdown("<ul><li>a<li>b</ul><table><tr><th>A<th>B<tr><td>1<td>2</table><p>x<p>y")
    assert "- a\n- b" in md and "| 1 | 2 |" in md and "x\n\ny" in md


def test_html_unclosed_paragraphs_and_deep_nesting_never_crash():
    md = html_to_markdown("<body>" + "".join(f"<p>para {i}" for i in range(3000)) + "</body>")
    assert md.count("para ") == 3000
    deep = html_to_markdown("<body>" + "<div>w " * 5000 + "</body>")
    assert deep.count("w") == 5000


def test_confluence_storage_is_not_given_implied_ends():
    xhtml = "<p>before<table><tbody><tr><td>c</td></tr></tbody></table>after</p>"
    assert "before" in html_to_markdown(xhtml, dialect="confluence")


def test_slack_rendering_and_markup_cleaning():
    users = {"U1": "Ann"}
    messages = [
        {
            "ts": "1767225600.000100",
            "user": "U1",
            "text": "hi <!here> see <#C1|general> and <https://x.io>",
        },
        {"ts": "1767225630.000200", "user": "U1", "text": "ping <!subteam^S1|@ops>"},
    ]
    chunk = messages_to_chunks("c", messages, users)[0]
    assert chunk.date == "2026-01-01"
    assert "00:00 Ann: hi @here see #general and https://x.io" in chunk.text
    assert "00:00 Ann: ping @ops" in chunk.text


def _flatten_reference(value, prefix="", max_depth=4):
    out = {}

    def walk(node, key, depth):
        if isinstance(node, dict) and node and depth < max_depth:
            for k, v in node.items():
                walk(v, f"{key}.{k}" if key else str(k), depth + 1)
        elif isinstance(node, list):
            if all(v is None or isinstance(v, str | int | float | bool) for v in node):
                out[key] = ", ".join(str(v) for v in node if v is not None)
            else:
                out[key] = json.dumps(node, ensure_ascii=False, separators=(",", ":"), default=str)
        elif isinstance(node, dict):
            out[key] = json.dumps(node, ensure_ascii=False, separators=(",", ":")) if node else None
        else:
            out[key] = node

    walk(value, prefix, 0)
    return out


def test_flatten_json_matches_the_recursive_walk():
    doc = {
        "a": {"b": {"c": {"d": {"e": 1}}}, "x": [1, None, "y"]},
        "z": [{"q": 1}],
        "e": {},
        "n": None,
    }
    assert flatten_json(doc) == _flatten_reference(doc)
    assert list(flatten_json(doc)) == list(_flatten_reference(doc))


def test_json_secondary_record_array_is_one_line_per_record():
    data = {
        "data": [{"id": i} for i in range(5)],
        "included": [{"id": "P1", "t": "x"}, {"id": "P2"}],
    }
    table = json_table(json.dumps(data))
    assert table.path == "data[]"
    assert table.context == [
        "included: 2 records",
        "included[1] id: P1 | t: x",
        "included[2] id: P2",
    ]


def test_polyglot_class_methods_become_symbols():
    ts = (
        "export class Svc {\n"
        "  public async run(a: number): Promise<number> {\n"
        "    if (a) {\n      return a;\n    }\n    return 0;\n  }\n"
        "  constructor() {\n  }\n}\n"
    )
    payload = process_polyglot_source(ts, "svc.ts")
    names = [(s.name, s.symbol_type, s.start_line, s.end_line) for s in payload.symbols]
    assert names == [
        ("Svc", "class", 1, 10),
        ("Svc.run", "method", 2, 7),
        ("Svc.constructor", "method", 8, 9),
    ]
    method = next(c for c in payload.chunks if c.symbol_name == "Svc.run")
    assert method.metadata["parent_class"] == "Svc" and "return 0;" in method.body_text


def test_polyglot_patterns_are_linear_on_long_space_runs():
    start = time.perf_counter()
    for n in (1500, 1900):
        process_polyglot_source("public" + " " * n + "x", "a.ts")
        process_polyglot_source("public static" + " " * n + "int x", "A.java")
    assert time.perf_counter() - start < 0.5


def test_extensionless_javascript_is_not_parsed_as_python():
    assert not _looks_python("import React from 'react';\nfunction a() {}\n")
    assert _looks_python("import os\n\nprint(os.name)\n")
    assert (
        process_code(
            "import x from 'y';\nfunction run() {\n  return 1;\n}\n", "script"
        ).metadata.language
        != "python"
    )


def test_mongo_flatten_cleans_once_with_identical_output():
    doc = {
        "_id": {"$oid": "abc"},
        "a": {"b": {"n": {"$numberLong": "5"}, "d": {"$date": "2026-01-01"}}},
    }
    doc["lines"] = [{"x": {"$numberInt": "1"}}, {"x": {"$numberInt": "2"}}]
    assert flatten_mongo_document(doc) == {
        "_id": "abc",
        "a.b.n": 5,
        "a.b.d": "2026-01-01",
        "lines[0].x": 1,
        "lines[1].x": 2,
    }


def test_adf_deep_nesting_keeps_every_text():
    node = {"type": "paragraph", "content": [{"type": "text", "text": "leaf"}]}
    for i in range(3000):
        item = {
            "type": "listItem",
            "content": [
                {"type": "paragraph", "content": [{"type": "text", "text": f"item{i}"}]},
                node,
            ],
        }
        node = {"type": "bulletList", "content": [item]}
    text = adf_to_markdown({"type": "doc", "content": [node]})
    assert "item0" in text and "item2999" in text and "leaf" in text
