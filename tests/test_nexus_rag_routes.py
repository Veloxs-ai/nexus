# Copyright 2026 Veloxs AI Inc.
# SPDX-License-Identifier: Apache-2.0
"""Document routing, map-reduce helpers and the grounding verifier (standard library only)."""

from __future__ import annotations

import time

from nexus.doc_routing import (
    candidate_documents,
    knowledge_index,
    mentions_in,
    question_mentions,
    rank_documents,
)
from nexus.grounding import (
    GroundingConfig,
    best_window,
    check_answer,
    cited_refs,
    split_claims,
    strip_unsupported,
)
from nexus.map_reduce import (
    Batch,
    Excerpt,
    coverage_note,
    excerpt,
    map_prompt,
    parse_map,
    plan_batches,
    reduce_groups,
    reduce_prompt,
)
from nexus.text_terms import key_tokens, numbers, query_words, question_terms, stem, terms

POLICY = (
    "Under the Finance Travel Policy, the approval limit is 45,000 USD and requests are "
    "answered within 9 business days."
)


# ---------------------------------------------------------------------------
# text_terms
# ---------------------------------------------------------------------------
def test_terms_stem_and_hyphen_parts():
    assert stem("expires") == stem("expired") == stem("expiring") == "expir"
    assert stem("policies") == "policy" and stem("business") == "business"
    got = terms("Term ends 2027-03-05. Auto-renew: yes.")
    assert {"2027", "2027-03-05", "auto-renew", "renew", "end"} <= got
    assert question_terms("List every contract that expires in 2027.") == [
        "contract",
        "expir",
        "2027",
    ]
    assert query_words("List every open P1 ticket, please.") == "open p1 ticket"


def test_numbers_and_keys():
    vals = {n.text: n for n in numbers("45,000 USD, 1.2 million, 45k, 12%, $3.50, 3 items, 2027")}
    assert vals["45,000"].value == 45000 and vals["45k"].tolerance == 500
    assert vals["1.2 million"].value == 1_200_000 and vals["12%"].percent
    assert vals["$3.50"].money and vals["3"].soft and vals["2027"].year
    assert numbers("C-1014 P1 2027-03-05 10:30") == []  # ids, dates and times are not numbers
    assert key_tokens("Ticket T-2001 is P1, ends 2027-03-05") == {"t-2001", "p1", "2027-03-05"}
    assert {"contract_c-1014", "c-1014"} <= key_tokens("contract_C-1014.md")
    assert vals["45k"].matches(numbers("45,000")[0]) and not vals["45,000"].matches(
        numbers("45,001")[0]
    )


# ---------------------------------------------------------------------------
# grounding
# ---------------------------------------------------------------------------
def test_split_claims_sentences_items_rows():
    ans = (
        "Hi! The limit is 45,000 USD [2]. Requests take 9 days. [2] e.g. one more [3].\n"
        "The matching records are: [4]\n- C-1014 ends 2027-03-05\n- C-1015 [5]\n\n"
        "| id | value |\n|---|---|\n| C-1 | 45k [2] |\n```\ncode [9]\n```"
    )
    claims = split_claims(ans)
    texts = [c.text for c in claims]
    assert texts == [
        "Hi!",
        "The limit is 45,000 USD.",
        "Requests take 9 days.",
        "e.g. one more.",
        "C-1014 ends 2027-03-05",
        "C-1015",
        "C-1; 45k",
    ]
    refs = [c.refs for c in claims]
    assert refs == [(), (2,), (2,), (3,), (4,), (5,), (2,)]  # item 1 inherits the intro's [4]
    assert cited_refs("a [2][3] b [3, 4] c [2]") == [2, 3, 4]


def test_check_supports_exact_and_flags_wrong_figure():
    report = check_answer(
        "The approval limit is 45,000 USD [1]. The approval limit is 90,000 USD [1].",
        {1: POLICY},
    )
    assert [c.status for c in report.checks] == ["supported", "unsupported"]
    assert "90,000" in report.checks[1].reason
    assert report.faithfulness == 0.5 and report.cited_refs == [1]


def test_check_paraphrase_uses_reranker_and_is_not_flagged():
    calls = []

    def score(query, passages):
        calls.append(query)
        return [0.93 for _ in passages]

    para = "Approvals are capped at forty-five thousand dollars for travel [1]."
    report = check_answer(para, {1: POLICY}, score=score)
    assert report.checks[0].status == "supported" and calls  # words alone were not enough
    assert check_answer(para, {1: POLICY}).checks[0].status in ("unverified", "unsupported")


