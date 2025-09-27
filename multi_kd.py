import discord
from discord.ext import commands
import asyncio
import os
import json
import threading
from flask import Flask, render_template, request, jsonify, redirect, url_for
from werkzeug.serving import make_server
import logging

# Tắt logging của discord.py để tiết kiệm RAM
logging.getLogger('discord').setLevel(logging.CRITICAL)

# --- Cấu hình ---
KARUTA_ID = 646937666251915264
FIXED_EMOJIS = ["1️⃣", "2️⃣", "3️⃣", "1️⃣", "2️⃣", "3️⃣"]
GRAB_TIMES = [1.3, 2.3, 3.2, 1.3, 2.3, 3.2]

# Lưu trữ global state
bot_instances = {}  # {token: bot_instance}
panels = {}  # {panel_id: panel_config}
current_drop_index = 0
is_running = False

# Flask app
app = Flask(__name__)

# --- Utility Functions ---
def load_tokens_from_env():
    """Load tokens từ environment variable"""
    tokens_str = os.getenv('TOKENS', '')
    if tokens_str:
        return [token.strip() for token in tokens_str.split(',') if token.strip()]
    return []

def save_panels():
    """Lưu panels vào file để persistence"""
    try:
        with open('panels.json', 'w') as f:
            json.dump(panels, f)
    except:
        pass

def load_panels():
    """Load panels từ file"""
    global panels
    try:
        with open('panels.json', 'r') as f:
            panels = json.load(f)
    except:
        panels = {}

# --- Bot Management ---
class OptimizedBot(commands.Bot):
    """Bot tối ưu hóa để tiết kiệm RAM"""
    def __init__(self, token):
        # Tối ưu hóa intents để giảm RAM
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guilds = False
        intents.members = False
        intents.presences = False
        
        super().__init__(
            command_prefix="!",
            self_bot=True,
            intents=intents,
            chunk_guilds_at_startup=False,
            member_cache_flags=discord.MemberCacheFlags.none()
        )
        self.token_value = token
        self.is_ready_flag = False

    async def setup_hook(self):
        """Setup bot sau khi ready"""
        self.is_ready_flag = True

async def create_bot_instance(token):
    """Tạo một bot instance"""
    if token in bot_instances:
        return bot_instances[token]
    
    bot = OptimizedBot(token)
    
    @bot.event
    async def on_ready():
        print(f"Bot ready: {bot.user} (ID: {bot.user.id})")
        bot.is_ready_flag = True

    @bot.event
    async def on_message(message):
        if message.author.id != KARUTA_ID:
            return
        
        if "is dropping 3 cards!" not in message.content:
            return
        
        # Tìm panel có channel này
        for panel_id, panel in panels.items():
            if str(message.channel.id) in panel['channels']:
                channel_config = panel['channels'][str(message.channel.id)]
                account_tokens = channel_config['accounts']
                
                if token in account_tokens:
                    account_index = account_tokens.index(token)
                    emoji = FIXED_EMOJIS[account_index]
                    grab_time = GRAB_TIMES[account_index]
                    
                    asyncio.create_task(react_to_drop(message, emoji, grab_time))
                break

    # Không start bot ngay, chỉ tạo instance
    bot_instances[token] = bot
    return bot

async def react_to_drop(message, emoji, delay):
    """React vào drop message"""
    await asyncio.sleep(delay)
    try:
        await message.add_reaction(emoji)
    except Exception as e:
        print(f"Error reacting: {e}")

async def drop_loop():
    """Vòng lặp drop chính"""
    global current_drop_index, is_running
    
    while is_running:
        try:
            # Đợi tất cả bot ready
            ready_bots = [bot for bot in bot_instances.values() if bot.is_ready_flag]
            if len(ready_bots) == 0:
                await asyncio.sleep(5)
                continue
            
            # Lấy tất cả channels từ tất cả panels
            all_tasks = []
            
            for panel_id, panel in panels.items():
                for channel_id, channel_config in panel['channels'].items():
                    if len(channel_config['accounts']) > current_drop_index:
                        token = channel_config['accounts'][current_drop_index]
                        if token in bot_instances:
                            bot = bot_instances[token]
                            if bot.is_ready_flag:
                                task = send_drop_command(bot, int(channel_id))
                                all_tasks.append(task)
            
            # Gửi tất cả lệnh drop cùng lúc
            if all_tasks:
                await asyncio.gather(*all_tasks, return_exceptions=True)
                print(f"Sent drop commands for account index {current_drop_index + 1}")
            
            # Chuyển sang account tiếp theo
            current_drop_index = (current_drop_index + 1) % 6
            
            # Đợi 305 giây
            await asyncio.sleep(305)
            
        except Exception as e:
            print(f"Error in drop loop: {e}")
            await asyncio.sleep(10)

