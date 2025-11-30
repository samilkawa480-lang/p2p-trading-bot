from flask import Flask, jsonify, request
from flask_cors import CORS
import os
import json
import time
import hashlib
import hmac
from datetime import datetime
import requests
import threading

app = Flask(__name__)
CORS(app)

# ============================================
# 🔐 API CONFIGURATION
# ============================================
BINANCE_API_KEY = os.environ.get('BINANCE_API_KEY', '')
BINANCE_SECRET_KEY = os.environ.get('BINANCE_SECRET_KEY', '')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')

# Exchange API URLs
BINANCE_BASE_URL = 'https://api.binance.com'
BINANCE_TESTNET_URL = 'https://testnet.binance.vision'
KUCOIN_BASE_URL = 'https://api.kucoin.com'
MEXC_BASE_URL = 'https://api.mexc.com'
GATE_BASE_URL = 'https://api.gateio.ws'

# ============================================
# 📊 TRADING DATA STORAGE
# ============================================

# Demo Account
demo_account = {
    'balance': 10000.00,
    'initial_balance': 10000.00,
    'holdings': {},
    'trade_history': [],
    'total_profit': 0,
    'today_profit': 0,
    'trades_today': 0,
    'wins': 0,
    'losses': 0,
    'scams_blocked': 0
}

# Real Account
real_account = {
    'balance': 0,
    'holdings': {},
    'trade_history': [],
    'total_profit': 0,
    'today_profit': 0,
    'trades_today': 0,
    'wins': 0,
    'losses': 0,
    'scams_blocked': 0
}

# Grid Bot State
grid_bots = {
    'demo': [],
    'real': []
}

# Active Signals
active_signals = []

# Blocked Traders (P2P)
blocked_traders = []

# ============================================
# 🔧 HELPER FUNCTIONS
# ============================================

def get_timestamp():
    return int(time.time() * 1000)

