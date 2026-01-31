#!/usr/bin/env python3
"""
使用 curl 作為後端的 Notion API 包裝器
繞過 Python SSL 問題
"""

import os
import json
import subprocess
import time
from datetime import datetime

NOTION_API_BASE = "https://api.notion.com/v1"

class CurlNotionClient:
    """使用 curl 的 Notion 客戶端"""
    
    def __init__(self, auth):
        self.auth = auth
        self.headers = {
            "Authorization": f"Bearer {auth}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json",
            "Connection": "close"
        }
    
    def _curl_request(self, method, path, data=None, max_retries=5):
        """使用 curl 發送請求"""
        url = f"{NOTION_API_BASE}{path}"
        
        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    wait_time = 2 ** attempt
                    print(f"   等待 {wait_time} 秒後重試...")
                    time.sleep(wait_time)
                
                # 構建 curl 命令
                cmd = [
                    "curl", "-X", method,
                    "--http1.1",
                    "--max-time", "60",  # 增加到 60 秒
                    "--connect-timeout", "30",  # 連接超時 30 秒
                    "--tcp-nodelay",  # 禁用 Nagle 算法
                    "--keepalive-time", "60"  # Keep-alive 超時
                ]
                
                # 在重試時添加 verbose 模式來診斷
                if attempt > 0:
                    cmd.append("-v")
                else:
                    cmd.append("-s")
                
                # 添加 headers
                for key, value in self.headers.items():
                    cmd.extend(["-H", f"{key}: {value}"])
                
                # 添加 data
                if data:
                    json_data = json.dumps(data, ensure_ascii=False)
                    cmd.extend(["-d", json_data])
                
                # 添加 URL
                cmd.append(url)
                
                # 調試：打印命令（隱藏敏感信息）
                if attempt == 0:
                    debug_cmd = [c if "Bearer" not in str(c) else "[HIDDEN]" for c in cmd]
                    print(f"   執行 curl: {' '.join(debug_cmd[:8])}... {url}")
                    if data:
                        # 打印數據大小
                        json_size = len(json.dumps(data, ensure_ascii=False))
                        print(f"   數據大小: {json_size} bytes")
                        if json_size > 10000:
                            print(f"   ⚠️ 警告：數據較大可能導致問題")
                
                # 執行命令
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=65  # 增加到 65 秒
                )
                
                if result.returncode == 0:
                    try:
                        response = json.loads(result.stdout)
                    except json.JSONDecodeError as e:
                        raise Exception(f"JSON 解析失敗: {result.stdout[:200]}")
                    
                    # 檢查是否有錯誤
                    if "object" in response and response["object"] == "error":
                        raise Exception(f"API Error: {response.get('message', 'Unknown error')}")
                    
                    return response
                else:
                    # 獲取更詳細的錯誤信息
                    error_msg = result.stderr if result.stderr else "無錯誤信息"
                    stdout_msg = result.stdout[:200] if result.stdout else ""
                    full_error = f"stdout: {stdout_msg}, stderr: {error_msg[:200]}"
                    raise Exception(f"curl 返回碼 {result.returncode}: {full_error}")
                    
            except subprocess.TimeoutExpired:
                if attempt < max_retries - 1:
                    print(f"   ⚠️ 請求超時 (嘗試 {attempt + 1}/{max_retries})")
                else:
                    raise Exception("請求超時")
            except Exception as e:
                if attempt < max_retries - 1:
                    print(f"   ⚠️ 請求失敗 (嘗試 {attempt + 1}/{max_retries}): {e}")
                else:
                    raise
        
        raise Exception("所有重試都失敗")
    
    def users_me(self):
        """獲取當前用戶信息"""
        return self._curl_request("GET", "/users/me")
    
    def databases_query(self, database_id):
        """查詢數據庫"""
        return self._curl_request("POST", f"/databases/{database_id}/query", data={})
    
    def databases_retrieve(self, database_id):
        """獲取數據庫信息"""
        return self._curl_request("GET", f"/databases/{database_id}")
    
    def pages_create(self, parent, properties, children=None):
        """創建頁面"""
        data = {
            "parent": parent,
            "properties": properties
        }
        if children:
            data["children"] = children
        
        return self._curl_request("POST", "/pages", data=data)
    
    def pages_update(self, page_id, properties):
        """更新頁面屬性"""
        data = {"properties": properties}
        return self._curl_request("PATCH", f"/pages/{page_id}", data=data)
    
    def blocks_children_list(self, block_id):
        """列出子區塊"""
        return self._curl_request("GET", f"/blocks/{block_id}/children")
    
    def blocks_delete(self, block_id):
        """刪除區塊"""
        return self._curl_request("DELETE", f"/blocks/{block_id}")
    
    def blocks_children_append(self, block_id, children):
        """添加子區塊"""
        data = {"children": children}
        return self._curl_request("PATCH", f"/blocks/{block_id}/children", data=data)


def test_curl_client():
    """測試 curl 客戶端"""
    print("=" * 60)
    print("🧪 測試 curl 客戶端")
    print("=" * 60)
    
    api_key = os.environ.get("NOTION_API_KEY")
    database_id = os.environ.get("NOTION_DATABASE_ID")
    
    if not api_key or not database_id:
        print("❌ 請設定 NOTION_API_KEY 和 NOTION_DATABASE_ID")
        return False
    
    try:
        client = CurlNotionClient(auth=api_key)
        
        # 測試 1: 獲取用戶信息
        print("\n1. 測試獲取用戶信息...")
        me = client.users_me()
        print(f"✅ 成功獲取用戶信息")
        print(f"   Bot 名稱: {me.get('name', 'N/A')}")
        
        # 測試 2: 獲取數據庫信息
        print("\n2. 測試獲取數據庫信息...")
        db = client.databases_retrieve(database_id)
        print(f"✅ 成功獲取數據庫")
        db_title = db.get('title', [{}])[0].get('plain_text', 'N/A')
        print(f"   數據庫名稱: {db_title}")
        
        # 測試 3: 查詢數據庫
        print("\n3. 測試查詢數據庫...")
        results = client.databases_query(database_id)
        print(f"✅ 成功查詢數據庫")
        print(f"   現有頁面數: {len(results.get('results', []))}")
        
        print("\n" + "=" * 60)
        print("✅ 所有測試通過！可以使用 curl 客戶端")
        print("=" * 60)
        return True
        
    except Exception as e:
        print(f"\n❌ 測試失敗: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    test_curl_client()
