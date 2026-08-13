import asyncio
import json
import time
import re
from playwright.async_api import async_playwright

# 全局配置
BASE_LIST_URL = "https://xiaomi.jobs.f.mioffice.cn/campus/?project=7659311908839262514&current={page}&limit=10"
DETAIL_URL_PREFIX = "https://xiaomi.jobs.f.mioffice.cn/campus/position/"
OUTPUT_FILE = "xiaomi_campus_jobs.json"

async def scrape_job_detail(page, job_id):
    """抓取单个岗位的详情页（增强版）"""
    detail_url = f"{DETAIL_URL_PREFIX}{job_id}/detail"
    start_time = time.time()
    print(f"  -> 正在抓取详情: {detail_url}")

    # 初始化一个空的结果字典
    result = {
        "detail_url": detail_url,
        "title": "",
        "location": "",
        "recruit_type": "",
        "job_nature": "",
        "category": "",
        "project": "",
        "description": "",
        "requirement": "",
        "fetch_time": 0,
        "error": None
    }

    try:
        # 1. 访问页面并增加等待时间
        await page.goto(detail_url, wait_until="domcontentloaded", timeout=20000)
        # 等待核心容器出现，最多等待15秒
        await page.wait_for_selector(".jobDetail", timeout=15000)
        # 额外等待，确保所有文本都渲染完成
        await asyncio.sleep(2)

        # 2. 提取岗位标题 (使用多个备选选择器)
        title_selectors = ['span[data-test="jobTitle"]', '.job-title', '.job-header span']
        for selector in title_selectors:
            title_elem = await page.query_selector(selector)
            if title_elem:
                title_text = await title_elem.inner_text()
                if title_text and title_text.strip():
                    result["title"] = title_text.strip()
                    break

        # 3. 提取岗位信息 (.job-info 下的所有直接子元素)
        info_texts = []
        info_elements = await page.query_selector_all(".job-info > *")
        for elem in info_elements:
            text = await elem.inner_text()
            if text and text.strip():
                info_texts.append(text.strip())

        # 根据已知结构分配信息 (位置、类型、性质、分类、项目)
        if len(info_texts) >= 5:
            result["location"] = info_texts[0]
            result["recruit_type"] = info_texts[1]
            result["job_nature"] = info_texts[2]
            result["category"] = info_texts[3]
            result["project"] = info_texts[4]
        elif len(info_texts) >= 1:
            # 如果信息不全，尝试从文本中智能提取，但至少保留一些内容
            result["location"] = info_texts[0] if len(info_texts) > 0 else ""
            result["recruit_type"] = info_texts[1] if len(info_texts) > 1 else ""
            result["job_nature"] = info_texts[2] if len(info_texts) > 2 else ""
            result["category"] = info_texts[3] if len(info_texts) > 3 else ""
            result["project"] = info_texts[4] if len(info_texts) > 4 else ""

        # 4. 提取职位描述和职位要求
        # 查找所有 .block-title 和其后的 .block-content
        block_titles = await page.query_selector_all(".block-title")
        for i, block in enumerate(block_titles):
            title_text = await block.inner_text()
            # 获取下一个兄弟元素 .block-content
            next_elem = await block.evaluate_handle('''
                (element) => {
                    let next = element.nextElementSibling;
                    while (next && !next.classList.contains('block-content')) {
                        next = next.nextElementSibling;
                    }
                    return next;
                }
            ''')
            content_text = ""
            if next_elem:
                content_text = await next_elem.inner_text()
                content_text = content_text.strip()

            if "职位描述" in title_text and not result["description"]:
                result["description"] = content_text
            elif "职位要求" in title_text and not result["requirement"]:
                result["requirement"] = content_text

        # 如果通过 .block-title 没找到，尝试直接查找 .block-content
        if not result["description"] or not result["requirement"]:
            all_contents = await page.query_selector_all(".block-content")
            if all_contents:
                # 如果还没找到描述，尝试将第一个 .block-content 作为描述
                if not result["description"] and len(all_contents) >= 1:
                    result["description"] = await all_contents[0].inner_text()
                # 如果还没找到要求，尝试将第二个 .block-content 作为要求
                if not result["requirement"] and len(all_contents) >= 2:
                    result["requirement"] = await all_contents[1].inner_text()

        # 5. 如果标题仍然为空，尝试从页面其他位置获取
        if not result["title"]:
            fallback_title = await page.query_selector('.job-header')
            if fallback_title:
                result["title"] = await fallback_title.inner_text()

        elapsed = time.time() - start_time
        result["fetch_time"] = elapsed
        
        print(f"    提取到的信息: 地点={result['location']}, 类型={result['recruit_type']}, 性质={result['job_nature']}, 分类={result['category']}, 项目={result['project']}")
        print(f"    详情抓取完成 | 标题: {result['title'][:30] if result['title'] else 'N/A'}... | 描述: {len(result['description'])}字 | 要求: {len(result['requirement'])}字 | 耗时: {elapsed:.2f}秒")
        
        # 如果核心信息（如标题）仍然缺失，记录一个警告
        if not result["title"]:
            print(f"    ⚠️ 警告: 未能提取到岗位标题，页面结构可能发生变化。")
            # 打印部分页面内容以帮助调试
            body_text = await page.inner_text('body')
            print(f"    页面内容预览: {body_text[:200]}...")

    except Exception as e:
        elapsed = time.time() - start_time
        result["fetch_time"] = elapsed
        result["error"] = str(e)
        print(f"    详情页抓取出错: {e}")

    # 即使出错也返回已提取到的部分信息
    return result

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
        max_pages = 68

        while current_page <= max_pages:
            print(f"\n{'='*60}")
            print(f"正在抓取列表页: 第 {current_page} 页")
            print(f"{'='*60}")
            list_url = BASE_LIST_URL.format(page=current_page)

            try:
                await list_page.goto(list_url, wait_until="domcontentloaded", timeout=15000)
                await asyncio.sleep(3)

                # 方案1: 直接查找所有详情链接（最可靠）
                job_links = await list_page.query_selector_all("a[href*='/campus/position/']")
                
                if job_links:
                    print(f"  通过链接找到 {len(job_links)} 个岗位")
                    
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
                            
                            # 获取岗位标题 - 从链接本身或父元素
                            title = await link.inner_text()
                            if not title or title.strip() == "":
                                # 尝试从父元素获取
                                parent = await link.query_selector("xpath=..")
                                if parent:
                                    title_elem = await parent.query_selector(".positionItem-title-text")
                                    if title_elem:
                                        title = await title_elem.inner_text()
                            
                            title = title.strip() if title else "Unknown"
                            # 如果标题包含换行，只取第一行
                            title = title.split('\n')[0]
                            
                            print(f"\n  处理岗位: {title}, ID: {job_id}")
                            
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
                else:
                    # 方案2: 尝试查找岗位卡片
                    print("  未找到链接，尝试查找岗位卡片...")
                    job_cards = await list_page.query_selector_all('div[data-test="positionItem"]')
                    
                    if not job_cards:
                        job_cards = await list_page.query_selector_all('.job-list-item')
                    
                    if job_cards:
                        print(f"  找到 {len(job_cards)} 个岗位卡片")
                        for card in job_cards:
                            try:
                                # 在卡片内查找链接
                                link_elem = await card.query_selector("a[href*='/campus/position/']")
                                if not link_elem:
                                    # 尝试在卡片内查找任何链接
                                    all_links = await card.query_selector_all("a")
                                    for l in all_links:
                                        href = await l.get_attribute("href")
                                        if href and "/campus/position/" in href:
                                            link_elem = l
                                            break
                                
                                if link_elem:
                                    href = await link_elem.get_attribute("href")
                                    id_match = re.search(r"/position/(\d+)/", href)
                                    if id_match:
                                        job_id = id_match.group(1)
                                        title_elem = await card.query_selector(".positionItem-title-text")
                                        if not title_elem:
                                            title_elem = await card.query_selector(".job-title")
                                        title = await title_elem.inner_text() if title_elem else "Unknown"
                                        title = title.strip()
                                        
                                        print(f"\n  处理岗位: {title}, ID: {job_id}")
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
                    else:
                        print("  未找到任何岗位")
                        # 调试：打印页面内容
                        page_text = await list_page.inner_text("body")
                        print(f"  页面文本前500字符: {page_text[:500]}")
                        break

                # 翻页逻辑
                next_button = await list_page.query_selector("li.atsx-pagination-next")
                
                if not next_button:
                    print("\n  未找到下一页按钮")
                    break
                
                is_disabled = await next_button.get_attribute("class")
                if is_disabled and "atsx-pagination-disabled" in is_disabled:
                    print("\n  下一页按钮已禁用，已到达最后一页")
                    break
                
                # 获取总页数
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