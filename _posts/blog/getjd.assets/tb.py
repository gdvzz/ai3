import asyncio
import json
import time
from playwright.async_api import async_playwright

# 全局配置
BASE_LIST_URL = "https://app.mokahr.com/campus-recruitment/threatbook/39679?locale=zh-CN#/jobs?"
OUTPUT_FILE = "threatbook_campus_jobs.json"

# 统计信息
stats = {"total": 0, "success": 0, "error": 0}

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
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080}
        )
        page = await context.new_page()

        print("正在访问列表页...")
        await page.goto(BASE_LIST_URL, wait_until="networkidle", timeout=30000)
        await asyncio.sleep(3)

        seen_ids = set()
        page_num = 1

        while True:
            print(f"\n--- 正在处理第 {page_num} 页 ---")

            # 滚动加载当前页所有岗位
            previous_height = 0
            scroll_attempts = 0
            while scroll_attempts < 20:
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await asyncio.sleep(1.5)
                load_more = await page.query_selector("button:has-text('加载更多'), .load-more, .show-more")
                if load_more:
                    await load_more.click()
                    await asyncio.sleep(1.5)
                    continue
                new_height = await page.evaluate("document.body.scrollHeight")
                if new_height == previous_height:
                    break
                previous_height = new_height
                scroll_attempts += 1

            # 提取当前页岗位数据
            job_items = await page.evaluate('''
                () => {
                    const items = [];
                    const cards = document.querySelectorAll('.card-content-eGHrYZMEX6');
                    cards.forEach(card => {
                        let id = null;
                        const link = card.closest('a[href*="/job/"]');
                        if (link) {
                            const href = link.getAttribute('href');
                            const match = href.match(/\\/job\\/([a-f0-9-]+)/);
                            if (match) id = match[1];
                        }
                        if (!id) {
                            const parent = card.closest('[data-id]');
                            if (parent) id = parent.getAttribute('data-id');
                        }
                        if (!id) return;

                        const titleEl = card.querySelector('.title-u2qk9xX9Ie');
                        const title = titleEl ? titleEl.innerText.trim() : '';

                        const dateEl = card.querySelector('.published-at-PQ5IBWmbJV');
                        const publish_date = dateEl ? dateEl.innerText.trim().replace('发布于 ', '') : '';

                        const infoContainer = card.querySelector('.info-tPG_0QGbhl');
                        const infoItems = infoContainer ? infoContainer.querySelectorAll('.sd-Ellipsis-hiddenContent-1Skwh') : [];
                        const texts = [];
                        infoItems.forEach(el => {
                            const txt = el.innerText.trim();
                            if (txt) texts.push(txt);
                        });
                        const department = texts[0] || '';
                        const job_nature = texts[1] || '';
                        const category = texts[2] || '';
                        const location = texts[3] || '';

                        let description = '';
                        let requirement = '';
                        const descContainer = card.querySelector('.job-description-WwRmovZt9o');
                        if (descContainer) {
                            const paragraphs = descContainer.querySelectorAll('p');
                            let fullText = '';
                            paragraphs.forEach(p => {
                                fullText += p.innerText.trim() + '\\n';
                            });
                            const parts = fullText.split(/任职条件[：:]/);
                            if (parts.length >= 2) {
                                description = parts[0].replace(/岗位职责[：:]/, '').trim();
                                requirement = parts[1].trim();
                            } else {
                                description = fullText.trim();
                            }
                        }
                        if (!description) {
                            const shortDesc = card.querySelector('.short-description-hpQeFUeJUY');
                            if (shortDesc) {
                                description = shortDesc.innerText.trim();
                            }
                        }

                        items.push({
                            id: id,
                            title: title,
                            department: department,
                            job_nature: job_nature,
                            category: category,
                            location: location,
                            publish_date: publish_date,
                            description: description,
                            requirement: requirement,
                        });
                    });
                    return items;
                }
            ''')

            if not job_items:
                print("当前页未提取到岗位，结束")
                break

            # 去重并保存
            new_count = 0
            for job in job_items:
                if job['id'] in seen_ids:
                    continue
                seen_ids.add(job['id'])
                new_count += 1
                stats["total"] += 1

                job_data = {
                    "id": job['id'],
                    "title": job['title'],
                    "department": job['department'],
                    "job_nature": job['job_nature'],
                    "category": job['category'],
                    "location": job['location'],
                    "publish_date": job['publish_date'],
                    "description": job['description'],
                    "requirement": job['requirement'],
                    "detail_url": f"https://app.mokahr.com/campus-recruitment/threatbook/39679?locale=zh-CN#/job/{job['id']}",
                }

                await save_job_to_file(job_data)
                stats["success"] += 1
                print(f"  ✅ {job['title']} (ID: {job['id'][:8]}...)")

            print(f"本页新增 {new_count} 个岗位，累计 {len(seen_ids)} 个")

            # 翻页逻辑 - 根据实际分页结构
            # 方式1: 查找“下一页”按钮
            next_button = await page.query_selector("button:has-text('下一页'), a:has-text('下一页'), .pagination-next, .next-page")
            
            if not next_button:
                # 方式2: 查找分页列表，获取当前页码并点击下一页
                page_buttons = await page.query_selector_all(".sd-Pagination-item-1cqBB")
                if page_buttons:
                    current_page_num = None
                    for btn in page_buttons:
                        is_active = await btn.get_attribute("class")
                        if is_active and "sd-Pagination-is-active-k2u5n" in is_active:
                            page_text = await btn.inner_text()
                            if page_text.isdigit():
                                current_page_num = int(page_text)
                                break
                    
                    if current_page_num is not None:
                        # 查找下一页对应的页码按钮
                        for btn in page_buttons:
                            page_text = await btn.inner_text()
                            if page_text.isdigit() and int(page_text) == current_page_num + 1:
                                next_button = btn
                                break
            
            if not next_button:
                print("未找到下一页按钮，已到达最后一页")
                break

            is_disabled = await next_button.get_attribute("disabled")
            if is_disabled:
                print("下一页按钮已禁用，已到最后一页")
                break

            print(f"点击翻到第 {page_num + 1} 页...")
            await next_button.click()
            await asyncio.sleep(3)
            page_num += 1

        await browser.close()

    total_elapsed = time.time() - start_total_time
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