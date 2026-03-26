# LINE 題庫 Bot + 後台（Zeabur 打包版）

這個專案已經包含：
- LINE Bot 隨機出題
- 選項隨機排序
- 計分與作答紀錄
- Flask 後台管理
- Excel 題庫匯入
- Zeabur 可部署結構

## 專案結構
- `app.py`：主程式，含 LINE Bot 與後台
- `schema.sql`：MySQL 建表與範例題目
- `create_admin.py`：產生 bcrypt 管理員密碼
- `.env.example`：環境變數範例
- `templates/`：後台 HTML
- `sample_questions.xlsx`：Excel 題庫匯入範例

## 本機測試
```bash
pip install -r requirements.txt
python create_admin.py
# 先用 schema.sql 建資料庫與資料表，再把 create_admin.py 印出的 SQL 貼到 MySQL
python app.py
```

## Zeabur 部署
1. 建立 Zeabur 專案
2. 新增 MySQL Service
3. 匯入 `schema.sql`
4. 設定環境變數（參考 `.env.example`）
5. 上傳此資料夾或連 GitHub
6. Start Command 可用：
   - `gunicorn app:app`
7. 部署完成後，把公開網址填到 LINE Developers 的 Webhook：
   - `https://你的網址/callback`

## 後台登入
- 帳號：你建立的 admin 帳號
- 密碼：你在 `create_admin.py` 設定的原始密碼

## Excel 欄位格式
必須是這 7 欄：
- category
- question
- A
- B
- C
- D
- answer

## 使用者指令
- `開始`：開始測驗
- `重新開始`：清空進度重新出題
- `A/B/C/D`：回答題目
