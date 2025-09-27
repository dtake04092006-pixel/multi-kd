import discord
from discord.ext import commands
import asyncio
import os
import threading
import json
import logging
from flask import Flask, render_template, request, jsonify, redirect, url_for
from keep_alive import keep_alive
import time

# Cấu hình logging để tiết kiệm RAM
logging.basicConfig(level=logging.WARNING)

# --- Cấu hình ---
KARUTA_ID = 646937666251915264
FIXED_EMOJIS = ["1️⃣", "2️⃣", "3️⃣", "1️⃣", "2️⃣", "3️⃣"]
GRAB_TIMES = [1.3, 2.3, 3.2, 1.3, 2.3, 3.2]

# Lưu trữ cấu hình panels và bots
panels_config = {}
bot_instances = {}
current_account_index = 0
drop_running = False

# Flask app
app = Flask(__name__)

# Lấy danh sách accounts từ env
def get_available_accounts():
    accounts = []
    
    # Lấy tokens từ 1 biến duy nhất, cách nhau bởi dấu phẩy
    tokens_str = os.getenv("TOKENS", "")
    if not tokens_str:
        return accounts
        
    tokens = [token.strip() for token in tokens_str.split(",") if token.strip()]
    
    # Lấy names từ 1 biến duy nhất (optional)
    names_str = os.getenv("NAMES", "")
    names = [name.strip() for name in names_str.split(",") if name.strip()] if names_str else []
    
    # Tạo danh sách accounts
    for i, token in enumerate(tokens):
        name = names[i] if i < len(names) else f"Account{i+1}"
        accounts.append({
            "name": name, 
            "token": token, 
            "id": f"acc{i+1}"
        })
    
    return accounts

AVAILABLE_ACCOUNTS = get_available_accounts()

class OptimizedBot:
    """Bot class tối ưu hóa để tiết kiệm RAM"""
    def __init__(self, token, panels):
        self.token = token
        self.panels = panels  # Dictionary {panel_name: channel_id}
        self.client = None
        self.is_ready = False
        
    async def start(self):
        """Khởi động bot với cấu hình tối ưu"""
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guilds = True
        
        # Tối ưu hóa cho RAM thấp
        self.client = discord.Client(
            intents=intents,
            chunk_guilds_at_startup=False,
            member_cache_flags=discord.MemberCacheFlags.none(),
            max_messages=None  # Không cache messages
        )
        
        @self.client.event
        async def on_ready():
            self.is_ready = True
            print(f"Bot sẵn sàng: {self.client.user}")
            
        @self.client.event
        async def on_message(message):
            if message.author.id == KARUTA_ID and "is dropping 3 cards!" in message.content:
                # Tìm panel tương ứng với channel này
                panel_name = None
                for pname, channel_id in self.panels.items():
                    if str(message.channel.id) == str(channel_id):
                        panel_name = pname
                        break
                
                if panel_name and panel_name in panels_config:
                    # Tìm account index trong panel
                    panel = panels_config[panel_name]
                    for i, acc in enumerate(panel['accounts']):
                        if acc['token'] == self.token:
                            emoji = FIXED_EMOJIS[i % len(FIXED_EMOJIS)]
                            grab_time = GRAB_TIMES[i % len(GRAB_TIMES)]
                            asyncio.create_task(self.react_to_drop(message, emoji, grab_time))
                            break
        
        try:
            await self.client.start(self.token)
        except Exception as e:
            print(f"Lỗi khởi động bot: {e}")
    
    async def react_to_drop(self, message, emoji, delay):
        """React vào drop"""
        await asyncio.sleep(delay)
        try:
            await message.add_reaction(emoji)
            print(f"Đã react {emoji}")
        except Exception as e:
            print(f"Lỗi react: {e}")
    
    async def send_kd(self, channel_id):
        """Gửi lệnh kd"""
        if not self.is_ready or not self.client:
            return False
            
        try:
            channel = self.client.get_channel(int(channel_id))
            if channel:
                await channel.send("kd")
                print(f"Đã gửi kd tại {channel_id}")
                return True
        except Exception as e:
            print(f"Lỗi gửi kd: {e}")
        return False

# Web Routes
@app.route('/')
def index():
    return render_template('index.html', 
                         panels=panels_config, 
                         available_accounts=AVAILABLE_ACCOUNTS,
                         drop_status="Đang chạy" if drop_running else "Dừng")

@app.route('/create_panel', methods=['POST'])
def create_panel():
    panel_name = request.form['panel_name']
    if panel_name in panels_config:
        return jsonify({'error': 'Panel đã tồn tại'}), 400
    
    panels_config[panel_name] = {
        'accounts': [],
        'channels': {}
    }
    return redirect(url_for('index'))

@app.route('/delete_panel/<panel_name>')
def delete_panel(panel_name):
    if panel_name in panels_config:
        del panels_config[panel_name]
        # Dọn dẹp bots
        asyncio.create_task(cleanup_panel_bots(panel_name))
    return redirect(url_for('index'))

