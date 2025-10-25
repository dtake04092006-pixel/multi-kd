# TÊN FILE: main.py
# PHIÊN BẢN: Multi-Farm Deep Control v2.3 (FIXED)
import discord
from discord.ext import commands
import asyncio
import os
import threading
import time
import requests
import json
import random
from flask import Flask, request, render_template_string, jsonify
from dotenv import load_dotenv

load_dotenv()

# --- CẤU HÌNH & BIẾN TOÀN CỤC ---
KARUTA_ID = 646937666251915264

# Tải danh sách tài khoản từ biến môi trường
TOKENS_STR = os.getenv("TOKENS", "")
ACC_NAMES_STR = os.getenv("ACC_NAMES", "")

# Xử lý danh sách tài khoản
GLOBAL_ACCOUNTS = []
tokens_list = [token.strip() for token in TOKENS_STR.split(',') if token.strip()]
acc_names_list = [name.strip() for name in ACC_NAMES_STR.split(',') if name.strip()]

for i, token in enumerate(tokens_list):
    name = acc_names_list[i] if i < len(acc_names_list) else f"Account {i + 1}"
    GLOBAL_ACCOUNTS.append({"id": f"acc_{i}", "name": name, "token": token})

# Biến trạng thái
panels = []
current_drop_slot = 0
is_kd_loop_enabled = True
bot_ready = False
GLOBAL_BOTS = {}
bot_ready_flags = {}
last_kd_cycle_time = 0

# --- CÁC HÀM TIỆN ÍCH ---

async def send_message_bot(bot_instance, channel_id, content):
    """Gửi tin nhắn bằng bot instance."""
    if not bot_instance or not channel_id: 
        return
    try:
        channel = bot_instance.get_channel(int(channel_id))
        if channel:
            await channel.send(content)
            print(f"[{bot_instance.user.name}] Gửi '{content}' tới kênh {channel_id}.")
        else:
            print(f"[{bot_instance.user.name}] Lỗi: Không tìm thấy kênh {channel_id}.")
    except discord.errors.Forbidden:
        print(f"[{bot_instance.user.name}] Lỗi: Không có quyền gửi tin nhắn.")
    except Exception as e:
        print(f"[{bot_instance.user.name}] Lỗi khi gửi tin nhắn: {e}")

async def add_reaction_bot(bot_instance, channel_id, message_id, emoji):
    """Thả reaction bằng bot instance."""
    if not bot_instance or not channel_id: 
        return
    try:
        await bot_instance.http.add_reaction(channel_id, message_id, emoji)
    except discord.errors.Forbidden:
        print(f"[{bot_instance.user.name}] Lỗi: Không có quyền thả reaction.")
    except Exception as e:
        print(f"[{bot_instance.user.name}] Lỗi khi thả reaction: {e}")

# --- LƯU & TẢI CẤU HÌNH PANEL ---

def save_panels():
    """Lưu cấu hình các panel lên JSONBin.io"""
    api_key = os.getenv("JSONBIN_API_KEY")
    bin_id = os.getenv("JSONBIN_BIN_ID")
    if not api_key or not bin_id:
        print("[Settings] Thiếu API Key hoặc Bin ID. Bỏ qua việc lưu.")
        return

    headers = {'Content-Type': 'application/json', 'X-Master-Key': api_key}
    url = f"https://api.jsonbin.io/v3/b/{bin_id}"
    try:
        def do_save():
            req = requests.put(url, json=panels, headers=headers, timeout=15)
            if req.status_code == 200:
                print("[Settings] Đã lưu cấu hình panels.")
            else:
                print(f"[Settings] Lỗi khi lưu: {req.status_code}")
        threading.Thread(target=do_save, daemon=True).start()
    except Exception as e:
        print(f"[Settings] Exception khi lưu: {e}")

