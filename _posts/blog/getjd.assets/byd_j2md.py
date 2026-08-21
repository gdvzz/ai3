import json
import re
from pypinyin import pinyin, Style
from collections import defaultdict


def to_pinyin(text):
    """将中文转换为拼音，用于排序"""
    if not text:
        return ""
    try:
        result = []
        for char in text:
            if "\u4e00" <= char <= "\u9fff":
                p = pinyin(char, style=Style.TONE3)
                result.append(p[0][0] if p else char)
            else:
                result.append(char)
        return "".join(result)
    except:
        return text


def sort_by_pinyin(items, key=None):
    """按拼音排序"""
    if key:
        return sorted(items, key=lambda x: to_pinyin(key(x)))
    return sorted(items, key=lambda x: to_pinyin(x))


def unique_preserve_order(items):
    """去重并保持顺序"""
    seen = set()
    result = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def format_text_with_numbers(text):
    """
    将文本中的序号（如 1、2、3 或 1. 2. 3. 或 1）转为有序列表
    保留原始序号，不统一改为1
    支持格式：1、2、3、 或 1. 2. 3. 或 1) 2) 3)
    """
    if not text:
        return text

    lines = text.split("\n")
    formatted_lines = []
    in_list = False
    list_items = []  # 存储 (序号, 内容)

    for line in lines:
        stripped = line.strip()
        if not stripped:
            if in_list and list_items:
                for num, content in list_items:
                    formatted_lines.append(f"{num}. {content}")
                list_items = []
                in_list = False
            formatted_lines.append(line)
            continue

        # 匹配序号：1、2、3、 或 1. 2. 3. 或 1) 2) 3)
        match = re.match(r"^(\d+)[、.．)）]\s*(.*)", stripped)
        if match:
            if not in_list:
                in_list = True
                list_items = []
            num = match.group(1)
            content = match.group(2).strip()
            list_items.append((num, content))
            continue

        # 如果当前在列表中，但这一行不是序号，可能是列表项的续行
        if in_list and list_items:
            list_items[-1] = (list_items[-1][0], list_items[-1][1] + " " + stripped)
            continue

        formatted_lines.append(line)

    # 处理末尾的列表
    if in_list and list_items:
        for num, content in list_items:
            formatted_lines.append(f"{num}. {content}")

    return "\n".join(formatted_lines)


def escape_pipe(text):
    """转义文本中的竖线 | 为 \|"""
    if not text:
        return text
    return text.replace("|", "\\|")


def split_job_type(job_type):
    """将jobType按逗号或顿号分割，返回列表"""
    if not job_type:
        return []
    types = re.split(r"[,，、]\s*", job_type)
    return [t.strip() for t in types if t.strip()]


def generate_job_type_index(jobs):
    """
    生成按 positionInfoList.jobType 分类的岗位+方向索引
    返回: {
        job_type: {
            "items": [(job_name, direction), ...],  # 所有条目
            "unique_jobs": set(job_name)            # 不重复的岗位名称
        }
    }
    """
    type_index = defaultdict(lambda: {"items": [], "unique_jobs": set()})

    for job in jobs:
        job_name = job.get("jobName", "未知岗位")
        position_info_list = job.get("positionInfoList", [])

        for info in position_info_list:
            job_type = info.get("jobType", "")
            direction = info.get("researchDirection", "未分类")

            if not job_type:
                type_index["未分类"]["items"].append((job_name, direction))
                type_index["未分类"]["unique_jobs"].add(job_name)
            else:
                types = split_job_type(job_type)
                for t in types:
                    if t:
                        type_index[t]["items"].append((job_name, direction))
                        type_index[t]["unique_jobs"].add(job_name)

    # 对每个类型下的条目按岗位名称拼音排序
    for t in type_index:
        type_index[t]["items"] = sort_by_pinyin(
            type_index[t]["items"], key=lambda x: x[0]
        )

    return type_index


