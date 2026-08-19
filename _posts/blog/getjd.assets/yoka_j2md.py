import json
import re
from pathlib import Path


def json_to_markdown(json_file_path, output_md_path=None):
    """
    将游卡招聘的JSON数据转换为Markdown文档
    """
    with open(json_file_path, "r", encoding="utf-8") as f:
        jobs = json.load(f)

    if not isinstance(jobs, list):
        jobs = [jobs]

    if not jobs:
        print("⚠️ JSON文件中没有数据")
        return

    md_lines = []
    md_lines.append("# 游卡校园招聘岗位详情\n")

    for job in jobs:
        job_name = job.get("job_name", "未知岗位")
        md_lines.append(f"## {job_name}\n")

        # 基本信息行
        education = job.get("education", "")
        job_nature = job.get("job_nature", "")
        experience = job.get("experience", "")
        location = job.get("location", "")
        publish_date = job.get("publish_date", "")

        info_parts = []
        if education:
            info_parts.append(f"`{education}`")
        if job_nature:
            info_parts.append(f"`{job_nature}`")
        if experience:
            info_parts.append(f"`{experience}`")
        if location:
            info_parts.append(f"`{location}`")
        if publish_date:
            info_parts.append(f"`发布于 {publish_date}`")

        md_lines.append(" \\| ".join(info_parts) + "\n")

        # ---- 处理描述文本 ----
        description = job.get("job_description", "")
        if description:
            raw_lines = description.strip().split("\n")
            formatted_lines = []

            for raw_line in raw_lines:
                line = raw_line.strip()
                if not line:
                    formatted_lines.append("")
                    continue

                # ---- 修复：只匹配行首序号，不做整行跳过 ----
                # 检查行首是否有 "数字、" 或 "数字." 等
                match = re.match(r"^(\d+)[、\.\)）]\s*(.*)", line)
                if match:
                    number = match.group(1)
                    content = match.group(2).strip()
                    # content 中的日期格式会原样保留
                    formatted_lines.append(f"{number}. {content}")
                else:
                    # 普通文本（如标题、加分项）原样保留
                    formatted_lines.append(line)

            md_lines.append("\n".join(formatted_lines) + "\n")
        else:
            md_lines.append("*（无职位描述）*\n")

        # 官网投递链接
        detail_url = job.get("detail_url", "")
        if detail_url:
            md_lines.append(f"[官网投递↗]({detail_url})\n")
        else:
            md_lines.append("*（无投递链接）*\n")

        md_lines.append("---\n")

    if output_md_path is None:
        output_md_path = Path(json_file_path).stem + ".md"

    with open(output_md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))

    print(f"✅ 转换完成！共 {len(jobs)} 个岗位")
    print(f"📄 输出文件: {output_md_path}")


if __name__ == "__main__":
    json_file = "yokagames_jobs.json"
    if not Path(json_file).exists():
        print(f"❌ 文件不存在: {json_file}")
    else:
        json_to_markdown(json_file)