def load_panels():
    """Tải cấu hình các panel từ JSONBin.io"""
    global panels
    api_key = os.getenv("JSONBIN_API_KEY")
    bin_id = os.getenv("JSONBIN_BIN_ID")
    if not api_key or not bin_id:
        print("[Settings] Thiếu API Key hoặc Bin ID.")
        return

    headers = {'X-Master-Key': api_key, 'X-Bin-Meta': 'false'}
    url = f"https://api.jsonbin.io/v3/b/{bin_id}/latest"
    try:
        req = requests.get(url, headers=headers, timeout=15)
        if req.status_code == 200:
            data = req.json()
            if isinstance(data, list):
                panels = data
                print(f"[Settings] Đã tải {len(panels)} panel.")
            else:
                save_panels()
        else:
            print(f"[Settings] Lỗi khi tải: {req.status_code}")
    except Exception as e:
        print(f"[Settings] Exception khi tải: {e}")

def get_server_name_from_channel(channel_id):
    """Lấy tên server từ Channel ID."""
    if not channel_id or not channel_id.isdigit():
        return "ID kênh không hợp lệ"
    if not GLOBAL_ACCOUNTS:
        return "Không có token"

    token = GLOBAL_ACCOUNTS[0]["token"]
    headers = {"Authorization": token}

    try:
        channel_res = requests.get(f"https://discord.com/api/v9/channels/{channel_id}", 
                                    headers=headers, timeout=10)
        if channel_res.status_code != 200:
            return "Không tìm thấy kênh"

        channel_data = channel_res.json()
        guild_id = channel_data.get("guild_id")

        if not guild_id:
            return "Đây là kênh DM/Group"

        guild_res = requests.get(f"https://discord.com/api/v9/guilds/{guild_id}", 
                                 headers=headers, timeout=10)
        if guild_res.status_code == 200:
            return guild_res.json().get("name", "Không thể lấy tên server")
        else:
            return "Không thể truy cập server"

    except requests.RequestException:
        return "Lỗi mạng"

# --- LOGIC BOT CHÍNH (ĐÃ SỬA LỖI) ---

async def handle_reactions(panel, message):
    """Xử lý việc thả reaction cho 3 tài khoản trong một panel."""
    accounts_in_panel = panel.get("accounts", {})
    if not accounts_in_panel: 
        return

    emojis = ["1️⃣", "2️⃣", "3️⃣"]
    grab_times = [1.3, 2.3, 3.2]
    
    tasks = []
    for i in range(3):
        slot_key = f"slot_{i + 1}"
        token = accounts_in_panel.get(slot_key)
        bot_to_react = GLOBAL_BOTS.get(token)
        
        if bot_to_react:
            delay = grab_times[i]
            emoji = emojis[i]
            
            async def react_task(bot, ch_id, msg_id, em, d):
                await asyncio.sleep(d)
                await add_reaction_bot(bot, ch_id, msg_id, em)
            
            tasks.append(react_task(bot_to_react, message.channel.id, message.id, emoji, delay))

    if tasks:
        await asyncio.gather(*tasks)

# FIX CHÍNH: Tạo bot instance với event handlers NGOÀI vòng lặp
def create_bot_instance(account_info, is_listener=False):
    """Tạo một bot instance với event handlers được định nghĩa đúng cách."""
    token = account_info["token"]
    name = account_info["name"]
    
    # Tạo intents tối giản để giảm tải
    intents = discord.Intents.none()
    intents.guilds = True
    intents.guild_messages = True
    intents.message_content = True
    
    # Tạo bot với cấu hình tối ưu
    bot = commands.Bot(
        command_prefix=f"!unused_prefix_{random.randint(10000, 99999)}", 
        self_bot=True,
        intents=intents,
        chunk_guilds_at_startup=False,  # QUAN TRỌNG: Tắt guild chunking
        guild_subscriptions=False        # Tắt guild subscriptions
    )
    
    # Định nghĩa event on_ready
    @bot.event
    async def on_ready():
        global bot_ready
        print(f"[BOT READY] '{bot.user.name}' (ID: {bot.user.id}) đã kết nối.")
        bot_ready_flags[token] = True
        
        # Kiểm tra xem tất cả bot đã sẵn sàng chưa
        if all(bot_ready_flags.values()):
            print("-" * 50)
            print(f"TẤT CẢ ({len(GLOBAL_BOTS)}) CÁC BOT ĐÃ SẴN SÀNG!")
            print("-" * 50)
            bot_ready = True
    
    # CHỈ gắn event on_message cho bot listener
    if is_listener:
        print(f"-> Gắn '{name}' làm BOT LẮNG NGHE CHÍNH.")
        
        @bot.event
        async def on_message(message):
            # Chỉ xử lý nếu là drop của Karuta
            if message.author.id != KARUTA_ID or "is dropping 3 cards!" not in message.content:
                return

            # Tìm panel tương ứng
            found_panel = None
            for p in panels:
                if p.get("channel_id") == str(message.channel.id):
                    found_panel = p
                    break
            
            if found_panel:
                print(f"[LISTENER] Phát hiện drop trong kênh {message.channel.id}")
                asyncio.create_task(handle_reactions(found_panel, message))
    
    return bot

