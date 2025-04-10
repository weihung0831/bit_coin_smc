from flask import Flask, render_template, jsonify, send_from_directory
import pandas as pd
from bitcoin_smc import *
import threading
import time
import ccxt
from datetime import datetime
import os

app = Flask(__name__, 
    static_folder='static',
    template_folder='templates'
)

# 全局變量用於存儲最新的分析結果
latest_analysis = None
latest_price = None
analysis_lock = threading.Lock()
price_lock = threading.Lock()

def update_price():
    """更新最新價格的背景任務"""
    global latest_price
    exchange = ccxt.binance({'enableRateLimit': True})
    
    while True:
        try:
            ticker = exchange.fetch_ticker('BTC/USDT')
            with price_lock:
                latest_price = {
                    'price': ticker['last'],
                    'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }
            time.sleep(1)  # 每秒更新一次
        except Exception as e:
            print(f"更新價格時發生錯誤：{str(e)}")
            time.sleep(1)

def update_analysis():
    """更新分析數據的背景任務"""
    global latest_analysis
    exchange = ccxt.binance({'enableRateLimit': True})
    
    while True:
        try:
            df = get_btc_data(exchange, timeframe="5m")
            if df is not None:
                with analysis_lock:
                    latest_analysis = {
                        'timestamp': df['timestamp'].iloc[-1].strftime('%Y-%m-%d %H:%M:%S'),
                        'current_price': float(df['close'].iloc[-1]),
                        'market_structure': {
                            'trend': str(df['market_structure'].iloc[-1]).lower(),
                            'support': float(df['low'].iloc[-20:].min()),
                            'resistance': float(df['high'].iloc[-20:].max())
                        },
                        'ob_info': {
                            'type': str(df[df['is_ob']].iloc[-1]['ob_type'] if len(df[df['is_ob']]) > 0 else 'none'),
                            'high': float(df[df['is_ob']].iloc[-1]['ob_high'] if len(df[df['is_ob']]) > 0 else 0),
                            'low': float(df[df['is_ob']].iloc[-1]['ob_low'] if len(df[df['is_ob']]) > 0 else 0)
                        },
                        'fvg_info': {
                            'type': str(df[df['fvg_type'] != 'none'].iloc[-1]['fvg_type'] if len(df[df['fvg_type'] != 'none']) > 0 else 'none'),
                            'high': float(df[df['fvg_type'] != 'none'].iloc[-1]['fvg_high'] if len(df[df['fvg_type'] != 'none']) > 0 else 0),
                            'low': float(df[df['fvg_type'] != 'none'].iloc[-1]['fvg_low'] if len(df[df['fvg_type'] != 'none']) > 0 else 0)
                        }
                    }
            time.sleep(300)  # 每5分鐘更新一次分析
        except Exception as e:
            print(f"更新分析時發生錯誤：{str(e)}")
            time.sleep(60)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/price')
def get_price():
    """獲取最新價格"""
    with price_lock:
        if latest_price is None:
            return jsonify({'error': '價格數據尚未準備好'})
        return jsonify(latest_price)

@app.route('/api/analysis')
def get_analysis():
    """獲取分析數據"""
    with analysis_lock:
        if latest_analysis is None:
            return jsonify({'error': '分析數據尚未準備好'})
        return jsonify(latest_analysis)

# 確保目錄結構存在
def ensure_directories():
    """確保必要的目錄結構存在"""
    directories = ['templates', 'static/css', 'static/js']
    for directory in directories:
        os.makedirs(directory, exist_ok=True)

if __name__ == '__main__':
    # 確保目錄結構存在
    ensure_directories()
    
    # 啟動價格更新線程
    price_thread = threading.Thread(target=update_price, daemon=True)
    price_thread.start()
    
    # 啟動分析更新線程
    analysis_thread = threading.Thread(target=update_analysis, daemon=True)
    analysis_thread.start()
    
    # 運行Flask應用
    app.run(debug=True, use_reloader=False, port=5000) 