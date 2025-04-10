// DOM 元素引用
const lastUpdateElement = document.getElementById('last-update');
const currentPriceElement = document.getElementById('current-price');
const marketStructureElement = document.getElementById('market-structure');
const liquidityAnalysisElement = document.getElementById('liquidity-analysis');
const entrySignalElement = document.getElementById('entry-signal');

let lastPrice = null;

// 更新價格顯示
function updatePriceDisplay(price, trend) {
    if (!price) return;
    
    // 判斷價格變化方向
    const priceChange = lastPrice ? price > lastPrice ? 'up' : price < lastPrice ? 'down' : 'neutral' : 'neutral';
    const priceClass = priceChange === 'up' ? 'price-up' : priceChange === 'down' ? 'price-down' : '';
    const trendEmoji = priceChange === 'up' ? '📈' : priceChange === 'down' ? '📉' : '↔️';
    
    currentPriceElement.className = `price ${priceClass}`;
    currentPriceElement.innerHTML = `
        <strong>$${price.toLocaleString('en-US', {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2
        })}</strong>
        <span class="trend-indicator">${trendEmoji}</span>
    `;
    
    lastPrice = price;
}

// 更新市場結構分析
function updateMarketStructure(marketStructure) {
    if (!marketStructure) return;

    const trendEmoji = {
        'bullish': '🟢',
        'bearish': '🔴',
        'neutral': '⚪'
    };

    const trendText = {
        'bullish': '看漲',
        'bearish': '看跌',
        'neutral': '中性'
    };

    const trend = marketStructure.trend || 'neutral';

    marketStructureElement.innerHTML = `
        <p><strong>趨勢：</strong>${trendEmoji[trend]} ${trendText[trend]}</p>
        <p><strong>支撐位：</strong>$${marketStructure.support.toLocaleString()}</p>
        <p><strong>阻力位：</strong>$${marketStructure.resistance.toLocaleString()}</p>
    `;
}

// 更新流動性分析
function updateLiquidityAnalysis(data) {
    if (!data) return;

    const { ob_info, fvg_info, entry_signal } = data;
    let html = '<div class="liquidity-status">';

    // 添加OB信息
    if (ob_info && ob_info.type !== 'none') {
        const obType = ob_info.type === 'bullish' ? '看漲' : '看跌';
        html += `
            <p><strong>訂單區塊(OB)：</strong>${obType} ${ob_info.type === 'bullish' ? '🟢' : '🔴'}</p>
            <p>高點：$${ob_info.high ? ob_info.high.toLocaleString() : 'N/A'}</p>
            <p>低點：$${ob_info.low ? ob_info.low.toLocaleString() : 'N/A'}</p>
        `;
    } else {
        html += '<p><strong>訂單區塊(OB)：</strong>無</p>';
    }

    // 添加FVG信息
    if (fvg_info && fvg_info.type !== 'none') {
        const fvgType = fvg_info.type === 'bullish' ? '看漲' : '看跌';
        html += `
            <p><strong>公允價值缺口(FVG)：</strong>${fvgType} ${fvg_info.type === 'bullish' ? '🟢' : '🔴'}</p>
            <p>高點：$${fvg_info.high ? fvg_info.high.toLocaleString() : 'N/A'}</p>
            <p>低點：$${fvg_info.low ? fvg_info.low.toLocaleString() : 'N/A'}</p>
        `;
    } else {
        html += '<p><strong>公允價值缺口(FVG)：</strong>無</p>';
    }

    // 添加進場信號
    if (entry_signal && entry_signal.signal !== 'none') {
        html += `
            <div class="entry-signal">
                <h3>🎯 進場信號</h3>
                <p><strong>方向：</strong>${entry_signal.direction}</p>
                <p><strong>進場價格：</strong>${entry_signal.price}</p>
                <p><strong>止損價格：</strong>${entry_signal.stop_loss}</p>
                <p><strong>TP1 價格：</strong>${entry_signal.tp1_price}</p>
                <p><strong>TP2 價格：</strong>${entry_signal.tp2_price}</p>
                <div class="risk-reward">
                    <p><strong>TP1 風險報酬比：</strong>${entry_signal.risk_reward1}</p>
                    <p><strong>TP2 風險報酬比：</strong>${entry_signal.risk_reward2}</p>
                </div>
            </div>
        `;
    }

    html += '</div>';
    liquidityAnalysisElement.innerHTML = html;
}

// 更新最後更新時間
function updateLastUpdate(timestamp) {
    if (!timestamp) {
        timestamp = new Date().toLocaleString('zh-TW');
    }
    lastUpdateElement.textContent = `最後更新：${timestamp}`;
}

// 更新價格
async function updatePrice() {
    try {
        const response = await fetch('/api/price');
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        const data = await response.json();

        if (data.error) {
            throw new Error(data.error);
        }

        // 更新價格和時間戳
        updatePriceDisplay(data.price);
        updateLastUpdate(data.timestamp);

    } catch (error) {
        console.error('更新價格時發生錯誤：', error);
        currentPriceElement.innerHTML = '<p class="error">價格更新失敗</p>';
    }
}

// 更新分析
async function updateAnalysis() {
    try {
        const response = await fetch('/api/analysis');
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        const data = await response.json();

        if (data.error) {
            throw new Error(data.error);
        }

        updateMarketStructure(data.market_structure);
        updateLiquidityAnalysis(data);

    } catch (error) {
        console.error('更新分析時發生錯誤：', error);
        const errorMessage = '數據更新時發生錯誤，請稍後再試。';
        marketStructureElement.innerHTML = `<p class="error">${errorMessage}</p>`;
        liquidityAnalysisElement.innerHTML = `<p class="error">${errorMessage}</p>`;
    }
}

// 初始化
document.addEventListener('DOMContentLoaded', () => {
    // 立即執行一次更新
    updatePrice();
    updateAnalysis();

    // 設置定時更新
    setInterval(updatePrice, 1000);    // 每秒更新價格
    setInterval(updateAnalysis, 60000); // 每分鐘更新分析
}); 