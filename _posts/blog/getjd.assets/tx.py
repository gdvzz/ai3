import asyncio
import json
import time
import aiohttp
from pathlib import Path
from playwright.async_api import async_playwright

# --- 配置 ---
BASE_URL = "https://join.qq.com"
API_URL = "https://join.qq.com/api/v1/position/searchPosition"
LIST_URL = f"{BASE_URL}/post.html?query=p_1"
OUTPUT_FILE = "tencent_jobs.json"
REQUEST_TIMEOUT = 30000  # 毫秒
CONCURRENT_REQUESTS = 5  # 并发抓取详情页的数量
PAGE_SIZE = 10  # 每页获取10个岗位

# --- 辅助函数 ---
def clean_text(text: str) -> str:
    """清理文本中的多余空白字符"""
    if not text:
        return ""
    lines = text.split('\n')
    cleaned_lines = [line.strip() for line in lines if line.strip()]
    return '\n'.join(cleaned_lines)

async def fetch_all_jobs(session):
    """
    通过API分页获取所有校园招聘岗位
    每页获取 PAGE_SIZE 个
    """
    all_jobs = []
    page_index = 1
    total_count = None
    
    # 正确的请求体结构
    base_payload = {
        "projectIdList": [],
        "projectMappingIdList": [1],  # 关键：1代表校园招聘
        "keyword": "",
        "bgList": [],
        "workCountryType": 0,
        "workCityList": [],
        "recruitCityList": [],
        "positionFidList": [],
        "pageIndex": page_index,
        "pageSize": PAGE_SIZE
    }
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Referer": LIST_URL,
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
    }
    
    try:
        while True:
            # 更新页码
            base_payload["pageIndex"] = page_index
            
            print(f"📡 正在请求第 {page_index} 页 (每页{PAGE_SIZE}个)...")
            async with session.post(API_URL, headers=headers, json=base_payload, timeout=30) as response:
                if response.status != 200:
                    print(f"⚠️ API请求失败，状态码: {response.status}")
                    break
                    
                data = await response.json()
                if data.get("status") != 0:
                    print(f"⚠️ API返回错误: {data.get('message')}")
                    break
                
                position_list = data.get("data", {}).get("positionList", [])
                if total_count is None:
                    total_count = data.get("data", {}).get("count", 0)
                    print(f"📊 服务器总岗位数: {total_count}")
                
                if not position_list:
                    print("📭 当前页无数据，分页结束")
                    break
                
                all_jobs.extend(position_list)
                print(f"  ✅ 获取到 {len(position_list)} 个岗位，累计 {len(all_jobs)} 个")
                
                # 判断是否获取全部
                if len(all_jobs) >= total_count:
                    print("✅ 已获取全部岗位")
                    break
                
                page_index += 1
                
    except Exception as e:
        print(f"❌ 请求API时出错: {e}")
    
    print(f"📋 总共从API获取 {len(all_jobs)} 个岗位")
    return all_jobs

async def scrape_job_detail(page, post_id: str, job_title: str) -> dict:
    """抓取单个岗位的详情页"""
    start_time = time.time()
    job_url = f"{BASE_URL}/post_detail.html?postid={post_id}"
    
    result = {
        "post_id": post_id,
        "title": job_title,
        "url": job_url,
        "description": "",
        "requirements": "",
        "bonus": "",
        "interview_city": "",
        "departments": [],
        "work_locations": [],
        "status": "success",
        "error": None,
        "fetch_time": 0,
        "desc_word_count": 0,
        "req_word_count": 0,
    }

    try:
        await page.goto(job_url, timeout=REQUEST_TIMEOUT)
        await page.wait_for_load_state("networkidle", timeout=REQUEST_TIMEOUT)
        await page.wait_for_selector(".post_detail, .detail_box", state="attached", timeout=10000)

        detail_data = await page.evaluate('''
            () => {
                const result = {
                    description: '',
                    requirements: '',
                    bonus: '',
                    interview_city: '',
                    departments: [],
                    work_locations: []
                };
                
                const boxes = document.querySelectorAll('.detail_box');
                boxes.forEach(box => {
                    const subtitle = box.querySelector('.subtitle');
                    if (!subtitle) return;
                    const titleText = subtitle.innerText.trim();
                    
                    let textContent = '';
                    const textElem = box.querySelector('.detail_text, .detail_text p, .text_box');
                    if (textElem) {
                        textContent = textElem.innerText.trim();
                    } else {
                        const clone = box.cloneNode(true);
                        const subClone = clone.querySelector('.subtitle');
                        if (subClone) subClone.remove();
                        textContent = clone.innerText.trim();
                    }
                    
                    if (titleText.includes('岗位描述')) {
                        result.description = textContent;
                    } else if (titleText.includes('岗位要求')) {
                        result.requirements = textContent;
                    } else if (titleText.includes('加分项')) {
                        result.bonus = textContent;
                    } else if (titleText.includes('面试城市')) {
                        result.interview_city = textContent;
                    } else if (titleText.includes('招聘部门')) {
                        const deptElements = box.querySelectorAll('.branch_tab');
                        deptElements.forEach(dept => {
                            const name = dept.innerText.trim();
                            if (name) result.departments.push(name);
                        });
                        const cityElements = box.querySelectorAll('.cityText span');
                        cityElements.forEach(city => {
                            const cityName = city.innerText.trim();
                            if (cityName) result.work_locations.push(cityName);
                        });
                    }
                });
                
                if (result.work_locations.length === 0) {
                    const citySpans = document.querySelectorAll('.cityText span, .work-city span');
                    citySpans.forEach(span => {
                        const city = span.innerText.trim();
                        if (city) result.work_locations.push(city);
                    });
                }
                
                return result;
            }
        ''')
        
        result.update(detail_data)
        result["desc_word_count"] = len(result["description"])
        result["req_word_count"] = len(result["requirements"])

    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)
        print(f"  ❌ 抓取详情失败: {job_title} (post_id: {post_id}) - {e}")

    result["fetch_time"] = round(time.time() - start_time, 2)
    return result