def process_job_data(job):
    """处理单个岗位数据，生成Markdown格式"""
    job_name = job.get("jobName", "未知岗位")
    job_type = job.get("jobType", "")
    work_place = job.get("workPlace", "")
    update_time = job.get("updateTime", "")
    position_info_list = job.get("positionInfoList", [])

    md_lines = []

    # 1. 二级标题：岗位名称
    md_lines.append(f"## {job_name}")
    md_lines.append("")

    # 2. 信息行：jobType | workPlace | 更新于 updateTime
    if work_place:
        work_places = [w.strip() for w in work_place.split(",") if w.strip()]
        work_places = unique_preserve_order(work_places)
        work_places = sort_by_pinyin(work_places)
        work_place_str = "、".join(work_places)
    else:
        work_place_str = ""

    info_parts = []
    if job_type:
        info_parts.append(f"`{escape_pipe(job_type)}`")
    if work_place_str:
        info_parts.append(f"`{escape_pipe(work_place_str)}`")
    if update_time:
        info_parts.append(f"`更新于 {update_time}`")

    md_lines.append(" \\| ".join(info_parts))
    md_lines.append("")

    if not position_info_list:
        md_lines.append("---")
        md_lines.append("")
        return "\n".join(md_lines)

    # 按方向分组
    direction_groups = {}
    for info in position_info_list:
        direction = info.get("researchDirection", "未分类")
        if direction not in direction_groups:
            direction_groups[direction] = []
        direction_groups[direction].append(info)

    sorted_directions = sort_by_pinyin(list(direction_groups.keys()))

    for direction in sorted_directions:
        infos = direction_groups[direction]

        # 3. 三级标题：jobName > direction
        md_lines.append(f"### {job_name} > {direction}")
        md_lines.append("")

        # 收集该方向下的所有信息
        all_job_types = []
        all_duties = []
        all_requirements = []
        division_places = {}

        for info in infos:
            # 4. positionInfoList.jobType
            p_job_type = info.get("jobType", "")
            if p_job_type:
                all_job_types.append(p_job_type)

            duty = info.get("jobDuty", "")
            if duty:
                all_duties.append(duty)

            req = info.get("jobRequirements", "")
            if req:
                all_requirements.append(req)

            division = info.get("division", "未分类")
            place = info.get("workPlace", "")
            if place:
                places = [w.strip() for w in place.split(",") if w.strip()]
                if division not in division_places:
                    division_places[division] = []
                division_places[division].extend(places)

        # 4. 显示 positionInfoList.jobType
        if all_job_types:
            unique_job_types = unique_preserve_order(all_job_types)
            if len(unique_job_types) == 1:
                md_lines.append(f"`{escape_pipe(unique_job_types[0])}`")
            else:
                sorted_job_types = sort_by_pinyin(unique_job_types)
                md_lines.append(
                    " \\| ".join([f"`{escape_pipe(t)}`" for t in sorted_job_types])
                )
            md_lines.append("")

        # 5. 工作职责
        if all_duties:
            md_lines.append("**工作职责**")
            for duty in all_duties:
                formatted_duty = format_text_with_numbers(duty)
                md_lines.append(formatted_duty)
            md_lines.append("")

        # 6. 职位要求
        if all_requirements:
            md_lines.append("**职位要求**")
            for req in all_requirements:
                formatted_req = format_text_with_numbers(req)
                md_lines.append(formatted_req)
            md_lines.append("")

        # 7. 工作地点
        if division_places:
            md_lines.append("**工作地点**")
            sorted_divisions = sort_by_pinyin(list(division_places.keys()))
            for division in sorted_divisions:
                places = unique_preserve_order(division_places[division])
                places = sort_by_pinyin(places)
                place_str = "、".join(places)
                md_lines.append(f"- {escape_pipe(division)}：{escape_pipe(place_str)}")
            md_lines.append("")

    md_lines.append("---")
    md_lines.append("")

    return "\n".join(md_lines)


def main():
    input_file = "byd_y27fa.json"
    output_file = "byd_y27fa.md"

    print(f"正在读取 {input_file}...")
    try:
        with open(input_file, "r", encoding="utf-8") as f:
            jobs = json.load(f)
    except FileNotFoundError:
        print(f"错误：找不到文件 {input_file}")
        return
    except json.JSONDecodeError as e:
        print(f"错误：JSON解析失败 - {e}")
        return

    print(f"共加载 {len(jobs)} 个岗位")

    all_md = []
    all_md.append("# 比亚迪2027届校园招聘岗位详情")
    all_md.append("")
    all_md.append(f"共 {len(jobs)} 个岗位")
    all_md.append("")
    all_md.append("---")
    all_md.append("")

    # 10. 岗位分类索引（按 positionInfoList.jobType 分类）
    print("正在生成岗位分类索引...")
    type_index = generate_job_type_index(jobs)

    all_md.append("## 岗位分类索引")
    all_md.append("")

    sorted_types = sort_by_pinyin(list(type_index.keys()))
    for job_type in sorted_types:
        items = type_index[job_type]["items"]
        unique_jobs = type_index[job_type]["unique_jobs"]
        # 显示：条目总数 和 不重复岗位数
        all_md.append(f"### {job_type}（{len(items)} 条，{len(unique_jobs)} 个岗位）")
        all_md.append("")
        for job_name, direction in items:
            all_md.append(f"- {job_name} > {direction}")
        all_md.append("")

    all_md.append("---")
    all_md.append("")

    # 按JSON文件中的原始顺序输出
    print("正在按JSON原始顺序生成岗位详情...")
    for i, job in enumerate(jobs, 1):
        job_name = job.get("jobName", "未知岗位")
        print(f"处理: {job_name} ({i}/{len(jobs)})")
        job_md = process_job_data(job)
        all_md.append(job_md)

    print(f"正在写入 {output_file}...")
    with open(output_file, "w", encoding="utf-8") as f:
        f.write("\n".join(all_md))

    print(f"✅ 完成！已生成 {output_file}")


if __name__ == "__main__":
    main()
