import ccxt
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import time
import os
import requests
import json

# Line Messaging API 設定
LINE_CHANNEL_ACCESS_TOKEN = "z68YRxJ/qbEiyGNxX7AUoDowS0DyloaaAB2MS0fP+gmSU91DeqK5eYjt52frOUPDsHBsLGzZmsWBmmg30TGuh1E4OrlB3yXjjMzZ/D9PCaTFVAubxMFHvIdVO+fouu2QDu4GbkhKpIclWVhShY5AwAdB04t89/1O/w1cDnyilFU="  # 請替換成你的 Channel Access Token
LINE_USER_ID = "U0b9de9354c9bc872d46675ff5deafb8c"  # 請替換成你的 Line User ID
LINE_MESSAGING_API = "https://api.line.me/v2/bot/message/push"


def send_line_message(message):
    """發送 Line Messaging API 訊息"""
    headers = {
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    
    # 構建訊息內容
    payload = {
        "to": LINE_USER_ID,
        "messages": [
            {
                "type": "text",
                "text": f"比特幣交易機會通知 🚨\n"
                       f"時間: {message['time']}\n"
                       f"方向: {message['direction']}\n"
                       f"進場價格: {message['entry_price']}\n"
                       f"止損價格: {message['stop_loss']}\n"
                f"TP1 價格: {message['tp1_price']}\n"
                f"TP2 價格: {message['tp2_price']}\n"
                f"風險報酬比: {message['risk_reward1']} / {message['risk_reward2']}",
            }
        ],
    }
    
    try:
        response = requests.post(
            LINE_MESSAGING_API, headers=headers, data=json.dumps(payload), timeout=10
        )
        
        if response.status_code == 200:
            print("Line 訊息發送成功")
            return True
        else:
            print(f"Line 訊息發送失敗: {response.text}")
            return False
            
    except Exception as e:
        print(f"Line 訊息發送錯誤: {str(e)}")
        return False


def analyze_market_structure(df):
    """分析市場結構(Market Structure)

    判斷條件：
    - 看跌結構：currentLow < previousLow && currentHigh < previousHigh
    - 看漲結構：currentHigh > previousHigh && currentLow > previousLow
    """
    df["previousHigh"] = df["high"].shift(1)
    df["currentHigh"] = df["high"]
    df["previousLow"] = df["low"].shift(1)
    df["currentLow"] = df["low"]

    # 初始化市場結構列
    df["market_structure"] = "neutral"

    # 判斷看跌結構
    bearish_mask = (df["currentLow"] < df["previousLow"]) & (
        df["currentHigh"] < df["previousHigh"]
    )
    df.loc[bearish_mask, "market_structure"] = "bearish"

    # 判斷看漲結構
    bullish_mask = (df["currentHigh"] > df["previousHigh"]) & (
        df["currentLow"] > df["previousLow"]
    )
    df.loc[bullish_mask, "market_structure"] = "bullish"

    return df


def analyze_liquidity_grab(df):
    """分析流動性掃蕩(Liquidity Grab)

    定義：突然的關鍵突破高/低點，立刻反轉 → 代表機構掃蕩散戶

    判斷條件：
    - 上影線：if candle_high > key_resistance && close < open
    - 下影線：if candle_low < key_support && close > open
    """
    # 計算關鍵阻力位和支撐位（使用前20根K線的高點和低點）
    df["key_resistance"] = df["high"].rolling(window=20).max()
    df["key_support"] = df["low"].rolling(window=20).min()

    # 初始化流動性掃蕩列
    df["liquidity_grab"] = "none"

    # 判斷上影線掃蕩（多空陷阱）
    upper_grab_mask = (df["high"] > df["key_resistance"]) & (df["close"] < df["open"])
    df.loc[upper_grab_mask, "liquidity_grab"] = "upper_trap"

    # 判斷下影線掃蕩（空多陷阱）
    lower_grab_mask = (df["low"] < df["key_support"]) & (df["close"] > df["open"])
    df.loc[lower_grab_mask, "liquidity_grab"] = "lower_trap"

    return df


def analyze_order_blocks(df):
    """分析訂單區塊(Order Block, OB)

    定義：超勢反轉前，最後一根推進K棒區間
    系統OB新法：在CHoCH前，偵測最後一根實體較大K棒（多為紅K或綠K）
    儲存：OB_high, OB_low, OB_open, OB_close
    """
    # 初始化OB相關列
    df["is_ob"] = False
    df["ob_type"] = "none"
    df["ob_high"] = None
    df["ob_low"] = None
    df["ob_open"] = None
    df["ob_close"] = None

    # 計算K棒實體大小（收盤價與開盤價的差距絕對值）
    df["body_size"] = abs(df["close"] - df["open"])

    # 計算前20根K線的平均實體大小作為參考
    df["avg_body_size"] = df["body_size"].rolling(window=20).mean()

    # 找出實體較大的K棒（實體大小大於平均值的1.5倍）
    df["is_large_body"] = df["body_size"] > (df["avg_body_size"] * 1.5)

    # 判斷趨勢變化點（CHoCH）
    for i in range(3, len(df)):
        # 如果發現趨勢變化點
        if df.iloc[i]["market_structure"] != df.iloc[i - 1]["market_structure"]:
            # 向前尋找最後一根實體較大的K棒
            for j in range(i - 1, max(0, i - 5), -1):  # 最多往前找4根K線
                if df.iloc[j]["is_large_body"]:
                    # 標記為OB
                    df.at[df.index[j], "is_ob"] = True
                    # 判斷OB類型（看漲或看跌）
                    if df.iloc[j]["close"] > df.iloc[j]["open"]:  # 紅K
                        df.at[df.index[j], "ob_type"] = "bullish"
                    else:  # 綠K
                        df.at[df.index[j], "ob_type"] = "bearish"
                    # 記錄OB的高低點和開收盤價
                    df.at[df.index[j], "ob_high"] = df.iloc[j]["high"]
                    df.at[df.index[j], "ob_low"] = df.iloc[j]["low"]
                    df.at[df.index[j], "ob_open"] = df.iloc[j]["open"]
                    df.at[df.index[j], "ob_close"] = df.iloc[j]["close"]
                break

    return df


def analyze_fvg(df):
    """分析 Fair Value Gap (FVG)

    定義：快速移動中，K棒間隔過的區間（價格未交易）

    系統條件（3根K棒判斷）：
    - 空方FVG：中間K棒高 < 第一根K棒低 → 向下缺口
    - 多方FVG：中間K棒低 > 第一根K棒高 → 向上缺口
    """
    # 初始化FVG相關列
    df["fvg_type"] = "none"
    df["fvg_high"] = None
    df["fvg_low"] = None

    # 至少需要3根K線才能判斷FVG
    if len(df) < 3:
        return df

    # 遍歷K線（從第三根開始）
    for i in range(2, len(df)):
        # 取得三根K線的數據
        candle0 = df.iloc[i - 2]  # 第一根
        candle1 = df.iloc[i - 1]  # 中間
        candle2 = df.iloc[i]  # 第三根

        # 判斷空方FVG（向下缺口）
        if candle1["low"] > candle0["high"] and candle1["low"] > candle2["high"]:
            df.at[df.index[i - 1], "fvg_type"] = "bearish"
            df.at[df.index[i - 1], "fvg_high"] = candle1["low"]
            df.at[df.index[i - 1], "fvg_low"] = max(candle0["high"], candle2["high"])

        # 判斷多方FVG（向上缺口）
        elif candle1["high"] < candle0["low"] and candle1["high"] < candle2["low"]:
            df.at[df.index[i - 1], "fvg_type"] = "bullish"
            df.at[df.index[i - 1], "fvg_high"] = min(candle0["low"], candle2["low"])
            df.at[df.index[i - 1], "fvg_low"] = candle1["high"]

    return df


def calculate_sl_tp(df, i, signal_type):
    """計算止損和獲利目標價位

    止損（SL）：
    - 設於 OB 外圈（空單在 OB high 上方，多單在 OB low 下方）

    獲利目標（TP）：
    - TP1：設於前高/前低
    - TP2：下個結構點或新一輪流動性點
    """
    current_candle = df.iloc[i]
    prev_candle = df.iloc[i - 1]

    # 初始化返回值
    sl_price = None
    tp1_price = None
    tp2_price = None

    # 計算前高前低（使用前20根K線）
    lookback = min(20, i)
    prev_high = df["high"].iloc[i - lookback : i].max()
    prev_low = df["low"].iloc[i - lookback : i].min()

    if signal_type == "long":
        # 多單止損：OB low下方
        if pd.notna(prev_candle["ob_low"]):
            sl_price = (
                prev_candle["ob_low"]
                - (current_candle["high"] - current_candle["low"]) * 0.1
            )
        else:
            sl_price = (
                current_candle["low"]
                - (current_candle["high"] - current_candle["low"]) * 0.1
            )

        # 多單TP1：前高
        tp1_price = prev_high

        # 多單TP2：下個結構高點（預估為當前價格加上前高到前低的距離）
        price_range = prev_high - prev_low
        tp2_price = current_candle["close"] + price_range

    else:  # short
        # 空單止損：OB high上方
        if pd.notna(prev_candle["ob_high"]):
            sl_price = (
                prev_candle["ob_high"]
                + (current_candle["high"] - current_candle["low"]) * 0.1
            )
        else:
            sl_price = (
                current_candle["high"]
                + (current_candle["high"] - current_candle["low"]) * 0.1
            )

        # 空單TP1：前低
        tp1_price = prev_low

        # 空單TP2：下個結構低點（預估為當前價格減去前高到前低的距離）
        price_range = prev_high - prev_low
        tp2_price = current_candle["close"] - price_range

    return sl_price, tp1_price, tp2_price


def analyze_entry(df):
    """分析進場條件（Entry）

    空單進場條件：
    1. 發生 Liquidity Grab
    2. 出現 CHoCH 向下
    3. 價格回測 OB 區 / 補 FVG
    4. OB 區內出現雙K（吞沒、Pinbar）

    多單進場條件：
    1. 發生 Liquidity Grab（跌破前低）
    2. 出現 CHoCH 向上
    3. 價格回測 OB 區 / 補 FVG
    4. OB 區內出現雙K（吞沒、Pinbar）
    """
    # 初始化進場信號相關列
    df["entry_signal"] = "none"
    df["entry_price"] = None
    df["stop_loss"] = None
    df["tp1_price"] = None
    df["tp2_price"] = None

    # 至少需要4根K線才能判斷進場條件
    if len(df) < 4:
        return df

    # 遍歷K線（從第四根開始）
    for i in range(3, len(df)):
        current_candle = df.iloc[i]
        prev_candle = df.iloc[i - 1]

        # 檢查是否在OB區域內
        in_ob_zone = False
        try:
            if (
                pd.notna(prev_candle["ob_low"])
                and pd.notna(prev_candle["ob_high"])
                and pd.notna(current_candle["close"])
            ):
                if (
                    current_candle["close"] >= prev_candle["ob_low"]
                    and current_candle["close"] <= prev_candle["ob_high"]
                ):
                    in_ob_zone = True
        except Exception:
            in_ob_zone = False

        # 檢查是否在FVG區域內
        in_fvg_zone = False
        try:
            if (
                pd.notna(prev_candle["fvg_low"])
                and pd.notna(prev_candle["fvg_high"])
                and pd.notna(current_candle["close"])
            ):
                if (
                    current_candle["close"] >= prev_candle["fvg_low"]
                    and current_candle["close"] <= prev_candle["fvg_high"]
                ):
                    in_fvg_zone = True
        except Exception:
            in_fvg_zone = False

        # 判斷空單進場條件
        if (
            prev_candle["liquidity_grab"] == "upper_trap"  # Liquidity Grab
            and prev_candle["market_structure"] == "bearish"  # CHoCH向下
            and (in_ob_zone or in_fvg_zone)  # 價格在OB區或FVG區
            and pd.notna(current_candle["close"])
            and pd.notna(current_candle["open"])
            and current_candle["close"] < current_candle["open"]
        ):  # 收綠K確認

            df.at[df.index[i], "entry_signal"] = "short"
            df.at[df.index[i], "entry_price"] = current_candle["close"]

            # 計算止損和獲利目標
            sl_price, tp1_price, tp2_price = calculate_sl_tp(df, i, "short")
            df.at[df.index[i], "stop_loss"] = sl_price
            df.at[df.index[i], "tp1_price"] = tp1_price
            df.at[df.index[i], "tp2_price"] = tp2_price

        # 判斷多單進場條件
        elif (
            prev_candle["liquidity_grab"] == "lower_trap"  # Liquidity Grab（跌破前低）
            and prev_candle["market_structure"] == "bullish"  # CHoCH向上
            and (in_ob_zone or in_fvg_zone)  # 價格在OB區或FVG區
            and pd.notna(current_candle["close"])
            and pd.notna(current_candle["open"])
            and current_candle["close"] > current_candle["open"]
        ):  # 收紅K確認

            df.at[df.index[i], "entry_signal"] = "long"
            df.at[df.index[i], "entry_price"] = current_candle["close"]

            # 計算止損和獲利目標
            sl_price, tp1_price, tp2_price = calculate_sl_tp(df, i, "long")
            df.at[df.index[i], "stop_loss"] = sl_price
            df.at[df.index[i], "tp1_price"] = tp1_price
            df.at[df.index[i], "tp2_price"] = tp2_price

    return df


def get_btc_data(exchange, symbol="BTC/USDT", timeframe="5m"):
    """獲取比特幣最新行情數據"""
    try:
        # 獲取 OHLCV 數據
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe)
        df = pd.DataFrame(
            ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"]
        )
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms") + timedelta(
            hours=8
        )

        # 分析市場結構
        df = analyze_market_structure(df)
        # 分析流動性掃蕩
        df = analyze_liquidity_grab(df)
        # 分析訂單區塊
        df = analyze_order_blocks(df)
        # 分析FVG
        df = analyze_fvg(df)
        # 分析進場條件
        df = analyze_entry(df)

        return df
    except Exception as e:
        print(f"錯誤：{str(e)}")
        return None


