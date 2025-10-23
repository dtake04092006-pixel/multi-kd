# TÊN FILE: main.py
# PHIÊN BẢN: Multi-Farm Deep Control v2.2 (All-Online)
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

# Biến trạng thái, sẽ được load từ JSONBin
panels = []
current_drop_slot = 0 # Slot đang trong lượt drop (0-2)
is_kd_loop_enabled = True

# Biến trạng thái bot MỚI
bot_ready = False # Sẽ là True khi TẤT CẢ các bot đã sẵn sàng
GLOBAL_BOTS = {} # Map: token -> bot_instance
bot_ready_flags = {} # Map: token -> bool (để theo dõi từng bot)
last_kd_cycle_time = 0 # Thời gian của lần gửi 'kd' cuối


# --- CÁC HÀM TIỆN ÍCH & API DISCORD (ĐÃ THAY ĐỔI) ---

async def send_message_bot(bot_instance, channel_id, content):
    """Gửi tin nhắn bằng bot instance (thay vì HTTP)."""
    if not bot_instance or not channel_id: return
    try:
        channel = bot_instance.get_channel(int(channel_id))
        if channel:
            await channel.send(content)
            print(f"[{bot_instance.user.name}] Gửi '{content}' tới kênh {channel_id} thành công.")
        else:
            # Bot không thể thấy kênh này, có thể do lỗi phân quyền
            print(f"[{bot_instance.user.name}] Lỗi: Không tìm thấy kênh {channel_id}.")
    except discord.errors.Forbidden:
        print(f"[{bot_instance.user.name}] Lỗi: Không có quyền gửi tin nhắn tới kênh {channel_id}.")
    except Exception as e:
        print(f"[{bot_instance.user.name}] Lỗi ngoại lệ khi gửi tin nhắn: {e}")

async def add_reaction_bot(bot_instance, channel_id, message_id, emoji):
    """Thả reaction bằng bot instance (thay vì HTTP)."""
    if not bot_instance or not channel_id: return
    try:
        # Sử dụng bot.http.add_reaction đáng tin cậy hơn
        await bot_instance.http.add_reaction(channel_id, message_id, emoji)
        # print(f"[{bot_instance.user.name}] Thả reaction {emoji} thành công.")
    except discord.errors.Forbidden:
        print(f"[{bot_instance.user.name}] Lỗi: Không có quyền thả reaction tại {channel_id}.")
    except Exception as e:
        print(f"[{bot_instance.user.name}] Lỗi ngoại lệ khi thả reaction: {e}")


# --- LƯU & TẢI CẤU HÌNH PANEL ---
# (Không thay đổi - Giữ nguyên các hàm save_panels, load_panels, get_server_name_from_channel)
def save_panels():
    """Lưu cấu hình các panel lên JSONBin.io"""
    api_key = os.getenv("JSONBIN_API_KEY")
    bin_id = os.getenv("JSONBIN_BIN_ID")
    if not api_key or not bin_id:
        print("[Settings] Thiếu API Key hoặc Bin ID của JSONBin. Bỏ qua việc lưu.")
        return

    headers = {'Content-Type': 'application/json', 'X-Master-Key': api_key}
    url = f"https://api.jsonbin.io/v3/b/{bin_id}"
    try:
        def do_save():
            req = requests.put(url, json=panels, headers=headers, timeout=15)
            if req.status_code == 200:
                print("[Settings] Đã lưu cấu hình panels lên JSONBin.io thành công.")
            else:
                print(f"[Settings] Lỗi khi lưu cài đặt: {req.status_code} - {req.text}")
        threading.Thread(target=do_save, daemon=True).start()
    except Exception as e:
        print(f"[Settings] Exception khi lưu cài đặt: {e}")

def load_panels():
    """Tải cấu hình các panel từ JSONBin.io"""
    global panels
    api_key = os.getenv("JSONBIN_API_KEY")
    bin_id = os.getenv("JSONBIN_BIN_ID")
    if not api_key or not bin_id:
        print("[Settings] Thiếu API Key hoặc Bin ID của JSONBin. Bắt đầu với cấu hình rỗng.")
        return

    headers = {'X-Master-Key': api_key, 'X-Bin-Meta': 'false'}
    url = f"https://api.jsonbin.io/v3/b/{bin_id}/latest"
    try:
        req = requests.get(url, headers=headers, timeout=15)
        if req.status_code == 200:
            data = req.json()
            if isinstance(data, list):
                panels = data
                print(f"[Settings] Đã tải {len(panels)} panel từ JSONBin.io.")
            else:
                save_panels() # Nếu dữ liệu rỗng hoặc sai, tạo mới
        else:
            print(f"[Settings] Lỗi khi tải cài đặt: {req.status_code} - {req.text}")
    except Exception as e:
        print(f"[Settings] Exception khi tải cài đặt: {e}")

