import requests
import json
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any


class PurdueAPICrawler:
    def __init__(self):
        self.api_url = "https://pudutech1.zhiye.com/api/Jobad/GetJobAdPageList"
        self.detail_base = "https://pudutech1.zhiye.com/campus/detail"
        self.output_file = "purdue_jobs.json"
        self.stats_file = "crawl_stats.json"

        # 请求头
        self.headers = {
            "Accept": "application/json",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7",
            "Connection": "keep-alive",
            "Content-Type": "application/json",
            "Host": "pudutech1.zhiye.com",
            "Origin": "https://pudutech1.zhiye.com",
            "Referer": "https://pudutech1.zhiye.com/campus/jobs",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36",
            "X-Requested-With": "xmlhttprequest",
            "langType": "zh_CN",
        }

        # 统计信息
        self.stats = {
            "total_found": 0,
            "success": 0,
            "errors": 0,
            "start_time": None,
            "end_time": None,
            "job_details": [],
        }

        # 已保存的ID集合，用于去重
        self.saved_ids = set()
        self._load_existing_ids()

    def _load_existing_ids(self):
        """加载已保存的岗位ID，用于去重"""
        if Path(self.output_file).exists():
            try:
                with open(self.output_file, "r", encoding="utf-8") as f:
                    existing_data = json.load(f)
                    for job in existing_data:
                        job_id = job.get("job_id")
                        if job_id:
                            self.saved_ids.add(job_id)
                print(f"已加载 {len(self.saved_ids)} 个已保存的岗位ID")
            except Exception as e:
                print(f"加载已有数据时出错: {e}")

    def fetch_job_list(
        self, page_index: int = 0, page_size: int = 100
    ) -> Dict[str, Any]:
        """获取岗位列表（单页）"""
        payload = {
            "PageIndex": page_index,
            "PageSize": page_size,
            "Category": ["2"],  # 校园招聘
            "KeyWords": "",
            "SpecialType": 0,
            "PortalId": "",
            "DisplayFields": [
                "Category",
                "Kind",
                "LocId",
                "PostDate",
                "WorkWeChatQrCode",
            ],
        }

        try:
            response = requests.post(
                self.api_url, headers=self.headers, json=payload, timeout=30
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"API请求失败: {e}")
            return {}

    def get_all_jobs(self) -> List[Dict[str, Any]]:
        """获取所有岗位（处理分页）"""
        all_jobs = []
        page_index = 0
        page_size = 100

        print(f"开始获取岗位列表，每页{page_size}条...")

        while True:
            print(f"  正在获取第 {page_index + 1} 页...")
            result = self.fetch_job_list(page_index, page_size)

            if not result or result.get("Code") != 200:
                print(
                    f"  获取第 {page_index + 1} 页失败: {result.get('Message', '未知错误')}"
                )
                break

            data = result.get("Data", [])
            if not data:
                print(f"  第 {page_index + 1} 页没有数据，停止获取")
                break

            all_jobs.extend(data)
            print(f"  第 {page_index + 1} 页获取到 {len(data)} 个岗位")

            total_count = result.get("Count", 0)
            if total_count > 0 and len(all_jobs) >= total_count:
                print(f"  已获取所有 {total_count} 个岗位")
                break

            if len(data) < page_size:
                print(f"  本页数据少于{page_size}条，已到达最后一页")
                break

            page_index += 1
            time.sleep(0.5)

        return all_jobs

    def save_job(self, job_data: Dict[str, Any]) -> bool:
        """保存单个岗位信息到JSON文件（追加模式）"""
        job_id = job_data.get("job_id")

        if not job_id:
            print("  警告: 无法获取岗位ID，跳过保存")
            return False

        # 检查是否已存在
        if job_id in self.saved_ids:
            return False

        # 读取现有数据
        existing_data = []
        if Path(self.output_file).exists():
            try:
                with open(self.output_file, "r", encoding="utf-8") as f:
                    existing_data = json.load(f)
            except:
                existing_data = []

        # 添加新数据
        existing_data.append(job_data)
        self.saved_ids.add(job_id)

        # 写回文件
        with open(self.output_file, "w", encoding="utf-8") as f:
            json.dump(existing_data, f, ensure_ascii=False, indent=2)

        return True

    def process_job(self, job: Dict[str, Any]) -> Dict[str, Any]:
        """处理单个岗位数据，提取关键信息"""
        # 提取关键字段
        job_id = job.get("Id", "")
        job_title = job.get("JobAdName", "未知岗位")
        duty = job.get("Duty", "")
        require = job.get("Require", "")
        locations = job.get("LocNames", [])
        post_date = job.get("PostDate", "")
        category = job.get("Category", "")
        kind = job.get("Kind", "")

        # 构建详情页URL
        detail_url = f"{self.detail_base}?jobAdId={job_id}" if job_id else ""

        # 统计信息
        duty_len = len(duty)
        require_len = len(require)

        # 构建简洁的标准化数据
        processed_data = {
            "job_id": job_id,
            "job_title": job_title,
            "detail_url": detail_url,
            "duty": duty,
            "require": require,
            "locations": locations,
            "post_date": post_date,
            "category": category,
            "kind": kind,
            "crawl_time": datetime.now().isoformat(),
        }

        # 记录统计
        self.stats["job_details"].append(
            {
                "job_id": job_id,
                "title": job_title,
                "duty_length": duty_len,
                "require_length": require_len,
                "locations": locations,
                "post_date": post_date,
            }
        )

        # 输出调试信息
        print(f"\n  岗位: {job_title}")
        print(f"    职位描述: {duty_len} 字符")
        print(f"    职位要求: {require_len} 字符")
        print(f"    地点: {', '.join(locations) if locations else '未指定'}")
        print(f"    发布日期: {post_date}")
        print(f"    URL: {detail_url}")

        return processed_data

    def crawl(self):
        """主抓取流程"""
        self.stats["start_time"] = datetime.now().isoformat()
        print(f"开始抓取... 时间: {self.stats['start_time']}")
        print("=" * 60)

        # 获取所有岗位
        jobs = self.get_all_jobs()
        self.stats["total_found"] = len(jobs)
        print(f"\n总共发现 {len(jobs)} 个岗位")
        print("=" * 60)

        # 逐个处理岗位
        for idx, job in enumerate(jobs, 1):
            print(f"\n[{idx}/{len(jobs)}] 处理岗位...")

            try:
                # 处理岗位数据
                processed_data = self.process_job(job)

                # 保存到文件
                if self.save_job(processed_data):
                    self.stats["success"] += 1
                    print(f"  ✅ 已保存 (累计成功: {self.stats['success']})")
                else:
                    job_id = job.get("Id", "")
                    if job_id in self.saved_ids:
                        print(f"  ⚠️ 岗位已存在，跳过 (ID: {job_id})")
                    else:
                        print(f"  ⚠️ 保存失败")

            except Exception as e:
                self.stats["errors"] += 1
                print(f"  ❌ 处理失败: {e}")
                import traceback

                traceback.print_exc()

            time.sleep(0.3)

        # 完成统计
        self.stats["end_time"] = datetime.now().isoformat()
        print("\n" + "=" * 60)
        print("抓取完成！")
        print(f"  总计发现: {self.stats['total_found']} 个岗位")
        print(f"  成功抓取: {self.stats['success']} 个")
        print(
            f"  跳过(已存在): {len(jobs) - self.stats['success'] - self.stats['errors']} 个"
        )
        print(f"  错误数量: {self.stats['errors']} 个")
        print(f"  开始时间: {self.stats['start_time']}")
        print(f"  结束时间: {self.stats['end_time']}")

        # 保存统计信息
        with open(self.stats_file, "w", encoding="utf-8") as f:
            json.dump(self.stats, f, ensure_ascii=False, indent=2)
        print(f"\n统计信息已保存到 {self.stats_file}")
        print(f"岗位数据已保存到 {self.output_file}")


def main():
    crawler = PurdueAPICrawler()
    crawler.crawl()


if __name__ == "__main__":
    main()