def clear_screen():
    """清除終端機畫面"""
    os.system("cls" if os.name == "nt" else "clear")


def save_signals(
    timestamp,
    price,
    market_structure,
    liquidity_grab,
    ob_info,
    fvg_info,
    entry_info,
    filename=None,
):
    """記錄交易信號"""
    if filename is None:
        if not os.path.exists("record"):
            os.makedirs("record")
        filename = f"record/signals_{timestamp.strftime('%Y%m%d')}.csv"
    
    data = {
        "時間 (Time)": [timestamp.strftime("%Y-%m-%d %H:%M:%S")],
        "價格 (Price)": [f"${price:,.2f}"],
        "市場結構 (Market Structure)": [market_structure],
        "流動性掃蕩 (Liquidity Grab)": [liquidity_grab],
        "訂單區塊類型 (Order Block Type)": [ob_info.get("type", "none")],
        "OB高點 (OB High)": [
            f"${ob_info.get('high', 0):,.2f}" if ob_info.get("high") else "none"
        ],
        "OB低點 (OB Low)": [
            f"${ob_info.get('low', 0):,.2f}" if ob_info.get("low") else "none"
        ],
        "FVG類型 (FVG Type)": [fvg_info.get("type", "none")],
        "FVG高點 (FVG High)": [
            f"${fvg_info.get('high', 0):,.2f}" if fvg_info.get("high") else "none"
        ],
        "FVG低點 (FVG Low)": [
            f"${fvg_info.get('low', 0):,.2f}" if fvg_info.get("low") else "none"
        ],
        "進場信號 (Entry Signal)": [entry_info.get("signal", "none")],
        "進場價格 (Entry Price)": [
            f"${entry_info.get('price', 0):,.2f}" if entry_info.get("price") else "none"
        ],
        "止損價格 (Stop Loss)": [
            (
                f"${entry_info.get('stop_loss', 0):,.2f}"
                if entry_info.get("stop_loss")
                else "none"
            )
        ],
        "TP1價格 (TP1 Price)": [
            (
                f"${entry_info.get('tp1_price', 0):,.2f}"
                if entry_info.get("tp1_price")
                else "none"
            )
        ],
        "TP2價格 (TP2 Price)": [
            (
                f"${entry_info.get('tp2_price', 0):,.2f}"
                if entry_info.get("tp2_price")
                else "none"
            )
        ],
    }
    
    df = pd.DataFrame(data)
    
    # 如果文件不存在，創建新文件並寫入標題
    if not os.path.exists(filename):
        df.to_csv(filename, index=False, mode="w", encoding="utf-8")
    else:
        # 如果文件存在，追加數據
        df.to_csv(filename, index=False, mode="a", header=False, encoding="utf-8")


    # 顯示下次更新時間
