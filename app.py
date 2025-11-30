from flask import Flask, jsonify, request
from flask_cors import CORS
import os
import time
import hashlib
import hmac
from datetime import datetime
import requests

app = Flask(__name__)
CORS(app)

# API Configuration
BINANCE_API_KEY = os.environ.get('BINANCE_API_KEY', '')
BINANCE_SECRET_KEY = os.environ.get('BINANCE_SECRET_KEY', '')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')

BINANCE_BASE_URL = 'https://api.binance.com'

# Demo Account
demo_account = {
    'balance': 10000.00,
    'holdings': {},
    'trade_history': [],
    'total_profit': 0,
    'today_profit': 0,
    'trades_today': 0,
    'wins': 0,
    'losses': 0
}

def get_timestamp():
    return int(time.time() * 1000)

def create_signature(query_string, secret):
    return hmac.new(
        secret.encode('utf-8'),
        query_string.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()

def get_binance_price(symbol='BTCUSDT'):
    try:
        response = requests.get(
            f'{BINANCE_BASE_URL}/api/v3/ticker/price',
            params={'symbol': symbol},
            timeout=5
        )
        data = response.json()
        return float(data['price'])
    except Exception as e:
        return None

def get_all_binance_prices():
    try:
        response = requests.get(
            f'{BINANCE_BASE_URL}/api/v3/ticker/price',
            timeout=5
        )
        data = response.json()
        prices = {}
        for item in data:
            prices[item['symbol']] = float(item['price'])
        return prices
    except Exception as e:
        return {}

def calculate_safety_score(trader):
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

@app.route('/')
def home():
    return jsonify({
        'status': 'online',
        'service': 'P2P Safe Trader Bot',
        'version': '2.0',
        'timestamp': datetime.now().isoformat()
    })

@app.route('/api/status')
def get_status():
    return jsonify({
        'binance_connected': bool(BINANCE_API_KEY and BINANCE_SECRET_KEY),
        'ai_connected': bool(GEMINI_API_KEY),
        'demo_balance': demo_account['balance'],
        'timestamp': datetime.now().isoformat()
    })

@app.route('/api/account/demo')
def get_demo_account():
    return jsonify({
        'mode': 'demo',
        'balance': demo_account['balance'],
        'holdings': demo_account['holdings'],
        'total_profit': round(demo_account['total_profit'], 2),
        'today_profit': round(demo_account['today_profit'], 2),
        'trades_today': demo_account['trades_today']
    })

@app.route('/api/account/demo/reset', methods=['POST'])
def reset_demo():
    global demo_account
    demo_account = {
        'balance': 10000.00,
        'holdings': {},
        'trade_history': [],
        'total_profit': 0,
        'today_profit': 0,
        'trades_today': 0,
        'wins': 0,
        'losses': 0
    }
    return jsonify({'success': True, 'message': 'Demo account reset'})

@app.route('/api/account/real')
def get_real_account():
    if not BINANCE_API_KEY or not BINANCE_SECRET_KEY:
        return jsonify({'error': 'Binance API not configured', 'balance': 0})
    
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
            
            prices = get_all_binance_prices()
            
            for asset in data['balances']:
                free = float(asset['free'])
                locked = float(asset['locked'])
                total = free + locked
                
                if total > 0:
                    symbol = asset['asset']
                    usd_value = 0
                    
                    if symbol == 'USDT':
                        usd_value = total
                    elif symbol == 'BUSD':
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
            return jsonify({
                'error': data.get('msg', 'Unknown error'),
                'balance': 0
            })
    
    except Exception as e:
        return jsonify({
            'error': str(e),
            'balance': 0
        })

@app.route('/api/price/<symbol>')
def get_price(symbol):
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
    symbols = ['BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT', 'XRPUSDT', 'DOGEUSDT']
    prices = {}
    for symbol in symbols:
        price = get_binance_price(symbol)
        if price:
            prices[symbol] = price
    return jsonify({
        'prices': prices,
        'timestamp': datetime.now().isoformat()
    })

@app.route('/api/p2p/traders')
def get_p2p_traders():
    sellers = [
        {
            'name': 'CryptoKing254',
            'price': 129,
            'verified': True,
            'completion_rate': 99.2,
            'trade_count': 1247,
            'account_age_days': 730,
            'positive_reviews': 98,
            'online': True
        },
        {
            'name': 'MombasaTrader',
            'price': 130,
            'verified': True,
            'completion_rate': 94.5,
            'trade_count': 342,
            'account_age_days': 240,
            'positive_reviews': 91,
            'online': True
        },
        {
            'name': 'FastMoney001',
            'price': 125,
            'verified': False,
            'completion_rate': 67,
            'trade_count': 12,
            'account_age_days': 5,
            'positive_reviews': 45,
            'online': False
        }
    ]
    
    buyers = [
        {
            'name': 'TrustedBuyer',
            'price': 132,
            'verified': True,
            'completion_rate': 97.8,
            'trade_count': 892,
            'account_age_days': 548,
            'positive_reviews': 96,
            'online': True
        },
        {
            'name': 'KenyaCrypto',
            'price': 131,
            'verified': True,
            'completion_rate': 95.2,
            'trade_count': 456,
            'account_age_days': 365,
            'positive_reviews': 93,
            'online': True
        }
    ]
    
    for trader in sellers + buyers:
        trader['score'] = calculate_safety_score(trader)
    
    sellers.sort(key=lambda x: x['score'], reverse=True)
    buyers.sort(key=lambda x: x['score'], reverse=True)
    
    return jsonify({
        'sellers': sellers,
        'buyers': buyers,
        'market_rate': 130,
        'timestamp': datetime.now().isoformat()
    })

@app.route('/api/trade/demo', methods=['POST'])
def demo_trade():
    global demo_account
    data = request.json
    trade_type = data.get('type', 'BUY')
    symbol = data.get('symbol', 'BTCUSDT')
    amount_usd = float(data.get('amount', 100))
    
    current_price = get_binance_price(symbol)
    if not current_price:
        return jsonify({'error': 'Could not get price'})
    
    fee = amount_usd * 0.001
    
    if trade_type == 'BUY':
        if demo_account['balance'] < amount_usd:
            return jsonify({'error': 'Insufficient balance'})
        
        amount_crypto = (amount_usd - fee) / current_price
        demo_account['balance'] -= amount_usd
        
        if symbol not in demo_account['holdings']:
            demo_account['holdings'][symbol] = {'amount': 0, 'avg_price': 0}
        
        holdings = demo_account['holdings'][symbol]
        total_value = holdings['amount'] * holdings['avg_price'] + amount_crypto * current_price
        holdings['amount'] += amount_crypto
        if holdings['amount'] > 0:
            holdings['avg_price'] = total_value / holdings['amount']
        
        trade = {
            'type': 'BUY',
            'symbol': symbol,
            'amount_usd': amount_usd,
            'amount_crypto': amount_crypto,
            'price': current_price,
            'fee': fee,
            'timestamp': datetime.now().isoformat()
        }
    else:
        if symbol not in demo_account['holdings']:
            return jsonify({'error': 'No holdings to sell'})
        
        holdings = demo_account['holdings'][symbol]
        if holdings['amount'] <= 0:
            return jsonify({'error': 'No holdings to sell'})
        
        amount_crypto = min(amount_usd / current_price, holdings['amount'])
        amount_received = amount_crypto * current_price - fee
        profit = (current_price - holdings['avg_price']) * amount_crypto - fee
        
        holdings['amount'] -= amount_crypto
        demo_account['balance'] += amount_received
        demo_account['total_profit'] += profit
        demo_account['today_profit'] += profit
        
        if profit > 0:
            demo_account['wins'] += 1
        else:
            demo_account['losses'] += 1
        
        trade = {
            'type': 'SELL',
            'symbol': symbol,
            'amount_usd': amount_received,
            'amount_crypto': amount_crypto,
            'price': current_price,
            'fee': fee,
            'profit': profit,
            'timestamp': datetime.now().isoformat()
        }
    
    demo_account['trades_today'] += 1
    demo_account['trade_history'].append(trade)
    
    return jsonify({
        'success': True,
        'trade': trade,
        'balance': round(demo_account['balance'], 2)
    })

@app.route('/api/trade/real', methods=['POST'])
def real_trade():
    if not BINANCE_API_KEY or not BINANCE_SECRET_KEY:
        return jsonify({'error': 'Binance API not configured'})
    
    data = request.json
    trade_type = data.get('type', 'BUY').upper()
    symbol = data.get('symbol', 'BTCUSDT')
    amount = float(data.get('amount', 0))
    
    if amount <= 0:
        return jsonify({'error': 'Invalid amount'})
    
    try:
        timestamp = get_timestamp()
        
        if trade_type == 'BUY':
            params = {
                'symbol': symbol,
                'side': 'BUY',
                'type': 'MARKET',
                'quoteOrderQty': amount,
                'timestamp': timestamp
            }
        else:
            params = {
                'symbol': symbol,
                'side': 'SELL',
                'type': 'MARKET',
                'quantity': amount,
                'timestamp': timestamp
            }
        
        query_string = '&'.join([f"{k}={v}" for k, v in params.items()])
        signature = create_signature(query_string, BINANCE_SECRET_KEY)
        params['signature'] = signature
        
        response = requests.post(
            f'{BINANCE_BASE_URL}/api/v3/order',
            params=params,
            headers={'X-MBX-APIKEY': BINANCE_API_KEY},
            timeout=10
        )
        
        result = response.json()
        
        if 'orderId' in result:
            return jsonify({
                'success': True,
                'order': result
            })
        else:
            return jsonify({'error': result.get('msg', 'Order failed')})
    
    except Exception as e:
        return jsonify({'error': str(e)})

@app.route('/api/signals')
def get_signals():
    btc_price = get_binance_price('BTCUSDT')
    eth_price = get_binance_price('ETHUSDT')
    
    signals = [
        {
            'id': 1,
            'symbol': 'BTCUSDT',
            'type': 'BUY',
            'confidence': 75,
            'price': btc_price,
            'timestamp': datetime.now().isoformat()
        },
        {
            'id': 2,
            'symbol': 'ETHUSDT',
            'type': 'HOLD',
            'confidence': 60,
            'price': eth_price,
            'timestamp': datetime.now().isoformat()
        }
    ]
    return jsonify({'signals': signals})

@app.route('/api/exchanges')
def get_exchanges():
    return jsonify({
        'exchanges': [
            {
                'id': 'binance',
                'name': 'Binance',
                'connected': bool(BINANCE_API_KEY and BINANCE_SECRET_KEY),
                'icon': '🟡'
            },
            {
                'id': 'kucoin',
                'name': 'KuCoin',
                'connected': False,
                'icon': '🟢'
            },
            {
                'id': 'mexc',
                'name': 'MEXC',
                'connected': False,
                'icon': '🔵'
            },
            {
                'id': 'gate',
                'name': 'Gate.io',
                'connected': False,
                'icon': '🟣'
            }
        ]
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