async def run_single_bot(bot, token, account_name):
    """Chạy một bot và xử lý lỗi đăng nhập + reconnect."""
    max_retries = 3
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            print(f"[{account_name}] Đang kết nối... (Lần thử {retry_count + 1}/{max_retries})")
            await bot.start(token)
            # Nếu bot.start() kết thúc, có nghĩa là bot đã disconnect
            print(f"[{account_name}] Bot đã ngắt kết nối.")
            break
            
        except discord.errors.LoginFailure:
            print(f"[{account_name}] ❌ LỖI ĐĂNG NHẬP - Token không hợp lệ!")
            bot_ready_flags[token] = False
            break
            
        except (aiohttp.ClientConnectionError, asyncio.TimeoutError) as e:
            retry_count += 1
            print(f"[{account_name}] ⚠ Lỗi kết nối: {e}")
            if retry_count < max_retries:
                wait_time = retry_count * 5
                print(f"[{account_name}] Chờ {wait_time}s trước khi thử lại...")
                await asyncio.sleep(wait_time)
            else:
                print(f"[{account_name}] ❌ Đã thử {max_retries} lần, bỏ qua bot này.")
                bot_ready_flags[token] = False
                
        except Exception as e:
            print(f"[{account_name}] ❌ Lỗi không xác định: {e}")
            bot_ready_flags[token] = False
            break

async def run_all_bots():
    """Khởi chạy TẤT CẢ các tài khoản dưới dạng bot client."""
    global bot_ready, GLOBAL_BOTS, bot_ready_flags
    
    if not GLOBAL_ACCOUNTS:
        print("Không có token. Bot không thể khởi động.")
        bot_ready = True
        return

    print(f"Chuẩn bị khởi chạy {len(GLOBAL_ACCOUNTS)} tài khoản...")
    
    tasks = []
    for i, acc in enumerate(GLOBAL_ACCOUNTS):
        token = acc["token"]
        bot_ready_flags[token] = False
        
        # Tạo bot instance - CHỈ bot đầu tiên là listener
        bot = create_bot_instance(acc, is_listener=(i == 0))
        GLOBAL_BOTS[token] = bot
        
        # Tạo task để chạy bot
        tasks.append(run_single_bot(bot, token))
    
    # Chạy tất cả các bot song song
    await asyncio.gather(*tasks)

# --- GIAO DIỆN WEB & API FLASK ---

