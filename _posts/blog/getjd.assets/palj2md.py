import json
import re
from collections import defaultdict
from typing import List, Dict, Any, Set


class JsonToMarkdownConverter:
    def __init__(
        self,
        json_file: str = "pingan_positions.json",
        output_file: str = "pingan_positions.md",
    ):
        self.json_file = json_file
        self.output_file = output_file
        self.positions = []
        self.category_positions = defaultdict(list)
        self.name_counter = defaultdict(int)  # 统计岗位名称出现次数

    def load_json(self) -> bool:
        """加载JSON文件"""
        try:
            with open(self.json_file, "r", encoding="utf-8") as f:
                self.positions = json.load(f)
                if not isinstance(self.positions, list):
                    print("[ERROR] JSON文件根节点不是数组")
                    return False
                print(f"[INFO] 成功加载 {len(self.positions)} 个岗位")
                return True
        except FileNotFoundError:
            print(f"[ERROR] 文件不存在: {self.json_file}")
            return False
        except json.JSONDecodeError as e:
            print(f"[ERROR] JSON解析错误: {e}")
            return False

    def _count_duplicate_names(self):
        """统计重复的岗位名称"""
        for pos in self.positions:
            name = pos.get("positionName", "未知岗位")
            self.name_counter[name] += 1

    def _get_unique_title(self, position: Dict[str, Any]) -> str:
        """获取唯一的岗位标题，如果名称重复则添加-positionCode（小写）"""
        name = position.get("positionName", "未知岗位")
        code = position.get("positionCode", "")

        # 如果该名称出现多次，添加-positionCode（小写）
        if self.name_counter.get(name, 0) > 1 and code:
            return f"{name}-{code.lower()}"
        return name

    def _format_text_with_numbers(self, text: str) -> str:
        """将带有数字序号的文本转换为有序列表"""
        if not text:
            return ""

        lines = text.strip().split("\n")
        formatted_lines = []
        in_list = False

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # 匹配序号模式
            match = re.match(r"^(\d+)[.、）]\s*(.*)", line)
            if match:
                if not in_list:
                    formatted_lines.append("")
                    in_list = True
                formatted_lines.append(f"{match.group(1)}. {match.group(2)}")
            else:
                # 检查是否是以数字开头的序号但格式不同
                match2 = re.match(r"^(\d+)\s+(.*)", line)
                if match2 and len(line) < 50:
                    if not in_list:
                        formatted_lines.append("")
                        in_list = True
                    formatted_lines.append(f"{match2.group(1)}. {match2.group(2)}")
                else:
                    if in_list:
                        in_list = False
                    formatted_lines.append(line)

        # 如果内容包含明显的序号但没有匹配到，尝试分割处理
        if not any(
            "." in line
            for line in formatted_lines
            if line.startswith(("1.", "2.", "3.", "4.", "5.", "6.", "7.", "8.", "9."))
        ):
            has_list = False
            for line in text.strip().split("\n"):
                if re.match(r"^\s*(\d+)[)）、]\s*", line):
                    has_list = True
                    break
            if has_list:
                new_lines = []
                for line in text.strip().split("\n"):
                    line = line.strip()
                    if not line:
                        continue
                    match = re.match(r"^\s*(\d+)[)）、]\s*(.*)", line)
                    if match:
                        new_lines.append(f"{match.group(1)}. {match.group(2)}")
                    else:
                        new_lines.append(line)
                return "\n".join(new_lines)

        return "\n".join(formatted_lines)

    def _sort_cities(self, city_str: str) -> str:
        """按拼音排序城市名称"""
        if not city_str:
            return ""

        # 分割城市
        cities = [c.strip() for c in city_str.split(",") if c.strip()]

        # 按拼音排序
        cities.sort(
            key=lambda x: x.encode("gbk", errors="ignore").decode(
                "gbk", errors="ignore"
            )
        )

        return "，".join(cities)

    def _convert_single_position(self, position: Dict[str, Any]) -> str:
        """转换单个岗位为Markdown"""
        # 获取唯一标题
        title = self._get_unique_title(position)

        business_unit = position.get("businessUnitName", "")
        dept_show = position.get("deptShowName", "")
        category = position.get("positionCategoryName", "")
        education = position.get("education", "")
        recruit_number = position.get("recruitNumber", 0)
        updated_date = position.get("updatedDate", "")[:10]

        duty = position.get("duty", "")
        qualification = position.get("qualification", "")
        work_city = position.get("workCity", "")
        interview_city = position.get("interviewCity", "")
        detail_url = position.get("detailUrl", "")

        # 格式化职责和要求
        formatted_duty = self._format_text_with_numbers(duty)
        formatted_qual = self._format_text_with_numbers(qualification)

        # 排序城市
        sorted_work_city = self._sort_cities(work_city)
        sorted_interview_city = self._sort_cities(interview_city)

        # 构建Markdown
        md_parts = []

        # 2级标题 - 岗位名称（重复时带-positionCode小写）
        md_parts.append(f"## {title}")
        md_parts.append("")

        # 元信息行 - 使用\|分隔
        info_parts = []
        dept_str = ""
        if business_unit and dept_show:
            dept_str = f"`{business_unit} - {dept_show}`"
        elif business_unit:
            dept_str = f"`{business_unit}`"
        elif dept_show:
            dept_str = f"`{dept_show}`"

        if dept_str:
            info_parts.append(dept_str)

        if category:
            info_parts.append(f"`职位类别：{category}`")
        if education:
            info_parts.append(f"`{education}及以上`")
        if recruit_number:
            info_parts.append(f"`拟招：{recruit_number}`")
        if updated_date:
            info_parts.append(f"`更新：{updated_date}`")

        # 用 \| 分隔
        md_parts.append(" \\| ".join(info_parts))
        md_parts.append("")

        # 岗位职责
        if formatted_duty:
            md_parts.append("**岗位职责：**")
            md_parts.append("")
            if any(
                line.strip().startswith(
                    ("1.", "2.", "3.", "4.", "5.", "6.", "7.", "8.", "9.")
                )
                for line in formatted_duty.split("\n")
            ):
                md_parts.append(formatted_duty)
            else:
                for line in formatted_duty.split("\n"):
                    if line.strip():
                        md_parts.append(line)
            md_parts.append("")

        # 岗位要求
        if formatted_qual:
            md_parts.append("**岗位要求：**")
            md_parts.append("")
            if any(
                line.strip().startswith(
                    ("1.", "2.", "3.", "4.", "5.", "6.", "7.", "8.", "9.")
                )
                for line in formatted_qual.split("\n")
            ):
                md_parts.append(formatted_qual)
            else:
                for line in formatted_qual.split("\n"):
                    if line.strip():
                        md_parts.append(line)
            md_parts.append("")

        # 工作城市
        if sorted_work_city:
            md_parts.append("**工作城市：**")
            md_parts.append("")
            md_parts.append(sorted_work_city)
            md_parts.append("")

        # 面试城市 - 始终显示
        if sorted_interview_city:
            md_parts.append("**面试城市：**")
            md_parts.append("")
            md_parts.append(sorted_interview_city)
            md_parts.append("")
        else:
            # 如果没有面试城市信息，显示"同工作城市"或"待定"
            md_parts.append("**面试城市：**")
            md_parts.append("")
            if sorted_work_city:
                md_parts.append("同工作城市")
            else:
                md_parts.append("待定")
            md_parts.append("")

        # 官网投递链接
        if detail_url:
            md_parts.append(f"[官网投递↗]({detail_url})")
            md_parts.append("")

        # 分隔线
        md_parts.append("---")
        md_parts.append("")

        return "\n".join(md_parts)

    def _generate_category_index(self) -> str:
        """生成按类别分类的岗位索引"""
        # 收集所有类别
        categories = defaultdict(list)
        for pos in self.positions:
            category = pos.get("positionCategoryName", "未分类")
            name = pos.get("positionName", "未知岗位")
            code = pos.get("positionCode", "")

            # 如果名称重复，在目录中也显示-positionCode（小写）
            if self.name_counter.get(name, 0) > 1 and code:
                display_name = f"{name}-{code.lower()}"
            else:
                display_name = name
            categories[category].append(display_name)

        # 按类别排序
        md_parts = ["# 岗位目录", ""]

        # 总览
        md_parts.append(f"**共 {len(self.positions)} 个岗位**")
        md_parts.append("")

        # 按类别输出
        for category in sorted(categories.keys()):
            names = sorted(categories[category])
            md_parts.append(f"## {category} ({len(names)})")
            md_parts.append("")
            for name in names:
                md_parts.append(f"- {name}")
            md_parts.append("")

        md_parts.append("---")
        md_parts.append("")

        return "\n".join(md_parts)

    def convert(self) -> bool:
        """执行转换"""
        if not self.load_json():
            return False

        # 统计重复名称
        self._count_duplicate_names()

        print(f"[INFO] 开始转换 {len(self.positions)} 个岗位为Markdown...")

        # 显示重复名称信息
        duplicates = {
            name: count for name, count in self.name_counter.items() if count > 1
        }
        if duplicates:
            print(f"[INFO] 发现 {len(duplicates)} 个重复的岗位名称:")
            for name, count in duplicates.items():
                print(f"  - {name}: {count} 次")

        # 生成目录
        print("[INFO] 生成岗位目录...")
        index_content = self._generate_category_index()

        # 转换每个岗位
        print("[INFO] 转换岗位详情...")
        position_contents = []
        for idx, pos in enumerate(self.positions, 1):
            try:
                content = self._convert_single_position(pos)
                position_contents.append(content)
                name = pos.get("positionName", "未知岗位")
                code = pos.get("positionCode", "")
                if self.name_counter.get(name, 0) > 1:
                    print(
                        f"  [{idx}/{len(self.positions)}] 已转换: {name}-{code.lower()}"
                    )
                else:
                    print(f"  [{idx}/{len(self.positions)}] 已转换: {name}")
            except Exception as e:
                print(f"  [ERROR] 转换第 {idx} 个岗位失败: {e}")
                continue

        # 合并所有内容
        full_content = index_content + "\n".join(position_contents)

        # 写入文件
        try:
            with open(self.output_file, "w", encoding="utf-8") as f:
                f.write(full_content)
            print(f"[INFO] 成功保存到: {self.output_file}")
            return True
        except Exception as e:
            print(f"[ERROR] 保存文件失败: {e}")
            return False

    def show_sample(self, count: int = 1) -> str:
        """显示一个样例输出"""
        if not self.positions:
            if not self.load_json():
                return "无法加载数据"

        # 统计重复名称
        self._count_duplicate_names()

        sample_count = min(count, len(self.positions))
        print(f"\n[样例输出] 显示前 {sample_count} 个岗位的Markdown格式:")
        print("=" * 80)

        for idx in range(sample_count):
            content = self._convert_single_position(self.positions[idx])
            print(content)
            if idx < sample_count - 1:
                print("\n" + "=" * 80 + "\n")

        print("=" * 80)
        return ""


def main():
    """主函数"""
    converter = JsonToMarkdownConverter("pingan_positions.json", "pingan_positions.md")

    # 显示样例
    converter.show_sample(2)

    # 转换全部
    print("\n" + "=" * 80)
    print("[INFO] 开始完整转换...")
    print("=" * 80)

    if converter.convert():
        print("\n[SUCCESS] 转换完成!")
        print(f"  - 输入文件: {converter.json_file}")
        print(f"  - 输出文件: {converter.output_file}")
        print(f"  - 岗位数量: {len(converter.positions)}")

        # 显示重复名称统计
        duplicates = {
            name: count for name, count in converter.name_counter.items() if count > 1
        }
        if duplicates:
            print(f"  - 重复名称: {len(duplicates)} 个")
            for name, count in sorted(duplicates.items(), key=lambda x: -x[1]):
                print(f"    - {name}: {count} 次")
    else:
        print("\n[ERROR] 转换失败!")


if __name__ == "__main__":
    main()