def create_signature(query_string, secret):
    return hmac.new(
        secret.encode('utf-8'),
        query_string.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()

def get_binance_price(symbol='BTCUSDT'):
    """Get real-time price from Binance"""
    try:
        response = requests.get(
            f'{BINANCE_BASE_URL}/api/v3/ticker/price',
            params={'symbol': symbol},
            timeout=5
        )
        data = response.json()
        return float(data['price'])
    except Exception as e:
        print(f"Error getting price: {e}")
        return None

def get_all_prices():
    """Get prices for multiple pairs"""
    try:
        response = requests.get(
            f'{BINANCE_BASE_URL}/api/v3/ticker/price',
            timeout=5
        )
        data = response.json()
        prices = {item['symbol']: float(item['price']) for item in data}
        return prices
    except Exception as e:
        print(f"Error getting prices: {e}")
        return {}

def calculate_safety_score(trader):
    """Calculate P2P trader safety score (0-100)"""
    score = 0
    
    if trader.get('verified', False):
        score += 25
    
    completion = trader.get('completion_rate', 0)
    score += min(25, int((completion / 100) * 25))
    
    trades = trader.get('trade_count', 0)
    score += min(20, int((trades / 500) * 20))
    
    age_days = trader.get('account_age_days', 0)
    score += min(15, int((age_days / 365) * 15))
    
    reviews = trader.get('positive_reviews', 0)
    score += min(10, int((reviews / 100) * 10))
    
    if trader.get('online', False):
        score += 5
    
    return score

def analyze_trader(trader):
    """Full trader analysis"""
    score = calculate_safety_score(trader)
    
    red_flags = []
    green_flags = []
    
    if not trader.get('verified'):
        red_flags.append("Not verified")
    else:
        green_flags.append("Verified ✓")
    
    if trader.get('completion_rate', 0) < 90:
        red_flags.append(f"Low completion ({trader.get('completion_rate')}%)")
    elif trader.get('completion_rate', 0) >= 98:
        green_flags.append(f"Excellent completion ({trader.get('completion_rate')}%)")
    
    if trader.get('trade_count', 0) < 50:
        red_flags.append(f"Few trades ({trader.get('trade_count')})")
    elif trader.get('trade_count', 0) >= 500:
        green_flags.append(f"Experienced ({trader.get('trade_count')} trades)")
    
    if trader.get('account_age_days', 0) < 30:
        red_flags.append(f"New account ({trader.get('account_age_days')} days)")
    elif trader.get('account_age_days', 0) >= 365:
        green_flags.append(f"Established account")
    
    risk_level = "LOW" if score >= 80 else "MEDIUM" if score >= 60 else "HIGH"
    recommendation = "SAFE" if score >= 80 else "CAUTION" if score >= 60 else "AVOID"
    
    return {
        'score': score,
        'risk_level': risk_level,
        'recommendation': recommendation,
        'red_flags': red_flags,
        'green_flags': green_flags,
        'scam_probability': max(0, 100 - score)
    }

# ============================================
# 📈 TECHNICAL INDICATORS
# ============================================

def calculate_rsi(prices, period=14):
    """Calculate RSI indicator"""
    if len(prices) < period + 1:
        return 50
    
    deltas = [prices[i] - prices[i-1] for i in range(1, len(prices))]
    gains = [d if d > 0 else 0 for d in deltas]
    losses = [-d if d < 0 else 0 for d in deltas]
    
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    
    if avg_loss == 0:
        return 100
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    
    return round(rsi, 2)

def calculate_sma(prices, period=20):
    """Calculate Simple Moving Average"""
    if len(prices) < period:
        return prices[-1] if prices else 0
    return sum(prices[-period:]) / period

def get_market_analysis(symbol='BTCUSDT'):
    """Get full market analysis for a symbol"""
    try:
        # Get klines (candlestick data)
        response = requests.get(
            f'{BINANCE_BASE_URL}/api/v3/klines',
            params={
                'symbol': symbol,
                'interval': '1h',
                'limit': 100
            },
            timeout=10
        )
        klines = response.json()
        
        closes = [float(k[4]) for k in klines]
        highs = [float(k[2]) for k in klines]
        lows = [float(k[3]) for k in klines]
        volumes = [float(k[5]) for k in klines]
        
        current_price = closes[-1]
        rsi = calculate_rsi(closes)
        sma_20 = calculate_sma(closes, 20)
        sma_50 = calculate_sma(closes, 50)
        avg_volume = sum(volumes[-20:]) / 20
        current_volume = volumes[-1]
        
        # Determine trend
        trend = "BULLISH" if sma_20 > sma_50 else "BEARISH" if sma_20 < sma_50 else "NEUTRAL"
        
        # Determine signal
        signal = "HOLD"
        confidence = 50
        
        if rsi < 30 and current_price > sma_20:
            signal = "BUY"
            confidence = min(90, 60 + (30 - rsi))
        elif rsi > 70 and current_price < sma_20:
            signal = "SELL"
            confidence = min(90, 60 + (rsi - 70))
        elif rsi < 40 and trend == "BULLISH":
            signal = "BUY"
            confidence = 65
        elif rsi > 60 and trend == "BEARISH":
            signal = "SELL"
            confidence = 65
        
        return {
            'symbol': symbol,
            'current_price': current_price,
            'rsi': rsi,
            'sma_20': round(sma_20, 2),
            'sma_50': round(sma_50, 2),
            'trend': trend,
            'signal': signal,
            'confidence': confidence,
            'volume_ratio': round(current_volume / avg_volume, 2) if avg_volume > 0 else 1,
            'support': min(lows[-20:]),
            'resistance': max(highs[-20:]),
            'timestamp': datetime.now().isoformat()
        }
    except Exception as e:
        print(f"Error in market analysis: {e}")
        return None

# ============================================
# 🤖 GRID BOT ENGINE
# ============================================

class GridBot:
    def __init__(self, bot_id, symbol, lower_price, upper_price, grids, investment, mode='demo'):
        self.bot_id = bot_id
        self.symbol = symbol
        self.lower_price = lower_price
        self.upper_price = upper_price
        self.grids = grids
        self.investment = investment
        self.mode = mode
        self.active = False
        self.grid_levels = []
        self.orders = []
        self.trades = []
        self.profit = 0
        self.created_at = datetime.now().isoformat()
        
        # Calculate grid levels
        self.calculate_grids()
    
    def calculate_grids(self):
        """Calculate grid price levels"""
        price_range = self.upper_price - self.lower_price
        grid_spacing = price_range / self.grids
        
        self.grid_levels = []
        for i in range(self.grids + 1):
            price = self.lower_price + (i * grid_spacing)
            self.grid_levels.append(round(price, 2))
        
        self.amount_per_grid = self.investment / self.grids
    
    def start(self):
        """Start the grid bot"""
        self.active = True
        return {'status': 'started', 'bot_id': self.bot_id}
    
    def stop(self):
        """Stop the grid bot"""
        self.active = False
        return {'status': 'stopped', 'bot_id': self.bot_id}
    
    def check_and_execute(self, current_price):
        """Check price and execute trades if needed"""
        if not self.active:
            return None
        
        executed_trades = []
        
        for i, level in enumerate(self.grid_levels):
            # Check for buy opportunity (price dropped to grid level)
            if current_price <= level and not self._has_buy_at_level(level):
                trade = self._execute_buy(level, current_price)
                if trade:
                    executed_trades.append(trade)
            
            # Check for sell opportunity (price rose to grid level)
            elif current_price >= level and self._has_holding_below(level):
                trade = self._execute_sell(level, current_price)
                if trade:
                    executed_trades.append(trade)
        
        return executed_trades
    
    def _has_buy_at_level(self, level):
        """Check if we already bought at this level"""
        tolerance = (self.upper_price - self.lower_price) / self.grids / 2
        for order in self.orders:
            if order['type'] == 'BUY' and abs(order['price'] - level) < tolerance:
                return True
        return False
    
    def _has_holding_below(self, level):
        """Check if we have holdings bought below this level"""
        for order in self.orders:
            if order['type'] == 'BUY' and order['price'] < level and not order.get('sold'):
                return True
        return False
    
    def _execute_buy(self, level, actual_price):
        """Execute a buy order"""
        amount_usd = self.amount_per_grid
        amount_crypto = amount_usd / actual_price
        fee = amount_usd * 0.001  # 0.1% fee
        
        order = {
            'id': len(self.orders) + 1,
            'type': 'BUY',
            'price': actual_price,
            'grid_level': level,
            'amount_usd': amount_usd,
            'amount_crypto': amount_crypto,
            'fee': fee,
            'timestamp': datetime.now().isoformat(),
            'sold': False
        }
        
        self.orders.append(order)
        
        trade = {
            'type': 'BUY',
            'price': actual_price,
            'amount': amount_crypto,
            'value': amount_usd,
            'fee': fee,
            'timestamp': datetime.now().isoformat()
        }
        self.trades.append(trade)
        
        return trade
    
    def _execute_sell(self, level, actual_price):
        """Execute a sell order"""
        # Find the lowest buy order that hasn't been sold
        buy_order = None
        for order in self.orders:
            if order['type'] == 'BUY' and order['price'] < level and not order.get('sold'):
                if buy_order is None or order['price'] < buy_order['price']:
                    buy_order = order
        
        if not buy_order:
            return None
        
        buy_order['sold'] = True
        
        amount_crypto = buy_order['amount_crypto']
        amount_usd = amount_crypto * actual_price
        fee = amount_usd * 0.001  # 0.1% fee
        
        profit = amount_usd - buy_order['amount_usd'] - fee - buy_order['fee']
        self.profit += profit
        
        sell_order = {
            'id': len(self.orders) + 1,
            'type': 'SELL',
            'price': actual_price,
            'grid_level': level,
            'amount_usd': amount_usd,
            'amount_crypto': amount_crypto,
            'fee': fee,
            'profit': profit,
            'timestamp': datetime.now().isoformat(),
            'buy_order_id': buy_order['id']
        }
        
        self.orders.append(sell_order)
        
        trade = {
            'type': 'SELL',
            'price': actual_price,
            'amount': amount_crypto,
            'value': amount_usd,
            'fee': fee,
            'profit': profit,
            'timestamp': datetime.now().isoformat()
        }
        self.trades.append(trade)
        
        return trade
    
    def get_status(self):
        """Get current bot status"""
        return {
            'bot_id': self.bot_id,
            'symbol': self.symbol,
            'active': self.active,
            'mode': self.mode,
            'lower_price': self.lower_price,
            'upper_price': self.upper_price,
            'grids': self.grids,
            'investment': self.investment,
            'profit': round(self.profit, 2),
            'total_trades': len(self.trades),
            'open_orders': len([o for o in self.orders if o['type'] == 'BUY' and not o.get('sold')]),
            'grid_levels': self.grid_levels,
            'created_at': self.created_at
        }

# Store active grid bots
active_grid_bots = {}

# ============================================
# 🌐 API ENDPOINTS
# ============================================

@app.route('/')
def home():
    """Health check"""
    return jsonify({
        'status': 'online',
        'service': 'P2P Safe Trader Bot',
        'version': '2.0',
        'features': {
            'p2p_trading': True,
            'spot_trading': True,
            'grid_bot': True,
            'ai_signals': True,
            'scammer_detection': True,
            'demo_mode': True,
            'real_mode': True
        },
        'timestamp': datetime.now().isoformat()
    })

@app.route('/api/status')
def get_status():
    """Get system status"""
    return jsonify({
        'binance_connected': bool(BINANCE_API_KEY),
        'ai_connected': bool(GEMINI_API_KEY),
        'demo_account': {
            'balance': demo_account['balance'],
            'profit': demo_account['total_profit'],
            'trades': demo_account['trades_today']
        },
        'active_bots': len(active_grid_bots),
        'timestamp': datetime.now().isoformat()
    })

# ============================================
# 💰 ACCOUNT ENDPOINTS
# ============================================

@app.route('/api/account/demo')
def get_demo_account():
    """Get demo account info"""
    return jsonify({
        'mode': 'demo',
        'balance': demo_account['balance'],
        'initial_balance': demo_account['initial_balance'],
        'holdings': demo_account['holdings'],
        'total_profit': round(demo_account['total_profit'], 2),
        'today_profit': round(demo_account['today_profit'], 2),
        'trades_today': demo_account['trades_today'],
        'win_rate': round(demo_account['wins'] / max(1, demo_account['wins'] + demo_account['losses']) * 100, 1),
        'scams_blocked': demo_account['scams_blocked']
    })

@app.route('/api/account/demo/reset', methods=['POST'])
def reset_demo_account():
    """Reset demo account"""
    global demo_account
    demo_account = {
        'balance': 10000.00,
        'initial_balance': 10000.00,
        'holdings': {},
        'trade_history': [],
        'total_profit': 0,
        'today_profit': 0,
        'trades_today': 0,
        'wins': 0,
        'losses': 0,
        'scams_blocked': 0
    }
    return jsonify({'success': True, 'message': 'Demo account reset to $10,000'})

@app.route('/api/account/real')
def get_real_account():
    """Get real account info from Binance"""
    if not BINANCE_API_KEY or not BINANCE_SECRET_KEY:
        return jsonify({'error': 'Binance API not configured'})
    
    try:
        timestamp = get_timestamp()
        query_string = f'timestamp={timestamp}'
        signature = create_signature(query_string, BINANCE_SECRET_KEY)
        
        response = requests.get(
            f'{BINANCE_BASE_URL}/api/v3/account',
            params={
                'timestamp': timestamp,
                'signature': signature
            },
            headers={'X-MBX-APIKEY': BINANCE_API_KEY},
            timeout=10
        )
        
        data = response.json()
        
        if 'balances' in data:
            balances = {}
            total_usd = 0
            
            prices = get_all_prices()
            
            for asset in data['balances']:
                free = float(asset['free'])
                locked = float(asset['locked'])
                total = free + locked
                
                if total > 0:
                    symbol = asset['asset']
                    usd_value = total
                    
                    if symbol == 'USDT':
                        usd_value = total
                    elif f"{symbol}USDT" in prices:
                        usd_value = total * prices[f"{symbol}USDT"]
                    
                    balances[symbol] = {
                        'free': free,
                        'locked': locked,
                        'total': total,
                        'usd_value': round(usd_value, 2)
                    }
                    total_usd += usd_value
            
            return jsonify({
                'mode': 'real',
                'balances': balances,
                'total_usd': round(total_usd, 2),
                'timestamp': datetime.now().isoformat()
            })
        else:
            return jsonify({'error': data.get('msg', 'Unknown error')})
    
    except Exception as e:
        return jsonify({'error': str(e)})

# ============================================
# 📊 MARKET DATA ENDPOINTS
# ============================================

@app.route('/api/price/<symbol>')
def get_price(symbol):
    """Get current price for a symbol"""
    price = get_binance_price(symbol.upper())
    if price:
        return jsonify({
            'symbol': symbol.upper(),
            'price': price,
            'timestamp': datetime.now().isoformat()
        })
    return jsonify({'error': 'Could not fetch price'})

@app.route('/api/prices')
def get_prices():
    """Get prices for common pairs"""
    symbols = ['BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT', 'XRPUSDT', 'DOGEUSDT']
    prices = {}
    
    all_prices = get_all_prices()
    for symbol in symbols:
        if symbol in all_prices:
            prices[symbol] = all_prices[symbol]
    
    return jsonify({
        'prices': prices,
        'timestamp': datetime.now().isoformat()
    })

@app.route('/api/analysis/<symbol>')
def get_analysis(symbol):
    """Get technical analysis for a symbol"""
    analysis = get_market_analysis(symbol.upper())
    if analysis:
        return jsonify(analysis)
    return jsonify({'error': 'Could not analyze symbol'})

# ============================================
# 🤖 GRID BOT ENDPOINTS
# ============================================

@app.route('/api/gridbot/create', methods=['POST'])
def create_grid_bot():
    """Create a new grid bot"""
    data = request.json
    
    bot_id = f"grid_{int(time.time())}"
    
    bot = GridBot(
        bot_id=bot_id,
        
