#!/usr/bin/env python3
"""
离线生成/刷新知识模块画像（记忆文件）。

对每个模块，取题库中已标注该模块的题目样本，让 AI 总结该模块题目的典型特征，
输出到 data/knowledge_module_profile.json。该文件已被 .gitignore 忽略。

用法:
  python tools/build_tag_profile.py              # 生成画像（基于已有标注样本）
  python tools/build_tag_profile.py --sample 50  # 每个模块最多取50题样本（默认30）
  python tools/build_tag_profile.py --merge      # 与内置画像合并（保留内置作为兜底）
"""
import json
import os
import sqlite3
import sys
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.exam_type_utils import KNOWLEDGE_MODULES
from tools.tag_suggest import DEFAULT_MODULE_PROFILE, PROFILE_PATH, DB_PATH, _get_api_key

DEFAULT_BASE_URL = "https://api.deepseek.com/v1"
DEFAULT_MODEL = "deepseek-flash"
DEFAULT_SAMPLE = 30
CONTENT_TRUNCATE = 400


def _fetch_samples(module, limit, db_path=DB_PATH):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        "SELECT content FROM questions "
        "WHERE isInRecycleBin = 0 AND knowledge_modules LIKE ? "
        "ORDER BY questionID LIMIT ?",
        (f"%{module}%", limit),
    )
    rows = [r["content"] for r in cur.fetchall() if r["content"]]
    conn.close()
    return rows


def _generate_module_profile(module, samples, api_key, base_url, model):
    base = DEFAULT_MODULE_PROFILE.get(module, {})
    outline = base.get("outline", [])
    outline_text = "\n".join(outline) if outline else "（无）"
    samples_text = "\n\n".join(
        f"【题{i + 1}】{s[:CONTENT_TRUNCATE]}" for i, s in enumerate(samples)
    )

    messages = [
        {
            "role": "system",
            "content": (
                "你是高中政治学科专家。下面给你一个知识模块的教材章节结构（骨架）"
                "和已标注题目样本。请以教材章节结构为基础，结合样本题目补充该模块的典型特征。\n"
                "要求：\n"
                "- themes 必须覆盖教材各课的核心知识点，给 6-12 个主题词。\n"
                "- description 要体现教材结构脉络，结合样本中高频考法，150字以内。\n"
                '- 返回JSON：{"title": "教材主题名", "themes": ["关键词1","关键词2",...], '
                '"description": "该模块题目的典型特征描述"}'
            ),
        },
        {
            "role": "user",
            "content": (
                f"知识模块：{module}\n"
                f"教材章节结构（骨架）：\n{outline_text}\n\n"
                f"该模块已标注题目样本（共{len(samples)}题）：\n{samples_text}"
            ),
        },
    ]

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    url = f"{base_url.rstrip('/')}/chat/completions"
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "response_format": {"type": "json_object"},
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=90)
    except requests.RequestException as e:
        return None, f"网络请求失败: {e}"
    if resp.status_code != 200:
        return None, f"HTTP {resp.status_code}: {resp.text[:200]}"
    try:
        data = resp.json()
        return json.loads(data["choices"][0]["message"]["content"]), None
    except (ValueError, KeyError, IndexError) as e:
        return None, f"解析失败: {e}"


def main(sample_limit=DEFAULT_SAMPLE, merge=False):
    api_key = _get_api_key()
    if not api_key:
        print("错误：未配置 DEEPSEEK_API_KEY（环境变量或 secrets.toml）")
        return

    profile = dict(DEFAULT_MODULE_PROFILE) if merge else {}

    for module in KNOWLEDGE_MODULES:
        samples = _fetch_samples(module, sample_limit)
        if not samples:
            print(f"[{module}] 题库中无已标注样本，使用内置画像")
            profile[module] = DEFAULT_MODULE_PROFILE.get(module, {})
            continue

        print(f"[{module}] 分析 {len(samples)} 题样本...")
        result, err = _generate_module_profile(
            module, samples, api_key, DEFAULT_BASE_URL, DEFAULT_MODEL
        )
        if err:
            print(f"  失败：{err}，使用内置画像")
            profile[module] = DEFAULT_MODULE_PROFILE.get(module, {})
        else:
            profile[module] = result
            print(f"  完成：{result.get('title', '')} / "
                  f"{len(result.get('themes', []))} 个主题词")

    os.makedirs(os.path.dirname(PROFILE_PATH), exist_ok=True)
    with open(PROFILE_PATH, "w", encoding="utf-8") as f:
        json.dump(profile, f, ensure_ascii=False, indent=2)
    print(f"\n画像已保存至 {PROFILE_PATH}")


if __name__ == "__main__":
    _sample = DEFAULT_SAMPLE
    _merge = False
    for arg in sys.argv[1:]:
        if arg == "--merge":
            _merge = True
        elif arg == "--sample":
            pass
        elif arg.isdigit():
            _sample = int(arg)
    main(sample_limit=_sample, merge=_merge)
