import os
import json
import time
import glob
import csv
from urllib.parse import quote
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# --- 環境変数 (Secretsから取得) ---
USER_ID = os.environ.get("USER_ID", "your_id")
PASSWORD = os.environ.get("USER_PASS", "your_pass")
# GCP_JSONは文字列として読み込む
json_creds = json.loads(os.environ.get("GCP_JSON", "{}")) 
TARGET_URL = os.environ.get("TARGET_URL", "https://example.com/login") 

# --- 設定 ---
SPREADSHEET_ID = os.environ.get("SPREADSHEET_ID", "1H2TiCraNjMNoj3547ZB78nQqrdfbfk2a0rMLSbZBE48")
SHEET_NAME = "今月_raw"
PARTNER_NAME = "株式会社フルアウト"

def get_google_service(service_name, version, scopes):
    """Google APIサービスを取得するヘルパー関数"""
    creds = Credentials.from_service_account_info(json_creds, scopes=scopes)
    return build(service_name, version, credentials=creds)

def update_google_sheet(csv_path):
    """CSVの中身を読み込んでスプレッドシートに張り付ける関数"""
    print(f"スプレッドシートへの転記を開始: {SHEET_NAME}")
    service = get_google_service('sheets', 'v4', ['https://www.googleapis.com/auth/spreadsheets'])

    # 1. CSVデータの読み込み (文字コード判定付き)
    csv_data = []
    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            csv_data = list(reader)
    except UnicodeDecodeError:
        print("UTF-8での読み込みに失敗しました。Shift_JIS(CP932)で再試行します。")
        try:
            with open(csv_path, 'r', encoding='cp932') as f:
                reader = csv.reader(f)
                csv_data = list(reader)
        except Exception as e:
            print(f"CSV読み込みエラー: {e}")
            return

    if not csv_data:
        print("CSVデータが空のため転記をスキップします。")
        return

    # 2. シートのクリア (古いデータを消す)
    try:
        service.spreadsheets().values().clear(
            spreadsheetId=SPREADSHEET_ID,
            range=SHEET_NAME
        ).execute()
        print("既存データをクリアしました。")
    except Exception as e:
        print(f"シートクリアエラー: {e}")

    # 3. データの書き込み
    body = {
        'values': csv_data
    }
    try:
        result = service.spreadsheets().values().update(
            spreadsheetId=SPREADSHEET_ID,
            range=f"{SHEET_NAME}!A1",
            valueInputOption='USER_ENTERED',
            body=body
        ).execute()
        print(f"スプレッドシート更新完了: {result.get('updatedCells')} セル更新")
    except Exception as e:
        print(f"書き込みエラー: {e}")