def test_check_unrelated_unknown_citation_and_question_figures():
    def low(query, passages):
        return [0.01 for _ in passages]

    report = check_answer("The cafeteria opens at dawn [1]. Also see [7].", {1: POLICY}, score=low)
    assert [c.status for c in report.checks] == ["unsupported", "unsupported"]
    assert "not a source" in report.checks[1].reason
    # a figure the question states is not a claim the passage must contain
    ok = check_answer(
        "No: the approval limit is 45,000 USD, not 57,345 USD [1].",
        {1: POLICY},
        question="The limit is 57,345 USD, right?",
    )
    assert ok.checks[0].status == "supported"
    # small counts are derived, not quoted
    assert (
        check_answer("There are 3 policies with a limit [1].", {1: POLICY}).checks[0].missing == []
    )


def test_strip_unsupported_keeps_the_rest():
    ans = "The approval limit is 45,000 USD [1]. The penalty is 5% [1].\n- C-9 [1]"
    report = check_answer(ans, {1: POLICY})
    assert strip_unsupported(ans, report) == "The approval limit is 45,000 USD [1]."


def test_best_window_and_rerank_budget():
    passage = ("Filler sentence about nothing. " * 60) + POLICY + (" More filler here." * 40)
    window = best_window("approval limit 45,000 USD", passage, 300)
    assert "45,000" in window and len(window) <= 300
    calls = []
    ans = " ".join(f"Claim number {i} about travel approvals [1]." for i in range(5))
    check_answer(
        ans,
        {1: POLICY},
        score=lambda q, p: calls.append(q) or [0.9],
        config=GroundingConfig(max_rerank_claims=2),
    )
    assert len(calls) == 2


def test_grounding_speed():
    passages = {i: POLICY * 3 for i in range(1, 11)}
    ans = " ".join(
        f"The approval limit is 45,000 USD and answers take 9 days [{i}]." for i in range(1, 11)
    )
    start = time.perf_counter()
    for _ in range(20):
        check_answer(ans * 3, passages)
    assert (time.perf_counter() - start) / 20 < 0.05


# ---------------------------------------------------------------------------
# document routing
# ---------------------------------------------------------------------------
DOCS = [
    {
        "document_id": "1",
        "document_name": "contract_C-1000.md",
        "summary": "Contract with Acme. Ends 2027.",
    },
    {
        "document_id": "2",
        "document_name": "finance_travel_policy.md",
        "summary": "Approval limit for travel.",
    },
    {
        "document_id": "3",
        "document_name": "ticket_T-2000.md",
        "summary": "Ticket by Orion Retail. Priority P1.",
    },
    {
        "document_id": "4",
        "document_name": "hr_hiring_policy.md",
        "summary": "How hiring requests are approved.",
    },
]


def test_rank_documents_fuses_lists():
    ranked = rank_documents("travel approval limit policy", DOCS)
    assert ranked[0].id == "2" and "catalog" in ranked[0].reasons
    fused = rank_documents("anything", DOCS, vector=["4", "1"], chunks=["1"], named=["3"])
    assert [r.id for r in fused] == ["3", "1", "4"]
    everything = rank_documents("travel", DOCS, include_unmatched=True)
    assert everything[0].id == "2" and len(everything) == 4


def test_question_mentions():
    assert question_mentions("Which tickets and calls mention Orion Retail? List all.") == [
        "Orion Retail"
    ]
    assert question_mentions("How many P1 tickets are still open?") == ["P1"]
    assert question_mentions("List every contract that expires in 2027.") == []
    assert question_mentions('Everything about "Acme Corp" please') == ["Acme Corp"]
    assert question_mentions("Which tickets mention Globex?") == ["Globex"]
    assert mentions_in("Customer (Orion Retail): hello", ["orion retail", "P1"]) == ["orion retail"]
    assert mentions_in("Priority: P10", ["P1"]) == []


