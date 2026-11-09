"""评分细则匹配引擎。

将 PDF 解析出的评分细则匹配到题库已有题目，支持人工修正后批量提交。

匹配优先级：
  1. 题号精确匹配（confidence=1.0）
  2. 题干相似度匹配（Jaccard 系数 / 包含比）
  3. 知识点加权匹配（+0.3）

置信度阈值 CONFIDENCE_THRESHOLD=0.6，低于阈值标记 low_confidence。
已有评分细则的题目标记 skipped（去重）。
无候选题目标记 manual_match。

安全约束：仅读 question_services / note_services，不写库。
"""
import re

# 置信度阈值
CONFIDENCE_THRESHOLD = 0.6
# 已有备注相似度阈值（达到即视为"基本一致"，交用户在覆盖/追加/跳过中选择）
SIMILARITY_THRESHOLD = 0.75
# 候选数量上限
CANDIDATE_LIMIT = 1000


class CandidateTooLargeError(Exception):
    """候选题目数量超限。"""
    pass


def _tokenize(text):
    """简单中文分词：按非汉字非字母非数字字符切分，过滤空 token。"""
    if not text:
        return set()
    # 按非汉字字母数字下划线切分
    tokens = re.split(r"[^\u4e00-\u9fa5a-zA-Z0-9]+", text)
    return set(t for t in tokens if t)


def _char_ngrams(text, n=2):
    """字符级 n-gram 集合（适用于中文无分隔符文本）。"""
    if not text or len(text) < n:
        return set()
    return set(text[i:i + n] for i in range(len(text) - n + 1))


def _jaccard(set_a, set_b):
    """Jaccard 相似度。"""
    if not set_a or not set_b:
        return 0.0
    inter = len(set_a & set_b)
    union = len(set_a | set_b)
    return inter / union if union else 0.0


def _containment_ratio(needle, haystack):
    """needle 关键词在 haystack 中的包含比。"""
    if not needle:
        return 0.0
    matched = sum(1 for t in needle if t in haystack)
    return matched / len(needle)


def _text_similarity(text_a, text_b):
    """文本相似度：综合词级 Jaccard、字符级 2-gram Jaccard、包含比。"""
    if not text_a or not text_b:
        return 0.0
    tokens_a = _tokenize(text_a)
    tokens_b = _tokenize(text_b)
    # 词级 Jaccard
    sim1 = _jaccard(tokens_a, tokens_b)
    # 字符级 2-gram Jaccard（中文友好）
    ng_a = _char_ngrams(text_a, 2)
    ng_b = _char_ngrams(text_b, 2)
    sim2 = _jaccard(ng_a, ng_b)
    # 包含比（短文本在长文本中的覆盖）
    sim3 = max(_containment_ratio(tokens_a, tokens_b),
               _containment_ratio(tokens_b, tokens_a))
    # 子串包含检查
    sim4 = 1.0 if (text_a in text_b or text_b in text_a) and len(text_a) > 2 and len(text_b) > 2 else 0.0
    return max(sim1, sim2, sim3, sim4)


def normalize_question_no(question_no):
    """提取题号主号（如 19(3) -> 19），用于题库题号匹配。"""
    text = str(question_no or "").strip()
    match = re.match(r"(\d+)", text)
    return match.group(1) if match else text


def _paper_type_match(rubric_paper, cand_paper):
    """卷种宽松匹配（包含关系），任一侧为空返回 False。"""
    if not rubric_paper or not cand_paper:
        return False
    a = str(rubric_paper).strip()
    b = str(cand_paper).strip()
    return a in b or b in a


