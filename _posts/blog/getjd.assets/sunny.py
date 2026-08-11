"""
舜宇集团2026校招岗位抓取脚本（分页选择器修复版）
- 使用属性包含匹配定位分页按钮，避免 CSS Modules 后缀干扰
- 自动翻页获取全部岗位ID（80+）
- 逐个抓取详情，实时追加保存为 JSON Lines
- 输出详细调试信息（职位名称、描述字数、耗时等）
- 保存岗位详情页URL
"""

import json
import re
import time
from datetime import datetime
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

BASE_URL = "https://campus.sunnyoptical.cn/campus-recruitment/sunnyoptical/45602/#/jobs"
OUTPUT_FILE = "sunny_optical_jobs.jsonl"
DETAIL_URL_TEMPLATE = "https://campus.sunnyoptical.cn/campus-recruitment/sunnyoptical/45602/#/job/{}"


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


def wait_for_job_links(page):
    try:
        page.wait_for_selector('a[href*="#/job/"]', timeout=10000)
    except PlaywrightTimeout:
        log("⚠ 当前页面未检测到岗位链接，可能页面加载异常")


def collect_job_ids_from_current_page(page):
    links = page.locator('a[href*="#/job/"]')
    ids = []
    for i in range(links.count()):
        href = links.nth(i).get_attribute("href")
        if href:
            m = re.search(r'#/job/([\w-]+)', href)
            if m:
                ids.append(m.group(1))
    # 去重保持顺序
    seen = set()
    unique = []
    for jid in ids:
        if jid not in seen:
            seen.add(jid)
            unique.append(jid)
    return unique


def go_to_next_page(page):
    """翻到下一页（适配 CSS Modules 类名）"""
    # 等待分页区域出现（使用属性包含匹配）
    try:
        page.wait_for_selector('[class*="sd-Pagination-ul"]', timeout=5000)
    except PlaywrightTimeout:
        log("  ⚠ 分页组件未加载")
        return False

    # 找到当前高亮页码
    active_btn = page.locator('[class*="sd-Pagination-ul"] [class*="sd-Pagination-is-active"]').first
    if active_btn.count() == 0:
        log("  ⚠ 未找到当前页码（高亮按钮）")
        return False

    current_page = active_btn.get_attribute('data-page')
    if not current_page:
        log("  ⚠ 无法读取当前页码")
        return False

    current_page = int(current_page)
    next_page = current_page + 1

    # 定位下一页按钮
    next_btn = page.locator(f'[class*="sd-Pagination-ul"] button[data-page="{next_page}"]').first
    if next_btn.count() == 0:
        log(f"  🏁 已经是最后一页（当前页 {current_page}）")
        return False

    # 点击翻页
    next_btn.scroll_into_view_if_needed()
    page.wait_for_timeout(300)
    try:
        next_btn.click(timeout=3000)
    except PlaywrightTimeout:
        log("  ⚠ 点击下一页按钮超时")
        return False

    # 等待页码状态切换（下一页变为高亮）
    try:
        page.wait_for_selector(
            f'[class*="sd-Pagination-ul"] button[data-page="{next_page}"][class*="sd-Pagination-is-active"]',
            timeout=8000
        )
    except PlaywrightTimeout:
        log("  ⚠ 翻页后页码未变化，可能失败")
        return False

    # 额外等待岗位链接刷新
    page.wait_for_timeout(1500)
    return True