def main():
    print("=== Action Log取得処理開始(今月分) ===")
    
    download_dir = os.path.join(os.getcwd(), "downloads_action_month")
    if not os.path.exists(download_dir):
        os.makedirs(download_dir)

    # 以前のCSV削除
    for f in glob.glob(os.path.join(download_dir, "*")):
        os.remove(f)

    options = Options()
    options.add_argument('--headless') 
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--window-size=1920,1080')
    
    prefs = {
        "download.default_directory": download_dir,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True
    }
    options.add_experimental_option("prefs", prefs)
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    wait = WebDriverWait(driver, 20)

    try:
        # --- 1. ログイン ---
        safe_user = quote(USER_ID, safe='')
        safe_pass = quote(PASSWORD, safe='')
        url_body = TARGET_URL.replace("https://", "").replace("http://", "")
        auth_url = f"https://{safe_user}:{safe_pass}@{url_body}"
        
        print(f"アクセス中: {TARGET_URL}")
        driver.get(auth_url)
        time.sleep(3)
        
        # 画面リフレッシュ(念の為)
        driver.get(auth_url)
        time.sleep(5) 

        # --- 2. 「絞り込み検索」ボタンをクリック ---
        print("「絞り込み検索」ボタンを押してメニューを開きます...")
        try:
            filter_btn = wait.until(EC.element_to_be_clickable((By.ID, "searchFormOpen")))
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", filter_btn)
            time.sleep(1)
            filter_btn.click()
            print("「絞り込み検索」ボタンをクリックしました")
            time.sleep(2) # 開くのを待つ
        except Exception as e:
            print(f"絞り込み検索ボタンが見つかりません: {e}")
            pass

        # --- 3. 「今月」ボタンをクリック ---
        print("「今月」ボタンを選択します...")
        try:
            current_month_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, ".current_month")))
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", current_month_btn)
            time.sleep(1)
            current_month_btn.click()
            print("「今月」ボタンをクリックしました")
            time.sleep(3) # 日付入力欄への反映待ち
        except Exception as e:
            print(f"「今月」ボタンの操作エラー: {e}")

        # --- 4. パートナー（株式会社フルアウト）を選択 ---
        print(f"パートナー({PARTNER_NAME})を入力します...")
        try:
            # 「パートナー」ラベルの近くにある入力欄を探す
            partner_label = driver.find_element(By.XPATH, "//div[contains(text(), 'パートナー')] | //label[contains(text(), 'パートナー')]")
            partner_target = partner_label.find_element(By.XPATH, "./following::input[contains(@placeholder, '選択')][1]")
            
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", partner_target)
            
            # 入力欄をクリック
            partner_target.click()
            time.sleep(1)
            
            # 文字を入力
            active_elem = driver.switch_to.active_element
            active_elem.send_keys(PARTNER_NAME)
            
            # 【重要】候補が出るのをしっかり待つ
            time.sleep(3)
            
            # Enterで確定
            active_elem.send_keys(Keys.ENTER)
            print("パートナーを選択しました")
            time.sleep(2)

        except Exception as e:
            print(f"パートナー入力エラー: {e}")

        # --- 5. 検索ボタン実行 ---
        print("検索ボタンを探して押します...")
        try:
            # name="search" かつ classに"searchFormSubmit"を含むボタンを厳密に指定
            search_selector = "input.searchFormSubmit[name='search'], button.searchFormSubmit[name='search']"
            target_search_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, search_selector)))
            
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", target_search_btn)
            time.sleep(1)
            
            target_search_btn.click()
            print("検索ボタンをクリックしました")

        except Exception as e:
            print(f"検索ボタン操作エラー: {e}")
            # 万が一見つからない場合はEnterキーで代用
            webdriver.ActionChains(driver).send_keys(Keys.ENTER).perform()
        
        # --- 検索結果の反映待ち ---
        print("検索結果を待機中(15秒)...")
        time.sleep(15)

        # --- 6. CSV生成ボタン ---
        print("CSV生成ボタンを押します...")
        try:
            # inputタグのvalue="CSV生成" または buttonタグのテキスト
            csv_btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//*[@value='CSV生成' or contains(text(), 'CSV生成')]")))
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", csv_btn)
            time.sleep(1)
            driver.execute_script("arguments[0].click();", csv_btn)
            print("CSV生成ボタンをクリックしました")
            
        except Exception as e:
            print(f"CSVボタンエラー: {e}")
            return
        
        # ダウンロード待ち
        print("ダウンロード待機中...")
        time.sleep(5)
        csv_file_path = None
        for i in range(30):
            files = glob.glob(os.path.join(download_dir, "*.csv"))
            if files:
                csv_file_path = files[0]
                break
            time.sleep(2)
            
        if not csv_file_path:
            print("【エラー】CSVファイルが見つかりません。")
            return
        
        print(f"ダウンロード成功: {csv_file_path}")

        # --- 7. スプレッドシートへ転記 ---
        update_google_sheet(csv_file_path)

    except Exception as e:
        print(f"【エラー発生】: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        driver.quit()

if __name__ == "__main__":
    main()