def test_candidate_documents_by_terms_mentions_and_vector():
    chunks = [
        {"document_id": "c1", "text": "Contract C-1. Term ends 2027-03-05."},
        {"document_id": "c2", "text": "Contract C-2. Term ends 2026-01-01."},
        {"document_id": "c3", "text": "Contract C-3. Term ends 2027-11-30."},
        {"document_id": "x", "text": "Budget for 2027 planning."},
    ] + [
        {"document_id": f"o{i}", "text": f"Contract C-{9 + i}. Term ends 2025-01-01."}
        for i in range(6)
    ]
    got = candidate_documents(
        "List every contract that expires in 2027.", chunks, total_documents=40
    )
    assert got.ids[:2] == ["c1", "c3"] and "c2" not in got.ids and got.route == "terms"
    assert "x" in got.ids  # "2027" is the rarer term: half the question's weight
    named = candidate_documents(
        "Which tickets mention Orion Retail?",
        chunks,
        total_documents=40,
        mention_hits={"t1": ["Orion Retail"], "t2": []},
        vector=["v"],
    )
    assert named.ids == ["t1"] and named.route == "mentions"
    vec = candidate_documents("q", [], total_documents=40, vector=["v1", "v2"], vector_extra=1)
    assert vec.ids == ["v1"] and vec.route == "vector"


def test_knowledge_index_budget():
    many = [
        {"document_name": f"doc_{i}.md", "summary": "x" * 300, "file_type": "md"}
        for i in range(500)
    ]
    text = knowledge_index(
        many[:30],
        total=500,
        counts={"md": 480, "table": 20},
        heading="Most relevant:",
        max_tokens=3000,
    )
    assert text.startswith("500 document(s) in this knowledge:") and "480 md, 20 table" in text
    assert len(text) <= 3000 * 4 and text.endswith("… and 470 more")
    small = knowledge_index(many[:2])
    assert "By type" not in small and small.count("\n- ") == 2


# ---------------------------------------------------------------------------
# map-reduce helpers
# ---------------------------------------------------------------------------
def _chunks(n, text="filler words only", hit_at=()):
    return [
        {
            "id": f"k{i}",
            "chunk_index": i,
            "text": ("Contract ends 2027." if i in hit_at else f"{text} {i}"),
            "token_count": 100,
        }
        for i in range(n)
    ]


def test_excerpt_whole_or_matching_parts():
    small = excerpt("contract 2027", "d1", "a.md", _chunks(3), max_tokens=600)
    assert small.whole and small.tokens == 300 and small.chunk_ids == ["k0", "k1", "k2"]
    big = excerpt("contract 2027", "d2", "b.md", _chunks(20, hit_at={7, 15}), max_tokens=300)
    assert not big.whole and big.chunk_ids == ["k0", "k7", "k15"] and "\n...\n" in big.text


def test_plan_batches_and_cost_cap():
    exs = [Excerpt(str(i), f"d{i}.md", "t", 400, True) for i in range(30)]
    plan = plan_batches(exs, batch_tokens=1000, batch_documents=12, max_documents=25)
    assert [len(b.excerpts) for b in plan.batches] == [2] * 12 + [1]
    assert plan.skipped == [str(i) for i in range(25, 30)] and plan.tokens == 25 * 400
    capped = plan_batches(exs, max_tokens=1000)
    assert sum(len(b.excerpts) for b in capped.batches) == 2 and len(capped.skipped) == 28


def test_map_prompt_parse_and_reduce():
    batch = Batch(
        [
            Excerpt("a", "a.md", "Auto-renew: yes", 5, True),
            Excerpt("b", "b.md", "Auto-renew: no", 5, False),
            Excerpt("c", "c.md", "x", 5, True),
        ]
    )
    prompt = map_prompt("Which auto-renew?", batch)
    assert "[D2] b.md (matching parts)" in prompt and prompt.startswith("QUESTION:")
    reply = "[D1] Auto-renew: yes\n  (C-1)\nD2: NONE\n[D3] n/a\n[D9] stray"
    found = parse_map(reply, batch)
    assert [(f.document_id, f.text) for f in found] == [("a", "Auto-renew: yes (C-1)")]
    groups = reduce_groups(found * 5, group_tokens=20)
    assert sum(len(g) for g in groups) == 5 and len(groups) > 1
    assert "[D1] a.md: Auto-renew: yes" in reduce_prompt("q", found)


def test_coverage_note():
    assert "Every one of the 600 candidate documents" in coverage_note(600, 600, 240)
    partial = coverage_note(400, 600, 150, "the cost limit was reached")
    assert partial.startswith("PARTIAL: read 400 of 600 candidate documents (the cost limit")
