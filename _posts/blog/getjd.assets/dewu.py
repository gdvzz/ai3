import asyncio
import json
import time
import logging
from typing import List, Dict, Optional
from playwright.async_api import async_playwright, Page, BrowserContext

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

class DeWuCampusScraper:
    """得物校招岗位抓取器 - 使用多Tab方式"""
    
    def __init__(self, output_file: str = "dewu_campus_positions.json"):
        self.output_file = output_file
        self.list_url = "https://campus.dewu.com/578078/position/list"
        self.base_url = "https://campus.dewu.com"
        self.stats = {
            "total_found": 0,
            "success": 0,
            "failed": 0,
            "start_time": 0,
            "end_time": 0
        }
        self.positions = []
        self.processed_ids = set()
        self.max_pages = 16
        
    def _init_output_file(self):
        """初始化输出文件"""
        try:
            with open(self.output_file, 'w', encoding='utf-8') as f:
                json.dump([], f, ensure_ascii=False, indent=2)
            logger.info(f"已初始化输出文件: {self.output_file}")
        except Exception as e:
            logger.error(f"初始化输出文件失败: {e}")
            
    async def save_position(self, position_data: Dict):
        """保存单个岗位数据到JSON文件（追加模式）"""
        try:
            # 读取现有数据
            try:
                with open(self.output_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                data = []
            
            # 追加新数据
            data.append(position_data)
            
            # 写回文件
            with open(self.output_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"已保存岗位: {position_data.get('title', 'Unknown')} (ID: {position_data.get('id', 'N/A')})")
        except Exception as e:
            logger.error(f"保存岗位数据失败: {e}")
    
    async def parse_position_detail_in_new_tab(self, context: BrowserContext, detail_url: str, position_id: str) -> Optional[Dict]:
        """在新Tab中打开并解析岗位详情页"""
        try:
            start_time = time.time()
            logger.info(f"在新Tab中打开详情页: {detail_url}")
            
            # 创建新Tab
            new_page = await context.new_page()
            
            try:
                # 访问详情页
                response = await new_page.goto(detail_url, wait_until="networkidle", timeout=30000)
                if not response or response.status != 200:
                    logger.error(f"详情页加载失败: {detail_url}, 状态码: {response.status if response else 'N/A'}")
                    return None
                
                # 等待详情页加载完成
                await new_page.wait_for_selector(".jobDetail, .job-detail", timeout=10000)
                await new_page.wait_for_timeout(1000)
                
                # 提取标题
                title = "未知岗位"
                title_element = await new_page.query_selector(".job-title")
                if title_element:
                    title = await title_element.inner_text()
                    title = title.strip()
                
                # 提取职位描述和职位要求
                description = ""
                requirements = ""
                desc_title_elements = await new_page.query_selector_all(".block-title")
                content_elements = await new_page.query_selector_all(".block-content")
                
                for i, elem in enumerate(desc_title_elements):
                    text = await elem.inner_text()
                    if "职位描述" in text and i < len(content_elements):
                        description = await content_elements[i].inner_text()
                        description = description.strip()
                    elif "职位要求" in text and i < len(content_elements):
                        requirements = await content_elements[i].inner_text()
                        requirements = requirements.strip()
                
                # 提取 meta_info 并去重
                meta_info_raw = []
                job_info = await new_page.query_selector(".job-info")
                if job_info:
                    span_elements = await job_info.query_selector_all("span")
                    for span in span_elements:
                        text = await span.inner_text()
                        if text and text.strip():
                            meta_info_raw.append(text.strip())
                
                # 去重（保持顺序）
                meta_info = []
                seen = set()
                for item in meta_info_raw:
                    if item not in seen:
                        meta_info.append(item)
                        seen.add(item)
                
                # 智能提取城市和项目
                city = ""
                project = ""
                city_keywords = ["上海", "杭州", "北京", "广州", "廊坊", "沈阳", "成都", "贵阳", "咸阳", "武汉", "长沙"]
                for info in meta_info:
                    if any(keyword in info for keyword in city_keywords):
                        if not city:
                            city = info
                    elif "专项" in info or "项目" in info or "届" in info:
                        if not project:
                            project = info
                
                # 如果没提取到城市，尝试从元信息中找
                if not city and meta_info:
                    city = meta_info[0]
                
                # 提取标签
                tags = []
                tag_elements = await new_page.query_selector_all(".ud__tag")
                for tag in tag_elements:
                    text = await tag.inner_text()
                    if text and text.strip():
                        tags.append(text.strip())
                
                position_data = {
                    "id": position_id,
                    "title": title,
                    "url": detail_url,
                    "meta_info": meta_info,
                    "city": city,
                    "project": project,
                    "tags": tags,
                    "description": description,
                    "description_length": len(description),
                    "requirements": requirements,
                    "requirements_length": len(requirements),
                    "crawl_time": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "crawl_duration": round(time.time() - start_time, 2)
                }
                
                logger.info(f"详情页解析完成: {title} (meta: {len(meta_info)}项, 描述: {len(description)}字, 要求: {len(requirements)}字, 耗时: {position_data['crawl_duration']}秒)")
                return position_data
                
            finally:
                # 关闭新Tab
                await new_page.close()
                logger.debug(f"已关闭详情页Tab: {detail_url}")
            
        except Exception as e:
            logger.error(f"解析详情页失败 {detail_url}: {e}")
            return None
    
    async def parse_list_page(self, page: Page) -> List[Dict]:
        """解析列表页，获取岗位链接和基本信息"""
        try:
            # 等待岗位列表加载
            await page.wait_for_selector(".listItems__fca8c0 a[data-id]", timeout=10000)
            
            link_elements = await page.query_selector_all(".listItems__fca8c0 a[data-id]")
            if not link_elements:
                link_elements = await page.query_selector_all("a[data-id][href*='/position/']")
            
            logger.info(f"当前列表页找到 {len(link_elements)} 个岗位链接")
            
            positions_info = []
            for link_element in link_elements:
                try:
                    href = await link_element.get_attribute("href")
                    position_id = await link_element.get_attribute("data-id")
                    
                    if not href or not position_id:
                        continue
                    
                    if href.startswith('/'):
                        full_url = f"{self.base_url}{href}"
                    elif href.startswith('http'):
                        full_url = href
                    else:
                        full_url = f"{self.base_url}/578078/position/{href}"
                    
                    # 提取岗位标题
                    title = "未知岗位"
                    title_element = await link_element.query_selector(".positionItem-title-text")
                    if title_element:
                        title = await title_element.inner_text()
                        title = title.strip()
                    
                    # 提取 list_info 并去重
                    info_raw = []
                    sub_title = await link_element.query_selector(".subTitle__fca8c0")
                    if sub_title:
                        span_elements = await sub_title.query_selector_all("span")
                        for span in span_elements:
                            text = await span.inner_text()
                            if text and text.strip():
                                info_raw.append(text.strip())
                    
                    # 去重（保持顺序）
                    list_info = []
                    seen = set()
                    for item in info_raw:
                        if item not in seen:
                            list_info.append(item)
                            seen.add(item)
                    
                    # 提取列表页的城市（第一个信息通常是城市）
                    list_city = list_info[0] if list_info else ""
                    
                    positions_info.append({
                        "id": position_id,
                        "title": title,
                        "url": full_url,
                        "list_info": list_info,
                        "list_city": list_city
                    })
                    
                except Exception as e:
                    logger.warning(f"解析单个岗位卡片失败: {e}")
                    continue
            
            return positions_info
            
        except Exception as e:
            logger.error(f"解析列表页失败: {e}")
            return []
    
    async def crawl_page_positions(self, context: BrowserContext, list_page: Page, page_num: int) -> int:
        """抓取当前列表页的所有岗位（每个岗位在新Tab中打开）"""
        logger.info(f"正在抓取第 {page_num} 页")
        
        try:
            # 解析列表页获取岗位信息
            positions_info = await self.parse_list_page(list_page)
            
            if not positions_info:
                logger.warning(f"第 {page_num} 页没有找到岗位")
                return 0
            
            new_positions_count = 0
            
            # 逐个抓取详情（每个在新Tab中打开）
            for pos_info in positions_info:
                # 检查是否已处理
                if pos_info["id"] in self.processed_ids:
                    logger.debug(f"跳过已处理的岗位: {pos_info['title']} (ID: {pos_info['id']})")
                    continue
                
                self.processed_ids.add(pos_info["id"])
                self.stats["total_found"] += 1
                new_positions_count += 1
                
                try:
                    # 在新Tab中抓取详情
                    detail_data = await self.parse_position_detail_in_new_tab(
                        context, 
                        pos_info["url"], 
                        pos_info["id"]
                    )
                    
                    if detail_data:
                        # 合并列表信息
                        detail_data["list_info"] = pos_info["list_info"]
                        detail_data["list_city"] = pos_info["list_city"]
                        
                        self.stats["success"] += 1
                        await self.save_position(detail_data)
                        self.positions.append(detail_data)
                    else:
                        self.stats["failed"] += 1
                        logger.error(f"抓取详情失败: {pos_info['title']}")
                    
                    # 避免请求过快
                    await asyncio.sleep(0.5)
                    
                except Exception as e:
                    self.stats["failed"] += 1
                    logger.error(f"处理岗位异常 {pos_info['title']}: {e}")
            
            logger.info(f"第 {page_num} 页新增 {new_positions_count} 个岗位")
            return new_positions_count
            
        except Exception as e:
            logger.error(f"抓取第 {page_num} 页失败: {e}")
            return 0
    
    async def run(self):
        """主运行方法 - 保持列表页Tab，每个详情页在新Tab中打开"""
        self.stats["start_time"] = time.time()
        self._init_output_file()
        
        logger.info("="*50)
        logger.info("开始抓取得物校招岗位信息")
        logger.info("="*50)
        
        async with async_playwright() as p:
            # 启动浏览器（有头模式便于观察，可改为 headless=True）
            browser = await p.chromium.launch(headless=False)
            context = await browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            
            # 创建列表页Tab
            list_page = await context.new_page()
            
            try:
                # 访问列表页
                logger.info(f"访问列表页: {self.list_url}")
                await list_page.goto(self.list_url, wait_until="networkidle")
                await list_page.wait_for_timeout(3000)
                
                current_page = 1
                consecutive_empty = 0
                
                while current_page <= self.max_pages and consecutive_empty < 2:
                    # 抓取当前页的所有岗位（每个在新Tab中打开）
                    count = await self.crawl_page_positions(context, list_page, current_page)
                    
                    if count == 0:
                        consecutive_empty += 1
                    else:
                        consecutive_empty = 0
                    
                    # 尝试点击下一页
                    try:
                        # 查找下一页按钮
                        next_li = await list_page.query_selector("li.atsx-pagination-next")
                        
                        if not next_li:
                            logger.info("没有找到下一页按钮元素")
                            break
                        
                        # 检查是否禁用
                        is_disabled = await next_li.get_attribute("class")
                        if is_disabled and "atsx-pagination-disabled" in is_disabled:
                            logger.info("下一页按钮是禁用状态，已到达最后一页")
                            break
                        
                        aria_disabled = await next_li.get_attribute("aria-disabled")
                        if aria_disabled == "true":
                            logger.info("下一页按钮 aria-disabled=true，已到达最后一页")
                            break
                        
                        logger.info(f"点击下一页按钮，从第 {current_page} 页跳转...")
                        
                        # 点击按钮
                        next_link = await next_li.query_selector("a.atsx-pagination-item-link")
                        if next_link:
                            await next_link.click()
                        else:
                            await next_li.click()
                        
                        # 等待页面更新
                        await list_page.wait_for_timeout(2000)
                        
                        # 等待新内容加载
                        try:
                            await list_page.wait_for_selector(".listItems__fca8c0 a[data-id]", timeout=10000)
                        except:
                            logger.warning("等待新列表内容超时")
                        
                        await list_page.wait_for_timeout(1000)
                        
                        current_page += 1
                        logger.info(f"成功跳转到第 {current_page} 页")
                        
                    except Exception as e:
                        logger.error(f"点击下一页失败: {e}")
                        break
                
                logger.info(f"抓取完成，共处理 {current_page} 页")
                
            except Exception as e:
                logger.error(f"抓取过程发生错误: {e}")
                import traceback
                logger.error(traceback.format_exc())
                await list_page.screenshot(path="error_screenshot.png")
                logger.info("已保存错误截图: error_screenshot.png")
            finally:
                await browser.close()
        
        self.stats["end_time"] = time.time()
        self._print_summary()
    
    def _print_summary(self):
        """打印抓取总结"""
        duration = self.stats["end_time"] - self.stats["start_time"]
        
        logger.info("="*50)
        logger.info("抓取完成统计")
        logger.info("="*50)
        logger.info(f"总计发现岗位: {self.stats['total_found']}")
        logger.info(f"成功抓取: {self.stats['success']}")
        logger.info(f"失败: {self.stats['failed']}")
        logger.info(f"总耗时: {duration:.2f} 秒")
        logger.info(f"输出文件: {self.output_file}")
        logger.info("="*50)

async def main():
    """主函数"""
    scraper = DeWuCampusScraper()
    await scraper.run()

if __name__ == "__main__":
    asyncio.run(main())