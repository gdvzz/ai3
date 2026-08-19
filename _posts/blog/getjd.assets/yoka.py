import asyncio
import json
import re
import time
from datetime import datetime
from pathlib import Path
from playwright.async_api import (
    async_playwright,
    TimeoutError as PlaywrightTimeoutError,
)

# 配置
BASE_URL = (
    "https://app.mokahr.com/campus-recruitment/yokagames/41940#/jobs?page=1&pageSize=50"
)
OUTPUT_JSON = "yokagames_jobs.json"
DETAIL_BASE_URL = "https://app.mokahr.com/campus-recruitment/yokagames/41940"

stats = {"total_found": 0, "success": 0, "failed": 0, "start_time": datetime.now()}


def save_job_to_json(job_data):
    existing = []
    if Path(OUTPUT_JSON).exists():
        try:
            with open(OUTPUT_JSON, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except:
            existing = []
    existing.append(job_data)
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)


async def fetch_job_detail(page, job_id, job_name):
    """在新标签页中打开并抓取单个岗位详情（保留原文 + 换行）"""
    job_data = {}
    start_time = time.time()
    detail_url = f"{DETAIL_BASE_URL}#/job/{job_id}"
    job_data["job_id"] = job_id
    job_data["job_name"] = job_name
    job_data["detail_url"] = detail_url

    new_page = await page.context.new_page()

    try:
        await new_page.goto(detail_url, wait_until="networkidle", timeout=20000)
        await new_page.wait_for_timeout(1500)

        # ---- 1. 提取职位描述（保留换行） ----
        job_data["job_description"] = ""
        job_data["job_requirements"] = ""

        desc_container = new_page.locator(".job-description-VvfEUGocNE").first
        if await desc_container.count() > 0:
            # ---- 修复点：逐段落提取，保留换行 ----
            # 获取所有 <p> 标签
            p_elements = desc_container.locator("p")
            p_count = await p_elements.count()

            if p_count > 0:
                desc_parts = []
                for i in range(p_count):
                    p_text = await p_elements.nth(i).text_content()
                    if p_text:
                        desc_parts.append(p_text.strip())
                # 用换行符连接
                job_data["job_description"] = "\n".join(desc_parts)
            else:
                # 备选：直接获取文本，但保留换行
                desc_text = await desc_container.text_content()
                if desc_text:
                    # 按行分割，去除空行
                    lines = [
                        line.strip() for line in desc_text.split("\n") if line.strip()
                    ]
                    job_data["job_description"] = "\n".join(lines)
        else:
            # 备选提取
            body_text = await new_page.locator("body").text_content()
            if body_text:
                match = re.search(
                    r"职位描述\s*(.*?)(?:职位信息|$)", body_text, re.DOTALL
                )
                if match:
                    raw = match.group(1).strip()
                    lines = [line.strip() for line in raw.split("\n") if line.strip()]
                    job_data["job_description"] = "\n".join(lines)

        # ---- 2. 提取其他基本信息 ----
        info_elem = new_page.locator(".info-UcB_mxJq8y").first
        if await info_elem.count() > 0:
            info_text = await info_elem.text_content()
            if info_text:
                parts = [p.strip() for p in info_text.split("|")]
                if len(parts) >= 4:
                    job_data["education"] = parts[0]
                    job_data["job_nature"] = parts[1]
                    job_data["experience"] = parts[2]
                    job_data["location"] = parts[3]

        date_elem = new_page.locator(".sd-foundation-body-tertiary-2xged").first
        if await date_elem.count() > 0:
            date_text = await date_elem.text_content()
            if date_text:
                match = re.search(r"(\d{4}-\d{2}-\d{2})", date_text)
                if match:
                    job_data["publish_date"] = match.group(1)

        interview_elem = new_page.locator(
            ".info-row-HSEUCEHeFr:has-text('是否笔试') .value-mOhfHL5YFY"
        ).first
        if await interview_elem.count() > 0:
            interview_text = await interview_elem.text_content()
            if interview_text:
                job_data["interview"] = interview_text.strip()

        # 确保所有字段存在
        job_data.setdefault("education", "")
        job_data.setdefault("job_nature", "")
        job_data.setdefault("experience", "")
        job_data.setdefault("location", "")
        job_data.setdefault("publish_date", "")
        job_data.setdefault("interview", "")
        job_data.setdefault("job_description", "")
        job_data.setdefault("job_requirements", "")

        desc_len = len(job_data.get("job_description", "") or "")
        print(f"   📝 描述原文长度: {desc_len}字")
        print(
            f"   📋 {job_data.get('education')} | {job_data.get('job_nature')} | {job_data.get('experience')} | {job_data.get('location')}"
        )

        elapsed = time.time() - start_time
        print(f"   ⏱️ 耗时: {elapsed:.2f}秒")

        stats["success"] += 1
        return job_data, True

    except Exception as e:
        elapsed = time.time() - start_time
        error_msg = str(e)[:100]
        print(f"   ❌ 抓取失败: {error_msg}")
        print(f"   ⏱️ 耗时: {elapsed:.2f}秒")
        stats["failed"] += 1
        job_data["error"] = error_msg
        return job_data, False

    finally:
        await new_page.close()


