#!/usr/bin/env python3
"""
Anduril 台北/東京職缺自動同步腳本
自動抓取 Anduril 職缺頁面並更新到 Notion 資料庫
"""

import os
import re
import time
import requests
from datetime import datetime
from curl_notion_client import CurlNotionClient
from dotenv import load_dotenv

# 載入 .env 文件（優先從 test 資料夾載入，如果不存在則從根目錄載入）
if os.path.exists("test/.env"):
    load_dotenv("test/.env")
else:
    load_dotenv()

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



# 重試設定
MAX_RETRIES = 3
RETRY_DELAY = 2  # 秒（增加到 10 秒）
REQUEST_DELAY = 1  # 每個請求之間的延遲（增加到 3 秒）


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
                
                # 簡化版：不解析內文，只提取基本經驗要求
                # 從職缺標題或基本資訊中推斷經驗（如果有的話）
                title = job_detail.get("title", "")
                experience = extract_experience_from_title(title)

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


def extract_experience_from_title(title):
    """從職缺標題中提取經驗年數要求"""
    if not title:
        return "未指定"

    # 尋找常見的經驗層級關鍵字
    title_lower = title.lower()

    if "staff" in title_lower or "principal" in title_lower:
        return "10+ years"
    elif "senior" in title_lower or "sr" in title_lower:
        return "5+ years"
    elif "junior" in title_lower or "jr" in title_lower:
        return "0-2 years"
    elif "intern" in title_lower:
        return "學生/實習"

    # 嘗試從標題中直接提取數字
    match = re.search(r"(\d+)\+?\s*years?", title, re.IGNORECASE)
    if match:
        return f"{match.group(1)}+ years"

    return "未指定"


def get_existing_jobs_from_notion(notion, database_id):
    """獲取 Notion 資料庫中現有的職缺（含重試）"""
    existing = {}

    for attempt in range(MAX_RETRIES):
        try:
            # 使用 curl 客戶端查詢數據庫
            results = notion.databases_query(database_id)

            for page in results.get("results", []):
                props = page.get("properties", {})

                # 獲取 REQ ID 作為唯一識別符
                req_id_prop = props.get("REQ ID", {})
                rich_text = req_id_prop.get("rich_text", [])
                if rich_text and len(rich_text) > 0:
                    req_id = rich_text[0].get("text", {}).get("content", "")
                    if req_id:
                        # 提取標題
                        title_prop = props.get("職位名稱", {})
                        title_text = title_prop.get("title", [])
                        title = title_text[0].get("text", {}).get("content", "") if title_text else ""
                        
                        # 提取更新時間（從頁面的 last_edited_time）
                        updated_at = page.get("last_edited_time", "")
                        
                        existing[req_id] = {
                            "page_id": page["id"],
                            "properties": props,
                            "title": title,
                            "updated_at": updated_at
                        }

            print(f"📋 Notion 中現有 {len(existing)} 個職缺")
            return existing

        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                print(f"⚠️ 獲取 Notion 資料失敗 (嘗試 {attempt + 1}/{MAX_RETRIES}): {e}")
                print(f"   等待 {RETRY_DELAY} 秒後重試...")
                time.sleep(RETRY_DELAY)
            else:
                print(f"❌ 獲取 Notion 資料失敗（已達最大重試次數）: {e}")
                return {}