def calculate_next_update():
    """計算下一個更新時間"""
    now = datetime.now()
    minutes_until_next = 5 - (now.minute % 5)
    if minutes_until_next == 0 and now.second > 0:
        minutes_until_next = 5
    next_update = now + timedelta(minutes=minutes_until_next)
    return next_update.replace(second=0, microsecond=0)


def main():
    # 初始化交易所
    exchange = ccxt.binance(
        {
            "enableRateLimit": True,
        }
    )

    print("開始監控比特幣趨勢與流動性...")
    
    while True:
        try:
            # 計算下一個5分鐘的整點時間
            next_update = calculate_next_update()
            print(f"\n下次更新時間: {next_update.strftime('%Y-%m-%d %H:%M:%S')}")
            
            # 等待直到下一個更新時間
            wait_seconds = (next_update - datetime.now()).total_seconds()
            if wait_seconds > 0:
                time.sleep(wait_seconds)
            
            clear_screen()
            
            # 獲取最新數據
            df = get_btc_data(exchange, timeframe="5m")
            
            if df is not None:
                current_time = df["timestamp"].iloc[-1]
                current_price = df["close"].iloc[-1]
                market_structure = df["market_structure"].iloc[-1]
                liquidity_grab = df["liquidity_grab"].iloc[-1]

                # 獲取最新的OB信息
                latest_ob = (
                    df[df["is_ob"]].iloc[-1] if len(df[df["is_ob"]]) > 0 else None
                )
                ob_info = {
                    "type": latest_ob["ob_type"] if latest_ob is not None else "none",
                    "high": latest_ob["ob_high"] if latest_ob is not None else None,
                    "low": latest_ob["ob_low"] if latest_ob is not None else None,
                }

                # 獲取最新的FVG信息
                latest_fvg = (
                    df[df["fvg_type"] != "none"].iloc[-1]
                    if len(df[df["fvg_type"] != "none"]) > 0
                    else None
                )
                fvg_info = {
                    "type": (
                        latest_fvg["fvg_type"] if latest_fvg is not None else "none"
                    ),
                    "high": latest_fvg["fvg_high"] if latest_fvg is not None else None,
                    "low": latest_fvg["fvg_low"] if latest_fvg is not None else None,
                }

                # 獲取最新的進場信號
                latest_entry = (
                    df[df["entry_signal"] != "none"].iloc[-1]
                    if len(df[df["entry_signal"] != "none"]) > 0
                    else None
                )
                entry_info = {
                    "signal": (
                        latest_entry["entry_signal"]
                        if latest_entry is not None
                        else "none"
                    ),
                    "price": (
                        latest_entry["entry_price"]
                        if latest_entry is not None
                        else None
                    ),
                    "stop_loss": (
                        latest_entry["stop_loss"] if latest_entry is not None else None
                    ),
                    "tp1_price": (
                        latest_entry["tp1_price"] if latest_entry is not None else None
                    ),
                    "tp2_price": (
                        latest_entry["tp2_price"] if latest_entry is not None else None
                    ),
                }

                # 顯示分析結果
                print(f"\n時間 : {current_time.strftime('%Y-%m-%d %H:%M:%S')}")
                print(f"價格 : ${current_price:,.2f}")
                print(
                    f"市場結構 : {'看漲 🔼' if market_structure == 'bullish' else '看跌 🔽' if market_structure == 'bearish' else '中性 ↔'}"
                )
                print(
                    f"流動性掃蕩 : {'上影線陷阱 ⚠️' if liquidity_grab == 'upper_trap' else '下影線陷阱 ⚠️' if liquidity_grab == 'lower_trap' else '無'}"
                )

                # 顯示OB信息
                if ob_info["type"] != "none":
                    print(
                        f"訂單區塊 : {'看漲OB 🟢' if ob_info['type'] == 'bullish' else '看跌OB 🔴'}"
                    )
                    print(f"OB區間 : ${ob_info['low']:,.2f} - ${ob_info['high']:,.2f}")
                else:
                    print("訂單區塊 : 無")

                # 顯示FVG信息
                if fvg_info["type"] != "none":
                    print(
                        f"FVG類型 : {'看漲FVG 🟢' if fvg_info['type'] == 'bullish' else '看跌FVG 🔴'}"
                    )
                    print(
                        f"FVG區間 : ${fvg_info['low']:,.2f} - ${fvg_info['high']:,.2f}"
                    )
                else:
                    print("FVG : 無")

                # 顯示進場信號
                if entry_info["signal"] != "none":
                    print(
                        f"\n🎯 進場信號 : {'做多 ⬆️' if entry_info['signal'] == 'long' else '做空 ⬇️'}"
                    )
                    print(f"進場價格 : ${entry_info['price']:,.2f}")
                    print(f"止損價格 : ${entry_info['stop_loss']:,.2f}")
                    print(f"TP1 價格 : ${entry_info['tp1_price']:,.2f}")
                    print(f"TP2 價格 : ${entry_info['tp2_price']:,.2f}")

                    # 計算風險報酬比
                    if entry_info["signal"] == "long":
                        risk = entry_info["price"] - entry_info["stop_loss"]
                        reward1 = entry_info["tp1_price"] - entry_info["price"]
                        reward2 = entry_info["tp2_price"] - entry_info["price"]
                    else:  # short
                        risk = entry_info["stop_loss"] - entry_info["price"]
                        reward1 = entry_info["price"] - entry_info["tp1_price"]
                        reward2 = entry_info["price"] - entry_info["tp2_price"]

                    rr1 = abs(reward1 / risk) if risk != 0 else 0
                    rr2 = abs(reward2 / risk) if risk != 0 else 0
                    print(f"TP1 風險報酬比 : {rr1:.2f}")
                    print(f"TP2 風險報酬比 : {rr2:.2f}")

                    # 如果有新的進場信號，發送Line通知
                    if latest_entry is not None and latest_entry.name == df.index[-1]:
                        message = {
                            "時間": current_time.strftime("%Y-%m-%d %H:%M:%S"),
                            "方向": (
                                "做多" if entry_info["signal"] == "long" else "做空"
                            ),
                            "進場價格": entry_info["price"],
                            "止損價格": entry_info["stop_loss"],
                            "獲利目標1": entry_info["tp1_price"],
                            "獲利目標2": entry_info["tp2_price"],
                            "風險報酬比1": f"{rr1:.2f}",
                            "風險報酬比2": f"{rr2:.2f}",
                        }
                        send_line_message(message)

                print("\n按 Ctrl+C 可以停止程式")
                
                # 保存信號
                save_signals(
                    current_time,
                    current_price,
                    market_structure,
                    liquidity_grab,
                    ob_info,
                    fvg_info,
                    entry_info,
                )
            
        except Exception as e:
            print(f"發生錯誤：{str(e)}")
            time.sleep(60)


if __name__ == "__main__":
    main()