def get_server_name_from_channel(channel_id):
    """Lấy tên server từ Channel ID thông qua Discord API. (Vẫn dùng HTTP cho việc này vì nó chạy trong thread Flask)"""
    if not channel_id or not channel_id.isdigit():
        return "ID kênh không hợp lệ"
    if not GLOBAL_ACCOUNTS:
        return "Không có token để xác thực"

    token = GLOBAL_ACCOUNTS[0]["token"] # Dùng token đầu tiên để check
    headers = {"Authorization": token}

    try:
        channel_res = requests.get(f"https://discord.com/api/v9/channels/{channel_id}", headers=headers, timeout=10)
        if channel_res.status_code != 200:
            return "Không tìm thấy kênh"

        channel_data = channel_res.json()
        guild_id = channel_data.get("guild_id")

        if not guild_id:
            return "Đây là kênh DM/Group"

        guild_res = requests.get(f"https://discord.com/api/v9/guilds/{guild_id}", headers=headers, timeout=10)
        if guild_res.status_code == 200:
            return guild_res.json().get("name", "Không thể lấy tên server")
        else:
            return "Không thể truy cập server"

    except requests.RequestException:
        return "Lỗi mạng"

# --- LOGIC BOT CHÍNH (ĐÃ THAY ĐỔI) ---

# (Hàm drop_sender_loop sẽ được định nghĩa lại bên trong main())

async def handle_reactions(panel, message):
    """Xử lý việc thả reaction cho 3 tài khoản trong một panel. (Dùng bot instance)"""
    accounts_in_panel = panel.get("accounts", {})
    if not accounts_in_panel: return

    emojis = ["1️⃣", "2️⃣", "3️⃣"]
    grab_times = [1.3, 2.3, 3.2] # Giữ nguyên thời gian delay
    
    tasks = []
    for i in range(3):
        slot_key = f"slot_{i + 1}"
        token = accounts_in_panel.get(slot_key)
        
        # Lấy bot instance từ token
        bot_to_react = GLOBAL_BOTS.get(token) 
        
        if bot_to_react: # Chỉ thực hiện nếu bot tồn tại và đang chạy
            delay = grab_times[i]
            emoji = emojis[i]
            
            async def react_task(bot, ch_id, msg_id, em, d):
                await asyncio.sleep(d)
                # Gọi hàm add_reaction_bot mới
                await add_reaction_bot(bot, ch_id, msg_id, em)
            
            tasks.append(react_task(bot_to_react, message.channel.id, message.id, emoji, delay))

    if tasks:
        await asyncio.gather(*tasks)
        print(f"Đã hoàn thành các tác vụ reaction cho drop trong kênh {message.channel.id}")

async def run_single_bot(bot, token):
    """Hàm trợ giúp để chạy một bot và xử lý lỗi đăng nhập."""
    try:
        await bot.start(token)
    except discord.errors.LoginFailure:
        print(f"LỖI ĐĂNG NHẬP NGHIÊM TRỌNG với token của tài khoản. Vui lòng kiểm tra lại token!")
        bot_ready_flags[token] = False # Đánh dấu là lỗi
    except Exception as e:
        print(f"Lỗi không xác định với bot (Token: ...{token[-5:]}): {e}")
        bot_ready_flags[token] = False

