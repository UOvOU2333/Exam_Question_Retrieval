"""备注内容格式规范化（AI 生成 → 参考已有备注排版）。

只做排版，不改写原文措辞与赋分信息：
  - 评分细则以【评分细则】标题开头
  - ①②③④ 分点各占一行
  - “等级量表：水平4…／水平3…”转为 Markdown 表格
  - 保留【超越下水示例】等原文段落
"""
import re

_SCALE_HEADER = re.compile(r"等级量表[：:]?\s*")
_LEVEL_MARK = re.compile(r"水平\s*([1-4])\s*[（(]([^）)]*)[）)]")
_REF_MARK = re.compile(r"以上[①②③④]\s*[—\-–]\s*[①②③④]")
_MARKERS = "①②③④"


def _split_marker_line(line):
    """把同一行内的多个 ①②③④ 分点拆成多行；表格行和“以上①—③”引用行不拆。"""
    if line.strip().startswith("|"):
        return [line]

    refs = _REF_MARK.findall(line)
    protected = line
    for idx, ref in enumerate(refs):
        protected = protected.replace(ref, "@@REF%d@@" % idx, 1)

    marker_count = sum(protected.count(marker) for marker in _MARKERS)
    starts_with_marker = line.lstrip().startswith(tuple(_MARKERS))
    if marker_count == 0 or (marker_count == 1 and starts_with_marker):
        return [line]

    parts = re.split(r"(?=[①②③④])", protected)
    merged = []
    for part in parts:
        if not part:
            continue
        if merged and re.match(r"^[①②③④]", part):
            prev = merged[-1].rstrip()
            # “以上①—③”这类引用保持原样
            if prev.endswith("以上") or re.match(r"^[①②③④][—\-–]", part):
                merged[-1] += part
                continue
        merged.append(part)

    restored = []
    for part in merged:
        for idx, ref in enumerate(refs):
            part = part.replace("@@REF%d@@" % idx, ref)
        restored.append(part)
    return restored


def _cell(text):
    return (text or "").replace("|", "／").strip()


def _convert_level_scale(text):
    """把“等级量表：水平4…／水平3…”转成 Markdown 表格。"""
    match = _SCALE_HEADER.search(text)
    if not match:
        return text
    start = match.start()
    scale_start = match.end()
    # 量表段到下一个【标题】或文末
    next_section = text.find("【", scale_start)
    scale_end = next_section if next_section != -1 else len(text)
    scale_text = text[scale_start:scale_end].strip()
    levels = list(_LEVEL_MARK.finditer(scale_text))
    if len(levels) < 2:
        return text

    rows = []
    for idx, level in enumerate(levels):
        level_no = level.group(1)
        label = level.group(2).strip()
        seg_end = levels[idx + 1].start() if idx + 1 < len(levels) else len(scale_text)
        body = scale_text[level.end():seg_end].strip(" ；;，,。\n")
        points = [p.strip(" ；;，,。") for p in re.split(r"[／/]", body)]
        points = [p for p in points if p][:4]
        while len(points) < 4:
            points.append("")
        rows.append((level_no, label, points))

    table = [
        "| 等级 | 评分点1 | 评分点2 | 评分点3 | 评分点4 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for level_no, label, points in rows:
        level_name = "水平%s（%s）" % (level_no, label) if label else "水平%s" % level_no
        table.append("| %s | %s |" % (
            _cell(level_name), " | ".join(_cell(p) for p in points),
        ))
    return text[:start] + "\n".join(table) + text[scale_end:]


def normalize_rubric_content(content):
    """规范化评分细则备注排版；幂等，已有规范表格不会重复转换。"""
    if not content or not content.strip():
        return content
    text = content.strip()
    # 去掉复制/展示用标签（如“本次细则”）
    text = re.sub(r"^\s*本次细则\s*\n+", "", text, count=1)
    # 标题前有杂项时，从标题处截取，避免重复添加标题
    title_idx = text.find("【评分细则】")
    if title_idx > 0:
        text = text[title_idx:]
    has_table = bool(re.search(r"^\|\s*等级\s*\|", text, flags=re.MULTILINE))

    if not text.startswith("【评分细则】"):
        if "评分细则" in text or "评分标准" in text or text.startswith("本题"):
            text = "【评分细则】\n\n" + text

    lines = []
    for line in text.split("\n"):
        lines.extend(_split_marker_line(line))
    text = "\n".join(lines)

    if not has_table:
        text = _convert_level_scale(text)
    return text.strip()