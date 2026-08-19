import asyncio
import json
import time
import aiohttp
import aiofiles
from typing import Dict, Any
import logging
import uuid

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class BilibiliJobCrawler:
    def __init__(self):
        self.base_url = "https://jobs.bilibili.com/campus/positions?type=3"
        self.api_url = "https://jobs.bilibili.com/api/campus/position/positionList"
        self.output_file = "bilibili_jobs_y27fa.json"
        self.jobs = []
        self.success_count = 0
        self.error_count = 0
        self.total_count = 0
        # 生成session id
        self.aj_session_id = str(uuid.uuid4())

    async def fetch_job_list(self, page_num: int) -> Dict[str, Any]:
        """通过API获取岗位列表"""
        payload = {
            "pageSize": 10,
            "pageNum": page_num,
            "positionName": "",
            "postCode": [],
            "postCodeList": [],
            "workLocationList": [],
            "workTypeList": ["3"],
            "positionTypeList": ["3"],
            "deptCodeList": [],
            "recruitType": None,
            "practiceTypes": [],
            "onlyHotRecruit": 0,
        }

        headers = {
            "accept": "application/json, text/plain, */*",
            "accept-encoding": "gzip, deflate, br, zstd",
            "accept-language": "en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7",
            "content-type": "application/json",
            "origin": "https://jobs.bilibili.com",
            "referer": "https://jobs.bilibili.com/campus/positions?type=3",
            "sec-ch-ua": '"Not=A?Brand";v="99", "Google Chrome";v="151", "Chromium";v="151"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"macOS"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36",
            "x-appkey": "ops.ehr-api.auth",
            "x-channel": "campus",
            "x-csrf": str(uuid.uuid4()),  # 生成新的csrf token
            "x-usertype": "2",
            "ajSessionId": self.aj_session_id,  # 添加session id
        }

        async with aiohttp.ClientSession() as session:
            try:
                logger.info(f"请求第 {page_num} 页数据...")
                async with session.post(
                    self.api_url, json=payload, headers=headers, timeout=30
                ) as response:
                    logger.info(f"响应状态码: {response.status}")

                    if response.status == 200:
                        data = await response.json()
                        return data
                    else:
                        logger.error(f"API请求失败，状态码: {response.status}")
                        try:
                            error_text = await response.text()
                            logger.error(f"错误内容: {error_text[:200]}")
                        except:
                            pass
                        return None
            except asyncio.TimeoutError:
                logger.error(f"请求第 {page_num} 页超时")
                return None
            except Exception as e:
                logger.error(f"API请求异常: {e}")
                return None

    async def get_total_pages(self) -> int:
        """获取总页数"""
        logger.info("正在获取总页数...")
        data = await self.fetch_job_list(1)

        if data:
            logger.info(f"API响应码: {data.get('code')}")

            if data.get("code") == 0:
                data_content = data.get("data", {})

                # 直接从data中获取pages
                pages = data_content.get("pages")
                if pages is not None:
                    logger.info(f"从API获取总页数: {pages}")
                    return pages

                # 如果pages不存在，从total和size计算
                total = data_content.get("total", 0)
                size = data_content.get("size", 10)
                job_list = data_content.get("list", [])

                logger.info(
                    f"total: {total}, size: {size}, 当前页岗位数: {len(job_list)}"
                )

                if total > 0 and size > 0:
                    pages = (total + size - 1) // size
                    logger.info(f"计算得出总页数: {pages}")
                    return pages

                # 如果total为0但list有数据，说明是最后一页
                if len(job_list) > 0:
                    logger.warning("total为0但list有数据，尝试继续爬取...")
                    return 1

                return 0
            else:
                # 打印更详细的错误信息
                logger.error(
                    f"API返回错误: code={data.get('code')}, message={data.get('message')}"
                )
                logger.error(f"完整响应: {json.dumps(data, ensure_ascii=False)}")
                return 0
        else:
            logger.error("无法获取API数据")
            return 0

    async def save_job(self, job: Dict[str, Any]):
        """保存单个岗位信息到JSON文件（追加模式）"""
        try:
            # 读取现有数据
            try:
                async with aiofiles.open(self.output_file, "r", encoding="utf-8") as f:
                    content = await f.read()
                    if content.strip():
                        existing_jobs = json.loads(content)
                    else:
                        existing_jobs = []
            except FileNotFoundError:
                existing_jobs = []

            # 添加新岗位
            existing_jobs.append(job)

            # 写回文件
            async with aiofiles.open(self.output_file, "w", encoding="utf-8") as f:
                await f.write(json.dumps(existing_jobs, ensure_ascii=False, indent=2))

        except Exception as e:
            logger.error(f"保存岗位失败: {e}")

    def extract_job_detail(self, job_data: Dict[str, Any]) -> Dict[str, Any]:
        """提取岗位详细信息"""
        # 计算描述字数
        position_description = job_data.get("positionDescription", "")
        desc_word_count = len(
            position_description.replace("\n", "").replace(" ", "").replace("\r", "")
        )

        # 构建详情页URL
        job_id = job_data.get("id")
        detail_url = (
            f"https://jobs.bilibili.com/campus/positions/{job_id}" if job_id else None
        )

        return {
            "job_id": job_id,
            "position_name": job_data.get("positionName", ""),
            "position_type": job_data.get("positionTypeName", ""),
            "post_code_name": job_data.get("postCodeName", ""),
            "work_location": job_data.get("workLocation", ""),
            "push_time": job_data.get("pushTime", ""),
            "recruit_type": job_data.get("recruitType", ""),
            "hot_recruit": job_data.get("hotRecruit", 0),
            "campus_project_id": job_data.get("campusProjectId"),
            "position_description": position_description,
            "description_word_count": desc_word_count,
            "detail_url": detail_url,
        }

    async def crawl_page(self, page_num: int) -> tuple:
        """爬取单页的岗位信息"""
        start_time = time.time()

        try:
            data = await self.fetch_job_list(page_num)

            if not data:
                logger.error(f"第 {page_num} 页数据为空")
                return (0, 0)

            if data.get("code") != 0:
                logger.error(
                    f"第 {page_num} 页API返回错误: code={data.get('code')}, message={data.get('message')}"
                )
                return (0, 0)

            job_list = data.get("data", {}).get("list", [])
            page_size = len(job_list)

            logger.info(f"\n--- 开始处理第 {page_num} 页 ---")
            logger.info(f"本页岗位数量: {page_size}")

            if page_size == 0:
                logger.warning(f"第 {page_num} 页没有岗位数据")
                return (0, 0)

            success_count = 0
            error_count = 0

            for idx, job_data in enumerate(job_list, 1):
                try:
                    # 提取岗位信息
                    job_info = self.extract_job_detail(job_data)

                    # 打印调试信息
                    position_name = job_info["position_name"]
                    desc_words = job_info["description_word_count"]

                    logger.info(f"  [{idx}/{page_size}] 岗位: {position_name}")
                    logger.info(f"      职位描述字数: {desc_words}")
                    logger.info(f"      详情页: {job_info['detail_url']}")

                    # 保存到文件
                    await self.save_job(job_info)
                    self.jobs.append(job_info)

                    success_count += 1
                    self.success_count += 1

                except Exception as e:
                    logger.error(f"  处理第 {idx} 个岗位失败: {e}")
                    error_count += 1
                    self.error_count += 1

            elapsed_time = time.time() - start_time
            logger.info(
                f"第 {page_num} 页完成，耗时: {elapsed_time:.2f}秒，成功: {success_count}，失败: {error_count}"
            )

            return (success_count, error_count)

        except Exception as e:
            logger.error(f"爬取第 {page_num} 页失败: {e}")
            return (0, 0)

    async def crawl_all(self):
        """爬取所有岗位"""
        start_time = time.time()

        logger.info("=" * 60)
        logger.info("开始抓取B站校园招聘岗位信息")
        logger.info("=" * 60)

        # 获取总页数
        total_pages = await self.get_total_pages()

        if total_pages == 0:
            logger.error("无法获取总页数，程序退出")
            return

        logger.info(f"总页数: {total_pages}")

        # 初始化JSON文件
        async with aiofiles.open(self.output_file, "w", encoding="utf-8") as f:
            await f.write("[]")

        # 逐页爬取
        for page_num in range(1, total_pages + 1):
            success, error = await self.crawl_page(page_num)
            self.total_count += success + error

            # 打印累计统计
            logger.info(f"\n--- 累计统计 ---")
            logger.info(f"已处理页数: {page_num}/{total_pages}")
            logger.info(f"累计抓取岗位: {self.total_count}")
            logger.info(f"成功: {self.success_count}, 失败: {self.error_count}")
            logger.info("-" * 60)

            # 添加延迟，避免请求过快
            if page_num < total_pages:
                await asyncio.sleep(1)

        # 最终统计
        elapsed_time = time.time() - start_time
        logger.info("\n" + "=" * 60)
        logger.info("抓取完成！")
        logger.info(f"总耗时: {elapsed_time:.2f}秒")
        logger.info(f"累计抓取岗位: {self.total_count}")
        logger.info(f"成功: {self.success_count}")
        logger.info(f"失败: {self.error_count}")
        logger.info(f"数据已保存到: {self.output_file}")
        logger.info("=" * 60)


async def main():
    crawler = BilibiliJobCrawler()
    await crawler.crawl_all()


if __name__ == "__main__":
    asyncio.run(main())
