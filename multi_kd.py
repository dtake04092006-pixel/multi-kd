import discord
from discord.ext import commands
import asyncio
import os
import threading
import json
import logging
from flask import Flask, render_template, request, jsonify, redirect, url_for
import time
from concurrent.futures import ThreadPoolExecutor

# Cấu hình logging để tiết kiệm RAM
logging.basicConfig(level=logging.WARNING)

# --- Cấu hình ---
KARUTA_ID = 646937666251915264
FIXED_EMOJIS = ["1️⃣", "2️⃣", "3️⃣", "1️⃣", "2️⃣", "3️⃣"]
GRAB_TIMES = [1.3, 2.3, 3.2, 1.3, 2.3, 3.2]

# Lưu trữ cấu hình panels và bots
guilds_config = {}
bot_instances = {}
current_account_index = 0
drop_running = False
loop = None

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
    def __init__(self, token, guild_name, account_index):
        self.token = token
        self.guild_name = guild_name
        self.account_index = account_index
        self.client = None
        self.is_ready = False
        self.channel_id = None
        
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
            if self.guild_name in guilds_config:
                self.channel_id = guilds_config[self.guild_name]['channel_id']
            print(f"✅ Bot {self.account_index+1} sẵn sàng cho Guild: {self.guild_name}")
            
        @self.client.event
        async def on_message(message):
            if (message.author.id == KARUTA_ID and 
                "is dropping 3 cards!" in message.content and 
                str(message.channel.id) == str(self.channel_id)):
                
                emoji = FIXED_EMOJIS[self.account_index % len(FIXED_EMOJIS)]
                grab_time = GRAB_TIMES[self.account_index % len(GRAB_TIMES)]
                asyncio.create_task(self.react_to_drop(message, emoji, grab_time))
        
        try:
            await self.client.start(self.token)
        except Exception as e:
            print(f"❌ Lỗi khởi động bot {self.account_index+1}: {e}")
    
    async def react_to_drop(self, message, emoji, delay):
        """React vào drop"""
        await asyncio.sleep(delay)
        try:
            await message.add_reaction(emoji)
            print(f"🎯 Bot {self.account_index+1} đã react {emoji} tại Guild {self.guild_name}")
        except Exception as e:
            print(f"❌ Lỗi react Bot {self.account_index+1}: {e}")
    
    async def send_kd(self):
        """Gửi lệnh kd"""
        if not self.is_ready or not self.client or not self.channel_id:
            return False
            
        try:
            channel = self.client.get_channel(int(self.channel_id))
            if channel:
                await channel.send("kd")
                print(f"📤 Bot {self.account_index+1} đã gửi kd tại Guild {self.guild_name}")
                return True
        except Exception as e:
            print(f"❌ Lỗi gửi kd Bot {self.account_index+1}: {e}")
        return False

# Web Routes
@app.route('/')
def index():
    return render_template('index.html', 
                         guilds=guilds_config, 
                         available_accounts=AVAILABLE_ACCOUNTS,
                         drop_status="🟢 Đang chạy" if drop_running else "🔴 Dừng")

@app.route('/create_guild', methods=['POST'])
def create_guild():
    guild_name = request.form['guild_name'].strip()
    channel_id = request.form['channel_id'].strip()
    selected_accounts = request.form.getlist('accounts')
    
    if not guild_name or not channel_id:
        return jsonify({'error': 'Vui lòng nhập đầy đủ thông tin'}), 400
    
    if guild_name in guilds_config:
        return jsonify({'error': 'Guild đã tồn tại'}), 400
        
    if len(selected_accounts) != 6:
        return jsonify({'error': 'Phải chọn đúng 6 accounts'}), 400
    
    # Tạo guild config
    guild_accounts = []
    for acc_id in selected_accounts:
        for acc in AVAILABLE_ACCOUNTS:
            if acc['id'] == acc_id:
                guild_accounts.append(acc)
                break
    
    guilds_config[guild_name] = {
        'channel_id': channel_id,
        'accounts': guild_accounts
    }
    
    # Khởi động bots cho guild này
    if loop:
        asyncio.run_coroutine_threadsafe(start_guild_bots(guild_name), loop)
    
    return redirect(url_for('index'))

