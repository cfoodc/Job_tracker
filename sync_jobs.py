#!/usr/bin/env python3
"""
Anduril 台北/東京職缺自動同步腳本
自動抓取 Anduril 職缺頁面並更新到 Notion 資料庫
"""

import os
import re
import json
import requests
from datetime import datetime
from bs4 import BeautifulSoup
from notion_client import Client

# 設定
GREENHOUSE_API_BASE = "https://boards-api.greenhouse.io/v1/boards/andurilindustries/jobs"

# 要追蹤的地點關鍵字（不區分大小寫）
TARGET_LOCATIONS = {
    "taipei": "Taipei Taiwan",
    "taiwan": "Taipei Taiwan",
    "tokyo": "Tokyo Japan",
    "japan": "Tokyo Japan",
}

# 從環境變數讀取
NOTION_API_KEY = os.environ.get("NOTION_API_KEY")
NOTION_DATABASE_ID = os.environ.get("NOTION_DATABASE_ID")


def get_jobs_from_greenhouse():
    """從 Greenhouse API 獲取職缺列表（優化流量版本）"""
    jobs = []

    try:
        # 步驟 1: 先獲取職缺列表（不含詳細內容）- 節省流量
        print("📋 正在獲取職缺列表...")
        response = requests.get(GREENHOUSE_API_BASE)
        response.raise_for_status()
        data = response.json()
        
        all_jobs = data.get("jobs", [])
        print(f"📊 API 回傳 {len(all_jobs)} 個職缺")

        # 步驟 2: 篩選出目標地區的職缺
        target_job_ids = []
        target_job_basic = []
        
        for job in all_jobs:
            location = job.get("location", {}).get("name", "")
            location_lower = location.lower()
            
            # 檢查是否匹配任何目標地點
            if any(keyword in location_lower for keyword in TARGET_LOCATIONS.keys()):
                target_job_ids.append(job.get("id"))
                target_job_basic.append(job)
        
        print(f"🎯 找到 {len(target_job_ids)} 個目標地區職缺")

        # 步驟 3: 只獲取目標職缺的詳細內容
        for i, job_id in enumerate(target_job_ids, 1):
            try:
                print(f"  📥 正在獲取職缺 {i}/{len(target_job_ids)} 的詳細內容...")
                detail_response = requests.get(f"{GREENHOUSE_API_BASE}/{job_id}")
                detail_response.raise_for_status()
                job_detail = detail_response.json()
                
                # 取得基本資訊
                basic_info = target_job_basic[i-1]
                location = basic_info.get("location", {}).get("name", "")
                
                # 解析職缺內容
                content = job_detail.get("content", "")
                soup = BeautifulSoup(content, "html.parser")

                # 提取各區段
                about_job = extract_section(soup, ["about the job", "about the team"])
                what_youll_do = extract_section(soup, ["what you'll do", "what you will do"])
                required_quals = extract_section(soup, ["required qualifications", "requirements"])
                preferred_quals = extract_section(soup, ["preferred qualifications", "nice to have"])

                # 提取經驗要求
                experience = extract_experience(required_quals)

                # 提取部門
                departments = job_detail.get("departments", [])
                department = departments[0].get("name", "Unknown") if departments else "Unknown"

                jobs.append({
                    "id": str(job_detail.get("id", "")),
                    "title": job_detail.get("title", ""),
                    "location": location,
                    "department": department,
                    "apply_url": job_detail.get("absolute_url", ""),
                    "experience": experience,
                    "about_job": about_job,
                    "what_youll_do": what_youll_do,
                    "required_qualifications": required_quals,
                    "preferred_qualifications": preferred_quals,
                    "updated_at": job_detail.get("updated_at", ""),
                })
                
            except Exception as e:
                print(f"  ⚠️ 獲取職缺 {job_id} 詳細內容失敗: {e}")
                continue

        print(f"✅ 成功獲取 {len(jobs)} 個職缺（台北/東京）")
        return jobs

    except Exception as e:
        print(f"❌ 獲取職缺失敗: {e}")
        return []


