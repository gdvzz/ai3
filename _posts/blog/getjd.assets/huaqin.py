import asyncio
import json
import time
import re
from pathlib import Path
from typing import List, Dict, Any, Optional

from playwright.async_api import async_playwright, Page


class JobCrawler:
    def __init__(self, output_file: str = "huaqin_fy27fa.json", headless: bool = False):
        """
        初始化爬虫
        :param output_file: 输出JSON文件名
        :param headless: 是否使用无头模式，False表示有头模式（显示浏览器窗口）
        """
        self.output_file = Path(output_file)
        self.headless = headless
        self.base_url = "https://app.mokahr.com/campus-recruitment/hq/44757#/jobs"
        self.job_detail_base = (
            "https://app.mokahr.com/campus-recruitment/hq/44757#/job/"
        )
        self.total_jobs_found = 0
        self.total_jobs_succeeded = 0
        self.total_jobs_failed = 0
        self.start_time = time.time()
        self.processed_ids = set()
        self.job_counter = 0

        # 确保输出文件存在且为空
        self.output_file.parent.mkdir(parents=True, exist_ok=True)
        self.output_file.write_text("[]", encoding="utf-8")

    def _save_job(self, job_data: Dict[str, Any]) -> None:
        """将单个岗位数据追加到JSON文件中"""
        try:
            with open(self.output_file, "r", encoding="utf-8") as f:
                try:
                    data = json.load(f)
                except json.JSONDecodeError:
                    data = []

            data.append(job_data)

            with open(self.output_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            self.job_counter += 1

        except Exception as e:
            print(f"  ❌ 保存岗位数据时出错: {e}")

    def _print_statistics(self) -> None:
        """打印统计信息"""
        elapsed = time.time() - self.start_time
        minutes = int(elapsed // 60)
        seconds = int(elapsed % 60)

        print("\n" + "=" * 70)
        print(f"📊 抓取统计")
        print(f"  📌 发现岗位总数: {self.total_jobs_found}")
        print(f"  ✅ 成功抓取详情: {self.total_jobs_succeeded} 个岗位")
        print(f"  ❌ 失败: {self.total_jobs_failed} 个岗位")
        print(f"  💾 已保存到文件: {self.job_counter} 个岗位")
        print(f"  ⏱️  总耗时: {minutes}分{seconds}秒")
        print("=" * 70)

    async def _fetch_job_detail_in_new_tab(
        self, context, job_id: str, job_title: str
    ) -> Optional[Dict[str, Any]]:
        """在新标签页中抓取详情页 - 增强版等待策略"""
        detail_url = f"{self.job_detail_base}{job_id}"
        start_time = time.time()
        page = None

        try:
            # 创建新标签页
            page = await context.new_page()

            # 设置默认超时时间稍长一些
            page.set_default_timeout(20000)

            # 导航到详情页
            await page.goto(detail_url, wait_until="domcontentloaded", timeout=20000)

            # 关键修复：使用更可靠的等待策略
            # 1. 等待标题出现
            await page.wait_for_selector(
                ".title-ROUQFdjmhP", state="attached", timeout=10000
            )

            # 2. 等待描述容器出现
            await page.wait_for_selector(
                ".job-description-VvfEUGocNE", state="attached", timeout=10000
            )

            # 3. 额外等待一小段时间，确保动态内容完全渲染
            await page.wait_for_timeout(1000)

            # 4. 等待描述中的文本内容出现（至少有100个字符）
            await page.wait_for_function(
                """
                () => {
                    const descElem = document.querySelector('.job-description-VvfEUGocNE');
                    if (!descElem) return false;
                    const text = descElem.textContent;
                    return text && text.trim().length > 50;
                }
                """,
                timeout=10000,
            )

            # 提取岗位名称
            title_elem = await page.query_selector(".title-ROUQFdjmhP")
            if title_elem:
                job_title = (await title_elem.text_content()).strip()

            # 提取发布时间
            job_info = ""
            time_elem = await page.query_selector(
                ".sd-foundation-body-tertiary-2xged span"
            )
            if time_elem:
                job_info = (await time_elem.text_content()).strip()
            else:
                body_text = await page.text_content("body")
                time_match = re.search(r"发布于\s*(\d{4}-\d{2}-\d{2})", body_text)
                if time_match:
                    job_info = f"发布于 {time_match.group(1)}"

            # 提取职位描述
            description = ""

            # 方法1: 使用具体选择器
            desc_elem = await page.query_selector(".job-description-VvfEUGocNE")
            if desc_elem:
                p_elements = await desc_elem.query_selector_all("p")
                if p_elements:
                    desc_parts = []
                    for p in p_elements:
                        text = await p.text_content()
                        if text:
                            desc_parts.append(text.strip())
                    description = "\n".join(desc_parts)
                else:
                    description = await desc_elem.text_content()
                    if description:
                        description = description.strip()

            # 方法2: 如果上面没找到，尝试使用其他选择器
            if not description:
                desc_elem = await page.query_selector(
                    ".sd-LineClamp-clamp-container-3CTSx"
                )
                if desc_elem:
                    description = await desc_elem.text_content()
                    if description:
                        description = description.strip()

            # 构建返回数据
            job_data = {
                "job_id": job_id,
                "job_title": job_title,
                "job_url": detail_url,
                "job_description": description,
                "job_description_length": len(description),
                "job_info": job_info,
                "job_info_length": len(job_info),
                "crawl_time": time.strftime("%Y-%m-%d %H:%M:%S"),
                "crawl_duration": round(time.time() - start_time, 2),
            }

            return job_data

        except Exception as e:
            # 如果等待超时或出错，尝试获取已有内容
            print(f"  ⚠️ 详情页加载异常: {e}")
            try:
                # 尝试获取当前已加载的内容
                body_text = await page.text_content("body") if page else ""

                # 提取岗位名称
                title = job_title
                title_match = re.search(r"([^\n]+?)（2027届）", body_text)
                if title_match:
                    title = title_match.group(1).strip() + "（2027届）"

                # 提取发布时间
                info = ""
                time_match = re.search(r"发布于\s*(\d{4}-\d{2}-\d{2})", body_text)
                if time_match:
                    info = f"发布于 {time_match.group(1)}"

                # 提取描述（尝试从文本中提取）
                desc = ""
                desc_match = re.search(
                    r"职位描述\s*([\s\S]*?)(?=职位要求|任职资格|岗位要求|$)", body_text
                )
                if desc_match:
                    desc = desc_match.group(1).strip()
                    # 清理多余空白
                    desc = re.sub(r"\s+", " ", desc).strip()

                return {
                    "job_id": job_id,
                    "job_title": title,
                    "job_url": detail_url,
                    "job_description": desc,
                    "job_description_length": len(desc),
                    "job_info": info,
                    "job_info_length": len(info),
                    "crawl_time": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "crawl_duration": round(time.time() - start_time, 2),
                    "error": (
                        str(e)
                        if "超时" not in str(e)
                        else "内容加载超时，已获取部分内容"
                    ),
                }
            except Exception as fallback_error:
                print(f"  ❌ 备用提取也失败: {fallback_error}")
                return {
                    "job_id": job_id,
                    "job_title": job_title,
                    "job_url": detail_url,
                    "job_description": "",
                    "job_description_length": 0,
                    "job_info": "",
                    "job_info_length": 0,
                    "crawl_time": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "crawl_duration": round(time.time() - start_time, 2),
                    "error": str(e),
                }
        finally:
            if page:
                await page.close()

    async def _process_job_card(
        self, page: Page, card_element
    ) -> Optional[Dict[str, Any]]:
        """处理单个岗位卡片"""
        try:
            link_element = await card_element.query_selector("a.link-txmgVOCVz9")
            if not link_element:
                return None

            href = await link_element.get_attribute("href")
            if not href:
                return None

            job_id = None
            id_match = re.search(r"/job/([a-f0-9-]+)", href)
            if id_match:
                job_id = id_match.group(1)

            if not job_id or job_id in self.processed_ids:
                return None

            self.processed_ids.add(job_id)
            self.total_jobs_found += 1

            title_element = await card_element.query_selector(".title-u2qk9xX9Ie")
            job_title = ""
            if title_element:
                job_title = (await title_element.text_content()).strip()
            else:
                job_title = await link_element.text_content()
                if job_title:
                    job_title = job_title.strip()

            pub_element = await card_element.query_selector(".published-at-PQ5IBWmbJV")
            published_at = ""
            if pub_element:
                published_at = (await pub_element.text_content()).strip()

            print(f"\n📌 发现岗位 #{self.total_jobs_found}: {job_title}")
            print(f"   ID: {job_id}")
            print(f"   📅 发布时间: {published_at}")

            detail_data = await self._fetch_job_detail_in_new_tab(
                page.context, job_id, job_title
            )

            if detail_data:
                self.total_jobs_succeeded += 1
                # 检查是否获取到了描述内容
                has_description = detail_data["job_description_length"] > 0
                print(
                    f"  {'✅' if has_description else '⚠️'} 抓取详情 {'成功' if has_description else '完成但描述为空'}"
                )
                print(f"  📝 职位描述字数: {detail_data['job_description_length']}")
                print(f"  ℹ️  职位信息字数: {detail_data['job_info_length']}")
                print(f"  ⏱️  详情页耗时: {detail_data['crawl_duration']}秒")

                self._save_job(detail_data)
                return detail_data
            else:
                self.total_jobs_failed += 1
                print(f"  ❌ 抓取详情失败")
                return None

        except Exception as e:
            self.total_jobs_failed += 1
            print(f"  ❌ 处理岗位卡片时出错: {e}")
            return None

    async def crawl_page(self, page: Page, page_num: int = 1) -> bool:
        """抓取单页的岗位列表"""
        url = f"{self.base_url}?page={page_num}&pageSize=30"
        print(f"\n🌐 正在抓取第 {page_num} 页: {url}")

        try:
            await page.goto(url, wait_until="networkidle", timeout=30000)
            await page.wait_for_selector(
                ".jobs-AkItzswt6b .container-aOp138AX_X", timeout=15000
            )

            cards = await page.query_selector_all(
                ".jobs-AkItzswt6b .container-aOp138AX_X"
            )

            if not cards:
                print(f"  ⚠️ 第 {page_num} 页未找到岗位卡片")
                return False

            print(f"  📋 找到 {len(cards)} 个岗位卡片")

            for i, card in enumerate(cards, 1):
                try:
                    await self._process_job_card(page, card)
                    await asyncio.sleep(0.5)
                except Exception as e:
                    print(f"  ❌ 处理第 {i} 个卡片时出错: {e}")
                    continue

            return True

        except Exception as e:
            print(f"  ❌ 抓取第 {page_num} 页时出错: {e}")
            return False

    async def run(self, max_pages: int = 5):
        """主运行方法"""
        print("🚀 开始抓取华勤集团校园招聘岗位")
        print(f"📁 输出文件: {self.output_file}")
        print(
            f"🖥️  浏览器模式: {'有头模式（可见）' if not self.headless else '无头模式（后台）'}"
        )
        print(f"📊 预计最大页数: {max_pages}")
        print("=" * 70)

        async with async_playwright() as p:
            # 启动浏览器 - 有头模式
            browser = await p.chromium.launch(headless=self.headless)
            context = await browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            )
            page = await context.new_page()

            try:
                page.set_default_timeout(30000)
                await self.crawl_page(page, 1)

                for page_num in range(2, max_pages + 1):
                    has_more = await page.evaluate("""
                        () => {
                            const pagination = document.querySelector('.pagination, .pager, .el-pagination');
                            if (pagination) {
                                const nextBtn = pagination.querySelector('.next, .btn-next, .el-pagination__next');
                                return nextBtn && !nextBtn.disabled && !nextBtn.classList.contains('disabled');
                            }
                            return false;
                        }
                    """)

                    if not has_more and page_num > 2:
                        print(f"\n🔍 检测到没有更多页面，停止抓取")
                        break

                    await self.crawl_page(page, page_num)

                    if len(self.processed_ids) == 0:
                        print(f"\n⚠️ 第 {page_num} 页没有找到新岗位，停止抓取")
                        break

                    await asyncio.sleep(1.5)

            except Exception as e:
                print(f"\n❌ 运行过程中出现错误: {e}")

            finally:
                await browser.close()

        self._print_statistics()
        print(f"\n✅ 完成！数据已保存到 {self.output_file}")


async def main():
    # headless=False 表示有头模式，会显示浏览器窗口
    crawler = JobCrawler("huaqin_fy27fa.json", headless=False)
    await crawler.run(max_pages=5)


if __name__ == "__main__":
    asyncio.run(main())