async def run_all_bots():
    """Khởi chạy TẤT CẢ các tài khoản dưới dạng bot client."""
    global bot_ready, GLOBAL_BOTS, bot_ready_flags
    
    if not GLOBAL_ACCOUNTS:
        print("Không có token nào trong biến môi trường. Bot không thể khởi động.")
        bot_ready = True
        return

    print(f"Chuẩn bị khởi chạy {len(GLOBAL_ACCOUNTS)} tài khoản...")
    
    tasks = []
    for i, acc in enumerate(GLOBAL_ACCOUNTS):
        token = acc["token"]
        bot_ready_flags[token] = False
        
        # Tạo bot instance
        # self_bot=True là cần thiết cho user token
        # prefix ngẫu nhiên để tránh xung đột
        bot = commands.Bot(command_prefix=f"!prefix_ko_dung_{random.randint(1000, 9999)}", self_bot=True)
        GLOBAL_BOTS[token] = bot # Lưu bot instance
        
        # Gắn sự kiện on_ready cho TẤT CẢ các bot
        @bot.event
        async def on_ready(token=token): # Dùng closure để bắt giá trị token
            global bot_ready
            current_bot = GLOBAL_BOTS[token]
            print(f"[BOT READY] Tài khoản '{current_bot.user.name}' (ID: {current_bot.user.id}) đã kết nối.")
            bot_ready_flags[token] = True
            
            # Kiểm tra xem tất cả bot đã sẵn sàng chưa
            if all(bot_ready_flags.values()):
                print("-" * 30)
                print(f"TẤT CẢ ({len(GLOBAL_BOTS)}) CÁC BOT ĐÃ SẴN SÀNG!")
                print("-" * 30)
                bot_ready = True # Chỉ set True khi tất cả cùng online

        # CHỈ gắn sự kiện on_message cho bot ĐẦU TIÊN (bot lắng nghe)
        if i == 0:
            listener_name = acc["name"]
            print(f"-> Gắn '{listener_name}' làm BOT LẮNG NGHE CHÍNH.")
            
            @bot.event
            async def on_message(message):
                # Chỉ xử lý nếu là drop của Karuta
                if message.author.id != KARUTA_ID or "is dropping 3 cards!" not in message.content:
                    return

                # Tìm panel tương ứng với kênh này
                found_panel = None
                for p in panels:
                    if p.get("channel_id") == str(message.channel.id):
                        found_panel = p
                        break
                
                if found_panel:
                    print(f"[LISTENER] Phát hiện drop trong kênh {message.channel.id} (Panel: '{found_panel.get('name')}')")
                    # Tạo task để xử lý reaction, không làm nghẽn bot
                    asyncio.create_task(handle_reactions(found_panel, message))

        # Tạo task để chạy bot này
        tasks.append(run_single_bot(bot, token))

    # Chạy tất cả các bot song song
    await asyncio.gather(*tasks)


