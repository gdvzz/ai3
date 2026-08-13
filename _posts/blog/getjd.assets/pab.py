import asyncio
import json
from playwright.async_api import async_playwright

OUTPUT_FILE = "pingan_campus_jobs.json"

async def main():
    print(f"程序开始运行，输出文件: {OUTPUT_FILE}")
    print("=" * 60)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)  # 可改为True无头运行
        page = await browser.new_page(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36"
        )

        # 存储所有岗位
        all_jobs = []
        seen_ids = set()
        total_pages = None
        current_page = 0

        # 监听API响应
        async def handle_response(response):
            nonlocal total_pages, current_page, all_jobs, seen_ids
            url = response.url
            # 只处理岗位搜索API
            if "positionSearch/queryPositionPage" in url and response.status == 200:
                try:
                    data = await response.json()
                    if data.get("responseCode") != "10001":
                        return
                    page_data = data.get("data", {})
                    total_pages = page_data.get("totalPage", 1)
                    current_page = page_data.get("pageNo", 0)
                    job_list = page_data.get("list", [])
                    print(f"  📥 捕获API响应: 第{current_page}页，{len(job_list)}个岗位")

                    for item in job_list:
                        pid = item.get("idPosition")
                        if not pid or pid in seen_ids:
                            continue
                        seen_ids.add(pid)
                        job = {
                            "id": pid,
                            "title": item.get("positionName", ""),
                            "company": item.get("businessUnitName", ""),
                            "category": item.get("positionCategoryName", ""),
                            "dept_name": item.get("deptName", ""),
                            "dept_show_name": item.get("deptShowName", ""),
                            "location": item.get("workCity", ""),
                            "interview_city": item.get("interviewCity", ""),
                            "recruit_number": item.get("recruitNumber", 0),
                            "description": item.get("duty", ""),
                            "requirement": item.get("qualification", ""),
                            "detail_url": f"https://campus.pingan.com/pab/positionDetail?positionId={pid}",
                        }
                        all_jobs.append(job)
                        print(f"    ✅ {job['title']} (ID: {pid[:8]}...)")
                except Exception as e:
                    print(f"  处理API响应时出错: {e}")

        page.on("response", handle_response)

        # 访问列表页
        print("正在访问页面...")
        await page.goto("https://campus.pingan.com/pab/position", wait_until="networkidle")
        await asyncio.sleep(3)  # 等待初始API加载

        # 如果第一页数据已捕获，开始翻页
        if total_pages is None:
            print("未捕获到初始API响应，尝试等待...")
            await asyncio.sleep(5)

        # 翻页循环
        while True:
            if total_pages is not None and current_page >= total_pages:
                break

            # 查找下一页按钮
            next_btn = await page.query_selector("button.btn-next")
            if not next_btn:
                print("未找到下一页按钮，停止翻页")
                break

            disabled = await next_btn.get_attribute("disabled")
            if disabled:
                print("下一页按钮已禁用，停止翻页")
                break

            print(f"点击翻到第 {current_page + 1} 页...")
            # 点击前记录当前已捕获的页数，等待新数据
            prev_count = len(seen_ids)
            await next_btn.click()
            # 等待新数据到达（最多等待10秒）
            for _ in range(20):
                await asyncio.sleep(0.5)
                if len(seen_ids) > prev_count:
                    break
            else:
                print("等待新数据超时，可能已到最后一页")
                break

            await asyncio.sleep(1)  # 稳定间隔

        await browser.close()

    # 保存结果
    if all_jobs:
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(all_jobs, f, ensure_ascii=False, indent=2)
        print(f"\n✅ 抓取完成！共 {len(all_jobs)} 个岗位，已保存至 {OUTPUT_FILE}")
    else:
        print("\n⚠️ 未抓取到任何数据，请检查网络或页面是否正常加载")

if __name__ == "__main__":
    asyncio.run(main())