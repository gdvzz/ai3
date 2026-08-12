import asyncio
import json
import time
import re
from playwright.async_api import async_playwright

# 全局配置
BASE_LIST_URL = "https://envision-career.com/#/jobs?project%5B0%5D=100124183&page={page}&anchorName=jobsList"
DETAIL_URL_PREFIX = "https://envision-career.com/#/job/"
OUTPUT_FILE = "envision_campus_jobs.json"

async def scrape_job_detail(page, job_id):
    """抓取单个岗位的详情页"""
    detail_url = f"{DETAIL_URL_PREFIX}{job_id}"
    start_time = time.time()
    print(f"  -> 正在抓取详情: {detail_url}")

    try:
        # 访问详情页
        await page.goto(detail_url, wait_until="domcontentloaded", timeout=15000)
        # 等待内容加载
        await page.wait_for_selector(".job-description-VvfEUGocNE", timeout=10000)
        await asyncio.sleep(1)

        # 1. 提取岗位标题
        title_elem = await page.query_selector(".title-ROUQFdjmhP")
        title = await title_elem.inner_text() if title_elem else ""

        # 2. 提取岗位信息（公司、地点等）
        job_info = {}
        info_texts = []
        info_elems = await page.query_selector_all(".info-UcB_mxJq8y span")
        for elem in info_elems:
            text = await elem.inner_text()
            if text and text.strip() and text != "|":
                info_texts.append(text.strip())
        
        if len(info_texts) >= 2:
            job_info["company"] = info_texts[0]  # 远景能源
            job_info["location"] = info_texts[1]  # 上海市

        # 3. 提取职位描述
        description = ""
        desc_elem = await page.query_selector(".job-description-VvfEUGocNE")
        if desc_elem:
            description = await desc_elem.inner_text()

        # 清理重复内容（有时页面会有两份相同内容）
        if description:
            # 如果描述中有重复的"我们需要你"，只保留第一份
            parts = description.split("我们需要你：", 1)
            if len(parts) > 1:
                description = "我们需要你：" + parts[1]
            # 如果描述中包含了"我们期望你："之后的内容也保留
            # 但移除可能存在的重复段落
            lines = description.split('\n')
            unique_lines = []
            seen = set()
            for line in lines:
                line = line.strip()
                if line and line not in seen:
                    unique_lines.append(line)
                    seen.add(line)
            description = '\n'.join(unique_lines)

        elapsed = time.time() - start_time
        print(f"    详情抓取完成 | 标题: {title[:30] if title else 'N/A'}... | 描述字数: {len(description)} | 耗时: {elapsed:.2f}秒")

        return {
            "detail_url": detail_url,
            "title": title,
            "company": job_info.get("company", ""),
            "location": job_info.get("location", ""),
            "description": description,
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
        # 启动浏览器（可以改为 headless=False 查看过程）
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080}
        )
        
        # 创建两个页面：一个用于列表，一个用于详情
        list_page = await context.new_page()
        detail_page = await context.new_page()

        current_page = 1
        total_fetched = 0
        max_pages = 30  # 安全限制

        while current_page <= max_pages:
            print(f"\n{'='*60}")
            print(f"正在抓取列表页: 第 {current_page} 页")
            print(f"{'='*60}")
            list_url = BASE_LIST_URL.format(page=current_page)

            try:
                await list_page.goto(list_url, wait_until="domcontentloaded", timeout=15000)
                await asyncio.sleep(3)

                # 查找所有岗位卡片 - 根据提供的HTML，岗位卡片在列表项中
                # 尝试多种选择器
                job_items = await list_page.query_selector_all("li.sd-Pagination-item-1cqBB")  # 这是分页按钮，不是岗位
                # 实际岗位卡片可能需要不同的选择器
                # 根据页面结构，岗位可能在 .job-list-item 或类似的容器中
                
                # 尝试查找岗位链接
                job_links = await list_page.query_selector_all("a[href*='#/job/']")
                
                if not job_links:
                    print("  未找到任何岗位链接，可能页面结构不同")
                    # 打印页面内容帮助调试
                    page_text = await list_page.inner_text("body")
                    print(f"  页面文本前500字符: {page_text[:500]}")
                    break

                print(f"  找到 {len(job_links)} 个岗位链接")

                for link in job_links:
                    try:
                        href = await link.get_attribute("href")
                        if not href:
                            continue
                            
                        # 提取职位ID (从 #/job/ 后面)
                        id_match = re.search(r"#/job/([a-f0-9\-]+)", href)
                        if not id_match:
                            print(f"  无法从链接提取ID: {href}")
                            continue
                            
                        job_id = id_match.group(1)
                        print(f"\n  处理岗位，ID: {job_id}")
                        
                        # 获取岗位标题
                        title = await link.inner_text()
                        title = title.strip() if title else "Unknown"
                        print(f"    岗位名称: {title}")
                        
                        # 使用 detail_page 抓取详情
                        detail_data = await scrape_job_detail(detail_page, job_id)
                        
                        full_job_data = {
                            "id": job_id,
                            "title": title,
                            "detail_url": f"{DETAIL_URL_PREFIX}{job_id}",
                            **detail_data
                        }
                        
                        await save_job_to_file(full_job_data)
                        total_fetched += 1
                        print(f"    ✅ 已保存岗位: {title} (累计: {total_fetched})")
                        
                        await asyncio.sleep(0.5)

                    except Exception as e:
                        print(f"    处理岗位时出错: {e}")

                # 翻页逻辑 - 根据提供的HTML片段
                # 查找下一页按钮
                next_button = await list_page.query_selector("li:last-child button.sd-Pagination-item-1cqBB")
                if not next_button:
                    print("\n  未找到下一页按钮")
                    break
                
                # 检查是否禁用或是否为最后一页
                is_disabled = await next_button.get_attribute("disabled")
                if is_disabled:
                    print("\n  下一页按钮已禁用，已到达最后一页")
                    break
                
                # 检查当前是否在最后一页
                current_page_text = await list_page.query_selector("button.sd-Pagination-is-active-k2u5n")
                if current_page_text:
                    current_page_num = await current_page_text.inner_text()
                    print(f"  当前页码: {current_page_num}")
                    
                    # 检查是否还有下一页
                    all_pages = await list_page.query_selector_all("button.sd-Pagination-item-1cqBB")
                    page_numbers = []
                    for btn in all_pages:
                        num_text = await btn.inner_text()
                        if num_text.isdigit():
                            page_numbers.append(int(num_text))
                    
                    if page_numbers and current_page >= max(page_numbers):
                        print("  已到达最后一页")
                        break

                print(f"\n  翻到第 {current_page + 1} 页...")
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