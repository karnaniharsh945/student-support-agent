from pathlib import Path

import pytest

from services.policy_retrieval import PolicyRetriever, chunk_markdown

POLICY = Path(__file__).resolve().parent.parent / "data" / "student_policy.md"


@pytest.fixture(scope="module")
def retriever():
    return PolicyRetriever(POLICY)


def test_chunks_have_metadata(retriever):
    assert len(retriever.chunks) >= 8
    c = retriever.chunks[0]
    assert c.document == "student_policy.md" and c.chunk_id.startswith("policy-s") and c.section_title


def test_disclaimer_not_indexed():
    text = POLICY.read_text()
    assert all("SYNTHETIC" not in c.text for c in chunk_markdown(text, "x"))


@pytest.mark.parametrize("query,chunk", [
    ("The payment portal failed. Can I pay on the next working day?", "policy-s2-c1"),
    ("What is the late fee?", "policy-s3-c1"),
    ("How long does scholarship review take?", "policy-s4-c1"),
    ("Can I change my elective course?", "policy-s5-c1"),
    ("Who do I escalate to?", "policy-s7-c1"),
])
def test_relevant_chunk_is_top_hit(retriever, query, chunk):
    res = retriever.search(query)
    assert res.sufficient and res.hits[0].chunk_id == chunk


@pytest.mark.parametrize("query", ["What are the hostel curfew timings?", "What is the hostel fee?",
                                   "can I get a refund if I withdraw", "what are the library opening hours", "???"])
def test_insufficient_evidence_is_reported(retriever, query):
    assert retriever.search(query).sufficient is False


def test_not_whole_document_returned(retriever):
    res = retriever.search("What is the late fee?", top_k=3)
    assert len(res.hits) < len(retriever.chunks)