def save_job_to_file(job_detail: dict, all_jobs: list):
    """将单个岗位追加保存到JSON文件"""
    try:
        # 先更新all_jobs列表
        # 检查是否已存在相同post_id的岗位，如果存在则更新，否则追加
        existing_index = None
        for i, job in enumerate(all_jobs):
            if job.get("post_id") == job_detail.get("post_id"):
                existing_index = i
                break
        
        if existing_index is not None:
            all_jobs[existing_index] = job_detail
        else:
            all_jobs.append(job_detail)
        
        # 写入文件
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            json.dump(all_jobs, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"  ⚠️ 保存文件时出错: {e}")
        return False

async def main():
    start_total = time.time()
    all_jobs = []
    success_count = 0
    error_count = 0
    processed_ids = set()

    # 加载已有数据
    if Path(OUTPUT_FILE).exists():
        try:
            with open(OUTPUT_FILE, 'r', encoding='utf-8') as f:
                existing_data = json.load(f)
                if isinstance(existing_data, list):
                    all_jobs = existing_data
                    for job in all_jobs:
                        if job.get("post_id"):
                            processed_ids.add(job["post_id"])
                    print(f"📂 加载已有数据: {len(all_jobs)} 个岗位")
        except Exception as e:
            print(f"⚠️ 读取已有文件失败: {e}")

    async with aiohttp.ClientSession() as session:
        # 1. 从API获取岗位列表
        position_list = await fetch_all_jobs(session)
        if not position_list:
            print("❌ 无法获取岗位列表，程序退出。")
            return
        
        # 过滤出未处理的岗位
        new_positions = [p for p in position_list if str(p.get("postId")) not in processed_ids]
        print(f"📋 发现 {len(new_positions)} 个新岗位需要抓取")

        if not new_positions:
            print("✅ 所有岗位已是最新，无需抓取。")
            return

        # 2. 启动浏览器抓取详情
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            )
            pages = [await context.new_page() for _ in range(CONCURRENT_REQUESTS)]
            
            try:
                semaphore = asyncio.Semaphore(CONCURRENT_REQUESTS)
                
                async def process_job(position, page):
                    async with semaphore:
                        post_id = str(position.get("postId"))
                        title = position.get("positionTitle", "未知岗位")
                        print(f"🔄 正在抓取: {title} (ID: {post_id})")
                        
                        job_detail = await scrape_job_detail(page, post_id, title)
                        
                        # 合并API中的基础信息
                        job_detail.update({
                            "position_id": position.get("id"),
                            "position_family": position.get("positionFamily"),
                            "bgs": position.get("bgs", "").strip(),
                            "work_cities": position.get("workCities", "").strip(),
                            "project_name": position.get("projectName"),
                            "recruit_label": position.get("recruitLabelName"),
                        })
                        
                        # 每抓取一个就立即保存
                        if save_job_to_file(job_detail, all_jobs):
                            print(f"  💾 已保存到 {OUTPUT_FILE} (累计 {len(all_jobs)} 个)")
                        else:
                            print(f"  ⚠️ 保存失败: {title}")
                        
                        return job_detail
                
                # 分配任务到各个页面
                tasks = []
                for i, pos in enumerate(new_positions):
                    page = pages[i % CONCURRENT_REQUESTS]
                    tasks.append(process_job(pos, page))
                
                # 并发执行所有任务
                results = await asyncio.gather(*tasks)
                
                # 统计结果
                for job_detail in results:
                    if job_detail["status"] == "success":
                        success_count += 1
                    else:
                        error_count += 1
                    
                    processed_ids.add(job_detail["post_id"])
                    print(f"  📊 描述字数: {job_detail['desc_word_count']}, 要求字数: {job_detail['req_word_count']}, 耗时: {job_detail['fetch_time']}s")

            finally:
                await browser.close()

    # 最终统计
    total_time = round(time.time() - start_total, 2)
    print("\n" + "="*50)
    print(f"✅ 抓取完成！总耗时: {total_time} 秒")
    print(f"📊 统计信息:")
    print(f"   - 累计抓取岗位数: {len(all_jobs)}")
    print(f"   - 本次新增成功: {success_count}")
    print(f"   - 本次新增失败: {error_count}")
    print(f"   - 数据文件: {OUTPUT_FILE}")
    print("="*50)

if __name__ == "__main__":
    asyncio.run(main())