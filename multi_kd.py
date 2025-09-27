import os
import asyncio
import threading
import logging
from flask import Flask, render_template_string, request, jsonify, redirect, url_for
import discord
from discord.ext import commands

# ---------------------------------------------------------------------------
# PHẦN 1: NỘI DUNG HTML, CSS, JAVASCRIPT
# ---------------------------------------------------------------------------

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🎴 Karuta Multi-Guild Manager</title>
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet">
    <link href="https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        :root {
            --primary: #6366f1; --secondary: #8b5cf6; --accent: #06b6d4;
            --success: #10b981; --danger: #ef4444; --warning: #f59e0b;
            --dark: #1f2937; --light: #f8fafc;
        }
        body { font-family: 'Poppins', sans-serif; background: linear-gradient(135deg, #667eea 0%, #764ba2 25%, #f093fb 50%, #f5576c 75%, #4facfe 100%); background-size: 400% 400%; animation: gradientShift 15s ease infinite; min-height: 100vh; color: #333; }
        @keyframes gradientShift { 0% { background-position: 0% 50%; } 50% { background-position: 100% 50%; } 100% { background-position: 0% 50%; } }
        .container { max-width: 1400px; margin: 0 auto; padding: 20px; }
        .header { text-align: center; color: white; margin-bottom: 40px; text-shadow: 0 4px 20px rgba(0,0,0,0.3); position: relative; }
        .header h1 { font-size: 3rem; margin-bottom: 15px; font-weight: 700; background: linear-gradient(45deg, #fff, #fbbf24, #06b6d4, #8b5cf6); background-size: 400% 400%; -webkit-background-clip: text; -webkit-text-fill-color: transparent; animation: textGradient 3s ease infinite; }
        @keyframes textGradient { 0%, 100% { background-position: 0% 50%; } 50% { background-position: 100% 50%; } }
        .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin: 30px 0; z-index: 2; position: relative; }
        .stat-item { background: rgba(255,255,255,0.15); backdrop-filter: blur(20px); border: 1px solid rgba(255,255,255,0.2); padding: 25px; border-radius: 20px; color: white; text-align: center; transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1); box-shadow: 0 8px 32px rgba(0,0,0,0.1); }
        .stat-item:hover { transform: translateY(-8px) scale(1.02); box-shadow: 0 15px 40px rgba(0,0,0,0.2); }
        .stat-number { font-size: 2.5rem; font-weight: 700; display: block; background: linear-gradient(45deg, #fbbf24, #06b6d4); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
        .stat-label { font-size: 0.9rem; opacity: 0.9; font-weight: 500; margin-top: 5px; }
        .status-bar { display: flex; justify-content: center; gap: 25px; margin: 30px 0; flex-wrap: wrap; z-index: 2; position: relative; }
        .status-item { background: rgba(255,255,255,0.15); backdrop-filter: blur(20px); padding: 20px 30px; border-radius: 25px; color: white; font-weight: 600; }
        .status-item.running { background: linear-gradient(45deg, #10b981, #059669); box-shadow: 0 10px 25px rgba(16, 185, 129, 0.3); animation: pulse 2s infinite; }
        .status-item.stopped { background: linear-gradient(45deg, #ef4444, #dc2626); box-shadow: 0 10px 25px rgba(239, 68, 68, 0.3); }
        .controls { text-align: center; margin: 40px 0; z-index: 2; position: relative; }
        .btn { padding: 15px 30px; margin: 10px; border: none; border-radius: 25px; cursor: pointer; text-decoration: none; display: inline-flex; align-items: center; gap: 10px; font-weight: 600; font-size: 1rem; transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1); box-shadow: 0 10px 25px rgba(0,0,0,0.15); }
        .btn:hover { transform: translateY(-3px) scale(1.05); box-shadow: 0 15px 35px rgba(0,0,0,0.25); }
        .btn-primary { background: linear-gradient(45deg, var(--primary), var(--secondary)); color: white; }
        .btn-success { background: linear-gradient(45deg, var(--success), #059669); color: white; }
        .btn-danger { background: linear-gradient(45deg, var(--danger), #dc2626); color: white; }
        .btn-warning { background: linear-gradient(45deg, var(--warning), #d97706); color: white; }
        .btn-info { background: linear-gradient(45deg, var(--accent), #0891b2); color: white; }
        .card { background: rgba(255,255,255,0.95); backdrop-filter: blur(20px); margin: 30px 0; padding: 30px; border-radius: 25px; box-shadow: 0 20px 50px rgba(0,0,0,0.1); border: 1px solid rgba(255,255,255,0.3); z-index: 2; position: relative; }
        .card-header { font-size: 1.5rem; font-weight: 600; margin-bottom: 25px; color: var(--dark); display: flex; justify-content: space-between; align-items: center; padding-bottom: 15px; border-bottom: 2px solid #e5e7eb; }
        .form-group label { display: block; margin-bottom: 10px; font-weight: 600; color: var(--dark); }
        .form-group input { width: 100%; padding: 15px 20px; border: 2px solid #e5e7eb; border-radius: 15px; font-size: 1rem; transition: all 0.3s ease; }
        .form-group input:focus { border-color: var(--primary); outline: none; box-shadow: 0 0 0 4px rgba(99, 102, 241, 0.1); }
        .accounts-selector { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 15px; margin-top: 20px; padding: 20px; background: #f8fafc; border-radius: 15px; }
        .account-checkbox { display: flex; align-items: center; padding: 15px; background: white; border-radius: 12px; transition: all 0.3s ease; cursor: pointer; border: 2px solid #e5e7eb; }
        .account-checkbox:hover { border-color: var(--primary); transform: scale(1.02); }
        .account-checkbox.checked { background: linear-gradient(45deg, var(--primary), var(--secondary)); color: white; border-color: transparent; }
        .account-checkbox input { margin-right: 12px; width: 20px; height: 20px; accent-color: var(--primary); }
        .guild-item { background: #fff; padding: 25px; margin: 20px 0; border-radius: 20px; border-left: 6px solid var(--warning); box-shadow: 0 10px 25px rgba(0,0,0,0.05); }
        .guild-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
        .guild-title { font-size: 1.3rem; font-weight: 600; color: var(--dark); }
        .accounts-list { display: flex; flex-wrap: wrap; gap: 12px; }
        .account-tag { background: var(--dark); color: white; padding: 8px 15px; border-radius: 20px; font-size: 0.9rem; }
        .alert { padding: 20px; margin: 25px 0; border-radius: 15px; border-left: 5px solid; background: rgba(6, 182, 212, 0.1); }
        .loading-spinner { display: inline-block; width: 20px; height: 20px; border: 3px solid rgba(255,255,255,.3); border-radius: 50%; border-top-color: #fff; animation: spin 1s ease-in-out infinite; }
        @keyframes spin { to { transform: rotate(360deg); } }
        @keyframes pulse { 0% {transform: scale(1);} 50% {transform: scale(1.05);} 100% {transform: scale(1);} }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1><i class="fas fa-crown"></i> Karuta Multi-Guild Manager</h1>
            <div class="stats-grid">
                <div class="stat-item">
                    <span class="stat-number">{{ available_accounts|length }}</span>
                    <span class="stat-label"><i class="fas fa-users"></i> Available Accounts</span>
                </div>
                <div class="stat-item">
                    <span class="stat-number">{{ guilds|length }}</span>
                    <span class="stat-label"><i class="fas fa-server"></i> Active Guilds</span>
                </div>
                <div class="stat-item">
                    <span class="stat-number">{{ guilds|length * 6 }}</span>
                    <span class="stat-label"><i class="fas fa-robot"></i> Total Bots</span>
                </div>
                <div class="stat-item">
                    <span class="stat-number">{{ (guilds|length * 6 * 12 * 24)|int }}</span>
                    <span class="stat-label"><i class="fas fa-fire"></i> Drops/Day</span>
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
            <a href="/start_drop" class="btn btn-success"><i class="fas fa-rocket"></i> Launch Drop System</a>
            <a href="/stop_drop" class="btn btn-danger"><i class="fas fa-hand-paper"></i> Emergency Stop</a>
            <a href="#" onclick="location.reload()" class="btn btn-warning"><i class="fas fa-sync-alt"></i> Refresh</a>
        </div>

        <div class="card">
            <div class="card-header">
                <span><i class="fas fa-magic"></i> Create New Guild</span>
                <div style="font-size: 0.9rem; opacity: 0.7;">
                    <i class="fas fa-info-circle"></i> Each guild needs exactly 6 accounts
                </div>
            </div>
            {% if available_accounts|length < 6 %}
            <div class="alert">
                <strong>⚠️ Not enough accounts!</strong> You have {{ available_accounts|length }}. Need at least 6.
            </div>
            {% else %}
            <form method="POST" action="/create_guild">
                <div class="form-group">
                    <label><i class="fas fa-tag"></i> Guild Name</label>
                    <input type="text" name="guild_name" required placeholder="e.g., MainServer, TestGuild...">
                </div>
                <div class="form-group">
                    <label><i class="fas fa-hashtag"></i> Channel ID</label>
                    <input type="text" name="channel_id" required placeholder="Discord channel ID (18-19 digits)">
                </div>
                <div class="form-group">
                    <label><i class="fas fa-crown"></i> Select Accounts (Choose exactly 6)</label>
                    <div class="accounts-selector">
                        {% for account in available_accounts %}
                        <div class="account-checkbox" onclick="toggleAccount(this)">
                            <input type="checkbox" name="accounts" value="{{ account.id }}" id="acc_{{ account.id }}">
                            <label for="acc_{{ account.id }}"><i class="fas fa-user-ninja"></i> {{ account.name }}</label>
                        </div>
                        {% endfor %}
                    </div>
                    <div style="text-align: center; margin-top: 15px;">
                        <span id="selection-counter" style="font-weight: 600; color: var(--primary);">Selected: 0/6</span>
                    </div>
                </div>
                <div style="text-align: center; margin-top: 30px;">
                    <button type="submit" class="btn btn-primary" id="create-btn" disabled>
                        <i class="fas fa-plus-circle"></i> Create Guild
                    </button>
                </div>
            </form>
            {% endif %}
        </div>

        {% for guild_name, guild in guilds.items() %}
        <div class="guild-item">
            <div class="guild-header">
                <div class="guild-title">
                    <i class="fas fa-castle"></i> {{ guild_name }}
                    <small style="opacity: 0.8; font-weight: 400; display: block;">Channel: {{ guild.channel_id }}</small>
                </div>
                <a href="/delete_guild/{{ guild_name }}" class="btn btn-danger" 
                   onclick="return confirm('🚨 Delete {{ guild_name }}? This will stop its bots!')">
                    <i class="fas fa-trash"></i> Delete
                </a>
            </div>
            <div class="accounts-list">
                {% for account in guild.accounts %}
                <span class="account-tag"><i class="fas fa-user-secret"></i> {{ account.name }}</span>
                {% endfor %}
            </div>
        </div>
        {% endfor %}
    </div>

    <script>
        function toggleAccount(element) {
            const checkbox = element.querySelector('input[type="checkbox"]');
            checkbox.checked = !checkbox.checked;
            updateSelection();
        }
        function updateSelection() {
            const checked = document.querySelectorAll('input[name="accounts"]:checked');
            const counter = document.getElementById('selection-counter');
            const createBtn = document.getElementById('create-btn');
            counter.innerHTML = `Selected: ${checked.length}/6`;
            counter.style.color = checked.length === 6 ? 'var(--success)' : 'var(--danger)';
            createBtn.disabled = checked.length !== 6;
            
            document.querySelectorAll('.account-checkbox').forEach(el => {
                el.classList.toggle('checked', el.querySelector('input').checked);
            });
        }
        document.addEventListener('DOMContentLoaded', updateSelection);
    </script>
</body>
</html>
"""

# ---------------------------------------------------------------------------
# PHẦN 2: CODE PYTHON (FLASK & DISCORD.PY)
# ---------------------------------------------------------------------------

# Cấu hình logging
logging.basicConfig(level=logging.WARNING)

# Cấu hình Karuta & Bot
KARUTA_ID = 646937666251915264
FIXED_EMOJIS = ["1️⃣", "2️⃣", "3️⃣", "1️⃣", "2️⃣", "3️⃣"]
GRAB_TIMES = [1.3, 2.3, 3.2, 1.3, 2.3, 3.2]

# Biến toàn cục để lưu trữ trạng thái (dùng dict cho an toàn thread)
STATE = {
    "guilds_config": {},
    "bot_instances": {},
    "drop_status": "Đã dừng",
    "all_accounts": []
}
STATE_LOCK = threading.Lock()

# Flask App
app = Flask(__name__)

def get_all_accounts():
    """Lấy danh sách TẤT CẢ tài khoản từ biến môi trường."""
    if STATE["all_accounts"]:
        return STATE["all_accounts"]
    
    accounts = []
    tokens_str = os.getenv("TOKENS", "")
    if not tokens_str:
        return []
    
    tokens = [token.strip() for token in tokens_str.split(",") if token.strip()]
    names_str = os.getenv("NAMES", "")
    names = [name.strip() for name in names_str.split(",") if name.strip()] if names_str else []
    
    for i, token in enumerate(tokens):
        name = names[i] if i < len(names) else f"Account_{i+1}"
        accounts.append({"name": name, "token": token, "id": f"acc{i+1}"})
    
    STATE["all_accounts"] = accounts
    return accounts

def get_available_accounts():
    """Lọc ra những tài khoản chưa được sử dụng."""
    all_accounts = get_all_accounts()
    used_account_ids = set()
    with STATE_LOCK:
        for guild in STATE["guilds_config"].values():
            for acc in guild.get('accounts', []):
                used_account_ids.add(acc['id'])
    return [acc for acc in all_accounts if acc['id'] not in used_account_ids]

class OptimizedBot(commands.Bot):
    """Bot class cho discord.py-self, được tối ưu hóa."""
    def __init__(self, token, guild_name, account_index, channel_id, **options):
        super().__init__(command_prefix="!", self_bot=True, **options)
        self.token = token
        self.guild_name = guild_name
        self.account_index = account_index
        self.target_channel_id = int(channel_id)
        self.loop.create_task(self.start_bot())

    async def on_ready(self):
        print(f"✅ Bot {self.user.name} sẵn sàng cho Guild: {self.guild_name}")

    async def on_message(self, message):
        if (message.author.id == KARUTA_ID and 
            "is dropping 3 cards!" in message.content and 
            message.channel.id == self.target_channel_id):
            
            emoji = FIXED_EMOJIS[self.account_index % len(FIXED_EMOJIS)]
            grab_time = GRAB_TIMES[self.account_index % len(GRAB_TIMES)]
            await asyncio.sleep(grab_time)
            try:
                await message.add_reaction(emoji)
            except Exception as e:
                print(f"Lỗi khi react: {e}")

    async def start_bot(self):
        try:
            await self.start(self.token)
        except discord.errors.LoginFailure:
            print(f"❌ Token không hợp lệ cho Bot {self.account_index + 1}.")
        except Exception as e:
            print(f"Lỗi khi chạy bot {self.account_index + 1}: {e}")

def run_bot_in_thread(loop, bot):
    """Chạy bot trong một event loop riêng."""
    asyncio.set_event_loop(loop)
    loop.run_until_complete(bot.start_bot())

def start_all_bots():
    """Khởi động tất cả các bot từ cấu hình."""
    with STATE_LOCK:
        if STATE["drop_status"] == "Đang chạy...":
            print("Bots đã chạy rồi.")
            return
        
        STATE["drop_status"] = "Đang chạy..."
        print("Bắt đầu khởi động các bot...")
        
        for guild_name, config in STATE["guilds_config"].items():
            for i, acc in enumerate(config["accounts"]):
                bot_id = f"{guild_name}_{acc['id']}"
                if bot_id not in STATE["bot_instances"]:
                    new_loop = asyncio.new_event_loop()
                    bot = OptimizedBot(
                        token=acc["token"],
                        guild_name=guild_name,
                        account_index=i,
                        channel_id=config["channel_id"],
                        loop=new_loop
                    )
                    STATE["bot_instances"][bot_id] = (bot, new_loop)
                    threading.Thread(target=lambda: new_loop.run_forever(), daemon=True).start()

def stop_all_bots():
    """Dừng tất cả các bot đang chạy."""
    with STATE_LOCK:
        if not STATE["bot_instances"]:
            STATE["drop_status"] = "Đã dừng"
            return
        
        print("Bắt đầu dừng các bot...")
        for bot_id, (bot, loop) in STATE["bot_instances"].items():
            if bot.is_ready():
                asyncio.run_coroutine_threadsafe(bot.close(), loop).result()
            loop.call_soon_threadsafe(loop.stop)
        
        STATE["bot_instances"].clear()
        STATE["drop_status"] = "Đã dừng"
        print("Tất cả bot đã dừng.")

# --- Flask Routes ---

@app.route("/")
def index():
    """Trang chủ hiển thị dashboard."""
    with STATE_LOCK:
        # Thay vì render_template, ta dùng render_template_string
        return render_template_string(
            HTML_TEMPLATE,
            available_accounts=get_available_accounts(),
            guilds=STATE["guilds_config"],
            drop_status=STATE["drop_status"]
        )

@app.route("/create_guild", methods=["POST"])
def create_guild():
    guild_name = request.form.get("guild_name")
    channel_id = request.form.get("channel_id")
    account_ids = request.form.getlist("accounts")

    with STATE_LOCK:
        if guild_name in STATE["guilds_config"]:
            return "Tên guild đã tồn tại!", 400
        
        all_accounts = get_all_accounts()
        selected_accounts = [acc for acc in all_accounts if acc['id'] in account_ids]
        
        STATE["guilds_config"][guild_name] = {
            "channel_id": channel_id,
            "accounts": selected_accounts
        }
    return redirect(url_for("index"))

@app.route("/delete_guild/<guild_name>")
def delete_guild(guild_name):
    with STATE_LOCK:
        if guild_name in STATE["guilds_config"]:
            del STATE["guilds_config"][guild_name]
    # Thêm logic dừng bot của guild này nếu cần
    return redirect(url_for("index"))

@app.route("/start_drop")
def start_drop():
    threading.Thread(target=start_all_bots).start()
    return redirect(url_for("index"))

@app.route("/stop_drop")
def stop_drop():
    threading.Thread(target=stop_all_bots).start()
    return redirect(url_for("index"))

if __name__ == "__main__":
    # Lấy PORT từ biến môi trường, mặc định là 5000 nếu không có
    port = int(os.environ.get("PORT", 5000))
    # Chạy trên host 0.0.0.0 để Render có thể truy cập
    app.run(host='0.0.0.0', port=port)