async def send_drop_command(bot, channel_id):
    """Gửi lệnh kd"""
    try:
        channel = bot.get_channel(channel_id)
        if channel:
            await channel.send("kd")
            print(f"Sent 'kd' to channel {channel_id} from {bot.user}")
    except Exception as e:
        print(f"Error sending drop command: {e}")

# --- Flask Routes ---
@app.route('/')
def index():
    tokens = load_tokens_from_env()
    return render_template('index.html', panels=panels, tokens=tokens)

@app.route('/create_panel', methods=['POST'])
def create_panel():
    panel_name = request.form.get('panel_name')
    if not panel_name:
        return jsonify({'error': 'Panel name required'}), 400
    
    panel_id = f"panel_{len(panels) + 1}"
    panels[panel_id] = {
        'name': panel_name,
        'channels': {}
    }
    
    save_panels()
    return redirect(url_for('index'))

@app.route('/delete_panel/<panel_id>')
def delete_panel(panel_id):
    if panel_id in panels:
        del panels[panel_id]
        save_panels()
    return redirect(url_for('index'))

@app.route('/add_channel', methods=['POST'])
def add_channel():
    panel_id = request.form.get('panel_id')
    channel_id = request.form.get('channel_id')
    selected_accounts = request.form.getlist('accounts')
    
    if not all([panel_id, channel_id]) or len(selected_accounts) != 6:
        return jsonify({'error': 'Invalid data. Need exactly 6 accounts.'}), 400
    
    if panel_id not in panels:
        return jsonify({'error': 'Panel not found'}), 404
    
    panels[panel_id]['channels'][channel_id] = {
        'accounts': selected_accounts
    }
    
    save_panels()
    return redirect(url_for('index'))

@app.route('/delete_channel/<panel_id>/<channel_id>')
def delete_channel(panel_id, channel_id):
    if panel_id in panels and channel_id in panels[panel_id]['channels']:
        del panels[panel_id]['channels'][channel_id]
        save_panels()
    return redirect(url_for('index'))

@app.route('/start_system', methods=['POST'])
def start_system():
    global is_running
    if not is_running:
        is_running = True
        threading.Thread(target=start_bot_system, daemon=True).start()
        return jsonify({'status': 'started'})
    return jsonify({'status': 'already running'})

@app.route('/stop_system', methods=['POST'])
def stop_system():
    global is_running
    is_running = False
    return jsonify({'status': 'stopped'})

@app.route('/status')
def get_status():
    return jsonify({
        'is_running': is_running,
        'bot_count': len(bot_instances),
        'ready_bots': len([b for b in bot_instances.values() if b.is_ready_flag]),
        'panels': len(panels),
        'current_drop_index': current_drop_index + 1
    })

def start_bot_system():
    """Start bot system trong thread riêng"""
    asyncio.run(bot_manager())

async def bot_manager():
    """Quản lý tất cả bots"""
    global is_running
    
    # Load tokens
    tokens = load_tokens_from_env()
    if not tokens:
        print("No tokens found in environment!")
        return
    
    # Tạo tất cả bot instances
    tasks = []
    for token in tokens:
        bot = await create_bot_instance(token)
        tasks.append(bot.start(token))
    
    # Start drop loop
    tasks.append(drop_loop())
    
    try:
        await asyncio.gather(*tasks, return_exceptions=True)
    except Exception as e:
        print(f"Error in bot manager: {e}")

