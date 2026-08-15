import json
import re
from pathlib import Path

# --- 配置 ---
INPUT_JSON = "tencent_jobs.json"
OUTPUT_MD = "tencent_jobs.md"
POSITION_FAMILY_MAP = {
    2: "技术",
    3: "产品",
    4: "设计",
    5: "市场",
    6: "职能",
}

def escape_pipe(text: str) -> str:
    """将字符串中的 | 转义为 \|，防止被解析为表格分隔符"""
    if not text:
        return text
    return text.replace('|', '\\|')

def convert_text_to_ordered_list(text: str) -> str:
    """
    将包含序号（1、2、3. 或 1. 2. 3.）的文本转换为Markdown有序列表
    如果没有序号，则保持原样（但会转义 |）
    """
    if not text:
        return ""
    
    lines = text.strip().split('\n')
    result_lines = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        # 匹配以数字开头，后跟.、、、)等分隔符的序号
        match = re.match(r'^(\d+)[.、)）]\s*(.*)$', line)
        if match:
            number = match.group(1)
            content = match.group(2).strip()
            # 转义内容中的 | 符号
            content = escape_pipe(content)
            result_lines.append(f"{number}. {content}")
        else:
            # 转义整行中的 | 符号
            result_lines.append(escape_pipe(line))
    
    return '\n'.join(result_lines)

def convert_job_to_md(job: dict) -> str:
    """将单个岗位数据转换为Markdown格式"""
    title = job.get("title", "未知岗位")
    url = job.get("url", "#")
    position_family_code = job.get("position_family")
    position_family = POSITION_FAMILY_MAP.get(position_family_code, str(position_family_code))
    recruit_label = job.get("recruit_label", "")

    description = job.get("description", "")
    requirements = job.get("requirements", "")
    bonus = job.get("bonus", "")
    departments = job.get("departments", [])
    work_cities = job.get("work_cities", "").strip().split() if job.get("work_cities") else []
    
    # 处理描述、要求和加分项中的列表
    description_formatted = convert_text_to_ordered_list(description)
    requirements_formatted = convert_text_to_ordered_list(requirements)
    bonus_formatted = convert_text_to_ordered_list(bonus) if bonus else ""

    md_parts = []
    
    # 1. 岗位名称（二级标题）
    md_parts.append(f"## {title}\n")
    
    # 2. 岗位信息行：转义 | 符号，用反引号包裹
    family_display = escape_pipe(position_family)
    label_display = escape_pipe(recruit_label)
    md_parts.append(f"`{family_display}` \\| `{label_display}`\n")
    
    # 3. 岗位描述
    md_parts.append("**岗位描述**")
    md_parts.append(description_formatted if description_formatted else "暂无")
    md_parts.append("")
    
    # 4. 岗位要求
    md_parts.append("**岗位要求**")
    md_parts.append(requirements_formatted if requirements_formatted else "暂无")
    md_parts.append("")
    
    # 5. 加分项或注意事项（如果存在）
    if bonus_formatted:
        md_parts.append("**加分项或注意事项**")
        md_parts.append(bonus_formatted)
        md_parts.append("")
    
    # 6. 招聘部门和工作地
    md_parts.append("**招聘部门和工作地**")
    
    # 处理部门列表：用 \| 分隔，每个值用反引号包裹
    if departments:
        dept_list = [d.replace('\n', ' ').strip() for d in departments if d.strip()]
        # 每个部门用反引号包裹，然后用 \| 分隔
        dept_line = " \\| ".join([f"`{escape_pipe(d)}`" for d in dept_list])
        md_parts.append(f"- {dept_line}")
    else:
        md_parts.append("- 未提供部门信息")
    
    # 处理工作地点：一行，用 \| 分隔，每个值用反引号包裹
    if work_cities:
        city_list = [city.strip() for city in work_cities if city.strip()]
        # 每个城市用反引号包裹，然后用 \| 分隔
        city_line = " \\| ".join([f"`{escape_pipe(c)}`" for c in city_list])
        md_parts.append(f"- {city_line}")
    else:
        md_parts.append("- 未提供工作地点")
    md_parts.append("")
    
    # 7. 官网投递链接
    md_parts.append(f"[官网投递↗]({url})")
    
    # 分隔线（每个岗位之间用---分隔）
    md_parts.append("\n---\n")
    
    return '\n'.join(md_parts)

def main():
    # 读取JSON文件
    if not Path(INPUT_JSON).exists():
        print(f"❌ 文件 {INPUT_JSON} 不存在，请先运行抓取程序。")
        return
    
    try:
        with open(INPUT_JSON, 'r', encoding='utf-8') as f:
            jobs = json.load(f)
    except Exception as e:
        print(f"❌ 读取JSON文件失败: {e}")
        return
    
    if not jobs:
        print("⚠️ JSON文件中没有数据。")
        return
    
    print(f"📊 开始转换 {len(jobs)} 个岗位到Markdown...")
    
    # 添加文档头部
    md_content = []
    md_content.append("# 腾讯校园招聘岗位详情\n")
    md_content.append(f"> 共 {len(jobs)} 个岗位 | 数据抓取时间: {Path(INPUT_JSON).stat().st_mtime}\n")
    
    # 逐个转换岗位
    for i, job in enumerate(jobs, 1):
        print(f"🔄 正在处理 [{i}/{len(jobs)}]: {job.get('title', '未知岗位')}")
        job_md = convert_job_to_md(job)
        md_content.append(job_md)
    
    # 写入Markdown文件
    try:
        with open(OUTPUT_MD, 'w', encoding='utf-8') as f:
            f.write('\n'.join(md_content))
        print(f"✅ 转换完成！Markdown文件已保存为: {OUTPUT_MD}")
        print(f"📄 文件路径: {Path(OUTPUT_MD).absolute()}")
    except Exception as e:
        print(f"❌ 写入Markdown文件失败: {e}")

if __name__ == "__main__":
    main()