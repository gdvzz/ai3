import asyncio
import json
import time
import re
from pathlib import Path
from datetime import datetime
from playwright.async_api import async_playwright


class ShokzCrawler:
    def __init__(self):
        self.base_url = "https://app.mokahr.com/campus-recruitment/aftershokzhr/36940#/jobs?keyword=27%E5%B1%8A%E6%8F%90%E5%89%8D%E6%89%B9&page=1&pageSize=50"
        self.results = []
        self.success_count = 0
        self.error_count = 0
        self.total_count = 0
        self.output_file = "shokz_jobs_27.json"
        self.start_time = None
        self.processed_urls = set()

    def save_job(self, job_data):
        """保存单个岗位数据到JSON文件"""
        try:
            if Path(self.output_file).exists():
                with open(self.output_file, "r", encoding="utf-8") as f:
                    try:
                        existing_data = json.load(f)
                    except json.JSONDecodeError:
                        existing_data = []
            else:
                existing_data = []

            existing_urls = [j.get("job_url") for j in existing_data]
            if job_data.get("job_url") in existing_urls:
                return

            existing_data.append(job_data)

            with open(self.output_file, "w", encoding="utf-8") as f:
                json.dump(existing_data, f, ensure_ascii=False, indent=2)

        except Exception as e:
            print(f"保存失败: {e}")

    async def crawl_job_detail(self, context, job_url, job_title):
        """使用正确URL格式，在新标签页中抓取岗位详情"""
        try:
            # 修正URL拼接：直接使用从列表中获取的完整哈希链接
            if job_url.startswith("#/job/"):
                full_url = f"https://app.mokahr.com/campus-recruitment/aftershokzhr/36940{job_url}"
            else:
                full_url = job_url

            print(f"     🔍 访问详情: {full_url}")

            # 使用context.new_page()在当前窗口新建标签页
            detail_page = await context.new_page()

            try:
                # 设置请求头，模拟真实浏览器
                await detail_page.set_extra_http_headers(
                    {
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                        "Referer": "https://app.mokahr.com/campus-recruitment/aftershokzhr/36940#/jobs",
                    }
                )

                # 访问详情页
                await detail_page.goto(
                    full_url, wait_until="networkidle", timeout=30000
                )
                await detail_page.wait_for_timeout(2000)

                # 提取职位描述
                description = ""

                # 方式1: 使用job-description类
                desc_elem = await detail_page.query_selector(
                    ".job-description-VvfEUGocNE, .job-description"
                )
                if desc_elem:
                    description = await desc_elem.inner_text()

                # 方式2: 如果没找到，尝试LineClamp容器
                if not description:
                    clamp_elem = await detail_page.query_selector(
                        ".sd-LineClamp-clamp-container-3CTSx"
                    )
                    if clamp_elem:
                        description = await clamp_elem.inner_text()

                # 方式3: 查找包含"职位描述"的容器
                if not description:
                    desc_container = await detail_page.query_selector(
                        ".list-Yu939rjoGi"
                    )
                    if desc_container:
                        description = await desc_container.inner_text()
                        description = re.sub(r"职位描述\s*", "", description)

                # 提取工作地点和类型
                job_info = {}
                try:
                    info_elem = await detail_page.query_selector(".info-UcB_mxJq8y")
                    if info_elem:
                        info_text = await info_elem.inner_text()
                        parts = info_text.split("|")
                        for part in parts:
                            part = part.strip()
                            if "、" in part:
                                sub_parts = part.split("、")
                                for sub in sub_parts:
                                    if (
                                        "深圳" in sub
                                        or "北京" in sub
                                        or "上海" in sub
                                        or "广州" in sub
                                    ):
                                        job_info["location"] = sub
                                    elif "线上面试" in sub:
                                        job_info["interview"] = sub
                            elif "全职" in part or "实习" in part:
                                job_info["job_type"] = part
                except:
                    pass

                # 提取发布时间
                publish_time = ""
                try:
                    time_elem = await detail_page.query_selector(
                        ".sd-foundation-body-tertiary-2xged"
                    )
                    if time_elem:
                        publish_time = await time_elem.inner_text()
                        publish_time = publish_time.strip()
                except:
                    pass

                return {
                    "description": (
                        description.strip() if description else "无法获取描述"
                    ),
                    "description_length": (
                        len(description.strip()) if description else 0
                    ),
                    "job_info": job_info,
                    "job_info_length": len(str(job_info)),
                    "publish_time": publish_time,
                }

            finally:
                # 抓取完成后关闭这个标签页
                await detail_page.close()

        except Exception as e:
            print(f"     ❌ 抓取详情失败: {e}")
            return {
                "description": f"抓取失败: {str(e)}",
                "description_length": 0,
                "job_info": {},
                "job_info_length": 0,
                "publish_time": "",
            }

    async def crawl_page(self, context, page, page_num):
        """抓取单页岗位列表"""
        try:
            print(f"\n📄 正在抓取第 {page_num} 页...")

            await page.wait_for_timeout(2000)

            # 查找岗位卡片
            job_cards = await page.query_selector_all(".container-aOp138AX_X")

            if not job_cards:
                # 备用选择器
                job_cards = await page.query_selector_all(
                    '[class*="container"][class*="list"]'
                )

            if not job_cards:
                # 通过链接查找
                links = await page.query_selector_all('a[href*="/job/"]')
                print(f"  📋 通过链接找到 {len(links)} 个岗位")

                for link in links:
                    try:
                        href = await link.get_attribute("href")
                        if not href or href.startswith("http"):
                            continue

                        title_elem = await link.query_selector(
                            '.title-u2qk9xX9Ie, [class*="title"]'
                        )
                        title = (
                            await title_elem.inner_text() if title_elem else "未知岗位"
                        )
                        title = title.strip()

                        if href in self.processed_urls:
                            continue
                        self.processed_urls.add(href)

                        print(f"\n  📌 岗位: {title}")
                        print(f"     🔗 链接: {href}")

                        detail_data = await self.crawl_job_detail(context, href, title)

                        time_elem = await link.query_selector(
                            '.published-at-PQ5IBWmbJV, [class*="published"]'
                        )
                        publish_time = (
                            await time_elem.inner_text()
                            if time_elem
                            else detail_data.get("publish_time", "")
                        )
                        publish_time = publish_time.strip()

                        job_data = {
                            "job_title": title,
                            "publish_time": publish_time,
                            "job_url": href,
                            "full_url": (
                                f"https://app.mokahr.com/campus-recruitment/aftershokzhr/36940{href}"
                                if href.startswith("#/")
                                else href
                            ),
                            "description": detail_data.get("description", ""),
                            "description_length": detail_data.get(
                                "description_length", 0
                            ),
                            "job_info": detail_data.get("job_info", {}),
                            "job_info_length": detail_data.get("job_info_length", 0),
                            "crawl_time": datetime.now().isoformat(),
                            "page": page_num,
                        }

                        self.save_job(job_data)
                        self.success_count += 1
                        self.total_count += 1

                        print(
                            f"     ✅ 抓取成功 (描述: {job_data['description_length']}字, 信息: {job_data['job_info_length']}字)"
                        )
                        print(
                            f"     📊 累计: 成功{self.success_count}个, 错误{self.error_count}个, 总{self.total_count}个"
                        )

                    except Exception as e:
                        self.error_count += 1
                        print(f"  ❌ 抓取岗位失败: {e}")
                        print(
                            f"     📊 累计: 成功{self.success_count}个, 错误{self.error_count}个, 总{self.total_count}个"
                        )
                        continue

                return len(links)

            print(f"  📋 找到 {len(job_cards)} 个岗位卡片")

            count = 0
            for card in job_cards:
                try:
                    title_elem = await card.query_selector(
                        '.title-u2qk9xX9Ie, [class*="title"]'
                    )
                    if not title_elem:
                        continue

                    title = await title_elem.inner_text()
                    title = title.strip()

                    time_elem = await card.query_selector(
                        '.published-at-PQ5IBWmbJV, [class*="published"]'
                    )
                    publish_time = await time_elem.inner_text() if time_elem else ""
                    publish_time = publish_time.strip()

                    link_elem = await card.query_selector('a[href*="/job/"]')
                    if not link_elem:
                        continue

                    job_url = await link_elem.get_attribute("href")
                    if not job_url:
                        continue

                    if job_url in self.processed_urls:
                        continue
                    self.processed_urls.add(job_url)

                    print(f"\n  📌 岗位: {title}")
                    print(f"     🕐 发布时间: {publish_time}")
                    print(f"     🔗 链接: {job_url}")

                    detail_data = await self.crawl_job_detail(context, job_url, title)

                    job_data = {
                        "job_title": title,
                        "publish_time": publish_time
                        or detail_data.get("publish_time", ""),
                        "job_url": job_url,
                        "full_url": (
                            f"https://app.mokahr.com/campus-recruitment/aftershokzhr/36940{job_url}"
                            if job_url.startswith("#/")
                            else job_url
                        ),
                        "description": detail_data.get("description", ""),
                        "description_length": detail_data.get("description_length", 0),
                        "job_info": detail_data.get("job_info", {}),
                        "job_info_length": detail_data.get("job_info_length", 0),
                        "crawl_time": datetime.now().isoformat(),
                        "page": page_num,
                    }

                    self.save_job(job_data)
                    self.success_count += 1
                    self.total_count += 1
                    count += 1

                    print(
                        f"     ✅ 抓取成功 (描述: {job_data['description_length']}字, 信息: {job_data['job_info_length']}字)"
                    )
                    print(
                        f"     📊 累计: 成功{self.success_count}个, 错误{self.error_count}个, 总{self.total_count}个"
                    )

                except Exception as e:
                    self.error_count += 1
                    print(f"  ❌ 抓取岗位失败: {e}")
                    print(
                        f"     📊 累计: 成功{self.success_count}个, 错误{self.error_count}个, 总{self.total_count}个"
                    )
                    continue

            return count

        except Exception as e:
            print(f"  ❌ 抓取第 {page_num} 页失败: {e}")
            return 0

    async def go_to_page(self, page, page_num):
        """跳转到指定页面"""
        try:
            url = f"https://app.mokahr.com/campus-recruitment/aftershokzhr/36940#/jobs?keyword=27%E5%B1%8A%E6%8F%90%E5%89%8D%E6%89%B9&page={page_num}&pageSize=50"
            await page.goto(url, wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(2000)
            return True

        except Exception as e:
            print(f"  ⚠️ 跳转页面失败: {e}")
            return False

    async def run(self):
        """主运行方法"""
        self.start_time = time.time()

        print("=" * 60)
        print("🎯 韶音科技校招岗位爬虫 (27届提前批)")
        print("=" * 60)
        print(f"🔗 起始URL: {self.base_url}")
        print(f"📁 输出文件: {self.output_file}")
        print("=" * 60)

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
                locale="zh-CN",
                timezone_id="Asia/Shanghai",
            )

            await context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
                window.chrome = {
                    runtime: {}
                };
            """)

            page = await context.new_page()

            try:
                print(f"\n🌐 访问列表页...")
                await page.goto(self.base_url, wait_until="networkidle", timeout=45000)
                await page.wait_for_timeout(3000)

                # 抓取第1页
                await self.crawl_page(context, page, 1)

                # 尝试抓取更多页面
                print(
                    f"\n📊 当前累计: 成功{self.success_count}个, 错误{self.error_count}个, 总{self.total_count}个"
                )

                try:
                    pagination = await page.query_selector(".sd-Pagination-items-35tRS")
                    if pagination:
                        page_buttons = await pagination.query_selector_all(
                            "button[data-page]"
                        )
                        max_page = 1
                        for btn in page_buttons:
                            text = await btn.inner_text()
                            if text.isdigit():
                                max_page = max(max_page, int(text))

                        for page_num in range(2, max_page + 1):
                            print(f"\n🔄 准备跳转到第 {page_num} 页...")
                            await self.go_to_page(page, page_num)
                            await self.crawl_page(context, page, page_num)
                            print(
                                f"\n📊 当前累计: 成功{self.success_count}个, 错误{self.error_count}个, 总{self.total_count}个"
                            )
                            await page.wait_for_timeout(1000)
                except Exception as e:
                    print(f"  ⚠️ 翻页检测失败: {e}")

                # 计算总耗时
                elapsed_time = time.time() - self.start_time

                print("\n" + "=" * 60)
                print("📊 抓取统计")
                print("=" * 60)
                print(f"✅ 成功抓取: {self.success_count} 个岗位")
                print(f"❌ 失败: {self.error_count} 个岗位")
                print(f"📊 总计: {self.total_count} 个岗位")
                print(f"⏱️ 总耗时: {elapsed_time:.2f} 秒")
                print(f"📁 数据已保存到: {self.output_file}")
                print("=" * 60)

            except Exception as e:
                print(f"\n❌ 程序运行出错: {e}")
                import traceback

                traceback.print_exc()

            finally:
                await browser.close()


async def main():
    crawler = ShokzCrawler()
    await crawler.run()


if __name__ == "__main__":
    asyncio.run(main())