def create_job_page(notion, database_id, job):
    """在 Notion 建立新職缺頁面（簡化版：只建立屬性，不添加內容）"""

    # 清理並準備屬性
    def clean_text(text, max_len=None):
        """清理文本，移除可能導致問題的字符"""
        if not text:
            return ""
        # 移除控制字符和零寬字符
        text = ''.join(char for char in text if ord(char) >= 32 or char in '\n\r\t')
        if max_len:
            text = text[:max_len]
        return text

    properties = {
        "職位名稱": {
            "title": [
                {
                    "text": {
                        "content": clean_text(job["title"], 100)
                    }
                }
            ]
        },
        "部門": {
            "select": {
                "name": clean_text(normalize_department(job["department"]), 100)
            }
        },
        "地點": {
            "select": {
                "name": clean_text(normalize_location(job["location"]), 100)
            }
        },
        "REQ ID": {
            "rich_text": [
                {
                    "text": {
                        "content": clean_text(job["id"], 100)
                    }
                }
            ]
        },
        "經驗要求": {
            "rich_text": [
                {
                    "text": {
                        "content": clean_text(job["experience"], 100)
                    }
                }
            ]
        },
        "申請狀態": {
            "select": {
                "name": "尚未申請"
            }
        },
        "新增日期": {
            "date": {
                "start": datetime.now().strftime("%Y-%m-%d")
            }
        },
    }

    # URL 字段單獨處理，確保有效
    if job.get("apply_url") and job["apply_url"].startswith("http"):
        properties["申請連結"] = {"url": job["apply_url"]}
    else:
        # 如果 URL 無效，使用預設 URL
        properties["申請連結"] = {"url": "https://www.anduril.com"}

    for attempt in range(MAX_RETRIES):
        try:
            # 在每次嘗試前加入延遲（除了第一次）
            if attempt > 0:
                print(f"     等待 {RETRY_DELAY} 秒後重試...")
                time.sleep(RETRY_DELAY)

            # 創建頁面（只有屬性，不帶內容）
            page = notion.pages_create(
                parent={"database_id": database_id},
                properties=properties
            )

            print(f"  ✅ 新增: {job['title']}")
            time.sleep(REQUEST_DELAY)
            return page

        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                print(f"  ⚠️ 新增失敗 {job['title']} (嘗試 {attempt + 1}/{MAX_RETRIES}): {e}")
            else:
                print(f"  ❌ 新增失敗 {job['title']}（已達最大重試次數）: {e}")
                return None


def update_job_page(notion, page_id, job):
    """更新現有職缺頁面（簡化版：只更新屬性，不更新內容）"""

    for attempt in range(MAX_RETRIES):
        try:
            # 只更新基本屬性（標題、部門、地點等可能不會改變，這裡可選擇性更新）
            # 主要更新可能變化的欄位
            properties = {}

            # 如果需要更新特定欄位，可以在這裡添加
            # 例如：更新申請狀態或其他欄位

            # 如果有需要更新的屬性，才執行更新
            if properties:
                notion.pages_update(
                    page_id=page_id,
                    properties=properties
                )

            print(f"  🔄 更新: {job['title']}")
            return

        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                print(f"  ⚠️ 更新失敗 {job['title']} (嘗試 {attempt + 1}/{MAX_RETRIES}): {e}")
                print(f"     等待 {RETRY_DELAY} 秒後重試...")
                time.sleep(RETRY_DELAY)
            else:
                print(f"  ❌ 更新失敗 {job['title']}（已達最大重試次數）: {e}")


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
                notion.pages_update(
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

    # 清理並驗證 API key 格式
    api_key = NOTION_API_KEY.strip()
    if api_key.startswith('b"') or api_key.startswith("b'"):
        print("❌ 錯誤: NOTION_API_KEY 格式不正確，請確認是字串格式而非 bytes")
        return 1

    if not api_key.startswith('secret_') and not api_key.startswith('ntn_'):
        print("⚠️ 警告: NOTION_API_KEY 格式可能不正確，正常格式應以 'secret_' 或 'ntn_' 開頭")

    # 初始化 Notion client（使用 curl 後端）
    try:
        # 使用 curl 客戶端來繞過 Python SSL 問題
        notion = CurlNotionClient(auth=api_key)
        print("✅ Notion client 初始化成功 (使用 curl 後端)")
    except Exception as e:
        print(f"❌ 初始化 Notion client 失敗: {e}")
        return 1

    # 獲取最新職缺
    jobs = get_jobs_from_greenhouse()
    if not jobs:
        print("⚠️ 沒有找到台北/東京職缺")
        return 1

    # 獲取現有 Notion 資料
    existing_jobs = get_existing_jobs_from_notion(notion, NOTION_DATABASE_ID)

    # 在查詢後等待一下再開始新增/更新操作
    print("\n⏳ 等待 1 秒後開始同步...")
    time.sleep(1)

    # 同步職缺
    current_req_ids = set()
    for job in jobs:
        req_id = job["id"]
        current_req_ids.add(req_id)

        if req_id in existing_jobs:
            # 檢查是否需要更新
            existing_title = existing_jobs[req_id].get("title", "")
            existing_updated = existing_jobs[req_id].get("updated_at", "")

            if (job["title"] != existing_title or
                job.get("updated_at", "") != existing_updated):
                # 內容有變化，更新頁面
                update_job_page(notion, existing_jobs[req_id]["page_id"], job)
            else:
                print(f"  ⏭️  跳過（無變化）: {job['title']}")
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
