import requests
import json
import time
import os
from datetime import datetime
from collections import defaultdict

# ==================== 配置信息 ====================
BASE_URL = "https://job.byd.com/portal/api/portal-api"
LIST_API = f"{BASE_URL}/schoolPortal/queryPositionList"
DETAIL_API = f"{BASE_URL}/schoolPortal/queryPosition"
OUTPUT_FILE = "byd_y27fa.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Content-Type": "application/json",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://job.byd.com/portal/pc/#/school/schoolPositionList",
    "Origin": "https://job.byd.com",
}

# ==================== 去重相关 ====================
processed_jobs = {}
duplicate_records = defaultdict(list)


def is_duplicate(job_name, job_id, page, index):
    if job_name in processed_jobs:
        existing = processed_jobs[job_name]
        if existing["id"] == job_id:
            return True, existing
    return False, None


def add_to_processed(job_name, job_id, page, index):
    processed_jobs[job_name] = {"id": job_id, "page": page, "index": index}


def add_duplicate_record(job_name, job_id, page, index, existing):
    duplicate_records[job_name].append(
        {"id": job_id, "page": page, "index": index, "existing": existing}
    )


# ==================== 核心函数 ====================


def fetch_position_list(page_index, batch="2027", page_size=10):
    payload = {
        "topicCode": "",
        "batch": batch,
        "campusNature": "008501",
        "abroad": "",
        "degree": "",
        "jobType": [],
        "researchDirection": [],
        "workPlace": [],
        "keywords": "",
        "pageSize": page_size,
        "pageIndex": page_index,
    }
    try:
        response = requests.post(LIST_API, json=payload, headers=HEADERS, timeout=15)
        response.raise_for_status()
        result = response.json()
        if result.get("oK") and result.get("code") == 0:
            return result.get("data", []), result.get("page", {})
        else:
            print(f"  [错误] 列表API返回异常: {result.get('msg')}")
            return [], {}
    except Exception as e:
        print(f"  [错误] 请求列表页失败: {e}")
        return [], {}


def fetch_position_detail(position_id, abroad="", degree=""):
    params = {"id": position_id, "abroad": abroad, "degree": degree}
    try:
        response = requests.get(DETAIL_API, params=params, headers=HEADERS, timeout=15)
        response.raise_for_status()
        result = response.json()
        if result.get("oK") and result.get("code") == 0:
            return result.get("data")
        else:
            print(f"  [错误] 详情API返回异常: {result.get('msg')}")
            return None
    except Exception as e:
        print(f"  [错误] 请求详情页失败 (ID: {position_id}): {e}")
        return None


def append_to_json_file(data, filename):
    if not os.path.exists(filename):
        with open(filename, "w", encoding="utf-8") as f:
            json.dump([], f, ensure_ascii=False, indent=2)
    with open(filename, "r", encoding="utf-8") as f:
        try:
            existing_data = json.load(f)
        except json.JSONDecodeError:
            existing_data = []
    existing_data.append(data)
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(existing_data, f, ensure_ascii=False, indent=2)


def build_detail_url(position_id):
    return f"https://job.byd.com/portal/pc/#/school/schoolPositionDetail?positionId={position_id}"


def safe_get(data, *keys, default=""):
    for key in keys:
        try:
            data = data[key]
        except (KeyError, TypeError, IndexError):
            return default
    return data if data is not None else default


def print_duplicate_summary():
    """打印重复岗位的统计信息"""
    if not duplicate_records:
        print("\n" + "=" * 60)
        print("✅ 没有发现重复的岗位")
        print("=" * 60)
        return

    print("\n" + "=" * 60)
    print("📊 重复岗位统计信息")
    print("=" * 60)

    total_duplicates = 0
    for job_name, records in duplicate_records.items():
        total_duplicates += len(records)

    print(f"发现 {len(duplicate_records)} 个岗位名称存在重复")
    print(f"重复记录总数: {total_duplicates} 条")
    print("-" * 60)

    for job_name in sorted(duplicate_records.keys()):
        records = duplicate_records[job_name]
        existing = records[0]["existing"]

        all_positions = []
        all_positions.append(f"第{existing['page']}页第{existing['index']}个")
        for r in records:
            all_positions.append(f"第{r['page']}页第{r['index']}个")

        total_count = len(records) + 1

        print(f"\n📌 岗位: {job_name}")
        print(f"   ID: {existing['id']}")
        print(f"   共出现 {total_count} 个")
        print(f"   重复次数: {len(records)} 次")
        print(f"   出现位置: {' -> '.join(all_positions)}")

    print("\n" + "=" * 60)


