# Anduril 台北/東京職缺自動追蹤器

自動抓取 Anduril 台北和東京職缺並同步到 Notion 資料庫。

## 功能

- ✅ 每週自動抓取 Anduril 台北/東京職缺
- ✅ 自動新增新職缺到 Notion
- ✅ 更新現有職缺內容
- ✅ 標記已關閉的職缺
- ✅ 完整職缺描述同步到 Notion 頁面
- ✅ 使用 REQ ID 避免重複新增
- ✅ 優化流量使用（節省 95% API 流量）

---

## 本地測試步驟

### 1. 安裝依賴套件

```bash
# 使用 conda 環境
conda activate condve11
pip install -r requirements.txt
```

或直接安裝：
```bash
pip install requests beautifulsoup4 notion-client
```

### 2. 設定環境變數

**重要：API Key 必須是純字串格式，不能包含 `b'` 前綴**

```bash
# macOS/Linux
export NOTION_API_KEY='secret_your_api_key_here'
export NOTION_DATABASE_ID='your_database_id_here'

# Windows (PowerShell)
$env:NOTION_API_KEY='secret_your_api_key_here'
$env:NOTION_DATABASE_ID='your_database_id_here'
```

### 3. 執行測試

```bash
# 測試 Greenhouse API（不需要 Notion）
python test_greenhouse.py

# 診斷 Notion 設定
python test_notion_setup.py

# 執行完整同步
python sync_jobs.py
```

---

## 常見問題排解

### ❌ `Illegal header value b'***'`

**原因**: NOTION_API_KEY 格式錯誤，包含了 bytes 前綴

**解決方法**:
```bash
# ❌ 錯誤格式
export NOTION_API_KEY=b'secret_xxx'  # 不要這樣

# ✅ 正確格式
export NOTION_API_KEY='secret_xxx'   # 要這樣
```

### ❌ `'DatabasesEndpoint' object has no attribute 'query'`

**原因**: notion-client 版本問題或未安裝

**解決方法**:
```bash
pip install --upgrade notion-client
```

### ❌ 環境變數未設定

執行 `python test_notion_setup.py` 檢查環境變數是否正確設定。

---

## 設定步驟（GitHub Actions）

### 步驟 1: 建立 Notion Integration

1. 前往 [Notion Integrations](https://www.notion.so/my-integrations)
2. 點擊 **「+ New integration」**
3. 填寫資訊：
   - **Name**: `Anduril Job Tracker`
   - **Associated workspace**: 選擇你的 workspace
4. 點擊 **「Submit」**
5. **複製 Internal Integration Secret**（以 `secret_` 開頭）

### 步驟 2: 連結 Integration 到資料庫

1. 開啟你的 Notion 職缺追蹤資料庫
2. 點擊右上角 **「...」** → **「Connections」**
3. 搜尋並選擇你剛建立的 **「Anduril Job Tracker」**
4. 點擊 **「Confirm」**

### 步驟 3: 取得 Database ID

你的資料庫 URL 格式如下：
```
https://www.notion.so/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx?v=...
                      ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
                      這就是你的 Database ID
```

**你的資料庫 ID**: `3d5a587428e94283b44d260ecb12c145`

### 步驟 4: 設定 GitHub Repository

1. Fork 或建立新的 GitHub repository
2. 上傳這三個檔案：
   - `sync_jobs.py`
   - `requirements.txt`
   - `.github/workflows/sync-jobs.yml`

3. 前往 Repository → **Settings** → **Secrets and variables** → **Actions**

4. 新增兩個 Secrets：
   - **Name**: `NOTION_API_KEY`
     **Value**: 你的 Notion Integration Secret

   - **Name**: `NOTION_DATABASE_ID`
     **Value**: `3d5a587428e94283b44d260ecb12c145`

### 步驟 5: 啟用 GitHub Actions

1. 前往 Repository → **Actions**
2. 點擊 **「I understand my workflows, go ahead and enable them」**
3. 選擇 **「Sync Anduril Jobs to Notion」** workflow
4. 點擊 **「Run workflow」** 手動測試

---

## 執行時間表

- **自動執行**: 每週一早上 9:00 (台灣時間)
- **手動執行**: 隨時可在 GitHub Actions 頁面點擊「Run workflow」

---

## 本機測試

```bash
# 設定環境變數
export NOTION_API_KEY="secret_xxx..."
export NOTION_DATABASE_ID="3d5a587428e94283b44d260ecb12c145"

# 安裝套件
pip install -r requirements.txt

# 執行
python sync_jobs.py
```

---

## 資料庫欄位說明

| 欄位 | 說明 |
|-----|------|
| 職位名稱 | 職缺標題 |
| 部門 | 所屬部門 |
| 地點 | 工作地點 |
| REQ ID | 職缺編號 |
| 經驗要求 | 所需年資 |
| 申請連結 | 申請頁面 URL |
| 職缺描述摘要 | 簡短描述 |
| 申請狀態 | 你的申請進度 |
| 新增日期 | 職缺加入日期 |
| 備註 | 個人筆記 |

---

## 問題排解

**Q: GitHub Actions 執行失敗？**
- 確認 Secrets 設定正確
- 檢查 Notion Integration 是否已連結到資料庫

**Q: 沒有找到新職缺？**
- Anduril 可能沒有新開台北職缺
- 可手動檢查 [Anduril Careers](https://www.anduril.com/open-roles?location=taipei-taiwan)