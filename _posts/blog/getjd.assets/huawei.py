import asyncio
import json
import os
import re
import time
from datetime import datetime
from playwright.async_api import async_playwright
from typing import Dict, Any, List, Optional, Set
import logging
import httpx

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class HuaweiCrawler:
    def __init__(
        self,
        output_file: str = "huawei_jobs.json",
        dept_file: str = "huawei_departments.json",
    ):
        self.output_file = output_file
        self.dept_file = dept_file
        self.base_url = "https://career.huawei.com"
        self.list_url = f"{self.base_url}/cn/campus-recruitment-job-list?recruitmentType=FRESH_GRADUATE"

        # API接口
        self.api_detail_url = "https://apigw-dgg-b0.huawei.com/api/apig/channelhw/recruitmentPosition/pub/getRecruitmentPositionDetail"
        self.api_intention_url = "https://apigw-dgg-b0.huawei.com/api/apig/channelhw/recruitmentPosition/pub/getPositionIntentionList"
        self.api_dept_url = "https://apigw-dgg-b0.huawei.com/api/apig/channelhw/recruitmentPosition/pub/getDeptIntentionList"

        self.jobs = []
        self.success_count = 0
        self.error_count = 0
        self.total_count = 0

        # 部门全集：使用字典去重，key为部门代码
        self.departments_map: Dict[str, Dict[str, Any]] = {}

        # 初始化文件
        if os.path.exists(output_file):
            os.remove(output_file)

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump([], f)

        if os.path.exists(dept_file):
            os.remove(dept_file)

        with open(dept_file, "w", encoding="utf-8") as f:
            json.dump([], f)

    async def get_api_headers(self, page) -> Dict[str, str]:
        """从页面获取必要的请求头信息"""
        try:
            cookies = await page.context.cookies()
            cookie_str = "; ".join([f"{c['name']}={c['value']}" for c in cookies])

            headers = {
                "Accept": "application/json, text/plain, */*",
                "Accept-Encoding": "gzip, deflate, br, zstd",
                "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7",
                "Connection": "keep-alive",
                "Content-Type": "application/json",
                "Cookie": cookie_str,
                "Host": "apigw-dgg-b0.huawei.com",
                "Origin": "https://career.huawei.com",
                "Referer": "https://career.huawei.com/",
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "same-site",
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36",
                "X-HW-ID": "app_000000035886",
                "sec-ch-ua": '"Not=A?Brand";v="99", "Google Chrome";v="151", "Chromium";v="151"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"macOS"',
                "x-Referer": "https://career.huawei.com/cn",
                "x-alb-gray": "prod",
                "x-jalor-tenantAlias": "hcm",
                "x-language": "zh_CN",
            }
            return headers
        except Exception as e:
            logger.error(f"获取请求头失败: {str(e)}")
            return {}

    async def get_advertisement_id_by_click(self, page, card_element) -> str:
        """通过点击岗位卡片获取advertisementId"""
        try:
            name_element = await card_element.query_selector(".job-name")
            if not name_element:
                return ""

            await name_element.click(modifiers=["ControlOrMeta"])
            await asyncio.sleep(1)

            context = page.context
            pages = context.pages
            if len(pages) <= 1:
                logger.warning("未检测到新标签页")
                return ""

            new_page = pages[-1]
            await new_page.wait_for_load_state("domcontentloaded", timeout=15000)

            current_url = new_page.url
            advertisement_id = ""
            match = re.search(r"advertisementId=(\d+)", current_url)
            if match:
                advertisement_id = match.group(1)
                logger.info(f"从详情页URL提取到advertisementId: {advertisement_id}")

            await new_page.close()
            return advertisement_id

        except Exception as e:
            logger.error(f"点击获取advertisementId失败: {str(e)}")
            return ""

    async def get_job_detail_info(self, page, advertisement_id: str) -> Dict[str, Any]:
        """获取岗位基本信息（通过getRecruitmentPositionDetail）"""
        try:
            if not advertisement_id:
                return {}

            headers = await self.get_api_headers(page)
            if not headers:
                return {}

            params = {"X-HW-ID": "app_000000035886"}
            data = {"advertisementId": advertisement_id}

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    self.api_detail_url, params=params, json=data, headers=headers
                )

                if response.status_code != 200:
                    logger.error(f"获取岗位详情API请求失败: {response.status_code}")
                    return {}

                result = response.json()
                if result.get("status") != "SUCCESS":
                    logger.error(
                        f"获取岗位详情API返回错误: {result.get('errors', '未知错误')}"
                    )
                    return {}

                data = result.get("data", {})
                return {
                    "job_id": data.get("jobId"),
                    "job_name": data.get("jobname"),
                    "job_address": data.get("jobAddress"),
                    "job_area": data.get("jobArea"),
                    "job_city": data.get("jobCity"),
                    "category_name": data.get("categoryName"),
                    "scenario_name": data.get("scenarioName"),
                    "last_update_date": data.get("lastUpdateDate"),
                    "is_hot_job": data.get("isHotJob"),
                    "external_job_name": data.get("externalJobName"),
                    "main_business": data.get("mainBusiness"),
                    "job_require": data.get("jobRequire"),
                }

        except Exception as e:
            logger.error(f"获取岗位详情失败: {str(e)}")
            return {}

    async def get_job_intentions(self, page, job_id: str) -> List[Dict[str, Any]]:
        """获取岗位意向列表（通过getPositionIntentionList）"""
        try:
            if not job_id:
                return []

            headers = await self.get_api_headers(page)
            if not headers:
                return []

            params = {"X-HW-ID": "app_000000035886"}
            data = {"jobId": int(job_id)}

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    self.api_intention_url, params=params, json=data, headers=headers
                )

                if response.status_code != 200:
                    logger.error(f"获取意向API请求失败: {response.status_code}")
                    return []

                result = response.json()
                if result.get("status") != "SUCCESS":
                    logger.error(
                        f"获取意向API返回错误: {result.get('errors', '未知错误')}"
                    )
                    return []

                intentions = result.get("data", [])
                logger.info(f"获取到 {len(intentions)} 个岗位意向")

                # 解析意向数据
                parsed_intentions = []
                for intention in intentions:
                    # 解析部门与工作地点映射 (deptAndPlaceList)
                    dept_place_map = []
                    dept_place_list = intention.get("deptAndPlaceList", [])
                    for item in dept_place_list:
                        dept_place_map.append(
                            {
                                "dept_code": item.get("deptCode"),
                                "dept_name": item.get("deptName"),
                                "job_place": item.get("jobPlace"),
                                "job_place_name": item.get("jobPlaceName"),
                            }
                        )

                    parsed = {
                        "intention_id": intention.get("positionIntentionId"),
                        "intention_name": intention.get("positionIntention", ""),
                        "responsibilities": intention.get("jobResponsibilities", ""),
                        "requirements": intention.get("jobDemand", ""),
                        "work_location": intention.get("jobPlaceName", ""),
                        "department_names": intention.get("deptName", ""),
                        "department_codes": intention.get("deptCode", ""),
                        "external_post_code": intention.get("externalPostCode", ""),
                        "dept_place_map": dept_place_map,  # 新增：部门与工作地点映射
                        "department_codes_list": [],  # 将在后面填充
                    }
                    parsed_intentions.append(parsed)

                return parsed_intentions

        except Exception as e:
            logger.error(f"获取岗位意向失败: {str(e)}")
            return []

    async def get_department_info(
        self, page, job_id: str, external_post_code: str
    ) -> List[Dict[str, Any]]:
        """获取部门层级信息（通过getDeptIntentionList）"""
        try:
            if not job_id or not external_post_code:
                return []

            headers = await self.get_api_headers(page)
            if not headers:
                return []

            params = {"X-HW-ID": "app_000000035886"}
            data = {"jobId": int(job_id), "externalPostCode": external_post_code}

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    self.api_dept_url, params=params, json=data, headers=headers
                )

                if response.status_code != 200:
                    logger.error(f"获取部门API请求失败: {response.status_code}")
                    return []

                result = response.json()
                if result.get("status") != "SUCCESS":
                    logger.error(
                        f"获取部门API返回错误: {result.get('errors', '未知错误')}"
                    )
                    return []

                dept_data = result.get("data", [])
                logger.info(f"获取到 {len(dept_data)} 个一级部门")

                # 解析部门数据
                parsed_depts = []
                for dept in dept_data:
                    first_level_code = dept.get("firstLevelDeptCode", "")
                    first_level_name = dept.get("firstLevelDeptName", "")

                    parsed = {
                        "first_level_dept_code": first_level_code,
                        "first_level_dept_name": first_level_name,
                        "sub_depts": [],
                    }

                    sub_dept_list = dept.get("subDeptList", [])
                    for sub in sub_dept_list:
                        sub_code = sub.get("deptCode", "")
                        sub_name = sub.get("deptName", "")
                        sub_desc = sub.get("deptDesc", "")

                        parsed["sub_depts"].append(
                            {"dept_code": sub_code, "dept_name": sub_name}
                        )

                        # 收集到部门全集（包含描述）
                        if sub_code and sub_code not in self.departments_map:
                            self.departments_map[sub_code] = {
                                "dept_code": sub_code,
                                "dept_name": sub_name,
                                "first_level_dept_code": first_level_code,
                                "first_level_dept_name": first_level_name,
                                "dept_desc": sub_desc,
                            }

                    parsed_depts.append(parsed)

                return parsed_depts

        except Exception as e:
            logger.error(f"获取部门信息失败: {str(e)}")
            return []

    async def save_departments(self):
        """保存部门全集到文件"""
        try:
            dept_list = list(self.departments_map.values())
            with open(self.dept_file, "w", encoding="utf-8") as f:
                json.dump(dept_list, f, ensure_ascii=False, indent=2)
            logger.info(
                f"部门全集已保存到 {self.dept_file}，共 {len(dept_list)} 个部门"
            )
        except Exception as e:
            logger.error(f"保存部门全集失败: {str(e)}")

    async def fetch_job_details(self, page, advertisement_id: str) -> Dict[str, Any]:
        """整合所有接口获取完整岗位详情"""
        try:
            # 构建详情页URL
            detail_url = f"https://career.huawei.com/cn/job-details?advertisementId={advertisement_id}"

            result = {
                "advertisement_id": advertisement_id,
                "detail_url": detail_url,  # 新增：详情页URL
                "job_id": None,
                "basic_info": {},
                "intentions": [],
                "description": "",
                "description_length": 0,
            }

            # 1. 获取基本信息
            basic_info = await self.get_job_detail_info(page, advertisement_id)
            if not basic_info:
                logger.warning("未能获取基本信息")
                return result

            result["basic_info"] = basic_info
            result["job_id"] = basic_info.get("job_id")
            job_id = basic_info.get("job_id")

            if not job_id:
                logger.warning("未能获取jobId")
                return result

            # 2. 获取意向列表
            intentions = await self.get_job_intentions(page, job_id)

            # 3. 为每个意向获取对应的部门信息（仅保存部门代码列表）
            for intent in intentions:
                external_post_code = intent.get("external_post_code", "")
                if external_post_code:
                    dept_info = await self.get_department_info(
                        page, job_id, external_post_code
                    )
                    # 提取部门代码列表
                    dept_codes = []
                    for dept in dept_info:
                        dept_codes.append(dept.get("first_level_dept_code"))
                        for sub in dept.get("sub_depts", []):
                            dept_codes.append(sub.get("dept_code"))
                    intent["department_codes_list"] = dept_codes
                    logger.info(
                        f"  意向 '{intent.get('intention_name')}' 关联 {len(dept_codes)} 个部门"
                    )

            result["intentions"] = intentions

            # 4. 组合描述信息
            description_parts = []

            # 基本信息
            if basic_info.get("job_name"):
                description_parts.append(f"岗位名称：{basic_info['job_name']}")
            if basic_info.get("category_name"):
                description_parts.append(f"岗位类别：{basic_info['category_name']}")
            if basic_info.get("job_city"):
                description_parts.append(f"工作城市：{basic_info['job_city']}")
            if basic_info.get("main_business"):
                description_parts.append(f"主要职责：{basic_info['main_business']}")
            if basic_info.get("job_require"):
                description_parts.append(f"岗位要求：{basic_info['job_require']}")

            # 意向详情
            if intentions:
                description_parts.append(f"\n共有 {len(intentions)} 个岗位意向：")
                for idx, intent in enumerate(intentions, 1):
                    description_parts.append(
                        f"\n意向{idx}：{intent.get('intention_name', '')}"
                    )
                    if intent.get("responsibilities"):
                        clean_resp = re.sub(r"<br>", "\n", intent["responsibilities"])
                        description_parts.append(f"职责：{clean_resp}")
                    if intent.get("requirements"):
                        clean_req = re.sub(r"<br>", "\n", intent["requirements"])
                        description_parts.append(f"要求：{clean_req}")

                    # 添加部门代码列表
                    dept_codes = intent.get("department_codes_list", [])
                    if dept_codes:
                        description_parts.append(
                            f"关联部门代码：{', '.join(dept_codes)}"
                        )

            result["description"] = "\n".join(description_parts)
            result["description_length"] = len(result["description"])

            return result

        except Exception as e:
            logger.error(f"获取完整岗位详情失败: {str(e)}")
            return {}

    async def parse_job_card(self, card_element) -> Dict[str, Any]:
        """解析单个岗位卡片"""
        try:
            job_data = await card_element.evaluate("""
                (element) => {
                    const getText = (selector) => {
                        const el = element.querySelector(selector);
                        return el ? el.textContent.trim() : '';
                    };
                    
                    const nameEl = element.querySelector('.job-name');
                    let jobName = '', jobType = '';
                    if (nameEl) {
                        const fullText = nameEl.textContent.trim();
                        const parts = fullText.split(/\\s{2,}/);
                        jobName = parts[0] || '';
                        jobType = parts[1] ? parts[1].replace(/\\s/g, '') : '';
                    }
                    
                    const category = getText('.position-type');
                    const location = getText('.location');
                    const updateTime = getText('.update-time').replace('更新于', '').trim();
                    
                    return {
                        job_name: jobName,
                        job_type: jobType,
                        category: category,
                        location: location,
                        update_time: updateTime
                    };
                }
            """)
            return job_data
        except Exception as e:
            logger.error(f"解析岗位卡片失败: {str(e)}")
            return None

    async def save_job(self, job_data: Dict[str, Any]):
        """保存单个岗位数据到JSON文件"""
        try:
            with open(self.output_file, "r", encoding="utf-8") as f:
                try:
                    data = json.load(f)
                except:
                    data = []

            data.append(job_data)

            with open(self.output_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            self.success_count += 1
        except Exception as e:
            logger.error(f"保存岗位数据失败: {str(e)}")
            self.error_count += 1

    async def get_total_pages(self, page) -> int:
        """获取总页数"""
        try:
            await page.wait_for_selector(".aui-pager", timeout=10000)

            page_items = await page.query_selector_all(
                ".pager-item-pager-pc, .pager-item-active-pc"
            )
            max_page = 0
            for item in page_items:
                text = await item.text_content()
                if text and text.strip().isdigit():
                    page_num = int(text.strip())
                    if page_num > max_page:
                        max_page = page_num

            if max_page > 0:
                logger.info(f"检测到总页数: {max_page}")
                return max_page

            jumper_input = await page.query_selector(".pager-jumper input")
            if jumper_input:
                max_val = await jumper_input.get_attribute("max")
                if max_val and max_val.isdigit():
                    logger.info(f"从跳转输入框获取总页数: {max_val}")
                    return int(max_val)

            logger.warning("无法获取总页数，使用默认值7")
            return 7
        except Exception as e:
            logger.error(f"获取总页数失败: {str(e)}")
            return 7

    async def go_to_next_page(self, page) -> bool:
        """导航到下一页"""
        try:
            selectors = [
                "button:has(.aui-icon-chevron-right)",
                ".aui-pager button:last-child",
                'button[type="button"]:has(.aui-icon-chevron-right)',
                ".aui-pager .aui-pager-pc button:last-child",
            ]

            next_button = None
            for selector in selectors:
                next_button = await page.query_selector(selector)
                if next_button:
                    break

            if not next_button:
                next_button = await page.query_selector('button:has-text("下一页")')

            if not next_button:
                next_button = await page.query_selector('[aria-label="下一页"]')

            if not next_button:
                logger.warning("未找到下一页按钮")
                return False

            is_disabled = await next_button.get_attribute("disabled")
            if is_disabled is not None:
                logger.info("到达最后一页")
                return False

            is_disabled_class = await next_button.get_attribute("class")
            if is_disabled_class and "disabled" in is_disabled_class:
                logger.info("按钮被禁用，到达最后一页")
                return False

            await next_button.click()
            await page.wait_for_load_state("domcontentloaded", timeout=15000)

            try:
                await page.wait_for_selector(
                    ".job-item", state="visible", timeout=10000
                )
            except:
                logger.warning("等待岗位卡片超时，可能已到最后一页")
                return False

            await asyncio.sleep(1)
            return True
        except Exception as e:
            logger.error(f"翻页操作失败: {str(e)}")
            return False

    async def crawl_page(self, page, page_num: int) -> int:
        """抓取单页的岗位信息"""
        try:
            await page.wait_for_selector(".job-item", timeout=10000)

            job_cards = await page.query_selector_all(".job-item")
            logger.info(f"第{page_num}页找到 {len(job_cards)} 个岗位")

            page_success = 0
            page_errors = 0

            for idx, card in enumerate(job_cards):
                try:
                    # 解析卡片基本信息
                    job_info = await self.parse_job_card(card)
                    if not job_info or not job_info.get("job_name"):
                        logger.warning(f"第{page_num}页第{idx+1}个岗位解析失败，跳过")
                        page_errors += 1
                        continue

                    job_name = job_info["job_name"]
                    logger.info(f"处理岗位: {job_name}")

                    # 获取advertisementId
                    advertisement_id = await self.get_advertisement_id_by_click(
                        page, card
                    )

                    if advertisement_id:
                        # 获取完整详情
                        detail_info = await self.fetch_job_details(
                            page, advertisement_id
                        )
                        job_info.update(detail_info)

                        if detail_info.get("description_length", 0) > 0:
                            logger.info(
                                f"  描述字数: {detail_info['description_length']}"
                            )
                            if detail_info.get("intentions"):
                                logger.info(
                                    f"  意向数量: {len(detail_info['intentions'])}"
                                )
                        else:
                            logger.warning(f"  未能获取详情信息")
                    else:
                        logger.warning(f"  未能获取advertisementId，跳过详情获取")

                    # 添加元数据
                    job_info["crawl_time"] = datetime.now().isoformat()
                    job_info["page"] = page_num

                    # 保存到文件
                    await self.save_job(job_info)
                    page_success += 1
                    self.total_count += 1

                    logger.info(
                        f"  成功保存岗位: {job_name} (累计: {self.total_count})"
                    )

                    await asyncio.sleep(1)

                except Exception as e:
                    logger.error(f"处理第{page_num}页第{idx+1}个岗位失败: {str(e)}")
                    page_errors += 1
                    self.error_count += 1

            self.success_count += page_success
            logger.info(f"第{page_num}页完成: 成功 {page_success}, 失败 {page_errors}")
            return page_success
        except Exception as e:
            logger.error(f"抓取第{page_num}页失败: {str(e)}")
            return 0

    async def crawl(self):
        """主爬虫方法"""
        start_time = time.time()
        logger.info("开始抓取华为校招岗位信息...")
        logger.info(f"起始URL: {self.list_url}")

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False)
            context = await browser.new_context(
                viewport={"width": 800, "height": 1080},
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36",
            )
            page = await context.new_page()

            try:
                await page.set_viewport_size({"width": 800, "height": 1080})
            except:
                pass

            try:
                logger.info("正在加载列表页...")
                await page.goto(
                    self.list_url, wait_until="domcontentloaded", timeout=60000
                )
                await page.wait_for_selector(".job-item, .aui-pager", timeout=30000)
                await asyncio.sleep(2)

                total_pages = await self.get_total_pages(page)
                logger.info(f"总共需要抓取 {total_pages} 页")

                for page_num in range(1, total_pages + 1):
                    logger.info(f"=" * 50)
                    logger.info(f"开始抓取第 {page_num} 页...")
                    page_start = time.time()

                    if page_num > 1:
                        logger.info("尝试翻到下一页...")
                        success = await self.go_to_next_page(page)
                        if not success:
                            logger.warning(f"翻页失败，停止抓取")
                            break
                        logger.info("翻页成功")

                    await self.crawl_page(page, page_num)

                    page_elapsed = time.time() - page_start
                    logger.info(f"第 {page_num} 页完成，耗时: {page_elapsed:.2f}秒")
                    logger.info(
                        f"累计统计: 总岗位 {self.total_count}, 成功 {self.success_count}, 失败 {self.error_count}"
                    )

                    if page_num < total_pages:
                        await asyncio.sleep(2)

                # 保存部门全集
                await self.save_departments()

                elapsed = time.time() - start_time
                logger.info("=" * 60)
                logger.info("抓取完成!")
                logger.info(f"总耗时: {elapsed:.2f}秒")
                logger.info(f"累计抓取: {self.total_count} 个岗位")
                logger.info(f"成功: {self.success_count} 个")
                logger.info(f"失败: {self.error_count} 个")
                logger.info(f"岗位数据已保存到: {self.output_file}")
                logger.info(f"部门全集已保存到: {self.dept_file}")
                logger.info("=" * 60)

            except Exception as e:
                logger.error(f"爬虫运行错误: {str(e)}")
                import traceback

                traceback.print_exc()
            finally:
                await browser.close()


async def main():
    crawler = HuaweiCrawler()
    await crawler.crawl()


if __name__ == "__main__":
    asyncio.run(main())
