"""评分细则匹配引擎单元测试。"""
from chains.rubric_matcher import (
    match_rubric_to_question,
    match_rubric_batch,
    CONFIDENCE_THRESHOLD,
    SIMILARITY_THRESHOLD,
    CandidateTooLargeError,
)


def _candidate(qid, qno, content, km=""):
    return {"questionID": qid, "question_no": qno, "content": content,
            "paper_type": "a", "knowledge_modules": km}


def test_question_no_exact_match():
    """题号精确匹配 confidence=1.0。"""
    r = match_rubric_to_question(
        {"rubric_question_no": "3", "rubric_content": "", "rubric_knowledge": None},
        [_candidate(1, "3", "x")],
    )
    assert r["matched_question_id"] == 1
    assert r["confidence"] == 1.0
    assert r["features"] == ["question_no"]
    assert r["status"] == "pending"


def test_content_similarity_match():
    """题干相似度匹配。"""
    r = match_rubric_to_question(
        {"rubric_question_no": None, "rubric_content": "全过程人民民主是社会主义民主", "rubric_knowledge": None},
        [_candidate(2, "5", "全过程人民民主是社会主义民主的本质特征")],
    )
    assert r["matched_question_id"] == 2
    assert r["confidence"] > 0
    assert "content_similarity" in r["features"]


def test_low_confidence():
    """置信度低于阈值标记 low_confidence。"""
    r = match_rubric_to_question(
        {"rubric_question_no": None, "rubric_content": "abc", "rubric_knowledge": None},
        [_candidate(2, "5", "xyz")],
    )
    assert r["status"] in ("low_confidence", "manual_match")


def test_no_candidate_manual_match():
    """无候选题目标记 manual_match。"""
    r = match_rubric_to_question(
        {"rubric_question_no": "1", "rubric_content": "", "rubric_knowledge": None},
        [],
    )
    assert r["status"] == "manual_match"
    assert r["matched_question_id"] is None


def test_knowledge_weighted():
    """知识点匹配加权。"""
    r = match_rubric_to_question(
        {"rubric_question_no": None, "rubric_content": "经济", "rubric_knowledge": "经济生活"},
        [_candidate(3, "7", "政治生活", km="经济生活,政治生活")],
    )
    assert r["matched_question_id"] == 3


def test_batch_similar_existing_note():
    """已有同类型且内容基本一致 → similar，附带相似度与已有备注信息。"""
    rubrics = [{"question_no": "1", "content": "第一点，第二点，第三点。"}]
    candidates = [_candidate(10, "1", "x")]
    results = match_rubric_batch(
        rubrics, candidates, rubric_type_id=1,
        existing_notes_loader=lambda qid: [
            {"note_id": 99, "type_id": 1, "content": "第一点，第二点，第三点。"},
        ],
    )
    r = results[0]
    assert r["status"] == "similar"
    assert r["existing_note_id"] == 99
    assert r["similarity"] >= SIMILARITY_THRESHOLD


def test_batch_same_type_different_content_not_skipped():
    """同类备注内容不同不应跳过（同类可共存，允许追加）。"""
    rubrics = [{"question_no": "1", "content": "第一点，第二点，第三点。"}]
    candidates = [_candidate(10, "1", "x")]
    results = match_rubric_batch(
        rubrics, candidates, rubric_type_id=1,
        existing_notes_loader=lambda qid: [
            {"note_id": 99, "type_id": 1, "content": "完全不同的另一份细则内容。"},
        ],
    )
    assert results[0]["status"] == "pending"


def test_candidate_too_large():
    """候选超限抛异常。"""
    rubrics = [{"rubric_question_no": "1", "rubric_content": "", "rubric_knowledge": None}]
    candidates = [_candidate(i, str(i), "x") for i in range(1001)]
    try:
        match_rubric_batch(rubrics, candidates, rubric_type_id=1)
        assert False, "应抛 CandidateTooLargeError"
    except CandidateTooLargeError:
        pass