# HTML Template
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Karuta Multi-Server Manager</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            color: #333;
        }
        
        .container {
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
        }
        
        .header {
            text-align: center;
            color: white;
            margin-bottom: 30px;
        }
        
        .header h1 {
            font-size: 2.5rem;
            margin-bottom: 10px;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
        }
        
        .status-card {
            background: rgba(255, 255, 255, 0.95);
            border-radius: 15px;
            padding: 20px;
            margin-bottom: 20px;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
            backdrop-filter: blur(10px);
        }
        
        .controls {
            display: flex;
            gap: 10px;
            justify-content: center;
            margin-bottom: 20px;
        }
        
        .btn {
            background: linear-gradient(45deg, #4facfe, #00f2fe);
            color: white;
            border: none;
            padding: 12px 24px;
            border-radius: 25px;
            cursor: pointer;
            font-weight: bold;
            transition: all 0.3s;
            font-size: 14px;
        }
        
        .btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 4px 15px rgba(0,0,0,0.2);
        }
        
        .btn-danger {
            background: linear-gradient(45deg, #ff6b6b, #ee5a52);
        }
        
        .btn-success {
            background: linear-gradient(45deg, #51cf66, #40c057);
        }
        
        .card {
            background: rgba(255, 255, 255, 0.95);
            border-radius: 15px;
            padding: 25px;
            margin-bottom: 20px;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
            backdrop-filter: blur(10px);
        }
        
        .form-group {
            margin-bottom: 20px;
        }
        
        .form-group label {
            display: block;
            margin-bottom: 8px;
            font-weight: bold;
            color: #555;
        }
        
        .form-control {
            width: 100%;
            padding: 12px;
            border: 2px solid #e9ecef;
            border-radius: 10px;
            font-size: 16px;
            transition: all 0.3s;
        }
        
        .form-control:focus {
            border-color: #4facfe;
            outline: none;
            box-shadow: 0 0 0 3px rgba(79, 172, 254, 0.1);
        }
        
        .account-selector {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-top: 10px;
        }
        
        .account-item {
            background: #f8f9fa;
            padding: 15px;
            border-radius: 10px;
            border: 2px solid transparent;
            transition: all 0.3s;
            cursor: pointer;
        }
        
        .account-item:hover {
            border-color: #4facfe;
            background: #e3f2fd;
        }
        
        .account-item.selected {
            background: linear-gradient(45deg, #4facfe, #00f2fe);
            color: white;
            border-color: #0066cc;
        }
        
        .panel {
            border-left: 5px solid #4facfe;
            margin-bottom: 25px;
        }
        
        .panel-header {
            background: linear-gradient(45deg, #4facfe, #00f2fe);
            color: white;
            padding: 15px 20px;
            border-radius: 10px 10px 0 0;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        
        .panel-body {
            background: white;
            padding: 20px;
            border-radius: 0 0 10px 10px;
        }
        
        .channel-item {
            background: #f8f9fa;
            padding: 15px;
            margin: 10px 0;
            border-radius: 10px;
            border-left: 4px solid #28a745;
        }
        
        .channel-accounts {
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
            margin-top: 10px;
        }
        
        .account-badge {
            background: linear-gradient(45deg, #51cf66, #40c057);
            color: white;
            padding: 5px 12px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: bold;
        }
        
        .status-info {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 20px;
            text-align: center;
        }
        
        .status-item {
            background: #f8f9fa;
            padding: 15px;
            border-radius: 10px;
            border-top: 4px solid #4facfe;
        }
        
        .status-value {
            font-size: 2rem;
            font-weight: bold;
            color: #4facfe;
            margin-bottom: 5px;
        }
        
        .status-label {
            color: #666;
            font-size: 14px;
        }
        
        .modal {
            display: none;
            position: fixed;
            z-index: 1000;
            left: 0;
            top: 0;
            width: 100%;
            height: 100%;
            background: rgba(0,0,0,0.5);
            backdrop-filter: blur(5px);
        }
        
        .modal-content {
            background: white;
            margin: 5% auto;
            padding: 30px;
            border-radius: 15px;
            max-width: 600px;
            max-height: 80vh;
            overflow-y: auto;
            animation: slideIn 0.3s ease;
        }
        
        @keyframes slideIn {
            from { opacity: 0; transform: translateY(-50px); }
            to { opacity: 1; transform: translateY(0); }
        }
        
        .close {
            color: #aaa;
            float: right;
            font-size: 28px;
            font-weight: bold;
            cursor: pointer;
            line-height: 1;
        }
        
        .close:hover { color: #333; }
        
        .running { color: #28a745; }
        .stopped { color: #dc3545; }
        
        @media (max-width: 768px) {
            .container { padding: 10px; }
            .header h1 { font-size: 2rem; }
            .controls { flex-direction: column; align-items: center; }
            .status-info { grid-template-columns: 1fr 1fr; }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🎴 Karuta Multi-Server Manager</h1>
            <p>Quản lý nhiều server và tài khoản một cách dễ dàng</p>
        </div>
        
        <!-- Status Card -->
        <div class="status-card">
            <h3 style="text-align: center; margin-bottom: 20px;">📊 Trạng thái hệ thống</h3>
            <div class="status-info">
                <div class="status-item">
                    <div class="status-value" id="status">○</div>
                    <div class="status-label">Trạng thái</div>
                </div>
                <div class="status-item">
                    <div class="status-value" id="bot-count">0</div>
                    <div class="status-label">Tổng Bot</div>
                </div>
                <div class="status-item">
                    <div class="status-value" id="ready-bots">0</div>
                    <div class="status-label">Bot sẵn sàng</div>
                </div>
                <div class="status-item">
                    <div class="status-value" id="current-account">1</div>
                    <div class="status-label">Account hiện tại</div>
                </div>
            </div>
            
            <div class="controls">
                <button class="btn btn-success" onclick="startSystem()">🚀 Khởi động</button>
                <button class="btn btn-danger" onclick="stopSystem()">⏹ Dừng lại</button>
                <button class="btn" onclick="refreshStatus()">🔄 Làm mới</button>
            </div>
        </div>
        
        <!-- Create Panel -->
        <div class="card">
            <h3>➕ Tạo Panel mới</h3>
            <form method="post" action="/create_panel">
                <div class="form-group">
                    <label>Tên Panel</label>
                    <input type="text" name="panel_name" class="form-control" placeholder="Ví dụ: Server Game 1" required>
                </div>
                <button type="submit" class="btn">🎨 Tạo Panel</button>
            </form>
        </div>
        
        <!-- Panels List -->
        {% for panel_id, panel in panels.items() %}
        <div class="card panel">
            <div class="panel-header">
                <h3>🎯 {{ panel.name }}</h3>
                <div>
                    <button class="btn" onclick="openAddChannelModal('{{ panel_id }}', '{{ panel.name }}')">➕ Thêm kênh</button>
                    <a href="/delete_panel/{{ panel_id }}" class="btn btn-danger" onclick="return confirm('Xác nhận xóa panel này?')">🗑 Xóa</a>
                </div>
            </div>
            <div class="panel-body">
                {% if panel.channels %}
                    {% for channel_id, channel_config in panel.channels.items() %}
                    <div class="channel-item">
                        <div style="display: flex; justify-content: space-between; align-items: center;">
                            <div>
                                <strong>📺 Channel ID:</strong> {{ channel_id }}
                                <div class="channel-accounts">
                                    {% for account in channel_config.accounts %}
                                    <span class="account-badge">Account {{ loop.index }}</span>
                                    {% endfor %}
                                </div>
                            </div>
                            <a href="/delete_channel/{{ panel_id }}/{{ channel_id }}" class="btn btn-danger" onclick="return confirm('Xác nhận xóa kênh này?')">🗑</a>
                        </div>
                    </div>
                    {% endfor %}
                {% else %}
                    <p style="text-align: center; color: #666; padding: 20px;">
                        📭 Chưa có kênh nào. Hãy thêm kênh đầu tiên!
                    </p>
                {% endif %}
            </div>
        </div>
        {% endfor %}
        
        {% if panels|length == 0 %}
        <div class="card" style="text-align: center; color: #666;">
            <h3>📋 Chưa có Panel nào</h3>
            <p>Tạo panel đầu tiên để bắt đầu quản lý các server của bạn!</p>
        </div>
        {% endif %}
    </div>
    
    <!-- Add Channel Modal -->
    <div id="addChannelModal" class="modal">
        <div class="modal-content">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
                <h3>🔗 Thêm kênh mới</h3>
                <span class="close" onclick="closeModal()">&times;</span>
            </div>
            
            <form method="post" action="/add_channel">
                <input type="hidden" name="panel_id" id="modal-panel-id">
                
                <div class="form-group">
                    <label>ID Kênh Discord</label>
                    <input type="text" name="channel_id" class="form-control" placeholder="123456789012345678" required>
                </div>
                
                <div class="form-group">
                    <label>Chọn 6 tài khoản (theo thứ tự)</label>
                    <div class="account-selector" id="account-selector">
                        {% for token in tokens %}
                        <div class="account-item" data-token="{{ token }}" onclick="toggleAccount(this)">
                            <strong>Account {{ loop.index }}</strong>
                            <div style="font-size: 12px; color: #666; margin-top: 5px;">
                                Token: {{ token[:10] }}...
                            </div>
                        </div>
                        {% endfor %}
                    </div>
                    <div style="margin-top: 10px; font-size: 14px; color: #666;">
                        <span id="selected-count">0</span>/6 tài khoản đã chọn
                    </div>
                </div>
                
                <div style="text-align: center;">
                    <button type="submit" class="btn btn-success">💾 Lưu kênh</button>
                    <button type="button" class="btn" onclick="closeModal()">❌ Hủy</button>
                </div>
            </form>
        </div>
    </div>
    
    <script>
        let selectedAccounts = [];
        
        // Auto refresh status
        setInterval(refreshStatus, 5000);
        refreshStatus();
        
        function refreshStatus() {
            fetch('/status')
                .then(response => response.json())
                .then(data => {
                    document.getElementById('status').textContent = data.is_running ? '🟢 Đang chạy' : '🔴 Dừng';
                    document.getElementById('status').className = data.is_running ? 'running' : 'stopped';
                    document.getElementById('bot-count').textContent = data.bot_count;
                    document.getElementById('ready-bots').textContent = data.ready_bots;
                    document.getElementById('current-account').textContent = data.current_drop_index;
                })
                .catch(console.error);
        }
        
        function startSystem() {
            fetch('/start_system', {method: 'POST'})
                .then(response => response.json())
                .then(data => {
                    alert(data.status === 'started' ? '🚀 Hệ thống đã khởi động!' : '⚠️ Hệ thống đã đang chạy!');
                    refreshStatus();
                })
                .catch(console.error);
        }
        
        function stopSystem() {
            if (confirm('Bạn có chắc muốn dừng hệ thống?')) {
                fetch('/stop_system', {method: 'POST'})
                    .then(response => response.json())
                    .then(data => {
                        alert('⏹ Hệ thống đã dừng!');
                        refreshStatus();
                    })
                    .catch(console.error);
            }
        }
        
        function openAddChannelModal(panelId, panelName) {
            document.getElementById('modal-panel-id').value = panelId;
            document.getElementById('addChannelModal').style.display = 'block';
            selectedAccounts = [];
            updateAccountSelection();
        }
        
        function closeModal() {
            document.getElementById('addChannelModal').style.display = 'none';
        }
        
        function toggleAccount(element) {
            const token = element.dataset.token;
            const index = selectedAccounts.indexOf(token);
            
            if (index > -1) {
                selectedAccounts.splice(index, 1);
                element.classList.remove('selected');
            } else {
                if (selectedAccounts.length < 6) {
                    selectedAccounts.push(token);
                    element.classList.add('selected');
                } else {
                    alert('⚠️ Chỉ có thể chọn tối đa 6 tài khoản!');
                }
            }
            
            updateAccountSelection();
        }
        
        function updateAccountSelection() {
            document.getElementById('selected-count').textContent = selectedAccounts.length;
            
            // Update hidden inputs
            const form = document.querySelector('#addChannelModal form');
            const existingInputs = form.querySelectorAll('input[name="accounts"]');
            existingInputs.forEach(input => input.remove());
            
            selectedAccounts.forEach(token => {
                const input = document.createElement('input');
                input.type = 'hidden';
                input.name = 'accounts';
                input.value = token;
                form.appendChild(input);
            });
        }
        
        // Close modal when clicking outside
        window.onclick = function(event) {
            const modal = document.getElementById('addChannelModal');
            if (event.target === modal) {
                closeModal();
            }
        }
    </script>
</body>
</html>
'''

# Tạo template directory nếu chưa có
import os
os.makedirs('templates', exist_ok=True)

# Ghi file template
with open('templates/index.html', 'w', encoding='utf-8') as f:
    f.write(HTML_TEMPLATE)

# --- Main execution ---
if __name__ == "__main__":
    # Load panels từ file
    load_panels()
    
    # Chạy Flask app
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)
