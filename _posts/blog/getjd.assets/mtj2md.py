import json
import re
from datetime import datetime
from typing import List, Dict, Any
from collections import defaultdict


def parse_json_to_md(input_json_file: str, output_md_file: str):
    """
    将美团岗位JSON数据转换为Markdown格式文档

    Args:
        input_json_file: 输入的JSON文件路径
        output_md_file: 输出的Markdown文件路径
    """
    # 1. 读取JSON文件
    try:
        with open(input_json_file, "r", encoding="utf-8") as f:
            jobs = json.load(f)
        if not isinstance(jobs, list):
            jobs = [jobs]
    except FileNotFoundError:
        print(f"❌ 错误：找不到文件 {input_json_file}")
        return
    except json.JSONDecodeError as e:
        print(f"❌ 错误：JSON解析失败 - {e}")
        return

    if not jobs:
        print("⚠️ 警告：JSON文件为空")
        return

    # 2. 按 job_family 分组
    family_groups = defaultdict(list)
    for job in jobs:
        family = job.get("job_family", "未分类")
        family_groups[family].append(job)

    # 3. 生成Markdown内容
    md_lines = []
    md_lines.append("# 美团校园招聘岗位详情\n")

    # 3.1 生成岗位索引
    md_lines.append("## 📋 岗位索引\n")

    # 按 job_family 名称排序
    for family in sorted(family_groups.keys()):
        jobs_in_family = family_groups[family]
        total_count = len(jobs_in_family)
        md_lines.append(f"### {family}（{total_count}个）\n")

        # ✅ 判断：如果是"技术类"，按 job_family_group 细分
        if family == "技术类":
            # 按 job_family_group 分组
            group_dict = defaultdict(list)
            for job in jobs_in_family:
                group = job.get("job_family_group", "其他")
                group_dict[group].append(job)

            # 按 group 名称排序
            for group in sorted(group_dict.keys()):
                jobs_in_group = group_dict[group]
                md_lines.append(f"#### {group}（{len(jobs_in_group)}个）\n")

                for job in sorted(jobs_in_group, key=lambda x: x.get("job_name", "")):
                    job_name = job.get("job_name", "未知岗位")
                    anchor = generate_anchor(job_name)
                    md_lines.append(f"- [{job_name}](#{anchor})")
                md_lines.append("")
        else:
            # ✅ 非技术类：直接列出岗位
            for job in sorted(jobs_in_family, key=lambda x: x.get("job_name", "")):
                job_name = job.get("job_name", "未知岗位")
                anchor = generate_anchor(job_name)
                md_lines.append(f"- [{job_name}](#{anchor})")
            md_lines.append("")

        md_lines.append("")

    md_lines.append("---\n")

    # 3.2 输出每个岗位的详细信息
    for idx, job in enumerate(jobs, 1):
        job_name = job.get("job_name", "未知岗位")
        anchor = generate_anchor(job_name)
        md_lines.append(f"## {job_name}\n")

        # 元信息行
        job_family = job.get("job_family", "")
        job_group = job.get("job_family_group", "")
        family_display = (
            f"{job_family} > {job_group}"
            if job_family and job_group
            else job_family or job_group or ""
        )

        cities = job.get("cities", [])
        if cities:
            cities_sorted = sort_chinese_by_pinyin(cities)
            cities_display = " / ".join(cities_sorted)
        else:
            cities_display = ""

        refresh_time = job.get("refresh_time")
        if refresh_time:
            try:
                if isinstance(refresh_time, (int, float)):
                    dt = datetime.fromtimestamp(refresh_time / 1000)
                else:
                    dt = datetime.fromisoformat(
                        str(refresh_time).replace("Z", "+00:00")
                    )
                time_display = dt.strftime("%Y-%m-%d")
            except:
                time_display = str(refresh_time)
        else:
            time_display = ""

        meta_parts = []
        if family_display:
            meta_parts.append(f"`{family_display}`")
        if cities_display:
            meta_parts.append(f"`{cities_display}`")
        if time_display:
            meta_parts.append(f"`{time_display}`")

        md_lines.append(" \\| ".join(meta_parts) + "\n")

        # 岗位职责
        job_duty = job.get("job_duty", "")
        if job_duty:
            md_lines.append("**岗位职责**\n")
            md_lines.append(format_with_numbers(job_duty) + "\n")

        # 任职要求
        job_requirement = job.get("job_requirement", "")
        if job_requirement:
            md_lines.append("**任职要求**\n")
            md_lines.append(format_with_numbers(job_requirement) + "\n")

        # 官网投递链接
        job_url = job.get("job_url", "")
        if job_url:
            md_lines.append(f"[官网投递↗]({job_url})\n")

        if idx < len(jobs):
            md_lines.append("---\n")

    # 4. 写入Markdown文件
    with open(output_md_file, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))

    print(f"✅ 成功转换 {len(jobs)} 个岗位到 {output_md_file}")

    # 5. 输出统计信息
    print("\n📊 岗位分类统计：")
    for family in sorted(family_groups.keys()):
        jobs_in_family = family_groups[family]
        print(f"  - {family}: {len(jobs_in_family)} 个")
        # 如果是技术类，显示子分类统计
        if family == "技术类":
            group_dict = defaultdict(list)
            for job in jobs_in_family:
                group = job.get("job_family_group", "其他")
                group_dict[group].append(job)
            for group in sorted(group_dict.keys()):
                print(f"      └─ {group}: {len(group_dict[group])} 个")


