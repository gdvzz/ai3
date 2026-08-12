import asyncio
import json
import time
import re
from playwright.async_api import async_playwright

# 全局配置
BASE_LIST_URL = "https://nio.jobs.feishu.cn/campus/?project=7660736309090715940&current={page}"
DETAIL_URL_PREFIX = "https://nio.jobs.feishu.cn/campus/position/"
OUTPUT_FILE = "nio_campus_jobs.json"

async def scrape_job_detail(page, job_id):
    """抓取单个岗位的详情页"""
    detail_url = f"{DETAIL_URL_PREFIX}{job_id}/detail"
    start_time = time.time()
    print(f"  -> 正在抓取详情: {detail_url}")

    try:
        await page.goto(detail_url, wait_until="domcontentloaded", timeout=15000)
        await page.wait_for_selector(".jobDetail", timeout=10000)
        await asyncio.sleep(0.5)

        # 1. 提取岗位标题
        title_elem = await page.query_selector('span[data-test="jobTitle"]')
        title = await title_elem.inner_text() if title_elem else ""

        # 2. 提取岗位信息 - 改进版
        job_info = {}
        
        # 获取 .job-info 下所有直接子元素
        info_elements = await page.query_selector_all(".job-info > *")
        info_texts = []
        for elem in info_elements:
            text = await elem.inner_text()
            text = text.strip()
            if text:
                info_texts.append(text)
        
        # 根据实际显示顺序分配
        # 注意：第6个元素是 "职位 ID：A134913"，需要单独处理
        if len(info_texts) >= 7:
            job_info["location"] = info_texts[0]      # 上海
            job_info["recruit_type"] = info_texts[1]  # 校招
            job_info["job_nature"] = info_texts[2]    # 正式
            job_info["category"] = info_texts[3]      # 产品 - 产品经理
            job_info["education"] = info_texts[4]     # 本科及以上
            job_info["project"] = info_texts[5]       # 2027届校园招聘-技术提前批
            job_info["job_id_display"] = info_texts[6].replace("职位 ID：", "").strip()  # A134913
        elif len(info_texts) >= 6:
            # 如果只有6个元素，可能职位ID在最后一个
            job_info["location"] = info_texts[0]
            job_info["recruit_type"] = info_texts[1]
            job_info["job_nature"] = info_texts[2]
            job_info["category"] = info_texts[3]
            job_info["education"] = info_texts[4]
            # 检查最后一个是否包含"职位 ID"
            if "职位 ID：" in info_texts[5]:
                job_info["job_id_display"] = info_texts[5].replace("职位 ID：", "").strip()
                job_info["project"] = ""
            else:
                job_info["project"] = info_texts[5]
                job_info["job_id_display"] = ""
        elif len(info_texts) >= 5:
            job_info["location"] = info_texts[0]
            job_info["recruit_type"] = info_texts[1]
            job_info["job_nature"] = info_texts[2]
            job_info["category"] = info_texts[3]
            job_info["education"] = info_texts[4]
            job_info["project"] = ""
            job_info["job_id_display"] = ""

        # 打印调试信息
        print(f"    提取到的信息: 地点={job_info.get('location', 'N/A')}, 类型={job_info.get('recruit_type', 'N/A')}, 性质={job_info.get('job_nature', 'N/A')}, 分类={job_info.get('category', 'N/A')}, 学历={job_info.get('education', 'N/A')}, 项目={job_info.get('project', 'N/A')}, 职位ID显示={job_info.get('job_id_display', 'N/A')}")

        # 3. 提取职位描述
        description = ""
        block_titles = await page.query_selector_all(".block-title")
        for block in block_titles:
            title_text = await block.inner_text()
            if "职位描述" in title_text:
                next_elem = await block.evaluate_handle('''
                    (element) => {
                        let next = element.nextElementSibling;
                        while (next && !next.classList.contains('block-content')) {
                            next = next.nextElementSibling;
                        }
                        return next;
                    }
                ''')
                if next_elem:
                    description = await next_elem.inner_text()
                break

        if not description:
            all_contents = await page.query_selector_all(".block-content")
            if all_contents and len(all_contents) >= 1:
                description = await all_contents[0].inner_text()

        # 4. 提取职位要求
        requirement = ""
        for block in block_titles:
            title_text = await block.inner_text()
            if "职位要求" in title_text:
                next_elem = await block.evaluate_handle('''
                    (element) => {
                        let next = element.nextElementSibling;
                        while (next && !next.classList.contains('block-content')) {
                            next = next.nextElementSibling;
                        }
                        return next;
                    }
                ''')
                if next_elem:
                    requirement = await next_elem.inner_text()
                break

        if not requirement:
            all_contents = await page.query_selector_all(".block-content")
            if all_contents and len(all_contents) >= 2:
                requirement = await all_contents[1].inner_text()

        elapsed = time.time() - start_time
        print(f"    详情抓取完成 | 标题: {title[:30] if title else 'N/A'}... | 描述: {len(description)}字 | 要求: {len(requirement)}字 | 耗时: {elapsed:.2f}秒")

        return {
            "detail_url": detail_url,
            "title": title,
            "location": job_info.get("location", ""),
            "recruit_type": job_info.get("recruit_type", ""),
            "job_nature": job_info.get("job_nature", ""),
            "category": job_info.get("category", ""),
            "education": job_info.get("education", ""),
            "project": job_info.get("project", ""),
            "job_id_display": job_info.get("job_id_display", ""),
            "description": description,
            "requirement": requirement,
            "fetch_time": elapsed
        }
    except Exception as e:
        print(f"    详情页抓取出错: {e}")
        return {
            "detail_url": detail_url,
            "error": str(e),
            "fetch_time": time.time() - start_time
        }

