import json
from collections import defaultdict


def deduplicate_and_merge_dj_jobs(
    input_file: str = "longfor_jobs_dj.json",
    output_file: str = "longfor_jobs_dj_dedup.json",
):
    """
    专门处理'点将'项目岗位数据：
    1. 按 title + department_name + description 合并相同岗位
    2. 聚合多个城市
    3. 保留一个详情URL和投递路径作为示例
    """

    # 读取原始数据
    with open(input_file, "r", encoding="utf-8") as f:
        jobs = json.load(f)

    print(f"原始'点将'岗位数: {len(jobs)}")

    # 使用字典进行去重
    dedup_dict = {}

    for job in jobs:
        # 生成唯一键：title + department_name + description的前200字符作为指纹
        title = job.get("title", "").strip()
        department = job.get("department_name", "").strip()
        description = job.get("description", "").strip()

        # 使用description的前200个字符作为指纹（避免整段文本太长）
        desc_fingerprint = description[:200] if description else ""
        key = f"{title}|{department}|{desc_fingerprint}"

        if key not in dedup_dict:
            # 首次出现，保存完整数据
            dedup_dict[key] = {
                "title": title,
                "company_name": job.get("company_name", ""),
                "department_name": department,
                "org_name": job.get("org_name", ""),
                "job_type": job.get("job_type", ""),
                "salary_text": job.get("salary_text", ""),
                "min_salary": job.get("min_salary"),
                "max_salary": job.get("max_salary"),
                "min_education": job.get("min_education", ""),
                "working_exp": job.get("working_exp", ""),
                "description": description,
                "description_length": len(description),
                "cities": [],  # 存储多个城市
                "detail_urls": [],  # 存储所有URL
                "delivery_paths": [],  # 存储所有投递路径
                "job_ids": [],  # 存储所有job_id
                "job_numbers": [],  # 存储所有job_number
                "staff_names": [],  # 存储所有联系人
                "original_count": 0,  # 原始出现次数
            }

        # 更新聚合数据
        record = dedup_dict[key]

        # 添加城市（去重）
        city = job.get("city", "").strip()
        if city and city not in record["cities"]:
            record["cities"].append(city)

        # 添加详情URL（去重）
        detail_url = job.get("detail_url", "").strip()
        if detail_url and detail_url not in record["detail_urls"]:
            record["detail_urls"].append(detail_url)

        # 添加投递路径（去重）
        delivery_path = job.get("delivery_path", "").strip()
        if delivery_path and delivery_path not in record["delivery_paths"]:
            record["delivery_paths"].append(delivery_path)

        # 添加job_id（去重）
        job_id = job.get("job_id")
        if job_id and job_id not in record["job_ids"]:
            record["job_ids"].append(job_id)

        # 添加job_number（去重）
        job_number = job.get("job_number", "").strip()
        if job_number and job_number not in record["job_numbers"]:
            record["job_numbers"].append(job_number)

        # 添加联系人（去重）
        staff_name = job.get("staff_name", "").strip()
        if staff_name and staff_name not in record["staff_names"]:
            record["staff_names"].append(staff_name)

        # 更新计数
        record["original_count"] += 1

    # 转换为列表并排序
    dedup_jobs = list(dedup_dict.values())
    dedup_jobs.sort(key=lambda x: x["title"])

    # 统计信息
    total_cities = sum(len(job["cities"]) for job in dedup_jobs)
    total_urls = sum(len(job["detail_urls"]) for job in dedup_jobs)

    print(f"去重后'点将'岗位数: {len(dedup_jobs)}")
    print(f"总城市出现次数: {total_cities}")
    print(f"总URL数量: {total_urls}")

    # 保存去重后的数据
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(dedup_jobs, f, ensure_ascii=False, indent=2)

    print(f"去重数据已保存至: {output_file}")

    # 输出一些示例
    print("\n去重后的岗位示例（多城市）:")
    multi_city_jobs = [j for j in dedup_jobs if len(j["cities"]) > 1]
    for job in multi_city_jobs[:5]:
        print(
            f"  - {job['title']} | {job['department_name']} | 城市: {', '.join(job['cities'])} ({len(job['cities'])}个)"
        )

    return dedup_jobs


