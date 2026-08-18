import json
import os
import re
from typing import Dict, Any, List
from collections import defaultdict
from pypinyin import pinyin, Style


class JobToMarkdownConverter:
    def __init__(
        self,
        jobs_file: str = "huawei_jobs.json",
        depts_file: str = "huawei_departments.json",
    ):
        self.jobs_file = jobs_file
        self.depts_file = depts_file
        self.departments_map: Dict[str, Dict[str, Any]] = {}
        self.output_file = "huawei_jobs.md"

    def sort_by_pinyin(self, text_list: List[str]) -> List[str]:
        """按拼音排序文本列表"""
        if not text_list:
            return text_list
        text_list = [t for t in text_list if t]
        if not text_list:
            return text_list

        def get_pinyin(text):
            pinyin_list = pinyin(text, style=Style.TONE3)
            return "".join([item[0] for item in pinyin_list]).lower()

        return sorted(text_list, key=get_pinyin)

    def sort_by_pinyin_with_key(self, items: List[Dict], key_name: str) -> List[Dict]:
        """按拼音排序字典列表"""

        def get_pinyin(item):
            text = item.get(key_name, "")
            if not text:
                return ""
            pinyin_list = pinyin(text, style=Style.TONE3)
            return "".join([p[0] for p in pinyin_list]).lower()

        return sorted(items, key=get_pinyin)

    def load_data(self) -> tuple:
        """加载JSON数据"""
        if os.path.exists(self.depts_file):
            with open(self.depts_file, "r", encoding="utf-8") as f:
                depts_list = json.load(f)
                for dept in depts_list:
                    dept_code = dept.get("dept_code")
                    if dept_code:
                        self.departments_map[dept_code] = dept
            print(f"加载部门数据: {len(self.departments_map)} 个部门")
        else:
            print(f"警告: {self.depts_file} 不存在")

        if not os.path.exists(self.jobs_file):
            raise FileNotFoundError(f"{self.jobs_file} 不存在")

        with open(self.jobs_file, "r", encoding="utf-8") as f:
            jobs = json.load(f)

        print(f"加载岗位数据: {len(jobs)} 个岗位")
        return jobs

    def get_first_level_dept(self, dept_code: str) -> str:
        """根据部门代码获取一级部门名称"""
        if dept_code in self.departments_map:
            return self.departments_map[dept_code].get("first_level_dept_name", "")
        return ""

    def format_responsibilities(self, text: str) -> str:
        """格式化岗位职责，将序号转为有序列表"""
        if not text:
            return ""

        text = text.replace("<br>", "\n")
        lines = text.split("\n")
        result = []
        in_list = False

        for line in lines:
            line = line.strip()
            if not line:
                continue

            match = re.match(r"^(\d+)[、\.\)]\s*", line)
            if match:
                if not in_list:
                    result.append("")
                    in_list = True
                content = re.sub(r"^(\d+)[、\.\)]\s*", "", line)
                result.append(f"{match.group(1)}. {content}")
            else:
                if in_list and line:
                    result.append(f"   {line}")
                else:
                    if in_list:
                        result.append("")
                        in_list = False
                    result.append(line)

        return "\n".join(result)

    def format_requirements(self, text: str) -> str:
        """格式化岗位要求，将序号转为有序列表"""
        return self.format_responsibilities(text)

    def convert_job_to_md(self, job: Dict[str, Any]) -> str:
        """将单个岗位转换为Markdown"""
        lines = []

        # 1. 岗位名称 - 2级标题
        job_name = job.get("job_name", "未知岗位")
        lines.append(f"## {job_name}")
        lines.append("")

        # 2. 基本信息（工作地点按拼音排序）
        category = job.get("category", "")
        location = job.get("location", "")
        publish_time = job.get("publish_time", "")
        job_type = job.get("job_type", "")
        update_time = job.get("update_time", "")

        if location:
            cities = [c.strip() for c in location.split("/") if c.strip()]
            sorted_cities = self.sort_by_pinyin(cities)
            location = "/".join(sorted_cities)

        info_parts = []
        if category:
            info_parts.append(f"`{category}`")
        if location:
            info_parts.append(f"`{location}`")
        if publish_time:
            info_parts.append(f"`{publish_time}`")
        if job_type:
            info_parts.append(f"`{job_type}`")
        if update_time:
            info_parts.append(f"`{update_time}`")

        if info_parts:
            lines.append(" \\| ".join(info_parts))
            lines.append("")

        # 3. 岗位意向
        intentions = job.get("intentions", [])
        show_intention_title = len(intentions) > 1

        for idx, intention in enumerate(intentions):
            intention_name = intention.get("intention_name", "")

            if show_intention_title and intention_name:
                lines.append(f"### 岗位意向：{intention_name}")
                lines.append("")

            # 4. 岗位职责
            responsibilities = intention.get("responsibilities", "")
            if responsibilities:
                lines.append("**岗位职责**")
                lines.append("")
                formatted_resp = self.format_responsibilities(responsibilities)
                lines.append(formatted_resp)
                lines.append("")

            # 5. 岗位要求
            requirements = intention.get("requirements", "")
            if requirements:
                lines.append("**岗位要求**")
                lines.append("")
                formatted_req = self.format_requirements(requirements)
                lines.append(formatted_req)
                lines.append("")

            # 6. 部门意向
            dept_place_map = intention.get("dept_place_map", [])
            if dept_place_map:
                lines.append("**部门意向**")
                lines.append("")

                # 为每个部门添加一级部门名称
                for dept in dept_place_map:
                    dept_code = dept.get("dept_code", "")
                    dept["first_level_name"] = self.get_first_level_dept(dept_code)

                # 按一级部门分组
                grouped = defaultdict(list)
                for dept in dept_place_map:
                    first_level = dept.get("first_level_name", "")
                    grouped[first_level].append(dept)

                # 一级部门按拼音排序
                sorted_first_levels = self.sort_by_pinyin(list(grouped.keys()))

                # 用于去重的集合
                seen = set()

                for first_level in sorted_first_levels:
                    depts = grouped[first_level]

                    # 二级部门按拼音排序
                    sorted_depts = self.sort_by_pinyin_with_key(depts, "dept_name")

                    for dept in sorted_depts:
                        dept_name = dept.get("dept_name", "")
                        loc = dept.get("job_place_name", "")

                        # 构建显示文本
                        if dept_name and dept_name != first_level:
                            display_text = f"{first_level} > {dept_name}"
                        else:
                            display_text = first_level

                        # 工作地点按拼音排序
                        if loc:
                            cities = [c.strip() for c in loc.split("/") if c.strip()]
                            sorted_cities = self.sort_by_pinyin(cities)
                            display_text += f"，{'/'.join(sorted_cities)}"

                        # 去重
                        if display_text not in seen:
                            seen.add(display_text)
                            lines.append(f"- {display_text}")

                lines.append("")

        # 7. 官网投递链接
        detail_url = job.get("detail_url", "")
        if detail_url:
            lines.append(f"[官网投递↗]({detail_url})")
            lines.append("")

        lines.append("---")
        lines.append("")

        return "\n".join(lines)

    def convert_all_to_md(self):
        """转换所有岗位到Markdown"""
        jobs = self.load_data()

        if not jobs:
            print("没有岗位数据需要转换")
            return

        total_jobs = len(jobs)
        total_intentions = sum(len(job.get("intentions", [])) for job in jobs)

        print(f"开始转换: {total_jobs} 个岗位, {total_intentions} 个意向")

        md_lines = []

        md_lines.append("# 华为校招岗位信息")
        md_lines.append("")
        md_lines.append(f"> 共 {total_jobs} 个岗位，{total_intentions} 个意向")
        md_lines.append("")
        md_lines.append("---")
        md_lines.append("")

        for idx, job in enumerate(jobs, 1):
            print(f"处理岗位 {idx}/{total_jobs}: {job.get('job_name', '未知')}")
            job_md = self.convert_job_to_md(job)
            md_lines.append(job_md)

        with open(self.output_file, "w", encoding="utf-8") as f:
            f.write("\n".join(md_lines))

        print(f"\nMarkdown文档已保存到: {self.output_file}")
        print(f"共 {total_jobs} 个岗位，{total_intentions} 个意向")


def main():
    converter = JobToMarkdownConverter()
    converter.convert_all_to_md()


if __name__ == "__main__":
    main()
