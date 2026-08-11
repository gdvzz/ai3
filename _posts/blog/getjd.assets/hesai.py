import asyncio
import json
import os
import time
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

BASE_LIST_URL = "https://kwh0jtf778.jobs.feishu.cn/229043/position/list"
OUTPUT_FILE = "hesai_jobs_2026.json"
TOTAL_PAGES = 15  # 已知总页数

async def get_job_links_on_page(page):
    """获取当前页所有岗位详情链接"""
    origin = await page.evaluate("window.location.origin")
    try:
        await page.wait_for_selector('a[href*="/position/"]', timeout=5000)
    except PlaywrightTimeoutError:
        return []
    link_elements = await page.locator('a[href*="/position/"]').all()
    unique_links = set()
    for elem in link_elements:
        href = await elem.get_attribute("href")
        if href and "/detail" in href:
            if href.startswith("/"):
                full_link = f"{origin}{href}"
            else:
                full_link = href
            unique_links.add(full_link)
    return list(unique_links)

def append_job_to_file(job_data, filename=OUTPUT_FILE):
    """追加单个岗位数据到 JSON 文件"""
    if os.path.exists(filename):
        with open(filename, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                data = []
    else:
        data = []
    data.append(job_data)
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

async def scrape_job_detail(page, detail_url):
    """
    基于 HTML 结构提取岗位详情（使用 .block-title + .block-content）
    """
    start_time = time.time()
    await page.goto(detail_url, wait_until="domcontentloaded")
    try:
        await page.wait_for_selector('.job-title', timeout=5000)
    except PlaywrightTimeoutError:
        pass

    job_info = {"url": detail_url}

    # ---- 职位名称 ----
    try:
        title = await page.locator('.job-title').inner_text()
        job_info["title"] = title.strip()
    except:
        job_info["title"] = ""

    # ---- 地点 / 类型 / 分类 ----
    try:
        info_spans = page.locator('.job-info > span:not(.lineDevider)')
        count = await info_spans.count()
        tags = []
        for i in range(count):
            text = await info_spans.nth(i).inner_text()
            if text.strip():
                tags.append(text.strip())
        location = tags[0] if len(tags) > 0 and tags[0] in ["上海", "杭州"] else ""
        job_type = tags[1] if len(tags) > 1 and tags[1] in ["正式", "实习"] else ""
        category = tags[2] if len(tags) > 2 else ""
        job_info["location"] = location
        job_info["job_type"] = job_type
        job_info["category"] = category
    except:
        job_info["location"] = job_info["job_type"] = job_info["category"] = ""

    # ---- 职位描述 ----
    try:
        desc_block = page.locator('.block-title:has-text("职位描述") + .block-content')
        desc = await desc_block.inner_text()
        job_info["description"] = desc.strip()
    except:
        job_info["description"] = ""

    # ---- 职位要求（含加分项） ----
    try:
        req_block = page.locator('.block-title:has-text("职位要求") + .block-content')
        req = await req_block.inner_text()
        job_info["requirements"] = req.strip()
    except:
        job_info["requirements"] = ""

    elapsed = round(time.time() - start_time, 2)
    return job_info, elapsed

async def main():
    async with async_playwright() as p:
        # 显示浏览器，加速（禁用图片和CSS）
        browser = await p.chromium.launch(
            headless=False,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-images",
                "--disable-css"
            ]
        )
        context = await browser.new_context(
            viewport={"width": 1200, "height": 800},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/130.0.0.0 Safari/537.36",
            bypass_csp=True
        )
        page = await context.new_page()

        print("正在访问列表页...")
        await page.goto(BASE_LIST_URL, wait_until="domcontentloaded")
        await page.wait_for_timeout(2000)

        # 清空旧文件
        if os.path.exists(OUTPUT_FILE):
            os.remove(OUTPUT_FILE)

        all_links = set()      # 用于去重
        total_success = 0

        # 循环页码 1~15
        for page_num in range(1, TOTAL_PAGES + 1):
            print(f"\n--- 正在处理第 {page_num}/{TOTAL_PAGES} 页 ---")

            # 如果不是第一页，点击页码数字切换
            if page_num > 1:
                try:
                    # 使用 XPath 点击包含页码的 li 或 a
                    await page.click(f'//li[normalize-space()="{page_num}"] | //a[normalize-space()="{page_num}"]')
                    await page.wait_for_load_state("networkidle")
                    await page.wait_for_timeout(1000)
                except Exception as e:
                    print(f"⚠️ 点击页码 {page_num} 失败：{e}，尝试直接滚动加载...")
                    # 若点击失败，尝试滚动到底部触发加载（备用）
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await page.wait_for_timeout(1500)

            # 滚动到底部以确保加载完整
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(500)

            links = await get_job_links_on_page(page)
            print(f"当前页找到 {len(links)} 个岗位链接")

            if not links:
                print("⏳ 本页无链接，等待2秒后重试...")
                await page.wait_for_timeout(2000)
                links = await get_job_links_on_page(page)
                if not links:
                    print("跳过此页")
                    continue

            for link in links:
                if link in all_links:
                    continue
                all_links.add(link)

                print(f"  🔍 抓取: {link}")
                try:
                    detail_page = await context.new_page()
                    job_data, elapsed = await scrape_job_detail(detail_page, link)
                    await detail_page.close()

                    title = job_data.get('title', '未知标题')
                    desc_len = len(job_data.get('description', ''))
                    req_len = len(job_data.get('requirements', ''))
                    print(f"    ✅ 标题: {title}")
                    print(f"    📝 描述:{desc_len}字  要求:{req_len}字")
                    print(f"    ⏱️ 耗时: {elapsed}秒")

                    append_job_to_file(job_data)
                    total_success += 1
                    print(f"    💾 已保存 (累计 {total_success} 条)")
                except Exception as e:
                    print(f"    ❌ 抓取失败: {e}")
                    append_job_to_file({"url": link, "error": str(e)})

                await page.wait_for_timeout(300)   # 短延时

        await browser.close()

        if os.path.exists(OUTPUT_FILE):
            with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            print(f"\n✅ 共抓取 {len(data)} 个岗位，已保存至 {OUTPUT_FILE}")
        else:
            print("\n⚠️ 没有抓取到任何岗位，文件未生成。")

if __name__ == "__main__":
    asyncio.run(main())