def match_rubric_to_question(rubric_item, candidate_questions, confidence_threshold=CONFIDENCE_THRESHOLD):
    """单条细则匹配。

    Args:
        rubric_item: dict，含 rubric_question_no / rubric_knowledge / rubric_content（可选用于相似度）
        candidate_questions: list[dict]，每项含 questionID / question_no / content / paper_type / knowledge_modules
        confidence_threshold: 置信度阈值

    Returns:
        dict: {matched_question_id, confidence, features, status}
    """
    if not candidate_questions:
        return {
            "matched_question_id": None,
            "confidence": 0.0,
            "features": [],
            "status": "manual_match",
        }

    # 兼容两种字段命名：skill 内部用 rubric_*，Agent 工具入参用简短字段
    rubric_no = rubric_item.get("rubric_question_no") or rubric_item.get("question_no")
    rubric_knowledge = rubric_item.get("rubric_knowledge") or rubric_item.get("knowledge")
    rubric_content = rubric_item.get("rubric_content") or rubric_item.get("content", "")
    rubric_paper = str(rubric_item.get("paper_type") or "").strip()
    rubric_year = str(rubric_item.get("year") or "").strip()

    # 卷种/年份优先缩小候选，减少同题号跨卷误配
    scoped = list(candidate_questions)
    if rubric_paper:
        filtered = [c for c in scoped if _paper_type_match(rubric_paper, c.get("paper_type"))]
        if filtered:
            scoped = filtered
    if rubric_year:
        filtered = [c for c in scoped if str(c.get("year") or "").strip() == rubric_year]
        if filtered:
            scoped = filtered

    main_no = normalize_question_no(rubric_no) if rubric_no is not None else None
    same_no_count = 0
    for c in scoped:
        cand_no = c.get("question_no")
        if rubric_no is not None and (
            _question_no_match(rubric_no, cand_no)
            or (main_no and main_no != str(rubric_no).strip()
                and _question_no_match(main_no, cand_no))
        ):
            same_no_count += 1
    ambiguous = same_no_count > 1

    best_match = None
    best_conf = 0.0
    best_features = []

    for cand in scoped:
        features = []
        conf = 0.0
        cand_no = cand.get("question_no")
        exact_no = rubric_no is not None and _question_no_match(rubric_no, cand_no)
        main_no_match = (
            not exact_no and main_no is not None
            and main_no != str(rubric_no).strip()
            and _question_no_match(main_no, cand_no)
        )

        # 1. 题号匹配（原号 1.0，主号 0.9；卷种/年份不符降权）
        if exact_no or main_no_match:
            features.append("question_no" if exact_no else "question_no_main")
            conf = 1.0 if exact_no else 0.9
            cand_paper = cand.get("paper_type")
            cand_year = str(cand.get("year") or "").strip()
            if rubric_paper and not _paper_type_match(rubric_paper, cand_paper):
                conf = min(conf, 0.5)
                features.append("paper_type_mismatch")
            elif rubric_year and cand_year and cand_year != rubric_year:
                conf = min(conf, 0.5)
                features.append("year_mismatch")
        elif rubric_content:
            # 2. 题干相似度（细则与题干通常差异较大，仅作补充）
            sim = _text_similarity(rubric_content, cand.get("content", "") or "")
            if sim > conf:
                features = ["content_similarity"]
                conf = sim

        # 3. 知识点加权
        if rubric_knowledge and cand.get("knowledge_modules"):
            km = str(cand["knowledge_modules"])
            if rubric_knowledge in km:
                if "knowledge" not in features:
                    features.append("knowledge")
                conf = max(conf, 0.3)

        if conf > best_conf:
            best_conf = conf
            best_match = cand
            best_features = features

    if best_match is None or best_conf <= 0:
        return {
            "matched_question_id": None,
            "confidence": 0.0,
            "features": ["no_candidate"] if not candidate_questions else [],
            "status": "manual_match",
        }

    # 同题号多候选且无法用卷种/年份消歧时，降低置信度交人工核对
    if ambiguous:
        best_conf = min(best_conf, 0.5)
        best_features = best_features + ["ambiguous_question_no"]

    status = "pending" if best_conf >= confidence_threshold else "low_confidence"
    return {
        "matched_question_id": best_match["questionID"],
        "confidence": round(best_conf, 4),
        "features": best_features,
        "status": status,
    }


def _question_no_match(rubric_no, cand_no):
    """题号匹配（字符串比较，去除前后空格）。"""
    if rubric_no is None or cand_no is None:
        return False
    return str(rubric_no).strip() == str(cand_no).strip()


def _find_similar_note(rubric_content, notes, note_type_id):
    """在已有备注中找与本次细则最相似的一条（仅同类型）。

    返回 {note_id, content, similarity}，无同类型备注返回 None。
    """
    best = None
    for note in notes or []:
        if note_type_id and note.get("type_id") != note_type_id:
            continue
        similarity = _text_similarity(rubric_content, note.get("content", "") or "")
        if best is None or similarity > best["similarity"]:
            best = {
                "note_id": note.get("note_id"),
                "content": note.get("content", "") or "",
                "similarity": round(similarity, 4),
            }
    return best


def match_rubric_batch(rubrics, candidates, rubric_type_id,
                       confidence_threshold=CONFIDENCE_THRESHOLD,
                       existing_notes_loader=None,
                       similarity_threshold=SIMILARITY_THRESHOLD):
    """批量匹配。

    Args:
        rubrics: list[dict]，每条细则
        candidates: list[dict]，候选题目
        rubric_type_id: 评分细则备注类型 ID（用于筛选同类型已有备注）
        confidence_threshold: 置信度阈值
        existing_notes_loader: 可选函数 (question_id) -> list[dict]，读取该题已有备注；
            传入后对匹配到的题目做同类型备注内容相似度比对
        similarity_threshold: 相似度阈值，达到即标记 similar（已有基本一致的备注）

    Returns:
        list[dict]: 每条细则的匹配结果。similar 状态额外带
            existing_note_id / existing_content / similarity。

    Raises:
        CandidateTooLargeError: 候选数超 CANDIDATE_LIMIT
    """
    if len(candidates) > CANDIDATE_LIMIT:
        raise CandidateTooLargeError(
            "候选题目数 %d 超过上限 %d" % (len(candidates), CANDIDATE_LIMIT)
        )

    results = []
    for rubric in rubrics:
        result = match_rubric_to_question(rubric, candidates, confidence_threshold)
        # 已有同类型备注做内容相似度比对；同类备注允许共存，不做类型级跳过
        if (result["matched_question_id"] is not None
                and existing_notes_loader is not None):
            notes = existing_notes_loader(result["matched_question_id"])
            rubric_content = rubric.get("rubric_content") or rubric.get("content", "")
            similar = _find_similar_note(
                rubric_content, notes, rubric_type_id
            )
            if similar is not None and similar["similarity"] >= similarity_threshold:
                result["status"] = "similar"
                result["existing_note_id"] = similar["note_id"]
                result["existing_content"] = similar["content"]
                result["similarity"] = similar["similarity"]
                result["features"] = result.get("features", []) + ["similar_existing_note"]
        results.append({
            "rubric": rubric,
            **result,
        })
    return results