def parse_job_detail(page, job_id):
    detail_url = DETAIL_URL_TEMPLATE.format(job_id)
    detail = {
        "岗位ID": job_id,
        "详情页URL": detail_url,
    }
    t0 = time.time()
    try:
        page.wait_for_selector(".title-ROUQFdjmhP", timeout=10000)
    except PlaywrightTimeout:
        log(f"  ⚠ 详情页加载超时 ({job_id})")
        return None

    # 职位名称
    title_el = page.locator(".title-ROUQFdjmhP")
    detail["职位名称"] = title_el.first.inner_text().strip() if title_el.count() > 0 else ""

    # 学历 & 专业
    info_el = page.locator(".info-UcB_mxJq8y")
    if info_el.count() > 0:
        text = info_el.first.inner_text().strip()
        parts = [p.strip() for p in text.split("|")]
        detail["学历"] = parts[0] if len(parts) > 0 else ""
        detail["专业"] = parts[1] if len(parts) > 1 else ""
    else:
        detail["学历"] = ""
        detail["专业"] = ""

    # 发布日期
    date_el = page.locator("span:has-text('发布于')")
    detail["发布日期"] = date_el.first.inner_text().replace("发布于", "").strip() if date_el.count() > 0 else ""

    # 职位描述
    desc_el = page.locator(".job-description-VvfEUGocNE")
    detail["职位描述"] = desc_el.first.inner_text().strip() if desc_el.count() > 0 else ""

    # 职位信息块
    info_dict = {}
    info_rows = page.locator(".info-row-HSEUCEHeFr")
    for i in range(info_rows.count()):
        row = info_rows.nth(i)
        label_el = row.locator(".sd-Ellipsis-hiddenContent-1Skwh")
        if label_el.count() == 0:
            label_el = row.locator(".sd-foundation-body-tertiary-2xged")
        label = label_el.inner_text().strip() if label_el.count() > 0 else ""

        value_el = row.locator(".sd-LineClamp-clamp-container-3CTSx")
        if value_el.count() == 0:
            value_el = row.locator(".sd-foundation-body-primary-b0MG4")
        value = value_el.inner_text().strip() if value_el.count() > 0 else ""

        if label:
            info_dict[label] = value
    detail["职位信息"] = info_dict

    elapsed = time.time() - t0
    desc_len = len(detail["职位描述"])
    log(f"  ✔ {detail['职位名称']} | 描述{desc_len}字 | 职位信息{len(info_dict)}项 | 耗时{elapsed:.1f}s")
    return detail


def append_job_to_jsonl(job: dict, filename: str):
    with open(filename, "a", encoding="utf-8") as f:
        f.write(json.dumps(job, ensure_ascii=False) + "\n")


def main():
    start_time = time.time()
    all_job_ids = []
    total_jobs_saved = 0

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)  # 可见浏览器，便于观察
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        # 1. 收集所有岗位ID（翻页）
        log(f"打开列表页: {BASE_URL}")
        page.goto(BASE_URL, wait_until="networkidle")
        wait_for_job_links(page)
        page.wait_for_timeout(2000)

        page_no = 1
        collected_set = set()
        while True:
            log(f"🔍 正在扫描第 {page_no} 页...")
            ids_on_page = collect_job_ids_from_current_page(page)
            new_ids = [jid for jid in ids_on_page if jid not in collected_set]
            log(f"  本页获取 {len(ids_on_page)} 个ID，其中新增 {len(new_ids)} 个")
            all_job_ids.extend(new_ids)
            collected_set.update(new_ids)

            if go_to_next_page(page):
                page_no += 1
                # 等待新页面链接加载
                wait_for_job_links(page)
                page.wait_for_timeout(1500)
            else:
                log("📄 已无下一页，翻页结束。")
                break

        all_job_ids = list(dict.fromkeys(all_job_ids))
        log(f"✅ 共收集到 {len(all_job_ids)} 个岗位ID，开始逐个抓取详情...")

        # 2. 逐个详情抓取并实时写入
        for idx, jid in enumerate(all_job_ids, 1):
            log(f"[{idx}/{len(all_job_ids)}] 正在抓取: {jid}")
            detail_url = DETAIL_URL_TEMPLATE.format(jid)
            page.goto(detail_url, wait_until="networkidle")
            page.wait_for_timeout(800)
            job_data = parse_job_detail(page, jid)
            if job_data:
                append_job_to_jsonl(job_data, OUTPUT_FILE)
                total_jobs_saved += 1
                log(f"  💾 已保存至 {OUTPUT_FILE} (累计{total_jobs_saved}条)")
            else:
                log(f"  ❌ 跳过 {jid}，解析失败")
            time.sleep(0.6)

        browser.close()

    elapsed_total = time.time() - start_time
    log("=" * 50)
    log(f"🏁 抓取完成！总岗位数: {len(all_job_ids)}，成功保存: {total_jobs_saved}")
    log(f"⏱ 总耗时: {elapsed_total:.1f} 秒")
    log(f"📁 结果文件: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()