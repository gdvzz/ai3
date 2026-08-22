import json
import re
from collections import defaultdict


def convert_detail_to_md(detail_text):
    """
    将 job_detail 中的有序列表（如 1、2、3、 或 1. 2. 3.）
    转换为 Markdown 有序列表，保留原数字。
    """
    if not detail_text:
        return ""
    lines = detail_text.split("\n")
    new_lines = []
    for line in lines:
        # 匹配行首的数字序号，如 "1、", "1.", "1、"（含空格）
        match = re.match(r"^(\d+)[、.。]\s*", line)
        if match:
            num = match.group(1)
            rest = line[match.end() :]
            new_lines.append(f"{num}. {rest}")
        else:
            new_lines.append(line)
    return "\n".join(new_lines)


def generate_md_from_json(json_file, md_file):
    with open(json_file, "r", encoding="utf-8") as f:
        jobs = json.load(f)

    # 按 job_category 分组
    categories = defaultdict(list)
    for job in jobs:
        cat = job.get("job_category", "未分类")
        categories[cat].append(job)

    # 开始构建 Markdown
    md_lines = []
    md_lines.append("# 海能达校招岗位总览")
    md_lines.append("")
    md_lines.append("## 岗位分类目录")
    md_lines.append("")
    # 按分类列出岗位（仅文本，无链接）
    for cat, job_list in sorted(categories.items()):
        md_lines.append(f"### {cat}")
        for job in job_list:
            title = job.get("title", "无标题")
            md_lines.append(f"- {title}")  # 不再使用链接
        md_lines.append("")

    md_lines.append("---")
    md_lines.append("")

    # 遍历所有岗位生成详情
    for job in jobs:
        title = job.get("title", "无标题")
        job_type = job.get("job_type", "")
        job_category = job.get("job_category", "")
        location = job.get("location", "")
        detail = job.get("job_detail", "")
        detail_url = job.get("detail_url", "#")

        # 二级标题
        md_lines.append(f"## {title}")
        md_lines.append("")

        # 信息行：使用 \| 分隔（用户要求）
        info_parts = []
        if job_type:
            info_parts.append(f"`{job_type}`")
        if job_category:
            info_parts.append(f"`{job_category}`")
        if location:
            info_parts.append(f"`{location}`")
        # 用 " \\| " 连接，使得源码中显示为 \|，渲染为 |
        md_lines.append(" \\| ".join(info_parts))
        md_lines.append("")

        # 转换 detail 中的列表
        detail_md = convert_detail_to_md(detail)
        if detail_md:
            md_lines.append(detail_md)
            md_lines.append("")

        # 官网投递链接
        md_lines.append(f"[官网投递↗]({detail_url})")
        md_lines.append("")
        md_lines.append("---")
        md_lines.append("")

    # 写入文件
    with open(md_file, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))

    print(f"✅ Markdown 文档已生成：{md_file}")


if __name__ == "__main__":
    generate_md_from_json("hytera_y27fa.json", "hytera_y27fa.md")
