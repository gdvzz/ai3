import json
import re
from pathlib import Path
from datetime import datetime


def convert_json_to_md(json_file_path: str, md_file_path: str = None):
    """
    将岗位JSON数据转换为Markdown文档
    """
    json_path = Path(json_file_path)

    if md_file_path is None:
        md_file_path = json_path.with_suffix(".md")
    else:
        md_file_path = Path(md_file_path)

    with open(json_path, "r", encoding="utf-8") as f:
        jobs = json.load(f)

    if not jobs:
        print("⚠️ JSON文件中没有数据")
        return

    # 处理每个岗位的描述
    for job in jobs:
        if job.get("job_description"):
            job["job_description"] = convert_description_to_list(job["job_description"])

    # 生成Markdown
    md_lines = []
    md_lines.append("# 华勤集团校园招聘岗位详情 (2027届)")
    md_lines.append("")
    md_lines.append(
        f"> 共 {len(jobs)} 个岗位 | 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    md_lines.append("")
    md_lines.append("---")
    md_lines.append("")

    for job in jobs:
        title = job.get("job_title", "未知岗位")
        md_lines.append(f"## {title}")
        md_lines.append("")

        info = job.get("job_info", "")
        if info:
            md_lines.append(f"`{info}`")
            md_lines.append("")

        description = job.get("job_description", "")
        if description:
            md_lines.append(description)
        else:
            md_lines.append("*（暂无职位描述）*")
        md_lines.append("")

        url = job.get("job_url", "#")
        md_lines.append(f"[官网投递↗]({url})")
        md_lines.append("")
        md_lines.append("---")
        md_lines.append("")

    md_path = json_path.with_suffix(".md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))

    print(f"✅ Markdown文档已生成: {md_path}")
    print(f"📊 共处理 {len(jobs)} 个岗位")


def convert_description_to_list(text: str) -> str:
    """
    将描述中的编号转换为Markdown有序列表
    支持多种编号格式：
    - 1、2、3、（中文顿号）
    - 1. 2. 3.（英文句号）
    - 1) 2) 3)（右括号）
    - 1。 2。 3。（中文句号）
    - 1， 2， 3，（中文逗号）
    - 一、二、三、（中文数字）
    """
    if not text:
        return ""

    # 先按换行分割
    lines = text.split("\n")
    result_lines = []

    for line in lines:
        stripped = line.strip()

        if not stripped:
            result_lines.append("")
            continue

        # 检查一行中是否包含多个编号
        # 匹配模式：编号 + 分隔符 + 内容 + 分隔符 + 下一个编号
        if re.search(
            r"\d+[、.。），;；]\s*[^。；]*[；。]\s*\d+[、.。），;；]", stripped
        ):
            # 尝试按编号分割
            parts = re.split(r"(?=\d+[、.。），])", stripped)
            for part in parts:
                if part.strip():
                    converted = convert_single_line(part.strip())
                    if converted:
                        result_lines.append(converted)
        else:
            converted = convert_single_line(stripped)
            if converted:
                result_lines.append(converted)

    # 如果上面的方法没有产生有效结果（比如所有内容在一行且没有分号分割）
    # 尝试更激进的分割方式
    if len(result_lines) <= 1 and text:
        result_lines = convert_long_text(text)

    return "\n".join(result_lines)


def convert_single_line(line: str) -> str:
    """
    转换单行文本中的编号
    """
    stripped = line.strip()

    if not stripped:
        return ""

    # 匹配阿拉伯数字 + 多种分隔符：、.。），)）
    match = re.match(r"^(\d+)[、.。），)）]", stripped)
    if match:
        num = match.group(1)
        content = re.sub(r"^\d+[、.。），)）]", "", stripped).strip()
        return f"{num}. {content}"

    # 匹配中文数字编号：一、 二. 三。
    match = re.match(r"^([一二三四五六七八九十]+)[、.。）]", stripped)
    if match:
        cn_num = match.group(1)
        num_map = {
            "一": "1",
            "二": "2",
            "三": "3",
            "四": "4",
            "五": "5",
            "六": "6",
            "七": "7",
            "八": "8",
            "九": "9",
            "十": "10",
        }
        num = num_map.get(cn_num, "1")
        content = re.sub(r"^[一二三四五六七八九十]+[、.。）]", "", stripped).strip()
        return f"{num}. {content}"

    # 匹配子编号：a. b. c. 或 (1) (2) (3)
    if re.match(r"^[a-z]\.", stripped):
        content = re.sub(r"^[a-z]\.", "", stripped).strip()
        return f"   - {content}"

    if re.match(r"^\([0-9]+\)", stripped):
        content = re.sub(r"^\([0-9]+\)", "", stripped).strip()
        return f"   - {content}"

    # 普通文本行，原样保留
    return stripped


def convert_long_text(text: str) -> list:
    """
    专门处理没有换行的长文本
    按编号分割成多行
    """
    # 按编号分割（支持多种分隔符）
    # 匹配模式：数字 + 分隔符（、.。），)）等）
    parts = re.split(r"(?=\d+[、.。），)）])", text)

    result = []
    for part in parts:
        part = part.strip()
        if not part:
            continue

        # 检查是否以编号开头
        if re.match(r"^\d+[、.。），)）]", part):
            converted = convert_single_line(part)
            if converted:
                result.append(converted)
        else:
            # 如果没有编号，可能是标题或普通文本
            result.append(part)

    return result


if __name__ == "__main__":
    convert_json_to_md("huaqin_fy27fa.json")