def extract_section(soup, keywords):
    """從 HTML 中提取特定區段"""
    text = soup.get_text()

    for keyword in keywords:
        pattern = rf"{keyword}[:\s]*(.*?)(?=(?:what you|required|preferred|about|$))"
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if match:
            return match.group(1).strip()[:2000]  # 限制長度

    return ""


def extract_experience(text):
    """從文字中提取經驗年數要求"""
    if not text:
        return "未指定"

    # 尋找 X+ years 格式
    match = re.search(r"(\d+)\+?\s*years?", text, re.IGNORECASE)
    if match:
        return f"{match.group(1)}+ years"

    return "未指定"


def get_existing_jobs_from_notion(notion, database_id):
    """獲取 Notion 資料庫中現有的職缺"""
    existing = {}

    try:
        results = notion.databases.query(database_id=database_id)

        for page in results.get("results", []):
            props = page.get("properties", {})

            # 獲取 REQ ID 作為唯一識別符
            req_id_prop = props.get("REQ ID", {})
            rich_text = req_id_prop.get("rich_text", [])
            if rich_text and len(rich_text) > 0:
                req_id = rich_text[0].get("text", {}).get("content", "")
                if req_id:
                    existing[req_id] = {
                        "page_id": page["id"],
                        "properties": props
                    }

        print(f"📋 Notion 中現有 {len(existing)} 個職缺")
        return existing

    except Exception as e:
        print(f"❌ 獲取 Notion 資料失敗: {e}")
        return {}


def create_job_page(notion, database_id, job):
    """在 Notion 建立新職缺頁面"""

    # 準備屬性
    properties = {
        "職位名稱": {"title": [{"text": {"content": job["title"]}}]},
        "部門": {"select": {"name": normalize_department(job["department"])}},
        "地點": {"select": {"name": normalize_location(job["location"])}},
        "REQ ID": {"rich_text": [{"text": {"content": job["id"]}}]},
        "經驗要求": {"rich_text": [{"text": {"content": job["experience"]}}]},
        "申請連結": {"url": job["apply_url"]},
        "職缺描述摘要": {"rich_text": [{"text": {"content": job["about_job"][:2000] if job["about_job"] else ""}}]},
        "申請狀態": {"select": {"name": "尚未申請"}},
        "新增日期": {"date": {"start": datetime.now().strftime("%Y-%m-%d")}},
    }

    # 建立頁面內容
    content = build_page_content(job)

    try:
        # 建立頁面
        page = notion.pages.create(
            parent={"database_id": database_id},
            properties=properties,
            children=content
        )
        print(f"  ✅ 新增: {job['title']}")
        return page

    except Exception as e:
        print(f"  ❌ 新增失敗 {job['title']}: {e}")
        return None


def update_job_page(notion, page_id, job):
    """更新現有職缺頁面"""

    content = build_page_content(job)

    try:
        # 更新頁面內容
        # 先刪除現有內容
        existing_blocks = notion.blocks.children.list(block_id=page_id)
        for block in existing_blocks.get("results", []):
            notion.blocks.delete(block_id=block["id"])

        # 加入新內容
        notion.blocks.children.append(block_id=page_id, children=content)
        print(f"  🔄 更新: {job['title']}")

    except Exception as e:
        print(f"  ❌ 更新失敗 {job['title']}: {e}")


