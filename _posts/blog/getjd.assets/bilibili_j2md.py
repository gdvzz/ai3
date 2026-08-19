import json
import re
from datetime import datetime
from typing import List, Dict, Any


def parse_description(description: str) -> str:
    """解析职位描述，将序号转换为有序列表"""
    if not description:
        return description

    lines = description.split("\n")
    result_lines = []
    current_list = []
    in_list = False

    for line in lines:
        line = line.strip()
        if not line:
            if in_list and current_list:
                # 结束列表
                result_lines.append("\n".join(current_list))
                current_list = []
                in_list = False
            result_lines.append("")
            continue

        # 检查是否以数字开头（有序列表）
        # 匹配模式：数字. 或 数字、 或 数字)
        match = re.match(r"^(\d+)[\.、\)]\s*(.*)", line)
        if match:
            if not in_list:
                in_list = True
            num = match.group(1)
            content = match.group(2).strip()
            current_list.append(f"{num}. {content}")
        else:
            # 如果当前在列表中，先结束列表
            if in_list and current_list:
                result_lines.append("\n".join(current_list))
                current_list = []
                in_list = False
            result_lines.append(line)

    # 处理最后的列表
    if in_list and current_list:
        result_lines.append("\n".join(current_list))

    # 清理多余的空行
    final_result = []
    prev_empty = False
    for line in result_lines:
        if line == "":
            if not prev_empty:
                final_result.append("")
                prev_empty = True
        else:
            final_result.append(line)
            prev_empty = False

    return "\n".join(final_result)


def format_date(push_time: str) -> str:
    """格式化日期，只显示年月日"""
    try:
        # 尝试解析日期
        dt = datetime.strptime(push_time, "%Y-%m-%d %H:%M:%S")
        return dt.strftime("%Y年%m月%d日")
    except:
        return push_time.split(" ")[0] if " " in push_time else push_time


def json_to_md(json_file: str, md_file: str):
    """将JSON文件转换为MD文档"""

    # 读取JSON数据
    with open(json_file, "r", encoding="utf-8") as f:
        jobs = json.load(f)

    # 按 post_code_name 分组
    groups = {}
    for job in jobs:
        post_code = job.get("post_code_name", "未分类")
        if post_code not in groups:
            groups[post_code] = []
        groups[post_code].append(job)

    # 生成MD内容
    md_content = []

    # 标题
    md_content.append("# B站校园招聘岗位信息")
    md_content.append("")
    md_content.append(f"**总岗位数：{len(jobs)}**")
    md_content.append("")

    # 按岗位类型分类
    md_content.append("## 📋 岗位分类索引")
    md_content.append("")

    for post_code, job_list in sorted(groups.items()):
        md_content.append(f"### {post_code} ({len(job_list)}个)")
        md_content.append("")
        for job in job_list:
            position_name = job.get("position_name", "未知岗位")
            # 只显示岗位名称，不加链接
            md_content.append(f"- {position_name}")
        md_content.append("")

    md_content.append("---")
    md_content.append("")

    # 输出每个岗位的详细信息
    md_content.append("## 📝 岗位详情")
    md_content.append("")

    for idx, job in enumerate(jobs, 1):
        # 岗位名称（2级标题）
        position_name = job.get("position_name", "未知岗位")
        md_content.append(f"## {position_name}")
        md_content.append("")

        # 基本信息
        work_location = job.get("work_location", "未指定")
        position_type = job.get("position_type", "未指定")
        post_code_name = job.get("post_code_name", "未指定")
        push_time = format_date(job.get("push_time", ""))

        md_content.append(
            f"`{work_location}` \\| `{position_type}` \\| `{post_code_name}` \\| `{push_time} 发布`"
        )
        md_content.append("")

        # 职位描述
        description = job.get("position_description", "暂无描述")
        parsed_description = parse_description(description)
        if parsed_description:
            md_content.append(parsed_description)
            md_content.append("")

        # 官网投递链接
        detail_url = job.get("detail_url", "#")
        md_content.append(f"[官网投递↗]({detail_url})")
        md_content.append("")

        # 添加分隔线（除了最后一个）
        if idx < len(jobs):
            md_content.append("---")
            md_content.append("")

    # 写入MD文件
    with open(md_file, "w", encoding="utf-8") as f:
        f.write("\n".join(md_content))

    print(f"✅ MD文档已生成：{md_file}")
    print(f"📊 总岗位数：{len(jobs)}")
    print(f"📂 岗位分类：{len(groups)} 个类别")

    # 显示处理样例（前3个岗位）
    print("\n" + "=" * 60)
    print("📌 处理样例（前3个岗位）")
    print("=" * 60)

    for i, job in enumerate(jobs[:3], 1):
        print(f"\n{i}. 岗位名称：{job.get('position_name')}")
        print(f"   工作地点：{job.get('work_location')}")
        print(f"   岗位类型：{job.get('position_type')}")
        print(f"   职位类别：{job.get('post_code_name')}")
        print(f"   发布时间：{format_date(job.get('push_time', ''))}")
        desc = job.get("position_description", "")
        desc_preview = desc[:100] + "..." if len(desc) > 100 else desc
        print(f"   职位描述：{desc_preview}")
        print(f"   详情链接：{job.get('detail_url')}")


def main():
    # 配置文件名
    json_file = "bilibili_jobs_y27fa.json"
    md_file = "bilibili_jobs_y27fa.md"

    try:
        json_to_md(json_file, md_file)
    except FileNotFoundError:
        print(f"❌ 错误：找不到文件 {json_file}")
        print("请先运行抓取程序生成JSON文件")
    except json.JSONDecodeError as e:
        print(f"❌ 错误：JSON格式错误 - {e}")
    except Exception as e:
        print(f"❌ 错误：{e}")


if __name__ == "__main__":
    main()
