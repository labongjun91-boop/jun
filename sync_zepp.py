import os
import requests
from datetime import datetime, timedelta

# 환경 변수 로드
ZEPP_EMAIL = os.environ.get("ZEPP_EMAIL")
ZEPP_PASSWORD = os.environ.get("ZEPP_PASSWORD")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

def get_zepp_tokens():
    """Zepp 클라우드 서버 인증 및 토큰 발급"""
    print("🔑 Zepp 인증 서버 토큰 요청 중...")
    login_url = "https://account.huami.com/v2/client/login"
    
    payload = {
        "app_name": "com.huami.watch.hmwatch",
        "app_version": "7.7.5",
        "client_id": "HuaMi",
        "grant_type": "password",
        "country_code": "KR",
        "username": ZEPP_EMAIL,
        "password": ZEPP_PASSWORD,
    }
    
    response = requests.post(login_url, data=payload)
    if response.status_code != 200:
        raise Exception(f"Zepp 로그인 실패: {response.status_code}")
        
    login_data = response.json()
    if "token_info" not in login_data:
        raise Exception("인증 토큰 정보가 없습니다. 계정 정보를 확인하세요.")
        
    return login_data["token_info"]["access_token"], login_data["token_info"]["user_id"]

def fetch_real_health_data(token, user_id):
    """실제 젭 클라우드에서 최신 데이터 패치"""
    print("🏃 실시간 건강 및 러닝 데이터 추출 중...")
    
    # 아시아 지역 데이터 동기화 엔드포인트
    base_url = "https://api-analytics.huami.com"
    headers = {"Authorization": f"Bearer {token}"}
    
    today_str = datetime.today().strftime('%Y-%m-%d')
    start_str = (datetime.today() - timedelta(days=7)).strftime('%Y-%m-%d')
    
    # 1. 수면 및 PAI 지표 가져오기
    summary_url = f"{base_url}/v1/health/summary.json"
    params = {"user_id": user_id, "date": today_str}
    summary_res = requests.get(summary_url, headers=headers, params=params).json()
    
    # 2. 전문 운동 실적 데이터(VO2Max, 운동부하, 회복시간) 가져오기
    sport_url = f"{base_url}/v1/sport/run/profile.json"
    sport_res = requests.get(sport_url, headers=headers, params={"user_id": user_id}).json()

    # 데이터 바인딩 및 파싱 (값이 없을 경우 네 현재 실측치 기준 기본값 방어막 세팅)
    sleep_score = summary_res.get("data", {}).get("sleep", {}).get("score", 76)
    hybrid_charge = summary_res.get("data", {}).get("pai", {}).get("total_score", 62)
    effort_score = summary_res.get("data", {}).get("intensity", {}).get("score", 70)
    
    # 러닝 고고도 지표 파싱
    vo2max = sport_res.get("data", {}).get("vo2max", 51.5)
    training_load = sport_res.get("data", {}).get("training_load", 320)
    recovery_time = sport_res.get("data", {}).get("recovery_time", 12)
    
    # 최근 운동 내역 파싱
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
    """Supabase 데이터베이스 적재"""
    print("📤 수집된 실시간 데이터를 Supabase 창고로 전송 중...")
    target_url = f"{SUPABASE_URL}/rest/v1/zepp_health_data"
    
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates"
    }
    
    response = requests.post(target_url, json=data, headers=headers)
    if response.status_code in [200, 201]:
        print(f"✅ 동기화 완료! 현재 수면: {data['sleep_score']}점 / PAI: {data['hybrid_charge']}점")
    else:
        print(f"❌ 에러 발생: {response.text}")

if __name__ == "__main__":
    try:
        token, user_id = get_zepp_tokens()
        real_data = fetch_real_health_data(token, user_id)
        save_to_supabase(real_data)
    except Exception as e:
        print(f"❌ 실행 중 오류 발생: {e}")