app = Flask(__name__)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Multi-Farm Deep Control</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        :root { --primary-bg: #111; --secondary-bg: #1d1d1d; --panel-bg: #2a2a2a; --border-color: #444; --text-primary: #f0f0f0; --text-secondary: #aaa; --accent-color: #00aaff; --danger-color: #ff4444; }
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background-color: var(--primary-bg); color: var(--text-primary); margin: 0; padding: 20px; }
        .container { max-width: 1800px; margin: 0 auto; }
        .header { text-align: center; margin-bottom: 30px; }
        .header h1 { color: var(--accent-color); font-weight: 600; }
        .status-bar { display: flex; justify-content: space-around; background-color: var(--secondary-bg); padding: 15px; border-radius: 8px; margin-bottom: 20px; flex-wrap: wrap; gap: 15px; }
        .status-item { text-align: center; }
        .status-item span { display: block; font-size: 0.9em; color: var(--text-secondary); }
        .status-item strong { font-size: 1.2em; color: var(--accent-color); }
        .controls { display: flex; justify-content: center; margin-bottom: 30px; gap: 15px; }
        .btn { background-color: var(--accent-color); color: white; border: none; padding: 10px 20px; border-radius: 5px; cursor: pointer; font-size: 1em; transition: background-color 0.3s; }
        .btn:hover { background-color: #0088cc; }
        .btn-danger { background-color: var(--danger-color); }
        .btn-danger:hover { background-color: #cc3333; }
        .farm-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(380px, 1fr)); gap: 20px; }
        .panel { background-color: var(--secondary-bg); border: 1px solid var(--border-color); border-radius: 8px; padding: 20px; position: relative; }
        .panel-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; border-bottom: 1px solid var(--border-color); padding-bottom: 10px; }
        .panel-header h3 { margin: 0; font-size: 1.2em; }
        .input-group { margin-bottom: 15px; }
        .input-group label { display: block; color: var(--text-secondary); margin-bottom: 5px; font-size: 0.9em; }
        .input-group input, .input-group select { width: 100%; background-color: var(--primary-bg); border: 1px solid var(--border-color); color: var(--text-primary); padding: 8px; border-radius: 5px; box-sizing: border-box; }
        .account-slots { display: grid; grid-template-columns: 1fr; gap: 15px; }
        .server-name-display { font-size: 0.8em; color: var(--text-secondary); margin-top: 5px; display: block; height: 1.2em; }
        .btn-sm { padding: 6px 12px; font-size: 0.9em; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Multi-Farm Deep Control v2.3</h1>
            <p>Quản lý các server farm một cách tập trung và tiết kiệm tài nguyên.</p>
        </div>

        <div class="status-bar">
            <div class="status-item"><span>Trạng thái Bot</span><strong id="bot-status">Đang khởi động...</strong></div>
            <div class="status-item"><span>Tổng số Panel</span><strong id="total-panels">0</strong></div>
            <div class="status-item"><span>Lượt Drop Kế Tiếp</span><strong id="next-slot">Slot 1</strong></div>
            <div class="status-item"><span>Thời gian chờ</span><strong id="countdown">--:--:--</strong></div>
        </div>

        <div class="controls">
            <button id="add-panel-btn" class="btn"><i class="fas fa-plus"></i> Thêm Panel Mới</button>
            <button id="toggle-kd-btn" class="btn"></button>
        </div>    

        <div id="farm-grid" class="farm-grid"></div>
    </div>

<script>
document.addEventListener('DOMContentLoaded', function () {
    const API_ENDPOINT = '/api/panels';

    async function apiCall(method, data = null) {
        try {
            const options = { method: method, headers: { 'Content-Type': 'application/json' } };
            if (data) options.body = JSON.stringify(data);
            const response = await fetch(API_ENDPOINT, options);
            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
            return await response.json();
        } catch (error) {
            console.error('API call failed:', error);
            alert('Thao tác thất bại. Vui lòng kiểm tra console log.');
            return null;
        }
    }
    
    function renderPanels(panels) {
        const grid = document.getElementById('farm-grid');
        grid.innerHTML = '';
        if (!panels) return;
    
        const usedTokens = new Set();
        panels.forEach(p => {
            Object.values(p.accounts).forEach(token => {
                if (token) usedTokens.add(token);
            });
        });
    
        panels.forEach(panel => {
            const panelEl = document.createElement('div');
            panelEl.className = 'panel';
            panelEl.dataset.id = panel.id;
    
            let accountSlotsHTML = '';
            for (let i = 1; i <= 3; i++) {
                const slotKey = `slot_${i}`;
                const currentTokenForSlot = panel.accounts[slotKey] || '';
                let uniqueAccountOptions = '<option value="">-- Chọn tài khoản --</option>';
                
                {{ GLOBAL_ACCOUNTS_JSON | safe }}.forEach(acc => {
                    if (!usedTokens.has(acc.token) || acc.token === currentTokenForSlot) {
                        uniqueAccountOptions += `<option value="${acc.token}">${acc.name}</option>`;
                    }
                });
    
                accountSlotsHTML += `
                    <div class="input-group">
                        <label>Slot ${i}</label>
                        <select class="account-selector" data-slot="${slotKey}">${uniqueAccountOptions}</select>
                    </div>
                `;
            }
    
            panelEl.innerHTML = `
                <div class="panel-header">
                    <h3 contenteditable="true" class="panel-name">${panel.name}</h3>
                    <button class="btn btn-danger btn-sm delete-panel-btn"><i class="fas fa-trash"></i></button>
                </div>
                <div class="input-group">
                    <label>Channel ID</label>
                    <input type="text" class="channel-id-input" value="${panel.channel_id || ''}">
                    <small class="server-name-display">${panel.server_name || '(Tên server sẽ hiện ở đây)'}</small>
                </div>
                <div class="account-slots">${accountSlotsHTML}</div>
            `;
            grid.appendChild(panelEl);
            
            for (let i = 1; i <= 3; i++) {
                const slotKey = `slot_${i}`;
                const selectedToken = panel.accounts[slotKey] || '';
                panelEl.querySelector(`select[data-slot="${slotKey}"]`).value = selectedToken;
            }
        });
    }
    
    async function updateStatus() {
        try {
            const response = await fetch('/status');
            const data = await response.json();
            
            document.getElementById('bot-status').textContent = data.bot_ready ? 'Đang hoạt động' : 'Đang kết nối...';
            document.getElementById('total-panels').textContent = data.panels.length;
            document.getElementById('next-slot').textContent = `Slot ${data.current_drop_slot + 1}`;
            
            let timeString = new Date(data.countdown * 1000).toISOString().substr(11, 8);
            document.getElementById('countdown').textContent = timeString;

            const toggleBtn = document.getElementById('toggle-kd-btn');
            if (toggleBtn) {
                if (data.is_kd_loop_enabled) {
                    toggleBtn.textContent = 'TẮT VÒNG LẶP KD';
                    toggleBtn.classList.remove('btn-danger');
                } else {
                    toggleBtn.textContent = 'BẬT VÒNG LẶP KD';
                    toggleBtn.classList.add('btn-danger');
                }
            }
        } catch (e) {
            console.error("Error updating status:", e);
        }
    }

    async function fetchAndRenderPanels() {
        const response = await fetch('/status');
        const data = await response.json();
        renderPanels(data.panels);
    }
    
    document.getElementById('add-panel-btn').addEventListener('click', async () => {
        const name = prompt('Nhập tên cho panel mới:', 'Farm Server Mới');
        if (name) {
            await apiCall('POST', { name });
            fetchAndRenderPanels();
        }
    });

    document.getElementById('farm-grid').addEventListener('click', async (e) => {
        if (e.target.closest('.delete-panel-btn')) {
            const panelEl = e.target.closest('.panel');
            const panelId = panelEl.dataset.id;
            if (confirm(`Bạn có chắc muốn xóa panel "${panelEl.querySelector('.panel-name').textContent}"?`)) {
                await apiCall('DELETE', { id: panelId });
                fetchAndRenderPanels();
            }
        }
    });
    
    document.getElementById('farm-grid').addEventListener('change', async (e) => {
        const panelEl = e.target.closest('.panel');
        if (!panelEl) return;
        const panelId = panelEl.dataset.id;
        const payload = { id: panelId, update: {} };
    
        if (e.target.classList.contains('channel-id-input')) {
            payload.update.channel_id = e.target.value.trim();
            const updatedPanel = await apiCall('PUT', payload);
            if (updatedPanel) {
                const serverNameEl = panelEl.querySelector('.server-name-display');
                if (serverNameEl) {
                    serverNameEl.textContent = updatedPanel.server_name || '(Không tìm thấy server)';
                }
            }
        } else if (e.target.classList.contains('account-selector')) {
            const slot = e.target.dataset.slot;
            const token = e.target.value;
            payload.update.accounts = { [slot]: token };
            await apiCall('PUT', payload);
            fetchAndRenderPanels();
        }
    });
    
    document.getElementById('farm-grid').addEventListener('blur', async (e) => {
        if (e.target.classList.contains('panel-name')) {
             const panelEl = e.target.closest('.panel');
             const panelId = panelEl.dataset.id;
             const newName = e.target.textContent.trim();
             await apiCall('PUT', { id: panelId, update: { name: newName } });
        }
    }, true);

    document.getElementById('toggle-kd-btn').addEventListener('click', async () => {
        await fetch('/api/toggle_kd', { method: 'POST' });
        updateStatus();
    });

    setInterval(updateStatus, 1000);
    fetchAndRenderPanels(); 
});
</script>
</body>
</html>
"""

@app.route("/")
def index():
    global_accounts_json = json.dumps([{"name": acc["name"], "token": acc["token"]} for acc in GLOBAL_ACCOUNTS])
    return render_template_string(HTML_TEMPLATE, GLOBAL_ACCOUNTS_JSON=global_accounts_json)

@app.route("/api/panels", methods=['GET', 'POST', 'PUT', 'DELETE'])
def handle_panels():
    global panels
    if request.method == 'GET':
        return jsonify(panels)

    elif request.method == 'POST':
        data = request.get_json()
        name = data.get('name')
        if not name: return jsonify({"error": "Tên là bắt buộc"}), 400
        new_panel = {
            "id": f"panel_{int(time.time())}_{random.randint(1000,9999)}",
            "name": name,
            "channel_id": "",
            "server_name": "",
            "accounts": {f"slot_{i}": "" for i in range(1, 4)}
        }
        panels.append(new_panel)
        save_panels()
        return jsonify(new_panel), 201

    elif request.method == 'PUT':
        data = request.get_json()
        panel_id = data.get('id')
        update_data = data.get('update')
        panel_to_update = next((p for p in panels if p.get('id') == panel_id), None)
        if not panel_to_update: return jsonify({"error": "Không tìm thấy panel"}), 404

        if 'name' in update_data: 
            panel_to_update['name'] = update_data['name']

        if 'channel_id' in update_data:
            new_channel_id = update_data['channel_id'].strip()
            panel_to_update['channel_id'] = new_channel_id
            server_name = get_server_name_from_channel(new_channel_id)
            panel_to_update['server_name'] = server_name

        if 'accounts' in update_data:
            for slot, token in update_data['accounts'].items():
                panel_to_update['accounts'][slot] = token

        save_panels()
        return jsonify(panel_to_update)

    elif request.method == 'DELETE':
        data = request.get_json()
        panel_id = data.get('id')
        panels = [p for p in panels if p.get('id') != panel_id]
        save_panels()
        return jsonify({"message": "Đã xóa panel"}), 200

@app.route("/api/toggle_kd", methods=['POST'])
def toggle_kd():
    global is_kd_loop_enabled
    is_kd_loop_enabled = not is_kd_loop_enabled
    state = "BẬT" if is_kd_loop_enabled else "TẮT"
    print(f"[CONTROL] Vòng lặp gửi 'kd' đã được {state}.")
    return jsonify({"message": f"Vòng lặp đã được {state}.", "is_enabled": is_kd_loop_enabled})

# --- HÀM KHỞI CHẠY CHÍNH ---

async def main():
    global last_kd_cycle_time
    
    if not TOKENS_STR:
        print("Lỗi: Biến môi trường TOKENS chưa được thiết lập.")
        return

    load_panels()
    last_kd_cycle_time = time.time()

    # Khởi động Flask server
    def run_flask():
        try:
            from waitress import serve
            port = int(os.environ.get("PORT", 10000))
            print(f"Khởi động Web Server tại http://0.0.0.0:{port}")
            serve(app, host="0.0.0.0", port=port, threads=4)
        except Exception as e:
            print(f"[FLASK ERROR] Không thể khởi động server: {e}")
    
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    # Vòng lặp gửi 'kd' - ĐÃ TỐI ƯU
    async def drop_sender_loop():
        global current_drop_slot, last_kd_cycle_time
        
        print("Vòng lặp gửi 'kd' đang chờ TẤT CẢ các bot sẵn sàng...")
        while not bot_ready:
            await asyncio.sleep(1)
        
        print("=" * 60)
        print("TẤT CẢ BOT ĐÃ SẴN SÀNG - BẮT ĐẦU VÒNG LẶP GỬI 'KD'")
        print("=" * 60)
    
        while True:
            if not is_kd_loop_enabled:
                await asyncio.sleep(5)
                last_kd_cycle_time = time.time()
                continue
            
            try:
                slot_key = f"slot_{current_drop_slot + 1}"
                print(f"\n{'='*50}")
                print(f"ĐANG TRONG LƯỢT CỦA SLOT {current_drop_slot + 1}")
                print(f"{'='*50}")
    
                # Thu thập các task gửi tin nhắn
                send_tasks = []
                for panel in panels:
                    channel_id = panel.get("channel_id")
                    token_to_use = panel.get("accounts", {}).get(slot_key)
                    bot_to_use = GLOBAL_BOTS.get(token_to_use)
    
                    if bot_to_use and channel_id and channel_id.isdigit():
                        send_tasks.append({
                            'bot': bot_to_use,
                            'channel_id': channel_id,
                            'panel_name': panel.get('name', 'Unknown')
                        })
                
                if send_tasks:
                    print(f"Sẽ gửi {len(send_tasks)} lệnh 'kd' cho {slot_key}...")
                    
                    # Gửi TUẦN TỰ với delay nhỏ để tránh rate limit
                    for idx, task_info in enumerate(send_tasks, 1):
                        try:
                            await send_message_bot(
                                task_info['bot'], 
                                task_info['channel_id'], 
                                "kd"
                            )
                            print(f"  [{idx}/{len(send_tasks)}] Đã gửi 'kd' tới panel '{task_info['panel_name']}'")
                            
                            # Delay nhỏ giữa các lần gửi (tránh rate limit)
                            if idx < len(send_tasks):
                                await asyncio.sleep(0.5)
                                
                        except Exception as e:
                            print(f"  [ERROR] Lỗi khi gửi tới panel '{task_info['panel_name']}': {e}")
                    
                    print(f"✓ Đã hoàn thành gửi {len(send_tasks)} lệnh 'kd' cho {slot_key}.")
                else:
                    print(f"⚠ Không có tài khoản nào được cấu hình cho {slot_key}.")
    
                # Chuyển sang slot tiếp theo
                current_drop_slot = (current_drop_slot + 1) % 3
                
                print(f"\n→ Chờ 605 giây cho lượt kế tiếp (Slot {current_drop_slot + 1})...")
                last_kd_cycle_time = time.time()
                
                # Sleep với check định kỳ để có thể dừng nhanh nếu cần
                for _ in range(121):  # 121 * 5 = 605 giây
                    if not is_kd_loop_enabled:
                        break
                    await asyncio.sleep(5)
    
            except Exception as e:
                print(f"[DROP SENDER ERROR] Lỗi nghiêm trọng: {e}")
                import traceback
                traceback.print_exc()
                await asyncio.sleep(60)

    # Endpoint status được cập nhật
    @app.route("/status")
    def updated_status():
        remaining_time = 0
        if is_kd_loop_enabled:
            elapsed = time.time() - last_kd_cycle_time
            remaining_time = max(0, 605 - elapsed)
        else:
            remaining_time = 605

        return jsonify({
            "bot_ready": bot_ready,
            "panels": panels,
            "current_drop_slot": current_drop_slot,
            "countdown": remaining_time,
            "is_kd_loop_enabled": is_kd_loop_enabled
        })
    
    # Ghi đè route 'status'
    app.view_functions['status'] = updated_status

    # Tạo và chạy các task
    print("\n" + "="*60)
    print("ĐANG KHỞI ĐỘNG HỆ THỐNG MULTI-FARM")
    print("="*60 + "\n")
    
    sender_task = asyncio.create_task(drop_sender_loop(), name='drop_sender_loop')
    bots_task = asyncio.create_task(run_all_bots(), name='run_all_bots')

    # Chạy đồng thời 2 task chính
    await asyncio.gather(sender_task, bots_task)


if __name__ == "__main__":
    try:
        import waitress
    except ImportError:
        print("Đang cài đặt waitress...")
        os.system('pip install waitress')
        
    # Chạy event loop chính
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n[SHUTDOWN] Đang dừng bot...")
    except Exception as e:
        print(f"\n[FATAL ERROR] Lỗi nghiêm trọng: {e}")
        import traceback
        traceback.print_exc()
