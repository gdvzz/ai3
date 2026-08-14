import asyncio
import json
import httpx
from playwright.async_api import async_playwright

# 全局配置
API_URL = "https://hrcareersweb.antgroup.com/api/campus/position/search"
DETAIL_URL_PREFIX = "https://talent.antgroup.com/campus-position?positionId="
OUTPUT_FILE = "antgroup_campus_jobs.json"

# 统计信息
stats = {"total": 0, "success": 0, "error": 0}

async def get_ctoken_and_cookie():
    """通过 Playwright 获取 ctoken 和完整 Cookie"""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        await page.goto("https://talent.antgroup.com/campus-full-list?type=campus_graduates", wait_until="networkidle", timeout=30000)
        await asyncio.sleep(3)

        cookies = await context.cookies()
        cookie_str = "; ".join([f"{c['name']}={c['value']}" for c in cookies])

        ctoken = await page.evaluate('''
            () => {
                let id = localStorage.getItem('ctoken');
                if (id) return id;
                const match = document.cookie.match(/ctoken=([^;]+)/);
                return match ? match[1] : null;
            }
        ''')
        await browser.close()
        return cookie_str, ctoken

async def fetch_positions(cookie_str, ctoken, page_num):
    """通过 API POST 获取岗位列表"""
    headers = {
        "Accept": "application/json",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7",
        "Content-Type": "application/json;charset=UTF-8",
        "Cookie": cookie_str,
        "Origin": "https://talent.antgroup.com",
        "Referer": "https://talent.antgroup.com/",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36",
        "sec-ch-ua": '"Not;A=Brand";v="8", "Chromium";v="150", "Google Chrome";v="150"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"macOS"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-site",
    }

    payload = {
        "channel": "campus_group_official_site",
        "language": "zh",
        "regions": "",
        "subCategories": "",
        "bgCode": "",
        "batchIds": ["26040200083752", "25030300059633", "26070900089909"],
        "pageIndex": page_num,
        "pageSize": 10,
        "recruitType": []
    }

    params = {"ctoken": ctoken}

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(API_URL, headers=headers, params=params, json=payload)
        if response.status_code == 200:
            return response.json()
        else:
            print(f"  API请求失败，状态码: {response.status_code}")
            print(f"  响应内容: {response.text[:200]}")
            return None

async def save_job_to_file(job_data):
    """将单个岗位数据追加到 JSON 文件中"""
    try:
        with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
            all_jobs = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        all_jobs = []

    all_jobs.append(job_data)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(all_jobs, f, ensure_ascii=False, indent=2)

async def main():
    start_total_time = asyncio.get_event_loop().time()
    print(f"程序开始运行，输出文件: {OUTPUT_FILE}")
    print("=" * 60)

    print("正在获取会话信息...")
    cookie_str, ctoken = await get_ctoken_and_cookie()
    if not cookie_str:
        print("⚠️ 未获取到 Cookie")
        return
    if not ctoken:
        print("⚠️ 未获取到 ctoken，尝试使用默认值...")
        ctoken = "bigfish_ctoken_1ac63jh4a0"
    print(f"  Cookie 长度: {len(cookie_str)}")
    print(f"  ctoken: {ctoken}")

    print("\n正在获取第一页数据...")
    first_response = await fetch_positions(cookie_str, ctoken, 1)
    if not first_response or not first_response.get("success"):
        print(f"  API返回错误: {first_response.get('errorMsg') if first_response else '无响应'}")
        return

    total_count = first_response.get("totalCount", 0)
    page_size = first_response.get("pageSize", 10)
    total_pages = (total_count + page_size - 1) // page_size
    print(f"  总岗位数: {total_count}, 总页数: {total_pages}")

    processed_ids = set()
    all_jobs = []

    for page in range(1, total_pages + 1):
        print(f"\n{'='*60}")
        print(f"正在抓取第 {page} 页")
        print(f"{'='*60}")

        if page == 1:
            api_response = first_response
        else:
            api_response = await fetch_positions(cookie_str, ctoken, page)
            await asyncio.sleep(0.5)

        if not api_response or not api_response.get("success"):
            print(f"  第 {page} 页API请求失败")
            continue

        job_list = api_response.get("content", [])
        print(f"  本页 {len(job_list)} 个岗位")

        for item in job_list:
            position_id = str(item.get("id", ""))
            if not position_id or position_id in processed_ids:
                continue

            processed_ids.add(position_id)
            title = item.get("name", "未知岗位")

            print(f"\n  处理岗位: {title}, ID: {position_id}")
            stats["total"] += 1

            # 提取详情数据（含发布时间）
            publish_time = item.get("publishTime", "")
            description = item.get("description", "")
            requirement = item.get("requirement", "")
            category = item.get("categoryName", "")
            work_locations = item.get("workLocations", [])
            interview_locations = item.get("interviewLocations", [])
            batch_name = item.get("batchName", "")
            tags = item.get("featureTagList", [])

            print(f"    类别: {category}")
            print(f"    工作地点: {', '.join(work_locations) if work_locations else 'N/A'}")
            print(f"    发布时间: {publish_time}")
            print(f"    描述字数: {len(description)}字")
            print(f"    要求字数: {len(requirement)}字")

            job_data = {
                "id": position_id,
                "title": title,
                "category": category,
                "batch_name": batch_name,
                "work_locations": work_locations,
                "interview_locations": interview_locations,
                "publish_time": publish_time,          # 新增发布时间字段
                "description": description,
                "requirement": requirement,
                "feature_tags": tags,
                "detail_url": f"{DETAIL_URL_PREFIX}{position_id}",
            }

            all_jobs.append(job_data)
            stats["success"] += 1

            await save_job_to_file(job_data)
            print(f"    ✅ 已保存岗位: {title} (累计成功: {stats['success']}, 错误: {stats['error']})")

        print(f"  本页新增 {len(job_list)} 个岗位，累计 {len(processed_ids)} 个")

    total_elapsed = asyncio.get_event_loop().time() - start_total_time
    print(f"\n{'='*60}")
    print(f"抓取完成!")
    print(f"{'='*60}")
    print(f"总计抓取岗位数: {stats['total']}")
    print(f"成功: {stats['success']}")
    print(f"错误: {stats['error']}")
    print(f"总耗时: {total_elapsed:.2f} 秒 ({total_elapsed/60:.2f} 分钟)")
    print(f"数据已保存至: {OUTPUT_FILE}")

if __name__ == "__main__":
    asyncio.run(main())