# ==================== 主程序 ====================


def main():
    global processed_jobs, duplicate_records

    processed_jobs = {}
    duplicate_records = defaultdict(list)

    print("=" * 60)
    print("比亚迪2027届校园招聘岗位抓取程序 (去重版)")
    print(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    total_fetched = 0
    total_success = 0
    total_failed = 0
    total_duplicated = 0
    page_index = 1
    total_pages = None

    while True:
        print(f"\n--- 正在抓取第 {page_index} 页 ---")
        position_list, page_info = fetch_position_list(page_index)
        if total_pages is None and page_info:
            total_pages = page_info.get("totalPage", 0)
            total_count = page_info.get("totalCount", 0)
            print(f"  总岗位数: {total_count}, 总页数: {total_pages}")

        if not position_list:
            print(f"  第 {page_index} 页无数据，抓取结束。")
            break

        for idx, item in enumerate(position_list, 1):
            position_id = item.get("id")
            job_name = item.get("jobName", "未知岗位")

            is_dup, existing = is_duplicate(job_name, position_id, page_index, idx)

            if is_dup:
                add_duplicate_record(job_name, position_id, page_index, idx, existing)
                total_duplicated += 1
                print(
                    f"\n  [{idx}/{len(position_list)}] ⚠️ 跳过重复岗位: {job_name} (ID: {position_id})"
                )
                print(f"      首次出现在 第{existing['page']}页第{existing['index']}个")
                continue

            add_to_processed(job_name, position_id, page_index, idx)

            print(
                f"\n  [{idx}/{len(position_list)}] 正在处理: {job_name} (ID: {position_id})"
            )

            detail_start = time.time()
            detail_data = fetch_position_detail(position_id)
            detail_elapsed = time.time() - detail_start

            if detail_data:
                detail_url = build_detail_url(position_id)

                position_info_list = detail_data.get("positionInfoList", [])
                job_duty = ""
                job_requirements = ""
                if position_info_list:
                    job_duty = position_info_list[0].get("jobDuty", "")
                    job_requirements = position_info_list[0].get("jobRequirements", "")

                record = {
                    "id": position_id,
                    "jobName": job_name,
                    "jobType": detail_data.get("jobType", ""),
                    "batch": detail_data.get("batch"),
                    "campusNature": detail_data.get("campusNature"),
                    "workPlace": detail_data.get("workPlace", ""),
                    "updateTime": detail_data.get("updateTime", ""),
                    "detailUrl": detail_url,
                    "positionInfoList": [],
                }

                for pos_info in position_info_list:
                    record["positionInfoList"].append(
                        {
                            "id": pos_info.get(
                                "id", ""
                            ),  # 新增：保存 positionInfo 的 id
                            "jobType": pos_info.get(
                                "jobType", ""
                            ),  # 新增：保存 positionInfo 的 jobType
                            "division": pos_info.get("division", ""),
                            "degree": pos_info.get("degree", ""),
                            "abroad": pos_info.get("abroad", ""),
                            "researchDirection": pos_info.get("researchDirection", ""),
                            "jobDuty": pos_info.get("jobDuty", ""),
                            "jobRequirements": pos_info.get("jobRequirements", ""),
                            "workPlace": pos_info.get("workPlace", ""),
                        }
                    )

                append_to_json_file(record, OUTPUT_FILE)
                total_success += 1
                total_fetched += 1

                print(f"    ✅ 成功抓取")
                print(f"       - 职位描述字数: {len(job_duty)}")
                print(f"       - 职位要求字数: {len(job_requirements)}")
                print(f"       - 详情页URL: {detail_url}")
                print(f"       - 耗时: {detail_elapsed:.2f} 秒")
            else:
                total_failed += 1
                total_fetched += 1
                print(f"    ❌ 抓取失败")

            print(
                f"  累计: 已处理 {total_fetched} 个, 成功 {total_success} 个, 失败 {total_failed} 个, 重复跳过 {total_duplicated} 个"
            )

        if page_info and page_index >= page_info.get("totalPage", 1):
            print(f"\n  已到达最后一页，抓取完成。")
            break

        page_index += 1
        time.sleep(0.5)

    print("\n" + "=" * 60)
    print("抓取完成！")
    print(f"结束时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"总计抓取: {total_fetched} 个岗位")
    print(f"成功: {total_success} 个")
    print(f"失败: {total_failed} 个")
    print(f"重复跳过: {total_duplicated} 个")
    print(f"数据已保存至: {OUTPUT_FILE}")
    print("=" * 60)

    print_duplicate_summary()


if __name__ == "__main__":
    main()