@app.route('/add_account', methods=['POST'])
def add_account():
    panel_name = request.form['panel_name']
    account_id = request.form['account_id']
    channel_id = request.form['channel_id']
    
    if panel_name not in panels_config:
        return jsonify({'error': 'Panel không tồn tại'}), 400
    
    panel = panels_config[panel_name]
    
    # Tìm account info
    account_info = None
    for acc in AVAILABLE_ACCOUNTS:
        if acc['id'] == account_id:
            account_info = acc
            break
    
    if not account_info:
        return jsonify({'error': 'Account không hợp lệ'}), 400
    
    if len(panel['accounts']) >= 6:
        return jsonify({'error': 'Panel đã đủ 6 accounts'}), 400
    
    # Thêm account vào panel
    panel['accounts'].append({
        'name': account_info['name'],
        'token': account_info['token'],
        'id': account_info['id']
    })
    panel['channels'][account_info['id']] = channel_id
    
    # Khởi động bot cho account này
    asyncio.create_task(start_account_bot(account_info['token'], panel_name, channel_id))
    
    return redirect(url_for('index'))

@app.route('/remove_account/<panel_name>/<account_id>')
def remove_account(panel_name, account_id):
    if panel_name in panels_config:
        panel = panels_config[panel_name]
        panel['accounts'] = [acc for acc in panel['accounts'] if acc['id'] != account_id]
        if account_id in panel['channels']:
            del panel['channels'][account_id]
        
        # Dọn dẹp bot
        bot_key = f"{panel_name}_{account_id}"
        if bot_key in bot_instances:
            asyncio.create_task(cleanup_bot(bot_key))
    
    return redirect(url_for('index'))

@app.route('/start_drop')
def start_drop():
    global drop_running
    if not drop_running:
        drop_running = True
        asyncio.create_task(drop_loop())
    return redirect(url_for('index'))

@app.route('/stop_drop')
def stop_drop():
    global drop_running
    drop_running = False
    return redirect(url_for('index'))

# Bot Management Functions
async def start_account_bot(token, panel_name, channel_id):
    """Khởi động bot cho một account"""
    bot_key = f"{panel_name}_{token[:10]}"
    
    if bot_key in bot_instances:
        return
    
    panels_for_bot = {panel_name: channel_id}
    bot = OptimizedBot(token, panels_for_bot)
    bot_instances[bot_key] = bot
    
    try:
        await bot.start()
    except Exception as e:
        print(f"Lỗi khởi động bot {bot_key}: {e}")
        if bot_key in bot_instances:
            del bot_instances[bot_key]

async def cleanup_panel_bots(panel_name):
    """Dọn dẹp tất cả bots của một panel"""
    keys_to_remove = []
    for key, bot in bot_instances.items():
        if key.startswith(f"{panel_name}_"):
            keys_to_remove.append(key)
            if bot.client:
                await bot.client.close()
    
    for key in keys_to_remove:
        del bot_instances[key]

async def cleanup_bot(bot_key):
    """Dọn dẹp một bot cụ thể"""
    if bot_key in bot_instances:
        bot = bot_instances[bot_key]
        if bot.client:
            await bot.client.close()
        del bot_instances[bot_key]

async def drop_loop():
    """Vòng lặp drop tối ưu"""
    global current_account_index, drop_running
    
    while drop_running:
        if not panels_config:
            await asyncio.sleep(10)
            continue
            
        # Lấy account index hiện tại (0-5)
        account_idx = current_account_index % 6
        
        tasks = []
        
        # Gửi kd cho tất cả panels với account index tương ứng
        for panel_name, panel in panels_config.items():
            if len(panel['accounts']) > account_idx:
                account = panel['accounts'][account_idx]
                channel_id = panel['channels'].get(account['id'])
                
                if channel_id:
                    # Tìm bot tương ứng
                    bot_key = f"{panel_name}_{account['token'][:10]}"
                    if bot_key in bot_instances:
                        tasks.append(bot_instances[bot_key].send_kd(channel_id))
        
        # Thực hiện tất cả lệnh kd đồng thời
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            success_count = sum(1 for r in results if r is True)
            print(f"Đã gửi kd cho account {account_idx + 1}: {success_count}/{len(tasks)} thành công")
        
        # Chuyển sang account tiếp theo
        current_account_index += 1
        
        # Đợi 305 giây
        await asyncio.sleep(305)

