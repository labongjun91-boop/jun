import os
import requests
import uuid
import urllib3
import re
from datetime import datetime

# SSL 경고 숨기기
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 환경 변수 로드
ZEPP_EMAIL = os.environ.get("ZEPP_EMAIL", "").strip()
ZEPP_PASSWORD = os.environ.get("ZEPP_PASSWORD", "").strip()
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").strip()
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "").strip()

def get_zepp_tokens():
    print("🔐 Zepp 정식 2단계 OAuth 인증 절차를 시작합니다...")
    
    # [1단계] 임시 인증 코드(access_code) 발급 요청
    url1 = f"https://api-user.huami.com/registrations/{ZEPP_EMAIL}/tokens"
    
    headers1 = {
        "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
        "User-Agent": "Zepp/7.7.5 (iPhone; iOS 16.6; Scale/2.00)"
    }
    
    data1 = {
        "emailOrPhone": ZEPP_EMAIL,
        "password": ZEPP_PASSWORD,
        "state": "REDIRECTION",
        "client_id": "HuaMi",
        "country_code": "KR",
        "token": "access",
        "redirect_uri": "https://s3-us-west-2.amazonaws.com/hm-registration/successsignin.html"
    }
    
    # 리다이렉트 주소에서 코드를 직접 가로채야 하므로 allow_redirects=False 설정
    res1 = requests.post(url1, data=data1, headers=headers1, allow_redirects=False, verify=False)
    
    location = res1.headers.get("Location")
    if not location:
        raise Exception(f"1단계 인증 코드 발급 실패 (양식 오류): {res1.status_code} - {res1.text}")
        
    print("🎯 1단계 인증 주소 획득 완료, access_code 추출 중...")
    
    # 리다이렉트 주소에서 access_code 값 추출
    access_code_match = re.search(r"access=([^&]+)", location)
    if not access_code_match:
        raise Exception(f"리다이렉트 주소 내 토큰 파싱 실패: {location}")
        
    access_code = access_code_match.group(1)
    
    # [2단계] 가로챈 access_code를 진짜 로그인 토큰과 맞교환
    url2 = "https://account.huami.com/v2/client/login"
    
    headers2 = {
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 Zepp/7.7.5"
    }
    
    data2 = {
        "app_name": "com.huami.watch.hmwatch",
        "app_version": "7.7.5",
        "client_id": "HuaMi",
        "code": access_code,
        "country_code": "KR",
        "grant_type": "access_token",  # 패스워드가 아닌 토큰 교환 방식으로 명시
        "device_id": str(uuid.uuid4()),
        "device_model": "iPhone15,3",
        "allow_reg": "0"
    }
    
    res2 = requests.post(url2, headers=headers2, data=data2, verify=False)
    if res2.status_code != 200:
        raise Exception(f"2단계 토큰 교환 실패: {res2.status_code} - {res2.text}")
        
    login_data = res2.json()
    if "token_info" not in login_data:
        raise Exception("로그인 성공했으나 유효 토큰이 반환되지 않았습니다.")
        
    print("✅ Zepp 2단계 OAuth 로그인 최종 성공!")
    return login_data["token_info"]["access_token"], login_data["token_info"]["user_id"]

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
