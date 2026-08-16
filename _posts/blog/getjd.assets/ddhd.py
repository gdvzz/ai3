import asyncio
import json
import time
from playwright.async_api import async_playwright


async def fetch_job_data():
    """
    使用Playwright抓取点点互动校招岗位信息
    """
    start_time = time.time()
    all_jobs = []
    error_count = 0
    request_count = 0
    total_jobs = 0
    page_size = 100  # 一次请求获取较多数据，减少请求次数

    async with async_playwright() as p:
        # 启动浏览器（无头模式）
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        # 监听请求和响应，便于调试
        async def handle_response(response):
            if "/api/Jobad/GetJobAdPageList" in response.url:
                try:
                    print(f"[调试] 收到API响应，状态码: {response.status}")
                except Exception:
                    pass

        page.on("response", handle_response)

        try:
            # 1. 首次请求，获取岗位总数
            print("[信息] 正在请求岗位列表API，获取总岗位数...")
            request_payload = {
                "PageIndex": 0,
                "PageSize": page_size,
                "Category": ["2"],
                "Channel4IsAllowExternalRecommend": True,
                "KeyWords": "",
                "SpecialType": 0,
                "PortalId": "",
                "DisplayFields": [
                    "Category",
                    "Kind",
                    "LocId",
                    "PostDate",
                    "Degree",
                    "ClassificationOne",
                    "WorkWeChatQrCode",
                ],
            }

            # 使用API routes来拦截并修改请求，或者直接使用fetch
            # 这里使用page.request.post来发送请求
            response = await page.request.post(
                "https://ddhd.cn/api/Jobad/GetJobAdPageList",
                data=request_payload,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json, text/plain, */*",
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
                },
            )

            if not response.ok:
                print(f"[错误] API请求失败，状态码: {response.status}")
                return

            data = await response.json()
            request_count += 1

            if data.get("Code") != 200:
                print(f"[错误] API返回错误: {data.get('Message')}")
                return

            total_jobs = data.get("Count", 0)
            print(f"[信息] 检测到岗位总数: {total_jobs}")

            if total_jobs == 0:
                print("[信息] 没有找到任何岗位。")
                return

            # 计算需要请求的页数
            total_pages = (total_jobs + page_size - 1) // page_size
            print(f"[信息] 共需请求 {total_pages} 页数据")

            # 2. 循环请求所有页面
            for page_index in range(total_pages):
                print(f"[信息] 正在请求第 {page_index + 1}/{total_pages} 页数据...")
                current_payload = request_payload.copy()
                current_payload["PageIndex"] = page_index

                response = await page.request.post(
                    "https://ddhd.cn/api/Jobad/GetJobAdPageList",
                    data=current_payload,
                    headers={
                        "Content-Type": "application/json",
                        "Accept": "application/json, text/plain, */*",
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
                    },
                )

                if not response.ok:
                    print(
                        f"[错误] 第 {page_index + 1} 页请求失败，状态码: {response.status}"
                    )
                    error_count += 1
                    continue

                page_data = await response.json()
                request_count += 1

                if page_data.get("Code") != 200:
                    print(
                        f"[错误] 第 {page_index + 1} 页API返回错误: {page_data.get('Message')}"
                    )
                    error_count += 1
                    continue

                jobs_on_page = page_data.get("Data", [])
                print(f"[信息] 第 {page_index + 1} 页获取到 {len(jobs_on_page)} 个岗位")

                # 处理本页的每个岗位
                for job in jobs_on_page:
                    # 提取正确的岗位唯一标识符 (Id)
                    job_uuid = job.get("Id")
                    if not job_uuid:
                        error_count += 1
                        continue

                    # 构建正确的岗位详情页链接（使用Id字段）
                    detail_url = f"https://ddhd.cn/campus/detail?jobAdId={job_uuid}"

                    # 提取关键信息
                    job_info = {
                        "job_uuid": job_uuid,  # 用于详情页链接的正确ID
                        "job_ad_id": job.get("JobAdId", ""),  # 原数字ID，作为参考
                        "job_name": job.get("JobAdName", ""),
                        "category": job.get("Category", ""),
                        "category_id": job.get("CategoryId", ""),
                        "location": job.get("LocNames", []),
                        "classification": job.get("ClassificationOne", ""),
                        "kind": job.get("Kind", ""),
                        "post_date": job.get("PostDate", ""),
                        "duty": job.get("Duty", ""),
                        "require": job.get("Require", ""),
                        "detail_url": detail_url,  # 修正后的链接
                    }

                    # 记录调试信息
                    duty_len = len(job_info["duty"])
                    require_len = len(job_info["require"])
                    print(
                        f"  [调试] 岗位: {job_info['job_name']}, 职责字数: {duty_len}, 要求字数: {require_len}"
                    )

                    all_jobs.append(job_info)

                    # 每抓取到一个岗位，就追加保存到文件
                    save_to_json(job_info, mode="a")  # 使用追加模式

                # 避免请求过快，适当休眠
                await asyncio.sleep(0.5)

            # 3. 全部抓取完成，输出汇总信息
            end_time = time.time()
            elapsed_time = end_time - start_time

            print("\n" + "=" * 50)
            print("[汇总] 抓取任务完成!")
            print(f"[汇总] 总耗时: {elapsed_time:.2f} 秒")
            print(f"[汇总] API请求次数: {request_count}")
            print(f"[汇总] 检测到岗位总数: {total_jobs}")
            print(f"[汇总] 成功抓取岗位数: {len(all_jobs)}")
            print(f"[汇总] 错误/失败次数: {error_count}")
            print("=" * 50)

        except Exception as e:
            print(f"[异常] 程序运行出错: {e}")
        finally:
            await browser.close()


def save_to_json(job_data, filename="century_games_jobs.json", mode="w"):
    """
    将单个岗位数据保存到JSON文件。
    首次写入使用'w'模式，后续追加使用'a'模式。
    """
    try:
        # 当mode为'a'时，需要读取现有数据，追加新数据后重新写入
        if mode == "a":
            try:
                with open(filename, "r", encoding="utf-8") as f:
                    existing_data = json.load(f)
                    if not isinstance(existing_data, list):
                        existing_data = []
            except (FileNotFoundError, json.JSONDecodeError):
                existing_data = []

            existing_data.append(job_data)
            with open(filename, "w", encoding="utf-8") as f:
                json.dump(existing_data, f, ensure_ascii=False, indent=2)
        else:
            # 'w'模式，直接写入一个包含当前岗位的列表
            with open(filename, "w", encoding="utf-8") as f:
                json.dump([job_data], f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[错误] 保存文件时出错: {e}")


# 运行主函数
if __name__ == "__main__":
    asyncio.run(fetch_job_data())
