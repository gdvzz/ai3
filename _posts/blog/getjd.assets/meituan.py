import requests
import json
import time
from datetime import datetime

# API 配置
API_URL = "https://zhaopin.meituan.com/api/official/job/getJobList"
OUTPUT_FILE = "meituan_jobs_api.json"

# 请求头，模拟浏览器访问
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Content-Type": "application/json",
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://zhaopin.meituan.com",
    "Referer": "https://zhaopin.meituan.com/web/campus?hiringType=4_1",
}

# 基础请求体
BASE_PAYLOAD = {
    "page": {"pageNo": 1, "pageSize": 10},
    "jobShareType": "1",
    "keywords": "",
    "cityList": [],
    "department": [],
    "jfJgList": [],
    "jobType": [{"code": "4", "subCode": ["1"]}],
    "typeCode": ["1"],
    "specialCode": [],
    "u_query_id": "356a5685dcdb863bfad2660af57ee854",
    "r_query_id": "178704001877448021037",
}


def save_jobs_to_file(jobs, filename):
    """将岗位列表追加保存到JSON文件"""
    try:
        # 尝试读取现有数据
        with open(filename, "r", encoding="utf-8") as f:
            existing_data = json.load(f)
        if not isinstance(existing_data, list):
            existing_data = []
    except (FileNotFoundError, json.JSONDecodeError):
        existing_data = []

    # 追加新数据
    existing_data.extend(jobs)

    # 写回文件
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(existing_data, f, ensure_ascii=False, indent=2)


def fetch_jobs_by_page(page_no, page_size=10):
    """抓取指定页码的岗位数据"""
    payload = BASE_PAYLOAD.copy()
    payload["page"]["pageNo"] = page_no
    payload["page"]["pageSize"] = page_size

    try:
        response = requests.post(API_URL, headers=HEADERS, json=payload, timeout=15)
        response.raise_for_status()

        result = response.json()
        if result.get("status") == 1 and result.get("data"):
            return result["data"]
        else:
            print(f"  ⚠️ API返回状态异常: {result.get('message', '未知错误')}")
            return None
    except requests.exceptions.RequestException as e:
        print(f"  ❌ 网络请求失败: {e}")
        return None
    except json.JSONDecodeError as e:
        print(f"  ❌ JSON解析失败: {e}")
        return None


def parse_job_data(job_list):
    """解析并格式化岗位数据，构造详情页URL"""
    parsed_jobs = []
    for job in job_list:
        # 提取城市名称列表
        cities = [
            city.get("name") for city in job.get("cityList", []) if city.get("name")
        ]

        # 构造详情页URL（修正为正确的格式）
        job_union_id = job.get("jobUnionId")
        job_url = (
            f"https://zhaopin.meituan.com/web/position/detail?jobUnionId={job_union_id}"
        )

        parsed_job = {
            "job_union_id": job_union_id,
            "job_name": job.get("name"),
            "job_url": job_url,  # ✅ 已添加详情页URL
            "job_family": job.get("jobFamily"),
            "job_family_group": job.get("jobFamilyGroup"),
            "cities": cities,
            "job_duty": job.get("jobDuty", "").strip(),
            "job_requirement": job.get("jobRequirement", "").strip(),
            "refresh_time": job.get("refreshTime"),
            "crawl_timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        parsed_jobs.append(parsed_job)
    return parsed_jobs


def main():
    start_time = time.time()
    total_fetched = 0
    total_pages = 0
    current_page = 1
    page_size = 10

    print(f"🚀 开始抓取美团校招岗位数据...")
    print(f"📡 API地址: {API_URL}")
    print("-" * 60)

    while True:
        print(f"\n📄 正在抓取第 {current_page} 页...")
        page_start_time = time.time()

        # 1. 请求API
        data = fetch_jobs_by_page(current_page, page_size)
        if not data:
            print("  ❌ 获取数据失败，停止抓取。")
            break

        # 2. 解析响应
        job_list = data.get("list", [])
        page_info = data.get("page", {})
        total_pages = page_info.get("totalPage", 0)
        total_count = page_info.get("totalCount", 0)

        if not job_list:
            print("  ℹ️ 本页无岗位数据，可能已到达末页。")
            break

        # 3. 处理并保存数据
        parsed_jobs = parse_job_data(job_list)
        save_jobs_to_file(parsed_jobs, OUTPUT_FILE)

        # 4. 输出调试信息（包含详情页URL）
        page_time = time.time() - page_start_time

        print(f"  ✅ 成功抓取 {len(parsed_jobs)} 个岗位")
        print(f"  ⏱️ 本页耗时: {page_time:.2f} 秒")

        # 显示本页所有岗位的名称和URL
        for idx, job in enumerate(parsed_jobs, 1):
            print(f"    {idx}. {job['job_name']}")
            print(f"       🔗 {job['job_url']}")

        # 累计统计
        total_fetched += len(parsed_jobs)
        print(f"  📊 累计抓取: {total_fetched} / {total_count} 个岗位")

        # 5. 判断是否继续翻页
        if current_page >= total_pages:
            print("\n🏁 已到达最后一页，抓取完成！")
            break

        current_page += 1
        # 适当延时，避免请求过快
        time.sleep(0.5)

    # 最终统计报告
    total_time = time.time() - start_time
    print("\n" + "=" * 60)
    print("📊 抓取统计报告")
    print("=" * 60)
    print(f"⏱️ 总耗时: {total_time:.2f} 秒")
    print(f"📋 总页数: {total_pages}")
    print(f"📋 总岗位数: {total_fetched}")
    print(f"💾 所有数据已保存至: {OUTPUT_FILE}")
    print("=" * 60)


if __name__ == "__main__":
    main()