async def save_job_to_file(job_data):
    """将单个岗位数据追加到JSON文件中"""
    try:
        with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
            all_jobs = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        all_jobs = []

    all_jobs.append(job_data)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(all_jobs, f, ensure_ascii=False, indent=2)

async def main():
    start_total_time = time.time()
    print(f"程序开始运行，输出文件: {OUTPUT_FILE}")
    print("=" * 60)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080}
        )
        
        list_page = await context.new_page()
        detail_page = await context.new_page()

        current_page = 1
        total_fetched = 0
        max_pages = 30

        while current_page <= max_pages:
            print(f"\n{'='*60}")
            print(f"正在抓取列表页: 第 {current_page} 页")
            print(f"{'='*60}")
            list_url = BASE_LIST_URL.format(page=current_page)

            try:
                await list_page.goto(list_url, wait_until="domcontentloaded", timeout=15000)
                await asyncio.sleep(3)

                job_links = await list_page.query_selector_all("a[href*='/campus/position/']")
                
                if not job_links:
                    print("  未找到任何岗位链接，可能已到最后一页")
                    break

                print(f"  找到 {len(job_links)} 个岗位链接")

                for link in job_links:
                    try:
                        href = await link.get_attribute("href")
                        if not href:
                            continue
                            
                        id_match = re.search(r"/position/(\d+)/", href)
                        if not id_match:
                            print(f"  无法从链接提取ID: {href}")
                            continue
                            
                        job_id = id_match.group(1)
                        print(f"\n  处理岗位，ID: {job_id}")
                        
                        title = await link.inner_text()
                        if not title or title.strip() == "":
                            parent = await link.query_selector("xpath=..")
                            if parent:
                                title_elem = await parent.query_selector(".positionItem-title-text")
                                if title_elem:
                                    title = await title_elem.inner_text()
                        
                        title = title.strip() if title else "Unknown"
                        title = title.split('\n')[0]
                        print(f"    岗位名称: {title}")
                        
                        detail_data = await scrape_job_detail(detail_page, job_id)
                        
                        full_job_data = {
                            "id": job_id,
                            "title": title,
                            "detail_url": f"{DETAIL_URL_PREFIX}{job_id}/detail",
                            **detail_data
                        }
                        
                        await save_job_to_file(full_job_data)
                        total_fetched += 1
                        print(f"    ✅ 已保存岗位: {title} (累计: {total_fetched})")
                        
                        await asyncio.sleep(0.5)

                    except Exception as e:
                        print(f"    处理岗位时出错: {e}")

                # 翻页逻辑
                next_button = await list_page.query_selector("li.atsx-pagination-next")
                
                if not next_button:
                    print("\n  未找到下一页按钮")
                    break
                
                is_disabled = await next_button.get_attribute("class")
                if is_disabled and "atsx-pagination-disabled" in is_disabled:
                    print("\n  下一页按钮已禁用，已到达最后一页")
                    break
                
                page_items = await list_page.query_selector_all("li.atsx-pagination-item")
                total_pages = 0
                for item in page_items:
                    title_attr = await item.get_attribute("title")
                    if title_attr and title_attr.isdigit():
                        page_num = int(title_attr)
                        if page_num > total_pages:
                            total_pages = page_num
                
                if total_pages > 0:
                    print(f"  总共有 {total_pages} 页，当前第 {current_page} 页")
                    if current_page >= total_pages:
                        print("  已到达最后一页")
                        break

                print(f"\n  翻到第 {current_page + 1} 页...")
                next_link = await next_button.query_selector("a")
                if next_link:
                    await next_link.click()
                else:
                    await next_button.click()
                
                await asyncio.sleep(3)
                current_page += 1

            except Exception as e:
                print(f"  列表页处理出错: {e}")
                import traceback
                traceback.print_exc()
                break

        print("\n按任意键关闭浏览器...")
        input()
        await browser.close()

    total_elapsed = time.time() - start_total_time
    print(f"\n{'='*60}")
    print(f"抓取完成!")
    print(f"{'='*60}")
    print(f"总计抓取岗位数: {total_fetched}")
    print(f"总耗时: {total_elapsed:.2f} 秒 ({total_elapsed/60:.2f} 分钟)")
    print(f"数据已保存至: {OUTPUT_FILE}")
    print(f"{'='*60}")

if __name__ == "__main__":
    asyncio.run(main())