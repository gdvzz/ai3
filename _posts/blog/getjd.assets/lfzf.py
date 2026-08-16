import asyncio
import json
import time
import logging
from datetime import datetime
from typing import Dict, List, Any
from playwright.async_api import async_playwright

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class LongForJobCrawler:
    def __init__(self, output_file: str = "longfor_jobs_zf.json"):
        self.output_file = output_file
        self.stats = {
            "total_jobs": 0,
            "success_jobs": 0,
            "error_jobs": 0,
            "sub_companies": [],
            "start_time": None,
            "end_time": None,
        }
        self.page = None

        # 初始化输出文件
        self._init_output_file()

    def _init_output_file(self):
        """初始化输出文件"""
        with open(self.output_file, "w", encoding="utf-8") as f:
            json.dump([], f, ensure_ascii=False, indent=2)

    def _save_job(self, job_data: Dict[str, Any]):
        """保存单个岗位到JSON文件"""
        try:
            with open(self.output_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            data.append(job_data)

            with open(self.output_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

        except Exception as e:
            logger.error(f"保存岗位数据失败: {e}")

    async def get_sub_companies(self, page) -> List[Dict[str, Any]]:
        """获取子公司和部门列表 - 使用浏览器fetch"""
        logger.info("开始获取子公司列表...")

        try:
            # 访问"绽放"项目页面建立会话
            await page.goto(
                "https://longfor.zhaopin.com/zf/index.html",
                wait_until="domcontentloaded",
            )
            await asyncio.sleep(3)  # 等待页面完全加载

            # 使用针对"绽放"项目的正确请求参数
            payload = {
                "rootCompanyId": "105173",
                "companyOrDepartmentId": "10126972",  # 关键：已更新为"绽放"项目的ID
                "format": "tree",
            }

            # 使用浏览器fetch发送POST请求
            result = await page.evaluate(
                """
                async (payload) => {
                    try {
                        const response = await fetch('https://fe.zhaopin.com/grace/api/dsc/get-sub-company-and-department-list', {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json',
                                'Accept': 'application/json, text/plain, */*',
                                'Referer': 'https://longfor.zhaopin.com/',
                                'Origin': 'https://longfor.zhaopin.com'
                            },
                            credentials: 'include',
                            body: JSON.stringify(payload)
                        });
                        const data = await response.json();
                        return data;
                    } catch(e) {
                        return {error: e.message, stack: e.stack};
                    }
                }
            """,
                payload,
            )

            if result and not result.get("error"):
                logger.info(f"API响应码: {result.get('code')}")

                if result.get("code") == 200:
                    data = result.get("data", {})
                    company_list = data.get("list", [])

                    if company_list:
                        logger.info(f"成功获取到 {len(company_list)} 个业务板块")
                        return self._parse_companies(company_list)
                    else:
                        logger.warning(
                            f"API返回的list为空，完整响应: {json.dumps(result, ensure_ascii=False)[:500]}"
                        )
                else:
                    logger.error(f"API返回错误: {result}")
            else:
                logger.error(
                    f"浏览器fetch失败: {result.get('error') if result else '未知错误'}"
                )

        except Exception as e:
            logger.error(f"获取子公司列表失败: {e}")
            import traceback

            traceback.print_exc()

        # 如果API调用失败，使用基于您提供数据的备用列表
        logger.warning("使用备用公司列表")
        return self._get_fallback_companies()

    def _parse_companies(self, company_list):
        """解析公司列表"""
        all_companies = []

        for parent in company_list:
            parent_name = parent.get("companyName", "")
            parent_id = parent.get("id")

            logger.info(f"处理父级: {parent_name} (ID: {parent_id})")

            # 添加父级本身
            all_companies.append(
                {"id": parent_id, "name": parent_name, "level": "parent"}
            )

            # 添加子级
            children = parent.get("children", [])
            for child in children:
                child_name = child.get("companyName", "")
                child_id = child.get("id")

                all_companies.append(
                    {
                        "id": child_id,
                        "name": f"{parent_name}-{child_name}",
                        "parentId": parent_id,
                        "level": "child",
                        "parent_name": parent_name,
                    }
                )

            logger.info(f"  包含 {len(children)} 个子部门")

        logger.info(f"总共展开得到 {len(all_companies)} 个可搜索的单位")
        self.stats["sub_companies"] = all_companies
        return all_companies

    def _get_fallback_companies(self):
        """获取备用的公司列表（基于"绽放"项目API返回的数据）"""
        fallback = [
            {"id": 10126991, "name": "地产开发", "level": "parent"},
            {"id": 10126992, "name": "商业管理", "level": "parent"},
            {"id": 10126993, "name": "资产管理", "level": "parent"},
            {"id": 10129525, "name": "龙智造", "level": "parent"},
        ]
        # 注意：这里仅添加了父级，您可根据需要从API响应中添加更多子级
        self.stats["sub_companies"] = fallback
        return fallback

    async def search_job_list(self, page, params: Dict[str, Any]) -> Dict[str, Any]:
        """搜索岗位列表 - 使用浏览器fetch"""
        try:
            result = await page.evaluate(
                """
                async (params) => {
                    try {
                        const response = await fetch('https://fe.zhaopin.com/grace/api/dsc/search-job-list', {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json',
                                'Accept': 'application/json, text/plain, */*',
                                'Referer': 'https://longfor.zhaopin.com/',
                                'Origin': 'https://longfor.zhaopin.com'
                            },
                            credentials: 'include',
                            body: JSON.stringify(params)
                        });
                        const data = await response.json();
                        return data;
                    } catch(e) {
                        return {error: e.message};
                    }
                }
            """,
                params,
            )

            if result and not result.get("error"):
                return result
            else:
                logger.error(
                    f"搜索失败: {result.get('error') if result else '未知错误'}"
                )
                return {}

        except Exception as e:
            logger.error(f"搜索岗位失败: {e}")
            return {}

    async def process_company(self, page, company: Dict[str, Any]):
        """处理单个公司/部门的岗位"""
        company_name = company.get("name", "未知")
        company_id = company.get("id")
        level = company.get("level", "unknown")

        if not company_id:
            logger.warning(f"公司 {company_name} 没有ID，跳过")
            return

        logger.info(f"开始处理: {company_name} (ID: {company_id}, Level: {level})")

        page_index = 1
        total_pages = 1
        has_data = False

        while page_index <= total_pages:
            # 构建请求参数 - jobSource可能需要根据"绽放"项目调整
            params = {
                "orgNumbers": "105173",
                "jobSource": 2,  # 假设"绽放"项目使用相同的jobSource值
                "pageIndex": page_index,
                "pageSize": 20,
                "orgDepartmentIds": [],
                "campusParentDepartmentIds": company_id,
                "workRegionIds": "",
                "jobTypes": "",
                "priorityMajors": "",
                "customTags": "",
                "keyword": "",
            }

            logger.info(f"  请求第 {page_index} 页...")
            start_time = time.time()

            result = await self.search_job_list(page, params)
            elapsed = time.time() - start_time

            if result.get("code") != 200:
                logger.error(f"  请求失败: {result.get('message')}")
                break

            data = result.get("data", {})
            job_list = data.get("jobList", [])
            page_info = data.get("pageInfo", {})

            if page_info:
                total_pages = page_info.get("totalPage", 1)
                total_num = page_info.get("totalNum", 0)
            else:
                total_pages = 1 if job_list else 0
                total_num = len(job_list)

            logger.info(
                f"  第 {page_index}/{total_pages} 页，当前页 {len(job_list)} 个岗位，共 {total_num} 个岗位"
            )
            logger.info(f"  耗时: {elapsed:.2f}秒")

            # 处理每个岗位
            for job_item in job_list:
                has_data = True
                self.stats["total_jobs"] += 1

                try:
                    job_data = self.parse_job_data(job_item, company_name)
                    self._save_job(job_data)
                    self.stats["success_jobs"] += 1

                    desc = job_data.get("description", "")
                    desc_len = len(desc) if desc else 0
                    logger.info(
                        f"    ✅ 岗位: {job_data.get('title')} | "
                        f"城市: {job_data.get('city')} | "
                        f"描述字数: {desc_len} | "
                        f"详情页: {job_data.get('detail_url')}"
                    )

                except Exception as e:
                    self.stats["error_jobs"] += 1
                    logger.error(f"    ❌ 解析岗位失败: {e}")

            if len(job_list) == 0:
                break

            page_index += 1
            await asyncio.sleep(1)  # 避免请求过快

        if not has_data:
            logger.info(f"  {company_name} 没有岗位数据")

    def parse_job_data(
        self, job_item: Dict[str, Any], company_name: str
    ) -> Dict[str, Any]:
        """解析单个岗位数据"""
        company = job_item.get("company", {})
        job = job_item.get("job", {})
        staff = job_item.get("staff", {})

        description = job.get("detail", "")
        description_len = len(description) if description else 0

        detail_url = job.get("url", "")
        delivery_path = job.get("deliveryPath", "")

        job_data = {
            "job_id": job.get("id"),
            "job_number": job.get("jobNumber"),
            "title": job.get("title", ""),
            "company_name": company_name,
            "org_name": company.get("campusOrgName", ""),
            "org_short_name": company.get("campusOrgShortName", ""),
            "department_name": company.get("campusParentDepartment", {}).get(
                "name", ""
            ),
            "city": job.get("cityName", ""),
            "district": job.get("districtName", ""),
            "address": job.get("address", ""),
            "job_type": job.get("jobTypeName", ""),
            "job_type_code": job.get("jobType"),
            "min_salary": job.get("minSalary"),
            "max_salary": job.get("maxSalary"),
            "salary_text": job.get("salary", ""),
            "min_education": job.get("minEducationName", ""),
            "working_exp": job.get("workingExpName", ""),
            "employment_type": job.get("employmentType"),
            "quantity": job.get("quantity", 0),
            "description": description,
            "description_length": description_len,
            "detail_url": detail_url,
            "delivery_path": delivery_path,
            "modified_time": job.get("modifiedTime"),
            "staff_name": staff.get("nickName", ""),
            "staff_avatar": staff.get("avatar", ""),
            "crawl_time": datetime.now().isoformat(),
        }

        return job_data

    async def crawl(self):
        """主爬取流程"""
        self.stats["start_time"] = datetime.now()
        logger.info("=" * 60)
        logger.info("开始爬取龙湖'绽放'校招岗位信息")
        logger.info(f"目标页面: https://longfor.zhaopin.com/zf/index.html")
        logger.info(f"开始时间: {self.stats['start_time']}")
        logger.info("=" * 60)

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=False, args=["--disable-blink-features=AutomationControlled"]
            )
            context = await browser.new_context(
                viewport={"width": 1280, "height": 720},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            )
            page = await context.new_page()

            try:
                # 访问"绽放"项目页面建立会话
                await page.goto(
                    "https://longfor.zhaopin.com/zf/index.html",
                    wait_until="domcontentloaded",
                )
                await asyncio.sleep(3)

                # 获取子公司列表
                companies = await self.get_sub_companies(page)

                if not companies:
                    logger.warning("未获取到子公司列表，使用备用列表")
                    companies = self._get_fallback_companies()

                # 处理所有公司（包括父级和子级）
                logger.info(f"开始处理 {len(companies)} 个公司/部门")

                for idx, company in enumerate(companies, 1):
                    logger.info(
                        f"\n[{idx}/{len(companies)}] 处理公司: {company.get('name')}"
                    )
                    await self.process_company(page, company)
                    await asyncio.sleep(1)  # 增加延迟避免被限制

            except Exception as e:
                logger.error(f"爬取过程中发生错误: {e}")
                import traceback

                traceback.print_exc()

            finally:
                await browser.close()

        self.stats["end_time"] = datetime.now()
        self._print_stats()

    def _print_stats(self):
        """输出统计信息"""
        duration = (self.stats["end_time"] - self.stats["start_time"]).total_seconds()

        logger.info("=" * 60)
        logger.info("爬取完成！")
        logger.info(f"结束时间: {self.stats['end_time']}")
        logger.info(f"总耗时: {duration:.2f}秒")
        logger.info("-" * 60)
        logger.info(f"累计抓取岗位: {self.stats['total_jobs']}")
        logger.info(f"成功抓取: {self.stats['success_jobs']}")
        logger.info(f"失败: {self.stats['error_jobs']}")
        logger.info(f"处理的公司/部门数: {len(self.stats['sub_companies'])}")
        logger.info(f"数据保存至: {self.output_file}")
        logger.info("=" * 60)


async def main():
    crawler = LongForJobCrawler("longfor_jobs_zf.json")
    await crawler.crawl()


if __name__ == "__main__":
    asyncio.run(main())