def generate_dj_markdown_report(
    dedup_jobs: list, output_file: str = "longfor_jobs_dj_report.md"
):
    """生成'点将'项目的Markdown报告"""

    with open(output_file, "w", encoding="utf-8") as f:
        f.write("# 龙湖'点将'校招岗位汇总\n\n")
        f.write(
            f"**更新时间**: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        )
        f.write(f"**岗位总数**: {len(dedup_jobs)}\n\n")
        f.write("---\n\n")

        # 统计城市分布
        city_count = {}
        for job in dedup_jobs:
            for city in job["cities"]:
                city_count[city] = city_count.get(city, 0) + 1

        f.write("## 城市分布\n\n")
        for city, count in sorted(city_count.items(), key=lambda x: x[1], reverse=True):
            f.write(f"- **{city}**: {count}个岗位\n")

        f.write("\n---\n\n")

        # 岗位详情
        f.write("## 岗位详情\n\n")

        for idx, job in enumerate(dedup_jobs, 1):
            f.write(f"### {idx}. {job['title']}\n\n")

            f.write("| 属性 | 值 |\n")
            f.write("|------|----|\n")
            f.write(f"| **公司** | {job.get('company_name', '')} |\n")
            f.write(f"| **部门** | {job.get('department_name', '')} |\n")
            f.write(f"| **岗位类型** | {job.get('job_type', '')} |\n")
            f.write(f"| **城市** | {', '.join(job['cities'])} |\n")
            f.write(f"| **薪资** | {job.get('salary_text', '')} |\n")
            f.write(f"| **学历要求** | {job.get('min_education', '不限')} |\n")
            f.write(f"| **工作经验** | {job.get('working_exp', '不限')} |\n")
            f.write(f"| **合并数** | {job['original_count']}个相似岗位 |\n")

            # 显示多个投递链接
            if job["detail_urls"]:
                urls = job["detail_urls"]
                if len(urls) == 1:
                    f.write(f"| **详情页** | [点击查看]({urls[0]}) |\n")
                else:
                    links = " ".join([f"[↗]({url})" for url in urls])
                    f.write(f"| **详情页** | {links} |\n")
            else:
                f.write("| **详情页** | 暂无 |\n")

            f.write("\n")

            # 职位描述
            description = job.get("description", "")
            if description:
                desc = description.replace("<br>", "\n").replace("<br/>", "\n")
                f.write("**职位描述**:\n\n")
                f.write(f"{desc}\n\n")

            f.write("---\n\n")

    print(f"Markdown报告已保存至: {output_file}")


def main():
    # 1. 去重处理
    dedup_jobs = deduplicate_and_merge_dj_jobs(
        input_file="longfor_jobs_dj.json", output_file="longfor_jobs_dj_dedup.json"
    )

    # 2. 生成Markdown报告
    generate_dj_markdown_report(
        dedup_jobs=dedup_jobs, output_file="longfor_jobs_dj_report.md"
    )

    # 3. 输出统计信息
    print("\n" + "=" * 50)
    print("'点将'项目统计信息:")

    # 统计每个岗位的城市分布
    single_city = sum(1 for job in dedup_jobs if len(job["cities"]) == 1)
    multi_city = sum(1 for job in dedup_jobs if len(job["cities"]) > 1)
    print(f"- 单一城市岗位: {single_city}")
    print(f"- 多个城市岗位: {multi_city}")

    # 找出合并最多的岗位
    if dedup_jobs:
        max_merge = max(dedup_jobs, key=lambda x: x["original_count"])
        print(
            f"- 合并最多的岗位: {max_merge['title']} (合并了 {max_merge['original_count']} 个相似岗位)"
        )
        print(f"  涉及城市: {', '.join(max_merge['cities'])}")


if __name__ == "__main__":
    main()