# HTML Template
def create_templates():
    """Tạo template HTML"""
    os.makedirs('templates', exist_ok=True)
    
    html_content = '''<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Karuta Multi-Server Manager</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }
        .container { max-width: 1200px; margin: 0 auto; background: white; padding: 20px; border-radius: 8px; }
        .header { text-align: center; color: #333; margin-bottom: 30px; }
        .status { padding: 10px; margin: 10px 0; border-radius: 5px; text-align: center; font-weight: bold; }
        .status.running { background: #d4edda; color: #155724; }
        .status.stopped { background: #f8d7da; color: #721c24; }
        .controls { margin: 20px 0; text-align: center; }
        .btn { padding: 10px 20px; margin: 5px; border: none; border-radius: 5px; cursor: pointer; text-decoration: none; display: inline-block; }
        .btn-primary { background: #007bff; color: white; }
        .btn-success { background: #28a745; color: white; }
        .btn-danger { background: #dc3545; color: white; }
        .btn-warning { background: #ffc107; color: #212529; }
        .panel { border: 1px solid #ddd; margin: 20px 0; padding: 15px; border-radius: 5px; background: #f9f9f9; }
        .panel-header { font-size: 18px; font-weight: bold; margin-bottom: 10px; color: #333; }
        .form-group { margin: 10px 0; }
        .form-group label { display: inline-block; width: 120px; font-weight: bold; }
        .form-group input, .form-group select { padding: 5px; width: 200px; }
        .account-list { margin: 10px 0; }
        .account-item { padding: 8px; margin: 5px 0; background: #e9ecef; border-radius: 3px; display: flex; justify-content: space-between; align-items: center; }
        .create-panel { background: #fff; padding: 20px; margin: 20px 0; border-radius: 5px; border: 2px dashed #007bff; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🎴 Karuta Multi-Server Manager</h1>
            <div class="status {{ 'running' if drop_status == 'Đang chạy' else 'stopped' }}">
                Trạng thái Drop: {{ drop_status }}
            </div>
        </div>

        <div class="controls">
            <a href="/start_drop" class="btn btn-success">▶️ Bắt đầu Drop</a>
            <a href="/stop_drop" class="btn btn-danger">⏹️ Dừng Drop</a>
        </div>

        <div class="create-panel">
            <h3>➕ Tạo Panel Mới</h3>
            <form method="POST" action="/create_panel">
                <div class="form-group">
                    <label>Tên Panel:</label>
                    <input type="text" name="panel_name" required placeholder="VD: Server1, Guild2...">
                    <button type="submit" class="btn btn-primary">Tạo Panel</button>
                </div>
            </form>
        </div>

        {% for panel_name, panel in panels.items() %}
        <div class="panel">
            <div class="panel-header">
                📋 Panel: {{ panel_name }} ({{ panel.accounts|length }}/6 accounts)
                <a href="/delete_panel/{{ panel_name }}" class="btn btn-danger" 
                   onclick="return confirm('Xóa panel này?')" style="float: right;">❌ Xóa</a>
            </div>

            <div class="account-list">
                {% for account in panel.accounts %}
                <div class="account-item">
                    <span>👤 {{ account.name }} → 📍 Channel: {{ panel.channels[account.id] }}</span>
                    <a href="/remove_account/{{ panel_name }}/{{ account.id }}" 
                       class="btn btn-warning" onclick="return confirm('Xóa account này?')">🗑️</a>
                </div>
                {% endfor %}
            </div>

            {% if panel.accounts|length < 6 %}
            <form method="POST" action="/add_account">
                <input type="hidden" name="panel_name" value="{{ panel_name }}">
                <div class="form-group">
                    <label>Account:</label>
                    <select name="account_id" required>
                        <option value="">Chọn account...</option>
                        {% for acc in available_accounts %}
                        <option value="{{ acc.id }}">{{ acc.name }}</option>
                        {% endfor %}
                    </select>
                </div>
                <div class="form-group">
                    <label>Channel ID:</label>
                    <input type="text" name="channel_id" required placeholder="123456789012345678">
                    <button type="submit" class="btn btn-success">➕ Thêm</button>
                </div>
            </form>
            {% endif %}
        </div>
        {% endfor %}

        {% if not panels %}
        <div style="text-align: center; color: #666; margin: 50px 0;">
            <p>🎯 Chưa có panel nào. Tạo panel đầu tiên để bắt đầu!</p>
        </div>
        {% endif %}
    </div>
</body>
</html>'''
    
    with open('templates/index.html', 'w', encoding='utf-8') as f:
        f.write(html_content)

async def main():
    """Hàm main tối ưu"""
    # Tạo templates
    create_templates()
    
    # Khởi động keep_alive trong thread riêng
    keep_alive_thread = threading.Thread(target=lambda: app.run(host='0.0.0.0', port=8080, debug=False))
    keep_alive_thread.daemon = True
    keep_alive_thread.start()
    
    print("🚀 Karuta Multi-Server Manager đã khởi động!")
    print(f"📊 Tìm thấy {len(AVAILABLE_ACCOUNTS)} accounts")
    
    # Giữ chương trình chạy
    while True:
        await asyncio.sleep(60)
        # Dọn dẹp bộ nhớ định kỳ
        import gc
        gc.collect()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Đang dừng chương trình...")