def generate_anchor(text: str) -> str:
    """生成Markdown锚点"""
    anchor = (
        text.replace(" ", "_")
        .replace("（", "_")
        .replace("）", "_")
        .replace("(", "_")
        .replace(")", "_")
    )
    anchor = re.sub(r"[^\w\u4e00-\u9fa5_-]", "", anchor)
    return anchor


def sort_chinese_by_pinyin(texts: List[str]) -> List[str]:
    """对中文文本列表按拼音排序"""
    try:
        from pypinyin import pinyin, Style

        def get_pinyin(text: str) -> str:
            pinyins = pinyin(text, style=Style.FIRST_LETTER)
            return "".join([p[0].lower() for p in pinyins])

        return sorted(texts, key=get_pinyin)

    except ImportError:
        try:
            import locale

            locale.setlocale(locale.LC_ALL, "zh_CN.UTF-8")
            return sorted(texts, key=locale.strxfrm)
        except:
            return sorted(texts)


def format_with_numbers(text: str) -> str:
    """将包含数字序号的文本转换为有序列表，不添加额外样式"""
    if not text:
        return ""

    lines = text.split("\n")
    formatted_lines = []
    i = 0

    while i < len(lines):
        line = lines[i].strip()
        if not line:
            formatted_lines.append("")
            i += 1
            continue

        match = re.match(r"^(\d+)[\.、]\s*(.*)", line)
        if match:
            num = match.group(1)
            content = match.group(2)

            if not content and i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                if next_line and not re.match(r"^(\d+)[\.、]", next_line):
                    content = next_line
                    i += 1

            formatted_lines.append(f"{num}. {content}")
            i += 1
        else:
            formatted_lines.append(line)
            i += 1

    return "\n".join(formatted_lines)


def main():
    """主函数"""
    import sys

    default_input = "meituan_jobs_api.json"
    default_output = "meituan_jobs.md"

    if len(sys.argv) >= 2:
        input_file = sys.argv[1]
    else:
        input_file = default_input

    if len(sys.argv) >= 3:
        output_file = sys.argv[2]
    else:
        if input_file.endswith(".json"):
            output_file = input_file.replace(".json", ".md")
        else:
            output_file = default_output

    print(f"📖 读取JSON文件: {input_file}")
    parse_json_to_md(input_file, output_file)


if __name__ == "__main__":
    main()