async def main():
    print("=" * 60)
    print("🚀 游卡校园招聘岗位抓取工具 (保留原文版)")
    print(f"📋 目标URL: {BASE_URL}")
    print(f"💾 输出文件: {OUTPUT_JSON}")
    print("=" * 60)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        )
        page = await context.new_page()

        print("\n⏳ 正在加载列表页...")
        start_load = time.time()
        await page.goto(BASE_URL, wait_until="networkidle")
        load_time = time.time() - start_load
        print(f"   ✅ 列表页加载完成，耗时: {load_time:.2f}秒")

        try:
            await page.wait_for_selector("div.jobs-AkItzswt6b", timeout=15000)
            print("   ✅ 职位容器已加载")
        except PlaywrightTimeoutError:
            print("   ⚠️ 未找到职位容器")

        cards = await page.locator("div.jobs-AkItzswt6b a[href*='#/job/']").all()

        seen_hrefs = set()
        unique_cards = []
        for card in cards:
            href = await card.get_attribute("href")
            if href and href not in seen_hrefs and "#/job/" in href:
                seen_hrefs.add(href)
                unique_cards.append(card)

        card_count = len(unique_cards)
        stats["total_found"] = card_count
        print(f"\n📊 找到 {card_count} 个唯一职位（预期34个）")

        if card_count == 0:
            print("⚠️ 未找到职位卡片，请检查页面结构")
            await browser.close()
            return

        print("\n" + "=" * 60)
        print("开始抓取岗位详情...")
        print("=" * 60 + "\n")

        Path(OUTPUT_JSON).write_text("[]", encoding="utf-8")

        for i, card in enumerate(unique_cards):
            try:
                job_name = "未知岗位"
                title_elem = card.locator("span.title-u2qk9xX9Ie").first
                if await title_elem.count() > 0:
                    job_name = await title_elem.text_content()
                    job_name = job_name.strip() if job_name else "未知岗位"

                href = await card.get_attribute("href")
                job_id = (
                    href.replace("#/job/", "") if href and "#/job/" in href else None
                )

                if not job_id:
                    print(f"\n❌ 第 {i+1} 个职位缺少ID，跳过")
                    stats["failed"] += 1
                    continue

                print(f"\n📌 处理第 {i+1}/{card_count} 个: {job_name}")

                job_data, success = await fetch_job_detail(page, job_id, job_name)
                save_job_to_json(job_data)

                if success:
                    print(f"   ✅ 已保存: {job_data.get('job_name', '未知')}")
                else:
                    print(f"   ⚠️ 已保存错误记录")

                print(f"   📈 累计: 成功 {stats['success']} / 失败 {stats['failed']}")

                await page.wait_for_timeout(300)

            except Exception as e:
                print(f"❌ 处理第 {i+1} 个职位时出错: {e}")
                stats["failed"] += 1
                continue

        elapsed_total = (datetime.now() - stats["start_time"]).total_seconds()
        print("\n" + "=" * 60)
        print("📊 抓取完成！")
        print(f"   ✅ 成功: {stats['success']} 个")
        print(f"   ❌ 失败: {stats['failed']} 个")
        print(f"   📊 总计: {stats['total_found']} 个")
        print(f"   ⏱️ 总耗时: {elapsed_total:.2f}秒")
        if stats["success"] > 0:
            print(f"   ⏱️ 平均: {elapsed_total/stats['success']:.2f}秒/个")
        print(f"   💾 数据: {OUTPUT_JSON}")
        print("=" * 60)

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