@app.route('/delete_guild/<guild_name>')
def delete_guild(guild_name):
    if guild_name in guilds_config:
        # Dọn dẹp bots
        if loop:
            asyncio.run_coroutine_threadsafe(cleanup_guild_bots(guild_name), loop)
        del guilds_config[guild_name]
    return redirect(url_for('index'))

@app.route('/start_drop')
def start_drop():
    global drop_running
    if not drop_running and loop:
        drop_running = True
        asyncio.run_coroutine_threadsafe(drop_loop(), loop)
    return redirect(url_for('index'))

@app.route('/stop_drop')
def stop_drop():
    global drop_running
    drop_running = False
    return redirect(url_for('index'))

@app.route('/status')
def status():
    return jsonify({
        'guilds': len(guilds_config),
        'bots': len(bot_instances),
        'drop_running': drop_running,
        'accounts_available': len(AVAILABLE_ACCOUNTS)
    })

# Bot Management Functions
async def start_guild_bots(guild_name):
    """Khởi động tất cả bots cho một guild"""
    if guild_name not in guilds_config:
        return
    
    guild = guilds_config[guild_name]
    tasks = []
    
    for i, account in enumerate(guild['accounts']):
        bot_key = f"{guild_name}_bot{i+1}"
        if bot_key not in bot_instances:
            bot = OptimizedBot(account['token'], guild_name, i)
            bot_instances[bot_key] = bot
            tasks.append(bot.start())
    
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)

async def cleanup_guild_bots(guild_name):
    """Dọn dẹp tất cả bots của một guild"""
    keys_to_remove = []
    for key, bot in bot_instances.items():
        if key.startswith(f"{guild_name}_"):
            keys_to_remove.append(key)
            if bot.client:
                await bot.client.close()
    
    for key in keys_to_remove:
        del bot_instances[key]

async def drop_loop():
    """Vòng lặp drop tối ưu"""
    global current_account_index, drop_running
    
    print("🚀 Bắt đầu Drop Loop!")
    
    while drop_running:
        if not guilds_config:
            await asyncio.sleep(10)
            continue
            
        # Lấy account index hiện tại (0-5)
        account_idx = current_account_index % 6
        
        tasks = []
        
        # Gửi kd cho tất cả guilds với account index tương ứng
        for guild_name in guilds_config:
            bot_key = f"{guild_name}_bot{account_idx+1}"
            if bot_key in bot_instances:
                tasks.append(bot_instances[bot_key].send_kd())
        
        # Thực hiện tất cả lệnh kd đồng thời
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            success_count = sum(1 for r in results if r is True)
            print(f"📊 Account {account_idx + 1}: {success_count}/{len(tasks)} guilds thành công")
        
        # Chuyển sang account tiếp theo
        current_account_index += 1
        
        # Đợi 305 giây
        print(f"⏳ Đợi 305 giây để chuyển sang Account {(current_account_index % 6) + 1}...")
        await asyncio.sleep(305)

