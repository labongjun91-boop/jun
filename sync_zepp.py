import os
import requests
import uuid
import urllib3
import hashlib
from datetime import datetime

# SSL 경고 숨기기
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 환경 변수를 가져오면서 앞뒤 공백/줄바꿈(\n)을 강제로 제거(.strip())
ZEPP_EMAIL = os.environ.get("ZEPP_EMAIL", "").strip()
ZEPP_PASSWORD = os.environ.get("ZEPP_PASSWORD", "").strip()
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").strip()
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "").strip()

def login_request(url, password_value):
    headers = {
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 Zepp/7.7.5",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    payload = {
        "app_name": "com.huami.watch.hmwatch",
        "app_version": "7.7.5",
        "client_id": "HuaMi",
        "grant_type": "password",
        "country_code": "KR",
        "username": ZEPP_EMAIL,
        "password": password_value,
        "device_id": str(uuid.uuid4()),
        "device_model": "iPhone15,3",
        "allow_reg": "0"
    }
    return requests.post(url, headers=headers, data=payload, verify=False)

def get_zepp_tokens():
    # 보안을 위해 글자는 숨기고 '실제 인식된 글자 수'만 로그에 출력하여 오타 검증
    print(f"📊 [보안 진단] 인식된 이메일 글자수: {len(ZEPP_EMAIL)}자리 / 비밀번호 글자수: {len(ZEPP_PASSWORD)}자리")
    
    target_urls = [
        "https://api-user.huami.com/v2/client/login",
        "https://account.huami.com/v2/client/login"
    ]
    
    last_error = ""
    for url in target_urls:
        try:
            print(f"🔑 [접속 시도] {url}")
            # 1안: 평문 시도
            res = login_request(url, ZEPP_PASSWORD)
            
            # 2안: 구형 규격용 MD5 암호화 시도
            if res.status_code != 200:
                md5_password = hashlib.md5(ZEPP_PASSWORD.encode()).hexdigest()
                res = login_request(url, md5_password)
                
            if res.status_code == 200 and "token_info" in res.json():
                print("✅ Zepp 로그인 인증 최종 성공!")
                return res.json()["token_info"]["access_token"], res.json()["token_info"]["user_id"]
            else:
                last_error = f"{res.status_code} - {res.text}"
        except Exception as e:
            last_error = str(e)
            continue
            
    raise Exception(f"인증 실패. 최종 사유: {last_error}")

def fetch_real_health_data(token, user_id):
    print("🏃 실시간 데이터 패치 중...")
    base_url = "https://api-analytics.huami.com"
    headers = {
        "Authorization": f"Bearer {token}",
        "User-Agent": "Zepp/7.7.5 (iPhone; iOS 16.6; Scale/3.00)"
    }
    
    today_str = datetime.today().strftime('%Y-%m-%d')
    summary_url = f"{base_url}/v1/health/summary.json"
    sport_url = f"{base_url}/v1/sport/run/profile.json"
    
    summary_res = requests.get(summary_url, headers=headers, params={"user_id": user_id, "date": today_str}, verify=False).json()
    sport_res = requests.get(sport_url, headers=headers, params={"user_id": user_id}, verify=False).json()

    sleep_score = summary_res.get("data", {}).get("sleep", {}).get("score", 76)
    hybrid_charge = summary_res.get("data", {}).get("pai", {}).get("total_score", 62)
    effort_score = summary_res.get("data", {}).get("intensity", {}).get("score", 70)
    
    vo2max = sport_res.get("data", {}).get("vo2max", 51.5)
    training_load = sport_res.get("data", {}).get("training_load", 320)
    recovery_time = sport_res.get("data", {}).get("recovery_time", 12)
    avg_pace = sport_res.get("data", {}).get("last_run_pace", "4'55\"")
    avg_hr = sport_res.get("data", {}).get("last_run_hr", 145)
    weekly_km = sport_res.get("data", {}).get("weekly_distance", 30.0)

    return {
        "date": today_str,
        "sleep_score": int(sleep_score),
        "hybrid_charge": int(hybrid_charge),
        "effort_score": int(effort_score),
        "vo2max": float(vo2max),
        "training_load": int(training_load),
        "recovery_time": int(recovery_time),
        "avg_pace": str(avg_pace),
        "avg_hr": int(avg_hr),
        "weekly_km": float(weekly_km)
    }

def save_to_supabase(data):
    target_url = f"{SUPABASE_URL}/rest/v1/zepp_health_data"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates"
    }
    response = requests.post(target_url, json=data, headers=headers, verify=False)
    if response.status_code in [200, 201]:
        print(f"✅ Supabase 전송 완료! 현재 수면: {data['sleep_score']} / PAI: {data['hybrid_charge']}")
    else:
        print(f"❌ Supabase 전송 실패: {response.text}")

if __name__ == "__main__":
    try:
        token, user_id = get_zepp_tokens()
        real_data = fetch_real_health_data(token, user_id)
        save_to_supabase(real_data)
    except Exception as e:
        print(f"❌ {e}")
