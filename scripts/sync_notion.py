#!/usr/bin/env python3
"""
Erebor Radar - Notion Database Sync Script (Zero Dependencies)
Synchronizes portfolio and watchlist data from Notion Database to data/portfolioData.json
Uses standard library urllib.request for zero-dependency execution.
"""

import os
import sys
import json
import urllib.request
import urllib.error
from datetime import datetime

def get_property_value(prop):
    if not prop:
        return None
    ptype = prop.get("type")
    if ptype == "title":
        titles = prop.get("title", [])
        return titles[0].get("plain_text", "").strip() if titles else ""
    elif ptype == "rich_text":
        texts = prop.get("rich_text", [])
        return "".join([t.get("plain_text", "") for t in texts]).strip() if texts else ""
    elif ptype == "number":
        return prop.get("number")
    elif ptype == "select":
        sel = prop.get("select")
        return sel.get("name") if sel else None
    elif ptype == "formula":
        form = prop.get("formula", {})
        ftype = form.get("type")
        return form.get(ftype)
    elif ptype == "url":
        return prop.get("url")
    return None

def find_prop(properties, possible_keys):
    for k, v in properties.items():
        k_clean = k.strip().lower().replace(" ", "").replace("_", "")
        for target in possible_keys:
            if k_clean == target.strip().lower().replace(" ", "").replace("_", ""):
                return get_property_value(v)
    return None

def main():
    notion_token = os.environ.get("NOTION_TOKEN")
    database_id = os.environ.get("NOTION_DATABASE_ID")

    json_path = os.path.join(os.path.dirname(__file__), "..", "data", "portfolioData.json")
    
    # 기존 baseline 데이터 로드
    baseline_data = {}
    if os.path.exists(json_path):
        with open(json_path, "r", encoding="utf-8") as f:
            baseline_data = json.load(f)

    if not notion_token or not database_id:
        print("[!] NOTION_TOKEN 또는 NOTION_DATABASE_ID 환경변수가 설정되지 않았습니다.")
        print("[*] 기존 로컬 baseline 데이터를 유지합니다.")
        return

    # Database ID 정규화 (하이픈 제거된 32자리 UUID 허용)
    clean_db_id = database_id.replace("-", "")

    url = f"https://api.notion.com/v1/databases/{clean_db_id}/query"
    headers = {
        "Authorization": f"Bearer {notion_token}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
        "User-Agent": "EreborRadarSync/1.0"
    }

    print(f"[*] Notion Database ({clean_db_id}) 조회 시작...")

    try:
        req_body = json.dumps({"page_size": 100}).encode("utf-8")
        req = urllib.request.Request(url, data=req_body, headers=headers, method="POST")
        
        with urllib.request.urlopen(req, timeout=15) as response:
            res_body = response.read().decode("utf-8")
            data = json.loads(res_body)

        results = data.get("results", [])
        print(f"[*] 조회 완료: 총 {len(results)}건의 레코드 발견")

        stocks = baseline_data.get("stocks", {})
        watchlist = baseline_data.get("watchlist", [])

        # 노션 행 파싱
        updated_stocks_count = 0
        for page in results:
            props = page.get("properties", {})
            page_url = page.get("url")

            name = find_prop(props, ["종목명", "종목", "name", "기업명"])
            ticker = find_prop(props, ["티커", "ticker", "종목코드", "code"])
            status = find_prop(props, ["상태", "status", "포지션", "구분"])
            shares = find_prop(props, ["보유수량", "수량", "shares", "주식수"])
            avg_buy = find_prop(props, ["평단가", "매수가", "평균단가", "avgbuy", "buyprice"])
            curr_price = find_prop(props, ["현재가", "currentprice", "price", "종가"])
            weight = find_prop(props, ["비중", "weight", "portfolio%"])
            stop_loss = find_prop(props, ["손절가", "stoploss", "손절"])
            target1 = find_prop(props, ["1차목표가", "target1", "목표가1", "targetprice"])
            target2 = find_prop(props, ["2차목표가", "target2", "목표가2"])
            moat = find_prop(props, ["경제적해자", "해자", "moat"])
            thesis = find_prop(props, ["투자논거", "thesis", "동업논거"])
            catalyst = find_prop(props, ["촉매", "catalyst", "뉴스"])
            scenario = find_prop(props, ["시나리오", "대응시나리오", "scenario"])
            invalidation = find_prop(props, ["무효화조건", "invalidation", "아이디어무효화"])

            if not ticker and not name:
                continue

            # 티커 문자열 6자리 포맷팅
            if ticker:
                ticker = str(ticker).zfill(6)
            else:
                # 티커가 없으면 이름으로 기존 티커 매칭
                for tk, stk in stocks.items():
                    if stk.get("name") == name:
                        ticker = tk
                        break

            if not ticker:
                continue

            # 기존 주식 정보가 있으면 업데이트, 없으면 신규 생성
            stk_entry = stocks.get(ticker, {
                "name": name or f"종목_{ticker}",
                "ticker": ticker,
                "color": "#87867F",
                "scores": { "moat": 7.0, "value": 7.0, "catalyst": 7.0, "return": 7.0, "impact": 7.0 }
            })

            if name: stk_entry["name"] = name
            if shares is not None: stk_entry["shares"] = int(shares)
            if avg_buy is not None: stk_entry["avgBuy"] = int(avg_buy)
            if curr_price is not None: stk_entry["currentPrice"] = int(curr_price)
            if weight is not None: stk_entry["weight"] = float(weight)
            if stop_loss is not None: stk_entry["stopLoss"] = int(stop_loss)
            if target1 is not None: stk_entry["target1"] = int(target1)
            if target2 is not None: stk_entry["target2"] = int(target2)
            if status: stk_entry["status"] = status
            if moat: stk_entry["moat"] = moat
            if thesis: stk_entry["thesis"] = thesis
            if catalyst: stk_entry["catalyst"] = catalyst
            if scenario: stk_entry["scenario"] = scenario
            if invalidation: stk_entry["invalidation"] = invalidation
            if page_url: stk_entry["notionUrl"] = page_url

            # 손익 자동 재계산
            s_shares = stk_entry.get("shares", 0)
            s_curr = stk_entry.get("currentPrice", 0)
            s_buy = stk_entry.get("avgBuy", 0)
            if s_shares and s_curr:
                stk_entry["evalAmount"] = s_shares * s_curr
                if s_buy:
                    stk_entry["pnlAmount"] = (s_curr - s_buy) * s_shares
                    stk_entry["pnlRate"] = round(((s_curr - s_buy) / s_buy) * 100, 2)

            stocks[ticker] = stk_entry
            updated_stocks_count += 1

        baseline_data["stocks"] = stocks
        baseline_data["lastSynced"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 저장
        os.makedirs(os.path.dirname(json_path), exist_ok=True)
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(baseline_data, f, ensure_ascii=False, indent=2)

        print(f"[✓] 성공적으로 {updated_stocks_count}개 종목을 data/portfolioData.json 에 동기화했습니다.")

    except urllib.error.HTTPError as e:
        print(f"[!] Notion API HTTP 오류: {e.code} - {e.read().decode('utf-8')}")
    except Exception as e:
        print(f"[!] 동기화 중 오류 발생: {e}")

if __name__ == "__main__":
    main()