# HTML Template với giao diện đẹp
def create_templates():
    """Tạo template HTML với giao diện hiện đại"""
    os.makedirs('templates', exist_ok=True)
    
    html_content = '''<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🎴 Karuta Multi-Guild Manager</title>
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        
        body { 
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; 
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            color: #333;
        }
        
        .container { 
            max-width: 1400px; 
            margin: 0 auto; 
            padding: 20px;
        }
        
        .header { 
            text-align: center; 
            color: white; 
            margin-bottom: 40px;
            text-shadow: 0 2px 4px rgba(0,0,0,0.3);
        }
        
        .header h1 { 
            font-size: 2.5rem; 
            margin-bottom: 10px;
            font-weight: 300;
        }
        
        .status-bar { 
            display: flex; 
            justify-content: center; 
            gap: 20px; 
            margin: 20px 0;
            flex-wrap: wrap;
        }
        
        .status-item { 
            background: rgba(255,255,255,0.15); 
            backdrop-filter: blur(10px);
            padding: 15px 25px; 
            border-radius: 15px; 
            color: white; 
            font-weight: 500;
            border: 1px solid rgba(255,255,255,0.2);
        }
        
        .status-item.running { background: rgba(40, 167, 69, 0.8); }
        .status-item.stopped { background: rgba(220, 53, 69, 0.8); }
        
        .controls { 
            text-align: center; 
            margin: 30px 0;
        }
        
        .btn { 
            padding: 12px 25px; 
            margin: 8px; 
            border: none; 
            border-radius: 25px; 
            cursor: pointer; 
            text-decoration: none; 
            display: inline-flex;
            align-items: center;
            gap: 8px;
            font-weight: 500;
            transition: all 0.3s ease;
            box-shadow: 0 4px 15px rgba(0,0,0,0.2);
        }
        
        .btn:hover { transform: translateY(-2px); box-shadow: 0 6px 20px rgba(0,0,0,0.3); }
        
        .btn-primary { background: linear-gradient(45deg, #007bff, #0056b3); color: white; }
        .btn-success { background: linear-gradient(45deg, #28a745, #1e7e34); color: white; }
        .btn-danger { background: linear-gradient(45deg, #dc3545, #c82333); color: white; }
        .btn-warning { background: linear-gradient(45deg, #ffc107, #e0a800); color: #212529; }
        .btn-info { background: linear-gradient(45deg, #17a2b8, #138496); color: white; }
        
        .card { 
            background: rgba(255,255,255,0.95); 
            backdrop-filter: blur(15px);
            margin: 20px 0; 
            padding: 25px; 
            border-radius: 20px; 
            box-shadow: 0 8px 32px rgba(0,0,0,0.1);
            border: 1px solid rgba(255,255,255,0.2);
        }
        
        .card-header { 
            font-size: 1.3rem; 
            font-weight: 600; 
            margin-bottom: 20px; 
            color: #495057;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        
        .form-grid { 
            display: grid; 
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); 
            gap: 20px;
            margin: 20px 0;
        }
        
        .form-group { 
            margin: 15px 0; 
        }
        
        .form-group label { 
            display: block; 
            margin-bottom: 8px; 
            font-weight: 600; 
            color: #495057;
        }
        
        .form-group input, .form-group select { 
            width: 100%; 
            padding: 12px 15px; 
            border: 2px solid #e9ecef; 
            border-radius: 10px;
            font-size: 14px;
            transition: all 0.3s ease;
        }
        
        .form-group input:focus, .form-group select:focus { 
            border-color: #007bff; 
            outline: none; 
            box-shadow: 0 0 0 3px rgba(0,123,255,0.1);
        }
        
        .accounts-selector { 
            display: grid; 
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); 
            gap: 10px;
            margin: 15px 0;
        }
        
        .account-checkbox { 
            display: flex; 
            align-items: center; 
            padding: 10px; 
            background: #f8f9fa; 
            border-radius: 8px;
            transition: all 0.2s ease;
        }
        
        .account-checkbox:hover { background: #e9ecef; }
        
        .account-checkbox input { 
            margin-right: 10px; 
            width: auto;
        }
        
        .guild-item { 
            background: linear-gradient(135deg, #f8f9fa, #e9ecef);
            padding: 20px; 
            margin: 15px 0; 
            border-radius: 15px;
            border-left: 5px solid #007bff;
        }
        
        .guild-header { 
            display: flex; 
            justify-content: space-between; 
            align-items: center; 
            margin-bottom: 15px;
        }
        
        .guild-title { 
            font-size: 1.2rem; 
            font-weight: 600; 
            color: #495057;
        }
        
        .accounts-list { 
            display: flex; 
            flex-wrap: wrap; 
            gap: 10px;
        }
        
        .account-tag { 
            background: linear-gradient(45deg, #6c757d, #495057);
            color: white; 
            padding: 5px 12px; 
            border-radius: 15px; 
            font-size: 0.85rem;
            font-weight: 500;
        }
        
        .empty-state { 
            text-align: center; 
            color: white; 
            margin: 50px 0;
            opacity: 0.8;
        }
        
        .empty-state i { 
            font-size: 3rem; 
            margin-bottom: 20px; 
            opacity: 0.5;
        }
        
        @media (max-width: 768px) {
            .container { padding: 10px; }
            .header h1 { font-size: 2rem; }
            .form-grid { grid-template-columns: 1fr; }
            .accounts-selector { grid-template-columns: 1fr; }
            .btn { padding: 10px 20px; margin: 5px; }
        }
        
        .loading { 
            display: inline-block; 
            width: 20px; 
            height: 20px; 
            border: 3px solid rgba(255,255,255,.3); 
            border-radius: 50%; 
            border-top-color: #fff; 
            animation: spin 1s ease-in-out infinite;
        }
        
        @keyframes spin { to { transform: rotate(360deg); } }
        
        .alert { 
            padding: 15px; 
            margin: 20px 0; 
            border-radius: 10px; 
            border-left: 4px solid;
        }
        
        .alert-info { 
            background: rgba(23, 162, 184, 0.1); 
            border-color: #17a2b8; 
            color: #0c5460;
        }
        
        .stats-grid { 
            display: grid; 
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); 
            gap: 15px; 
            margin: 20px 0;
        }
        
        .stat-item { 
            text-align: center; 
            background: rgba(255,255,255,0.1); 
            padding: 15px; 
            border-radius: 15px; 
            color: white;
        }
        
        .stat-number { 
            font-size: 2rem; 
            font-weight: bold; 
            display: block;
        }
        
        .stat-label { 
            font-size: 0.9rem; 
            opacity: 0.8;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1><i class="fas fa-cards-blank"></i> Karuta Multi-Guild Manager</h1>
            <div class="stats-grid">
                <div class="stat-item">
                    <span class="stat-number">{{ guilds|length }}</span>
                    <span class="stat-label">Guilds</span>
                </div>
                <div class="stat-item">
                    <span class="stat-number">{{ available_accounts|length }}</span>
                    <span class="stat-label">Accounts</span>
                </div>
                <div class="stat-item">
                    <span class="stat-number">{{ guilds|length * 6 }}</span>
                    <span class="stat-label">Total Bots</span>
                </div>
            </div>
        </div>

        <div class="status-bar">
            <div class="status-item {{ 'running' if 'Đang chạy' in drop_status else 'stopped' }}">
                <i class="fas {{ 'fa-play' if 'Đang chạy' in drop_status else 'fa-stop' }}"></i>
                Drop Status: {{ drop_status }}
            </div>
        </div>

        <div class="controls">
            <a href="/start_drop" class="btn btn-success">
                <i class="fas fa-play"></i> Bắt đầu Drop
            </a>
            <a href="/stop_drop" class="btn btn-danger">
                <i class="fas fa-stop"></i> Dừng Drop
            </a>
            <a href="/status" class="btn btn-info">
                <i class="fas fa-chart-line"></i> Trạng thái
            </a>
        </div>

        <div class="card">
            <div class="card-header">
                <span><i class="fas fa-plus"></i> Tạo Guild Mới</span>
            </div>
            
            {% if available_accounts|length < 6 %}
            <div class="alert alert-info">
                <i class="fas fa-info-circle"></i>
                <strong>Cảnh báo:</strong> Bạn chỉ có {{ available_accounts|length }} accounts. 
                Cần ít nhất 6 accounts để tạo guild. Vui lòng thêm tokens vào biến môi trường TOKENS.
            </div>
            {% else %}
            <form method="POST" action="/create_guild">
                <div class="form-grid">
                    <div class="form-group">
                        <label><i class="fas fa-server"></i> Tên Guild</label>
                        <input type="text" name="guild_name" required placeholder="VD: Server1, MainGuild, TestServer...">
                    </div>
                    <div class="form-group">
                        <label><i class="fas fa-hashtag"></i> Channel ID</label>
                        <input type="text" name="channel_id" required placeholder="123456789012345678">
                    </div>
                </div>

                <div class="form-group">
                    <label><i class="fas fa-users"></i> Chọn 6 Accounts ({{ available_accounts|length }} available)</label>
                    <div class="accounts-selector">
                        {% for account in available_accounts %}
                        <div class="account-checkbox">
                            <input type="checkbox" name="accounts" value="{{ account.id }}" id="acc_{{ account.id }}">
                            <label for="acc_{{ account.id }}">{{ account.name }}</label>
                        </div>
                        {% endfor %}
                    </div>
                </div>

                <button type="submit" class="btn btn-primary">
                    <i class="fas fa-rocket"></i> Tạo Guild
                </button>
            </form>
            {% endif %}
        </div>

        {% for guild_name, guild in guilds.items() %}
        <div class="guild-item">
            <div class="guild-header">
                <div class="guild-title">
                    <i class="fas fa-shield-alt"></i> {{ guild_name }}
                    <small style="opacity: 0.7;">• Channel: {{ guild.channel_id }}</small>
                </div>
                <a href="/delete_guild/{{ guild_name }}" class="btn btn-danger" 
                   onclick="return confirm('⚠️ Xóa guild {{ guild_name }}?\\n\\nSẽ dừng tất cả bots của guild này!')">
                    <i class="fas fa-trash"></i> Xóa
                </a>
            </div>

            <div class="accounts-list">
                {% for account in guild.accounts %}
                <span class="account-tag">
                    <i class="fas fa-robot"></i> {{ account.name }}
                </span>
                {% endfor %}
            </div>
        </div>
        {% endfor %}

        {% if not guilds %}
        <div class="empty-state">
            <i class="fas fa-plus-circle"></i>
            <h3>Chưa có Guild nào</h3>
            <p>Tạo Guild đầu tiên để bắt đầu farming!</p>
        </div>
        {% endif %}
    </div>

    <script>
        // Validation cho form
        document.querySelector('form')?.addEventListener('submit', function(e) {
            const checkboxes = document.querySelectorAll('input[name="accounts"]:checked');
            if (checkboxes.length !== 6) {
                e.preventDefault();
                alert('⚠️ Bạn phải chọn đúng 6 accounts!\\n\\nHiện tại: ' + checkboxes.length + '/6');
                return false;
            }
        });

        // Auto refresh status mỗi 30s
        setInterval(() => {
            fetch('/status')
                .then(r => r.json())
                .then(data => {
                    console.log('Status:', data);
                })
                .catch(e => console.log('Status check failed:', e));
        }, 30000);

        // Checkbox limit
        document.addEventListener('change', function(e) {
            if (e.target.name === 'accounts') {
                const checked = document.querySelectorAll('input[name="accounts"]:checked');
                const all = document.querySelectorAll('input[name="accounts"]');
                
                if (checked.length >= 6) {
                    all.forEach(cb => {
                        if (!cb.checked) cb.disabled = true;
                    });
                } else {
                    all.forEach(cb => cb.disabled = false);
                }
            }
        });
    </script>
</body>
</html>'''
    
    with open('templates/index.html', 'w', encoding='utf-8') as f:
        f.write(html_content)

def run_flask():
    """Chạy Flask trong thread riêng"""
    app.run(host='0.0.0.0', port=8080, debug=False, threaded=True)

async def main():
    """Hàm main tối ưu"""
    global loop
    loop = asyncio.get_event_loop()
    
    # Tạo templates
    create_templates()
    
    # Khởi động Flask trong thread riêng
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    print("🚀 Karuta Multi-Guild Manager đã khởi động!")
    print(f"📊 Tìm thấy {len(AVAILABLE_ACCOUNTS)} accounts")
    print(f"🌐 Web Interface: http://localhost:8080")
    
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
        print("🛑 Đang dừng chương trình...")
