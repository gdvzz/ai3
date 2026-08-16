import json
import re


def zf_json_to_markdown(
    input_file: str = "longfor_jobs_zf_dedup.json",
    output_file: str = "longfor_jobs_zf_final.md",
):
    """
    将'绽放'项目去重后的JSON转换为Markdown文档
    """

    # 读取去重后的数据
    with open(input_file, "r", encoding="utf-8") as f:
        jobs = json.load(f)

    print(f"读取到 {len(jobs)} 个'绽放'岗位")

    # 生成Markdown
    md_lines = []

    # 添加标题
    md_lines.append("# 龙湖'绽放'校招岗位汇总\n")
    md_lines.append(f"**岗位总数**: {len(jobs)}\n")
    md_lines.append("---\n")

    # 按岗位名称排序
    jobs_sorted = sorted(jobs, key=lambda x: x.get("title", ""))

    for job in jobs_sorted:
        title = job.get("title", "未命名岗位")
        department = job.get("department_name", "")
        cities = job.get("cities", [])
        description = job.get("description", "")
        detail_urls = job.get("detail_urls", [])

        # 1. 岗位名称用2级标题（不加编号）
        md_lines.append(f"\n## {title}\n")

        # 2. department_name | cities（用反引号包裹，|转义）
        cities_str = "，".join(cities) if cities else "未指定"
        md_lines.append(f"`{department}` \\| `{cities_str}`\n")

        # 3. 显示description，处理序号转有序列表
        if description:
            # 清理HTML标签
            desc_clean = description.replace("<br>", "\n").replace("<br/>", "\n")

            # 处理有序列表
            lines = desc_clean.split("\n")
            processed_lines = []

            # 检测是否有序号（如 "1、", "1.", "1)" 等）
            has_numbered_list = False
            for line in lines:
                if re.match(r"^\s*\d+[、\.\)]\s*", line):
                    has_numbered_list = True
                    break

            if has_numbered_list:
                # 处理有序列表
                for line in lines:
                    # 匹配序号
                    match = re.match(r"^(\s*)(\d+)([、\.\)])\s*(.*)$", line)
                    if match:
                        indent = match.group(1)
                        num = match.group(2)
                        content = match.group(4)
                        processed_lines.append(f"{indent}{num}. {content}")
                    else:
                        # 保留非序号行
                        if line.strip():
                            processed_lines.append(line)
                        else:
                            processed_lines.append("")
            else:
                # 没有序号，保持原样
                processed_lines = lines

            # 去除空行并组合
            final_desc = "\n".join(processed_lines)

            if "\n" in final_desc:
                md_lines.append(f"\n{final_desc}\n")
            else:
                md_lines.append(f"\n{final_desc}\n")

        # 4. 网申投递链接 - 根据 detail_urls 数量决定显示格式
        if detail_urls:
            if len(detail_urls) == 1:
                # 只有1个链接，显示 [网申投递↗](url)
                md_lines.append(f"\n[网申投递↗]({detail_urls[0]})\n")
            else:
                # 多个链接，显示 网申投递 [↗](url1) [↗](url2) ...
                links = []
                for url in detail_urls:
                    links.append(f"[↗]({url})")
                md_lines.append(f"\n网申投递 " + " ".join(links) + "\n")
        else:
            md_lines.append("\n*暂无投递链接*\n")

        # 分隔线
        md_lines.append("\n---\n")

    # 写入文件
    with open(output_file, "w", encoding="utf-8") as f:
        f.write("".join(md_lines))

    print(f"Markdown文档已保存至: {output_file}")
    print(f"共生成 {len(jobs)} 个'绽放'岗位条目")


def main():
    # 转换去重后的JSON为Markdown
    zf_json_to_markdown(
        input_file="longfor_jobs_zf_dedup.json", output_file="longfor_jobs_zf_final.md"
    )


if __name__ == "__main__":
    main()