# --- GIAO DIỆN WEB & API FLASK ---
# (Không thay đổi - Giữ nguyên toàn bộ phần Flask)
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
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; background-color: var(--primary-bg); color: var(--text-primary); margin: 0; padding: 20px; }
        .container { max-width: 1800px; margin: 0 auto; }
        .header { text-align: center; margin-bottom: 30px; }
        .header h1 { color: var(--accent-color); font-weight: 600; }
        .status-bar { display: flex; justify-content: space-around; background-color: var(--secondary-bg); padding: 15px; border-radius: 8px; margin-bottom: 20px; flex-wrap: wrap; gap: 15px; }
        .status-item { text-align: center; }
        .status-item span { display: block; font-size: 0.9em; color: var(--text-secondary); }
        .status-item strong { font-size: 1.2em; color: var(--accent-color); }
        .controls { display: flex; justify-content: center; margin-bottom: 30px; }
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
        .server-name-display { 
            font-size: 0.8em; 
            color: var(--text-secondary); 
            margin-top: 5px; 
            display: block;
            height: 1.2em;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Multi-Farm Deep Control</h1>
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
            <button id="toggle-kd-btn" class="btn" style="margin-left: 15px;"></button>
        </div>    

        <div id="farm-grid" class="farm-grid">
        </div>
    </div>

<script>
document.addEventListener('DOMContentLoaded', function () {
    const API_ENDPOINT = '/api/panels';

    async function apiCall(method, data = null) {
        try {
            const options = {
                method: method,
                headers: { 'Content-Type': 'application/json' },
            };
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
                if (token) {
                    usedTokens.add(token);
                }
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
                    // Chỉ hiển thị token nếu nó chưa được dùng ở panel KHÁC, hoặc nó đang được dùng ở chính slot này
                    if (!usedTokens.has(acc.token) || acc.token === currentTokenForSlot) {
                        uniqueAccountOptions += `<option value="${acc.token}">${acc.name}</option>`;
                    }
                });
    
                accountSlotsHTML += `
                    <div class="input-group">
                        <label>Slot ${i}</label>
                        <select class="account-selector" data-slot="${slotKey}">
                            ${uniqueAccountOptions}
                        </select>
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
            
            let countdown = data.countdown;
            let timeString = new Date(countdown * 1000).toISOString().substr(11, 8);
            document.getElementById('countdown').textContent = timeString;

            const toggleBtn = document.getElementById('toggle-kd-btn');
            if (toggleBtn) {
                if (data.is_kd_loop_enabled) {
                    toggleBtn.textContent = 'TẮT VÒNG LẶP KD';
                    toggleBtn.classList.remove('btn-danger');
                    document.getElementById('next-slot').style.color = 'var(--accent-color)';
                } else {
                    toggleBtn.textContent = 'BẬT VÒNG LẶP KD';
                    toggleBtn.classList.add('btn-danger');
                    document.getElementById('next-slot').style.color = 'var(--danger-color)';
                }
            }
        } catch (e) {
            console.error("Error updating status:", e);
        }
    }

    async function fetchAndRenderPanels() {
        // Lấy status để có thông tin panels
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
            
            // Gửi API call để LƯU và LẤY tên server
            const updatedPanel = await apiCall('PUT', payload);
    
            // Cập nhật tên server ngay lập tức
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

            // BƯỚC 1: Gửi API call để LƯU lựa chọn mới
            await apiCall('PUT', payload);

            // BƯỚC 2: SAU KHI LƯU, vẽ lại tất cả các panel để cập nhật giao diện và danh sách ẩn
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

    const toggleBtn = document.getElementById('toggle-kd-btn');
    if (toggleBtn) {
        toggleBtn.addEventListener('click', async () => {
            await fetch('/api/toggle_kd', { method: 'POST' });
            updateStatus();
        });
    }

    setInterval(updateStatus, 1000); // Update countdown every second
    fetchAndRenderPanels(); 
});
</script>
</body>
</html>
"""

@app.route("/")
def index():
    # Cung cấp danh sách tài khoản cho template HTML
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
            "id": f"panel_{int(time.time())}",
            "name": name,
            "channel_id": "",
            "server_name": "",
            "accounts": {f"slot_{i}": "" for i in range(1, 4)} # 3 slots
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

        if 'name' in update_data: panel_to_update['name'] = update_data['name']

        if 'channel_id' in update_data:
            new_channel_id = update_data['channel_id'].strip()
            panel_to_update['channel_id'] = new_channel_id
            # Lấy tên server ngay khi cập nhật channel ID
            server_name = get_server_name_from_channel(new_channel_id)
            panel_to_update['server_name'] = server_name

        if 'accounts' in update_data:
            for slot, token in update_data['accounts'].items():
                panel_to_update['accounts'][slot] = token

        save_panels()
        return jsonify(panel_to_update) # Trả về panel đã cập nhật (với server_name)

    elif request.method == 'DELETE':
        data = request.get_json()
        panel_id = data.get('id')
        panels = [p for p in panels if p.get('id') != panel_id]
        save_panels()
        return jsonify({"message": "Đã xóa panel"}), 200
        
@app.route("/status")
def status():
    # Hàm này sẽ bị ghi đè bởi updated_status trong main()
    # Nhưng chúng ta giữ nó ở đây để tránh lỗi nếu main() chưa chạy tới
    return jsonify({
        "bot_ready": bot_ready,
        "panels": panels,
        "current_drop_slot": current_drop_slot,
        "countdown": 605,
        "is_kd_loop_enabled": is_kd_loop_enabled
    })
    
@app.route("/api/toggle_kd", methods=['POST'])
def toggle_kd():
    global is_kd_loop_enabled
    is_kd_loop_enabled = not is_kd_loop_enabled
    state = "BẬT" if is_kd_loop_enabled else "TẮT"
    print(f"[CONTROL] Vòng lặp gửi 'kd' đã được {state}.")
    return jsonify({"message": f"Vòng lặp gửi 'kd' đã được {state}.", "is_enabled": is_kd_loop_enabled})

# --- HÀM KHỞI CHẠY CHÍNH ---

async def main():
    global last_kd_cycle_time
    if not TOKENS_STR:
        print("Lỗi: Biến môi trường TOKENS chưa được thiết lập. Vui lòng thêm token vào file .env.")
        return

    load_panels()
    
    last_kd_cycle_time = time.time() # Khởi tạo đồng hồ bấm giờ

    def run_flask():
        try:
            from waitress import serve
            port = int(os.environ.get("PORT", 10000))
            print(f"Khởi động Web Server tại http://0.0.0.0:{port}")
            serve(app, host="0.0.0.0", port=port)
        except Exception as e:
            print(f"[FLASK ERROR] Không thể khởi động server: {e}")
    
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    # Vòng lặp gửi 'kd' được cập nhật để dùng bot instance
    async def updated_drop_sender_loop():
        global current_drop_slot, last_kd_cycle_time
        print("Vòng lặp gửi 'kd' đang chờ TẤT CẢ các bot sẵn sàng...")
        while not bot_ready:
            await asyncio.sleep(1)
        print("Tất cả bot đã sẵn sàng. Bắt đầu vòng lặp gửi 'kd'.")
    
        while True:
            if not is_kd_loop_enabled:
                await asyncio.sleep(5)
                # Khi tạm dừng, reset đồng hồ
                last_kd_cycle_time = time.time()
                continue
            
            try:
                slot_key = f"slot_{current_drop_slot + 1}"
                print(f"\n--- Đang trong lượt của Slot {current_drop_slot + 1} ---")
    
                tasks = []
                active_sends = 0
                for panel in panels:
                    channel_id = panel.get("channel_id")
                    token_to_use = panel.get("accounts", {}).get(slot_key)
                    
                    # Thay thế logic HTTP bằng logic bot instance
                    bot_to_use = GLOBAL_BOTS.get(token_to_use)
    
                    if bot_to_use and channel_id:
                        # task = asyncio.to_thread(send_message_http, token_to_use, channel_id, "kd")
                        task = send_message_bot(bot_to_use, channel_id, "kd") # Dùng hàm mới
                        tasks.append(task)
                        active_sends +=1
                    
                if tasks:
                    print(f"Gửi đồng thời {active_sends} lệnh 'kd' cho các tài khoản ở {slot_key}...")
                    await asyncio.gather(*tasks)
                else:
                    print(f"Không có tài khoản nào được cấu hình cho {slot_key} trong bất kỳ panel nào.")
    
                current_drop_slot = (current_drop_slot + 1) % 3
    
                print(f"Đã xong lượt. Chờ 605 giây cho lượt kế tiếp (Slot {current_drop_slot + 1})...")
                last_kd_cycle_time = time.time() # Reset đồng hồ sau khi gửi
                await asyncio.sleep(605)
    
            except Exception as e:
                print(f"[DROP SENDER ERROR] Lỗi nghiêm trọng trong vòng lặp gửi 'kd': {e}")
                await asyncio.sleep(60) # Chờ 1 phút nếu có lỗi

    # Endpoint status được cập nhật để tính toán thời gian countdown
    @app.route("/status")
    def updated_status():
        remaining_time = 0
        if is_kd_loop_enabled:
            elapsed = time.time() - last_kd_cycle_time
            remaining_time = max(0, 605 - elapsed)
        else:
            remaining_time = 605 # Hiển thị thời gian đầy đủ nếu đang tắt

        return jsonify({
            "bot_ready": bot_ready, # Trạng thái chung của tất cả các bot
            "panels": panels,
            "current_drop_slot": current_drop_slot,
            "countdown": remaining_time,
            "is_kd_loop_enabled": is_kd_loop_enabled
        })
    
    # Ghi đè route 'status' cũ bằng route 'updated_status' mới
    app.view_functions['status'] = updated_status

    # Tạo task cho vòng lặp gửi 'kd'
    sender_task = asyncio.create_task(updated_drop_sender_loop(), name='drop_sender_loop')
    
    # Tạo task để chạy TẤT CẢ các bot
    bots_task = asyncio.create_task(run_all_bots(), name='run_all_bots')

    # Chạy đồng thời 2 task chính
    await asyncio.gather(sender_task, bots_task)


if __name__ == "__main__":
    try:
        import waitress
    except ImportError:
        print("Đang cài đặt waitress...")
        os.system('pip install waitress')
        
    asyncio.run(main())
