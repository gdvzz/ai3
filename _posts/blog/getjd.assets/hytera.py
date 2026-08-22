import asyncio
import json
import time
import re
import os
from datetime import datetime
from playwright.async_api import async_playwright


class HyteraCrawler:
    def __init__(self):
        self.base_url = "https://app.mokahr.com"
        self.list_url = "https://app.mokahr.com/campus_apply/hytera/182194#/jobs"
        self.output_file = "hytera_y27fa.json"
        self.log_file = "crawler_log.txt"
        self.jobs_data = []
        self.stats = {
            "total_found": 0,
            "success": 0,
            "error": 0,
            "start_time": time.time(),
        }

        self.load_existing_data()
        self.setup_logging()

    def setup_logging(self):
        """设置日志"""
        with open(self.log_file, "w", encoding="utf-8") as f:
            f.write(
                f"=== 海能达校招爬虫日志 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===\n"
            )

    def log(self, message):
        """写入日志"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_msg = f"[{timestamp}] {message}"
        print(log_msg)
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(log_msg + "\n")

    def load_existing_data(self):
        """加载已保存的数据（断点续传）"""
        if os.path.exists(self.output_file):
            try:
                with open(self.output_file, "r", encoding="utf-8") as f:
                    self.jobs_data = json.load(f)
                self.log(f"📂 已加载 {len(self.jobs_data)} 条已有数据")
            except Exception as e:
                self.log(f"⚠️ 加载已有数据失败: {str(e)}")
                self.jobs_data = []
        else:
            self.jobs_data = []

    def save_job(self, job_data):
        """保存单个岗位数据到JSON文件"""
        found = False
        for i, existing in enumerate(self.jobs_data):
            if existing.get("job_id") == job_data.get("job_id"):
                self.jobs_data[i] = job_data
                found = True
                break
        if not found:
            self.jobs_data.append(job_data)

        try:
            with open(self.output_file, "w", encoding="utf-8") as f:
                json.dump(self.jobs_data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            self.log(f"❌ 保存数据失败: {str(e)}")
            return False

    async def get_all_job_links(self, page):
        """自动翻页获取所有岗位链接 - 精确过滤岗位卡片"""
        self.log("\n🔍 正在获取所有岗位列表...")
        all_jobs = []
        current_page = 1
        max_pages = 10

        while current_page <= max_pages:
            self.log(f"   📄 正在抓取第 {current_page} 页...")
            await page.wait_for_load_state("networkidle", timeout=10000)
            await page.wait_for_timeout(2000)

            # 获取所有包含 /job/ 的 a 标签
            all_a_tags = await page.query_selector_all('a[href*="/job/"]')
            self.log(f"   原始链接数量: {len(all_a_tags)}")

            # 过滤出真正的岗位卡片（包含 card-content 或 title- 类）
            job_cards = []
            for a in all_a_tags:
                card_content = await a.query_selector('div[class*="card-content-"]')
                if card_content:
                    job_cards.append(a)
                    continue
                title_elem = await a.query_selector('span[class*="title-"]')
                if title_elem:
                    job_cards.append(a)

            self.log(f"   过滤后卡片数量: {len(job_cards)}")

            if not job_cards:
                self.log(f"   ⚠️ 第 {current_page} 页没有找到岗位卡片，停止翻页。")
                break

            page_jobs = []
            for card in job_cards:
                try:
                    href = await card.get_attribute("href")
                    if href and "/job/" in href:
                        job_id = href.split("/job/")[-1].split("?")[0].strip()
                        title_elem = await card.query_selector('span[class*="title-"]')
                        title = (
                            await title_elem.text_content() if title_elem else "未知"
                        )
                        title = title.strip() if title else "未知"
                        location_elem = await card.query_selector(
                            'div[class*="ellipsis-"]'
                        )
                        location = (
                            await location_elem.text_content()
                            if location_elem
                            else "未知"
                        )
                        location = location.strip() if location else "未知"

                        page_jobs.append(
                            {
                                "job_id": job_id,
                                "title": title,
                                "location": location,
                                "url": f"{self.base_url}/campus_apply/hytera/182194#/job/{job_id}",
                            }
                        )
                except Exception as e:
                    continue

            if not page_jobs:
                break

            all_jobs.extend(page_jobs)
            self.log(
                f"   ✅ 第 {current_page} 页获取 {len(page_jobs)} 个岗位，累计 {len(all_jobs)} 个"
            )

            # 翻页逻辑：查找页码按钮
            page_buttons = await page.query_selector_all(
                'button[class*="sd-Pagination-item"][data-page]'
            )
            if page_buttons:
                page_numbers = []
                for btn in page_buttons:
                    page_num = await btn.get_attribute("data-page")
                    if page_num and page_num.isdigit():
                        page_numbers.append(int(page_num))
                if page_numbers:
                    max_page = max(page_numbers)
                    if current_page < max_page:
                        next_page = current_page + 1
                        next_button = await page.query_selector(
                            f'button[data-page="{next_page}"]'
                        )
                        if next_button:
                            self.log(f"   🔄 正在跳转到第 {next_page} 页...")
                            await next_button.click()
                            await page.wait_for_timeout(2000)
                            current_page = next_page
                            continue
                        else:
                            self.log(f"   ⚠️ 未找到第 {next_page} 页的按钮")
                            break
                    else:
                        self.log(f"   ✅ 已到达最后一页")
                        break
                else:
                    self.log(f"   ⚠️ 未找到有效页码")
                    break
            else:
                # 备用：尝试点击“下一页”按钮
                next_button = await page.query_selector(
                    'button[class*="sd-Pagination-forward"]:not([disabled])'
                )
                if next_button:
                    self.log(f"   🔄 点击下一页按钮...")
                    await next_button.click()
                    await page.wait_for_timeout(2000)
                    current_page += 1
                    continue
                else:
                    self.log(f"   ✅ 没有更多页面")
                    break

        self.stats["total_found"] = len(all_jobs)
        self.log(f"\n  ✅ 所有页面共解析到 {len(all_jobs)} 个岗位")
        return all_jobs

    async def get_job_detail(self, context, job_id, title):
        """获取单个岗位详情 - 将 <p> 转换为换行符"""
        detail_url = f"{self.base_url}/campus_apply/hytera/182194#/job/{job_id}"
        page = None
        try:
            page = await context.new_page()
            await page.goto(detail_url, timeout=30000)
            await page.wait_for_load_state("networkidle", timeout=30000)
            await page.wait_for_timeout(3000)

            job_info = {
                "job_id": job_id,
                "title": title,
                "location": "未知",
                "job_type": "全职",
                "job_category": "未知",
                "department": "",
                "job_detail": "",  # 合并后的详情，已转换换行
                "publish_date": "",
                "deadline": "",
                "is_urgent": False,
                "detail_url": detail_url,
                "crawl_time": datetime.now().isoformat(),
            }

            # 1. 获取完整标题
            title_elem = await page.query_selector('div[class*="title-ROUQFdjmhP"]')
            if title_elem:
                title_text = await title_elem.text_content()
                if title_text:
                    job_info["title"] = title_text.strip()

            # 2. 获取岗位信息（全职、技术类、地点）
            info_elem = await page.query_selector('div[class*="info-UcB_mxJq8y"]')
            if info_elem:
                info_text = await info_elem.text_content()
                if info_text:
                    parts = [p.strip() for p in info_text.split("|") if p.strip()]
                    if len(parts) >= 3:
                        job_info["job_type"] = parts[0]
                        job_info["job_category"] = parts[1]
                        job_info["location"] = parts[2]
                    elif len(parts) == 2:
                        job_info["job_category"] = parts[0]
                        job_info["location"] = parts[1]
                    elif len(parts) == 1:
                        job_info["location"] = parts[0]

            # 3. 获取详情内容，并将 <p> 标签转换为换行符
            detail_text = ""
            desc_elem = await page.query_selector(
                'div[class*="job-description-VvfEUGocNE"]'
            )
            if desc_elem:
                # 获取内部HTML
                html_content = await desc_elem.inner_html()
                # 将 <p> 和 </p> 替换为换行
                text = re.sub(r"<p>|</p>", "\n", html_content)
                # 移除其他可能残留的HTML标签（如 <br> 等）
                text = re.sub(r"<[^>]+>", "", text)
                # 合并多余的空白行
                text = re.sub(r"\n\s*\n", "\n", text).strip()
                detail_text = text

            # 备选：如果没找到 job-description，尝试 LineClamp
            if not detail_text:
                line_clamp = await page.query_selector(
                    'div[class*="sd-LineClamp-clamp-container"]'
                )
                if line_clamp:
                    html_content = await line_clamp.inner_html()
                    text = re.sub(r"<p>|</p>", "\n", html_content)
                    text = re.sub(r"<[^>]+>", "", text)
                    text = re.sub(r"\n\s*\n", "\n", text).strip()
                    detail_text = text

            # 最终备用：直接获取文本内容（但不转换段落）
            if not detail_text:
                content_selectors = [
                    'div[class*="detail"]',
                    'div[class*="content"]',
                    'div[class*="description"]',
                    'div[class*="rich-text"]',
                ]
                for selector in content_selectors:
                    elem = await page.query_selector(selector)
                    if elem:
                        html_content = await elem.inner_html()
                        text = re.sub(r"<p>|</p>", "\n", html_content)
                        text = re.sub(r"<[^>]+>", "", text)
                        text = re.sub(r"\n\s*\n", "\n", text).strip()
                        if len(text) > 50:
                            detail_text = text
                            break

            job_info["job_detail"] = detail_text

            # 4. 检查是否为急聘岗位
            urgent_elem = await page.query_selector('span[class*="prior-"]')
            if urgent_elem:
                job_info["is_urgent"] = True

            detail_len = len(job_info.get("job_detail", ""))
            self.log(f"      📝 详情内容: {detail_len} 字")

            await page.close()
            return job_info

        except Exception as e:
            self.log(f"  ⚠️ 获取详情出错: {str(e)}")
            if page:
                await page.close()
            return None

    async def crawl(self):
        """主爬取函数"""
        self.log("=" * 70)
        self.log("🚀 开始抓取海能达校招岗位信息")
        self.log("=" * 70)

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=False,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-dev-shm-usage",
                    "--no-sandbox",
                ],
            )

            context = await browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            )

            await context.set_extra_http_headers(
                {
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                    "Cache-Control": "no-cache",
                    "Pragma": "no-cache",
                }
            )

            page = await context.new_page()
            self.log(f"正在访问: {self.list_url}")
            await page.goto(self.list_url, timeout=60000, wait_until="networkidle")
            await page.wait_for_timeout(5000)

            await page.screenshot(path="page_screenshot.png")
            self.log("📸 已保存页面截图: page_screenshot.png")

            all_jobs = await self.get_all_job_links(page)

            if not all_jobs:
                self.log("\n⚠️ 未找到任何岗位，请检查页面是否正常加载")
                await browser.close()
                return

            self.log(f"\n📊 总共发现 {len(all_jobs)} 个岗位")
            self.log("=" * 70)

            existing_ids = set(j.get("job_id") for j in self.jobs_data)
            new_jobs = [j for j in all_jobs if j["job_id"] not in existing_ids]
            self.log(
                f"📝 需要新抓取 {len(new_jobs)} 个岗位，已存在 {len(all_jobs) - len(new_jobs)} 个"
            )

            for idx, job in enumerate(all_jobs, 1):
                job_id = job["job_id"]
                title = job["title"]

                self.log(f"\n[{idx}/{len(all_jobs)}] 📝 正在抓取: {title}")
                self.log(f"   ID: {job_id}")

                if job_id in existing_ids:
                    self.log(f"   ⏭️ 该岗位已存在，跳过")
                    self.stats["success"] += 1
                    continue

                try:
                    detail = await self.get_job_detail(context, job_id, title)
                    if detail:
                        detail_len = len(detail.get("job_detail", ""))
                        self.log(f"   ✅ 成功获取详情")
                        self.log(f"      📝 详情内容: {detail_len} 字")
                        self.log(f"      📍 地点: {detail.get('location', '未知')}")
                        self.log(f"      🏷️ 类别: {detail.get('job_category', '未知')}")
                        if detail.get("is_urgent"):
                            self.log(f"      🔥 急聘岗位")

                        if self.save_job(detail):
                            self.log(f"   💾 已保存到 {self.output_file}")
                            self.stats["success"] += 1
                        else:
                            self.stats["error"] += 1
                    else:
                        self.log(f"   ❌ 获取详情失败")
                        self.stats["error"] += 1
                except Exception as e:
                    self.log(f"   ❌ 处理出错: {str(e)}")
                    self.stats["error"] += 1

                await page.wait_for_timeout(1500)

            await browser.close()

        elapsed = time.time() - self.stats["start_time"]
        self.log("\n" + "=" * 70)
        self.log("🎉 抓取完成！统计信息：")
        self.log(f"   📊 累计发现岗位: {self.stats['total_found']}")
        self.log(f"   ✅ 成功抓取: {self.stats['success']}")
        self.log(f"   ❌ 失败: {self.stats['error']}")
        self.log(f"   ⏱️ 总耗时: {elapsed:.2f} 秒")
        self.log(f"   📁 数据保存至: {self.output_file}")
        self.log(f"   📝 共保存 {len(self.jobs_data)} 个岗位")
        self.log(f"   📄 日志保存至: {self.log_file}")
        self.log("=" * 70)

        if self.jobs_data:
            self.log("\n📋 数据样例（第一个岗位）:")
            sample = self.jobs_data[0]
            self.log(f"   标题: {sample.get('title', 'N/A')}")
            self.log(f"   地点: {sample.get('location', 'N/A')}")
            self.log(f"   类别: {sample.get('job_category', 'N/A')}")
            self.log(f"   急聘: {'是' if sample.get('is_urgent') else '否'}")
            detail_preview = sample.get("job_detail", "")[:100].replace("\n", "\\n")
            if detail_preview:
                self.log(f"   详情预览: {detail_preview}...")


async def main():
    crawler = HyteraCrawler()
    await crawler.crawl()


if __name__ == "__main__":
    asyncio.run(main())
