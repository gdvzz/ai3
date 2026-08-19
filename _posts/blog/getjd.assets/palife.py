import requests
import json
import time
import os
from datetime import datetime
from typing import Dict, List, Optional


class PingAnCampusCrawler:
    def __init__(self, output_file: str = "pingan_positions.json"):
        self.base_url = "https://campus.pingan.com/zztj-recruit-talent-webserver/rctt/candidate/position/campus/positionSearch/queryPositionPage"
        self.detail_url_template = (
            "https://campus.pingan.com/positionDetail?positionId={}"
        )
        self.output_file = output_file
        self.wecruit_id = "6c1db1bba8c33deab19a733ec785711a"

        # 统计信息
        self.total_fetched = 0
        self.total_success = 0
        self.total_errors = 0
        self.total_pages = 0
        self.start_time = None
        self.end_time = None

        # 请求头
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Referer": "https://campus.pingan.com/freshGraduates",
            "Origin": "https://campus.pingan.com",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
        }

        # 初始化输出文件
        self._init_output_file()

    def _init_output_file(self):
        """初始化输出文件，如果存在则备份"""
        if os.path.exists(self.output_file):
            backup_name = (
                f"{self.output_file}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            )
            os.rename(self.output_file, backup_name)
            print(f"[INFO] 已备份现有文件到: {backup_name}")

    def _save_position(self, position_data: Dict):
        """保存单个岗位数据到JSON文件（追加模式）"""
        try:
            # 读取现有数据
            existing_data = []
            if os.path.exists(self.output_file):
                try:
                    with open(self.output_file, "r", encoding="utf-8") as f:
                        existing_data = json.load(f)
                        if not isinstance(existing_data, list):
                            existing_data = []
                except (json.JSONDecodeError, ValueError):
                    existing_data = []

            # 追加新数据
            existing_data.append(position_data)

            # 写回文件
            with open(self.output_file, "w", encoding="utf-8") as f:
                json.dump(existing_data, f, ensure_ascii=False, indent=2)

            return True
        except Exception as e:
            print(f"[ERROR] 保存数据失败: {e}")
            return False

    def _fetch_page(self, page_num: int, page_size: int = 10) -> Optional[Dict]:
        """获取单页岗位数据"""
        payload = {
            "PageNum": page_num,
            "businessUnitId": "PA002",
            "pageSize": page_size,
            "positionCategoryId": "",
            "wecruitId": self.wecruit_id,
            "positionType": "1",
            "wecruitPlatform": True,
            "workCity": "",
            "interviewCity": "",
            "specialCodeList": [],
        }

        try:
            print(f"[DEBUG] 正在请求第 {page_num} 页...")
            response = requests.post(
                self.base_url, json=payload, headers=self.headers, timeout=30
            )
            response.raise_for_status()

            data = response.json()

            # 检查响应状态
            if data.get("responseCode") != "10001":
                print(f"[ERROR] API返回错误: {data.get('responseMsg', '未知错误')}")
                return None

            return data

        except requests.exceptions.RequestException as e:
            print(f"[ERROR] 请求第 {page_num} 页失败: {e}")
            return None
        except json.JSONDecodeError as e:
            print(f"[ERROR] 解析第 {page_num} 页JSON失败: {e}")
            return None

    def _extract_position_info(self, item: Dict) -> Dict:
        """提取单个岗位的详细信息"""
        position_id = item.get("idPosition", "")
        detail_url = self.detail_url_template.format(position_id)

        # 提取岗位信息
        position_info = {
            "positionId": position_id,
            "positionName": item.get("positionName", ""),
            "positionCode": item.get("positionCode", ""),
            "positionType": item.get("positionType", ""),
            "positionCategoryId": item.get("positionCategoryId", ""),
            "positionCategoryName": item.get("positionCategoryName", ""),
            "businessUnitId": item.get("businessUnitId", ""),
            "businessUnitName": item.get("businessUnitName", ""),
            "deptId": item.get("deptId", ""),
            "deptName": item.get("deptName", ""),
            "deptShowName": item.get("deptShowName", ""),
            "duty": item.get("duty", ""),
            "qualification": item.get("qualification", ""),
            "education": item.get("education", ""),
            "educationCode": item.get("educationCode", ""),
            "workCity": item.get("workCity", ""),
            "workCityCode": item.get("workCityCode", ""),
            "interviewCity": item.get("interviewCity", ""),
            "interviewCityCode": item.get("interviewCityCode", ""),
            "recruitNumber": item.get("recruitNumber", 0),
            "salaryMin": item.get("salaryMin"),
            "salaryMax": item.get("salaryMax"),
            "salaryType": item.get("salaryType", ""),
            "salaryTypeDesc": item.get("salaryTypeDesc", ""),
            "publishDate": item.get("publishDate", ""),
            "publishStatus": item.get("publishStatus", ""),
            "publishStatusDesc": item.get("publishStatusDesc", ""),
            "createdDate": item.get("createdDate", ""),
            "updatedDate": item.get("updatedDate", ""),
            "detailUrl": detail_url,
            "fetchedAt": datetime.now().isoformat(),
        }

        return position_info

    def crawl(self):
        """主抓取方法"""
        self.start_time = time.time()
        print("=" * 60)
        print("[INFO] 开始抓取平安人寿校招岗位信息")
        print(f"[INFO] 输出文件: {self.output_file}")
        print("=" * 60)

        # 先获取第一页，获取总页数
        first_page_data = self._fetch_page(1)
        if not first_page_data:
            print("[ERROR] 无法获取第一页数据，程序退出")
            return

        page_info = first_page_data.get("data", {})
        self.total_pages = page_info.get("totalPage", 0)
        total_count = page_info.get("totalCount", 0)

        print(f"[INFO] 总岗位数: {total_count}")
        print(f"[INFO] 总页数: {self.total_pages}")
        print(f"[INFO] 每页数量: {page_info.get('pageSize', 10)}")
        print("-" * 60)

        # 处理第一页的数据
        self._process_page(first_page_data, 1)

        # 处理后续页面
        for page_num in range(2, self.total_pages + 1):
            print("-" * 60)
            page_data = self._fetch_page(page_num)
            if page_data:
                self._process_page(page_data, page_num)
            else:
                print(f"[ERROR] 第 {page_num} 页抓取失败，跳过")
                self.total_errors += 10  # 估算错误数

        self.end_time = time.time()
        self._print_summary()

    def _process_page(self, page_data: Dict, page_num: int):
        """处理单页数据"""
        data = page_data.get("data", {})
        position_list = data.get("list", [])
        page_size = data.get("pageSize", 10)

        print(f"[INFO] 处理第 {page_num} 页，共 {len(position_list)} 个岗位")

        for idx, item in enumerate(position_list, 1):
            try:
                position_info = self._extract_position_info(item)
                position_name = position_info.get("positionName", "未知岗位")
                duty_length = len(position_info.get("duty", ""))
                qualification_length = len(position_info.get("qualification", ""))

                # 保存数据
                if self._save_position(position_info):
                    self.total_success += 1
                    print(f"  [+] {idx:2d}. {position_name}")
                    print(
                        f"      职位描述字数: {duty_length}, 职位要求字数: {qualification_length}"
                    )
                    print(f"      详情页: {position_info['detailUrl']}")
                else:
                    self.total_errors += 1
                    print(f"  [x] {idx:2d}. {position_name} - 保存失败")

                self.total_fetched += 1

                # 添加延时，避免请求过快
                time.sleep(0.2)

            except Exception as e:
                self.total_errors += 1
                print(f"  [x] 处理第 {idx} 个岗位时出错: {e}")

    def _print_summary(self):
        """打印抓取总结"""
        elapsed_time = self.end_time - self.start_time if self.end_time else 0

        print("=" * 60)
        print("[SUMMARY] 抓取完成!")
        print(f"  - 总耗时: {elapsed_time:.2f} 秒")
        print(f"  - 累计抓取岗位: {self.total_fetched}")
        print(f"  - 成功保存: {self.total_success}")
        print(f"  - 错误数量: {self.total_errors}")
        print(f"  - 总页数: {self.total_pages}")
        print(f"  - 输出文件: {self.output_file}")

        # 检查文件大小
        if os.path.exists(self.output_file):
            file_size = os.path.getsize(self.output_file)
            if file_size < 1024:
                size_str = f"{file_size} B"
            elif file_size < 1024 * 1024:
                size_str = f"{file_size / 1024:.2f} KB"
            else:
                size_str = f"{file_size / (1024 * 1024):.2f} MB"
            print(f"  - 文件大小: {size_str}")

            # 统计文件中的记录数
            try:
                with open(self.output_file, "r", encoding="utf-8") as f:
                    records = json.load(f)
                    print(f"  - 文件中记录数: {len(records)}")
            except:
                pass

        print("=" * 60)


def main():
    """主函数"""
    crawler = PingAnCampusCrawler("pingan_positions.json")
    crawler.crawl()


if __name__ == "__main__":
    main()