def build_page_content(job):
    """建立 Notion 頁面內容區塊"""
    blocks = []

    # About the Job
    if job.get("about_job"):
        blocks.append({"heading_1": {"rich_text": [{"text": {"content": "About the Job"}}]}})
        blocks.append({"paragraph": {"rich_text": [{"text": {"content": job["about_job"][:2000]}}]}})

    # What You'll Do
    if job.get("what_youll_do"):
        blocks.append({"heading_1": {"rich_text": [{"text": {"content": "What You'll Do"}}]}})
        blocks.append({"paragraph": {"rich_text": [{"text": {"content": job["what_youll_do"][:2000]}}]}})

    # Required Qualifications
    if job.get("required_qualifications"):
        blocks.append({"heading_1": {"rich_text": [{"text": {"content": "Required Qualifications"}}]}})
        blocks.append({"paragraph": {"rich_text": [{"text": {"content": job["required_qualifications"][:2000]}}]}})

    # Preferred Qualifications
    if job.get("preferred_qualifications"):
        blocks.append({"heading_1": {"rich_text": [{"text": {"content": "Preferred Qualifications"}}]}})
        blocks.append({"paragraph": {"rich_text": [{"text": {"content": job["preferred_qualifications"][:2000]}}]}})

    # 最後更新時間
    blocks.append({"divider": {}})
    blocks.append({
        "paragraph": {
            "rich_text": [{"text": {"content": f"🔄 最後同步: {datetime.now().strftime('%Y-%m-%d %H:%M')}"}}],
            "color": "gray"
        }
    })

    return blocks


def normalize_department(dept):
    """標準化部門名稱"""
    dept_lower = dept.lower()

    if "test" in dept_lower or "electrical" in dept_lower:
        return "Electrical Test Engineering"
    elif "business" in dept_lower or "bd" in dept_lower:
        return "Business Development"
    else:
        return dept[:100]  # Notion 限制


def normalize_location(location):
    """標準化地點名稱"""
    location_lower = location.lower()
    
    # 根據關鍵字映射到標準地點名稱
    for keyword, standard_name in TARGET_LOCATIONS.items():
        if keyword in location_lower:
            return standard_name
    
    # 如果沒有匹配，返回原始地點（截斷）
    return location[:100]  # Notion 限制


def mark_removed_jobs(notion, existing_jobs, current_job_ids):
    """標記已移除的職缺"""
    for req_id, data in existing_jobs.items():
        if req_id not in current_job_ids:
            try:
                # 更新備註欄位
                notion.pages.update(
                    page_id=data["page_id"],
                    properties={
                        "備註": {"rich_text": [{"text": {"content": f"⚠️ 職缺可能已關閉 ({datetime.now().strftime('%Y-%m-%d')})"}}]}
                    }
                )
                print(f"  ⚠️ 標記已關閉: REQ ID {req_id}")
            except Exception as e:
                print(f"  ❌ 標記失敗: {e}")


def main():
    """主程式"""
    print("=" * 50)
    print("🚀 Anduril 台北/東京職缺同步開始")
    print(f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)

    # 驗證環境變數
    if not NOTION_API_KEY:
        print("❌ 錯誤: 請設定 NOTION_API_KEY 環境變數")
        return 1

    if not NOTION_DATABASE_ID:
        print("❌ 錯誤: 請設定 NOTION_DATABASE_ID 環境變數")
        return 1

    # 初始化 Notion client
    notion = Client(auth=NOTION_API_KEY)

    # 獲取最新職缺
    jobs = get_jobs_from_greenhouse()
    if not jobs:
        print("⚠️ 沒有找到台北/東京職缺，嘗試備用方法...")
        # 可以加入備用抓取方法

    # 獲取現有 Notion 資料
    existing_jobs = get_existing_jobs_from_notion(notion, NOTION_DATABASE_ID)

    # 同步職缺
    current_req_ids = set()
    for job in jobs:
        req_id = job["id"]
        current_req_ids.add(req_id)

        if req_id in existing_jobs:
            # 更新現有職缺
            update_job_page(notion, existing_jobs[req_id]["page_id"], job)
        else:
            # 新增職缺
            create_job_page(notion, NOTION_DATABASE_ID, job)

    # 標記已移除的職缺
    mark_removed_jobs(notion, existing_jobs, current_req_ids)

    print("=" * 50)
    print("✅ 同步完成!")
    print("=" * 50)

    return 0


if __name__ == "__main__":
    exit(main())
