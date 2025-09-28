# TÊN FILE: main.py
# PHIÊN BẢN: Multi-Farm Deep Control v2.0
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
current_drop_slot = 0 # Slot đang trong lượt drop (0-5)
bot_ready = False
listener_bot = None

# --- CÁC HÀM TIỆN ÍCH & API DISCORD ---

def send_message_http(token, channel_id, content):
    """Gửi tin nhắn đến một kênh bằng requests, không cần bot instance."""
    if not token or not channel_id: return
    headers = {"Authorization": token}
    payload = {"content": content}
    url = f"https://discord.com/api/v9/channels/{channel_id}/messages"
    try:
        res = requests.post(url, headers=headers, json=payload, timeout=10)
        if res.status_code == 200:
            print(f"[HTTP SEND] Gửi '{content}' tới kênh {channel_id} thành công.")
        else:
            print(f"[HTTP SEND ERROR] Lỗi khi gửi tin nhắn tới kênh {channel_id}: {res.status_code} {res.text}")
    except Exception as e:
        print(f"[HTTP SEND EXCEPTION] Lỗi ngoại lệ khi gửi tin nhắn: {e}")

def add_reaction_http(token, channel_id, message_id, emoji):
    """Thả reaction vào tin nhắn bằng requests."""
    if not token or not channel_id: return
    headers = {"Authorization": token}
    # Emoji cần được URL-encoded (ví dụ: 1️⃣ -> %31%EF%B8%8F%E2%83%A3)
    encoded_emoji = requests.utils.quote(emoji)
    url = f"https://discord.com/api/v9/channels/{channel_id}/messages/{message_id}/reactions/{encoded_emoji}/@me"
    try:
        res = requests.put(url, headers=headers, timeout=10)
        if res.status_code != 204: # 204 No Content là thành công
             print(f"[HTTP REACT ERROR] Lỗi khi thả reaction {emoji} tới kênh {channel_id}: {res.status_code} {res.text}")
    except Exception as e:
        print(f"[HTTP REACT EXCEPTION] Lỗi ngoại lệ khi thả reaction: {e}")

# --- LƯU & TẢI CẤU HÌNH PANEL ---
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
        # Chạy trong luồng riêng để không block
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
            else: # Nếu bin rỗng hoặc sai định dạng
                save_panels() # Lưu cấu trúc rỗng lên
        else:
            print(f"[Settings] Lỗi khi tải cài đặt: {req.status_code} - {req.text}")
    except Exception as e:
        print(f"[Settings] Exception khi tải cài đặt: {e}")


# --- LOGIC BOT CHÍNH ---

async def drop_sender_loop():
    """Vòng lặp gửi 'kd', luân phiên giữa các slot tài khoản."""
    global current_drop_slot
    print("Vòng lặp gửi 'kd' đang chờ bot sẵn sàng...")
    while not bot_ready:
        await asyncio.sleep(1)
    print("Bot đã sẵn sàng. Bắt đầu vòng lặp gửi 'kd'.")

    while True:
        try:
            slot_key = f"slot_{current_drop_slot + 1}"
            print(f"\n--- Đang trong lượt của Slot {current_drop_slot + 1} ---")

            tasks = []
            active_sends = 0
            # Duyệt qua tất cả các panel đã cấu hình
            for panel in panels:
                channel_id = panel.get("channel_id")
                # Lấy ra token được gán cho slot hiện tại trong panel này
                token_to_use = panel.get("accounts", {}).get(slot_key)

                if token_to_use and channel_id:
                    # Tạo task gửi tin nhắn bằng HTTP request
                    # Dùng lambda để bắt giá trị của token và channel_id tại thời điểm lặp
                    task = asyncio.to_thread(send_message_http, token_to_use, channel_id, "kd")
                    tasks.append(task)
                    active_sends +=1
                
            if tasks:
                print(f"Gửi đồng thời {active_sends} lệnh 'kd' cho các tài khoản ở {slot_key}...")
                await asyncio.gather(*tasks)
            else:
                print(f"Không có tài khoản nào được cấu hình cho {slot_key} trong bất kỳ panel nào.")

            # Chuyển sang slot tiếp theo, quay vòng từ 0 đến 5
            current_drop_slot = (current_drop_slot + 1) % 6

            print(f"Đã xong lượt. Chờ 305 giây cho lượt kế tiếp (Slot {current_drop_slot + 1})...")
            await asyncio.sleep(305)

        except Exception as e:
            print(f"[DROP SENDER ERROR] Lỗi nghiêm trọng trong vòng lặp gửi 'kd': {e}")
            await asyncio.sleep(60) # Chờ 1 phút nếu có lỗi rồi thử lại

async def handle_reactions(panel, message):
    """Xử lý việc thả reaction cho 6 tài khoản trong một panel."""
    accounts_in_panel = panel.get("accounts", {})
    if not accounts_in_panel: return

    emojis = ["1️⃣", "2️⃣", "3️⃣", "1️⃣", "2️⃣", "3️⃣"]
    grab_times = [1.3, 2.3, 3.2, 1.3, 2.3, 3.2]
    
    tasks = []
    for i in range(6):
        slot_key = f"slot_{i + 1}"
        token = accounts_in_panel.get(slot_key)
        if token:
            delay = grab_times[i]
            emoji = emojis[i]
            # Tạo coroutine để sleep và sau đó gọi hàm http sync
            async def react_task(t, ch_id, msg_id, em, d):
                await asyncio.sleep(d)
                # Chạy hàm blocking (requests) trong một luồng riêng
                await asyncio.to_thread(add_reaction_http, t, ch_id, msg_id, em)
            
            tasks.append(react_task(token, message.channel.id, message.id, emoji, delay))

    if tasks:
        await asyncio.gather(*tasks)
        print(f"Đã hoàn thành các tác vụ reaction cho drop trong kênh {message.channel.id}")


async def run_listener_bot():
    """Chạy một bot duy nhất để lắng nghe sự kiện drop."""
    global bot_ready, listener_bot
    if not GLOBAL_ACCOUNTS:
        print("Không có token nào trong biến môi trường. Bot không thể khởi động.")
        bot_ready = True # Đánh dấu để các vòng lặp khác không bị kẹt
        return
    
    # Sử dụng token của tài khoản đầu tiên để lắng nghe
    listener_token = GLOBAL_ACCOUNTS[0]["token"]
    
    listener_bot = commands.Bot(command_prefix="!слушать", self_bot=True)

    @listener_bot.event
    async def on_ready():
        global bot_ready
        print("-" * 30)
        print(f"BOT LẮNG NGHE ĐÃ SẴN SÀNG!")
        print(f"Đăng nhập với tài khoản: {listener_bot.user} (ID: {listener_bot.user.id})")
        print("Bot này chỉ dùng để nhận diện drop, các hành động khác sẽ được thực hiện qua HTTP.")
        print("-" * 30)
        bot_ready = True

    @listener_bot.event
    async def on_message(message):
        # Lọc tin nhắn: chỉ từ Karuta và có nội dung drop
        if message.author.id != KARUTA_ID or "is dropping 3 cards!" not in message.content:
            return

        # Tìm xem tin nhắn này thuộc panel nào
        found_panel = None
        for p in panels:
            if p.get("channel_id") == str(message.channel.id):
                found_panel = p
                break
        
        # Nếu tìm thấy panel tương ứng, xử lý thả reaction
        if found_panel:
            print(f"Phát hiện drop trong kênh {message.channel.id} (Panel: '{found_panel.get('name')}')")
            # Tạo task mới để không block on_message
            asyncio.create_task(handle_reactions(found_panel, message))

    try:
        await listener_bot.start(listener_token)
    except discord.errors.LoginFailure:
        print(f"LỖI ĐĂNG NHẬP NGHIÊM TRỌNG với token của bot lắng nghe. Vui lòng kiểm tra TOKEN đầu tiên trong file .env.")
        bot_ready = True # Thoát khỏi vòng lặp chờ
    except Exception as e:
        print(f"Lỗi không xác định với bot lắng nghe: {e}")
        bot_ready = True


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
        .account-slots { display: grid; grid-template-columns: 1fr 1fr; gap: 15px; }
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
            <div class="status-item"><span>Thời gian chờ</span><strong id="countdown">--:--</strong></div>
        </div>

        <div class="controls">
            <button id="add-panel-btn" class="btn"><i class="fas fa-plus"></i> Thêm Panel Mới</button>
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

        panels.forEach(panel => {
            const panelEl = document.createElement('div');
            panelEl.className = 'panel';
            panelEl.dataset.id = panel.id;

            let accountOptions = '<option value="">-- Chọn tài khoản --</option>';
            {{ GLOBAL_ACCOUNTS_JSON | safe }}.forEach(acc => {
                accountOptions += `<option value="${acc.token}">${acc.name}</option>`;
            });
            
            let accountSlotsHTML = '';
            for (let i = 1; i <= 6; i++) {
                const slotKey = `slot_${i}`;
                const selectedToken = panel.accounts[slotKey] || '';
                accountSlotsHTML += `
                    <div class="input-group">
                        <label>Slot ${i}</label>
                        <select class="account-selector" data-slot="${slotKey}">
                            ${accountOptions}
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
                    <input type="text" class="channel-id-input" value="${panel.channel_id}">
                </div>
                <div class="account-slots">${accountSlotsHTML}</div>
            `;
            grid.appendChild(panelEl);
            
            // Set selected values for dropdowns after they are in the DOM
            for (let i = 1; i <= 6; i++) {
                const slotKey = `slot_${i}`;
                const selectedToken = panel.accounts[slotKey] || '';
                panelEl.querySelector(`select[data-slot="${slotKey}"]`).value = selectedToken;
            }
        });
    }

    async function refreshData() {
        const response = await fetch('/status');
        const data = await response.json();
        
        document.getElementById('bot-status').textContent = data.bot_ready ? 'Đang hoạt động' : 'Đang kết nối...';
        document.getElementById('total-panels').textContent = data.panels.length;
        document.getElementById('next-slot').textContent = `Slot ${data.current_drop_slot + 1}`;
        document.getElementById('countdown').textContent = new Date(data.countdown * 1000).toISOString().substr(14, 5);
        renderPanels(data.panels);
    }
    
    document.getElementById('add-panel-btn').addEventListener('click', async () => {
        const name = prompt('Nhập tên cho panel mới:', 'Farm Server Mới');
        if (name) {
            await apiCall('POST', { name });
            refreshData();
        }
    });

    document.getElementById('farm-grid').addEventListener('click', async (e) => {
        if (e.target.closest('.delete-panel-btn')) {
            const panelEl = e.target.closest('.panel');
            const panelId = panelEl.dataset.id;
            if (confirm(`Bạn có chắc muốn xóa panel "${panelEl.querySelector('.panel-name').textContent}"?`)) {
                await apiCall('DELETE', { id: panelId });
                refreshData();
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
        } else if (e.target.classList.contains('account-selector')) {
            const slot = e.target.dataset.slot;
            const token = e.target.value;
            payload.update.accounts = { [slot]: token };
        } else {
            return;
        }

        await apiCall('PUT', payload);
        // No need to refresh, the change is already reflected in the UI. 
        // We can add a visual confirmation if needed.
    });
    
    document.getElementById('farm-grid').addEventListener('blur', async (e) => {
        if (e.target.classList.contains('panel-name')) {
             const panelEl = e.target.closest('.panel');
             const panelId = panelEl.dataset.id;
             const newName = e.target.textContent.trim();
             await apiCall('PUT', { id: panelId, update: { name: newName } });
        }
    }, true);


    setInterval(refreshData, 2000);
    refreshData();
});
</script>
</body>
</html>
"""

@app.route("/")
def index():
    # Chuyển danh sách tài khoản sang dạng JSON để nhúng vào template HTML
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
            "accounts": {f"slot_{i}": "" for i in range(1, 7)}
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
        if 'channel_id' in update_data: panel_to_update['channel_id'] = update_data['channel_id']
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

@app.route("/status")
def status():
    # Tính toán thời gian còn lại cho lần drop kế tiếp
    # Đây là ước tính, không chính xác 100% nhưng đủ cho UI
    # Lấy thời gian từ lần chạy cuối của vòng lặp chính
    loop = asyncio.get_event_loop()
    tasks = [t for t in asyncio.all_tasks(loop) if t.get_name() == 'drop_sender_loop']
    countdown = 305
    # Logic tính toán countdown phức tạp, tạm thời trả về giá trị tĩnh
    # Để chính xác hơn cần chia sẻ state giữa luồng asyncio và flask
    
    return jsonify({
        "bot_ready": bot_ready,
        "panels": panels,
        "current_drop_slot": current_drop_slot,
        "countdown": countdown, 
    })


# --- HÀM KHỞI CHẠY CHÍNH ---
async def main():
    if not TOKENS_STR:
        print("Lỗi: Biến môi trường TOKENS chưa được thiết lập. Vui lòng thêm token vào file .env.")
        return

    # Tải cấu hình đã lưu
    load_panels()

    # Khởi chạy web server trong một luồng riêng
    def run_flask():
        # Sử dụng waitress thay cho server mặc định của Flask để tốt hơn cho production
        from waitress import serve
        port = int(os.environ.get("PORT", 10000))
        print(f"Khởi động Web Server tại http://0.0.0.0:{port}")
        serve(app, host="0.0.0.0", port=port)
    
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    # Tạo các task asyncio chính
    sender_task = asyncio.create_task(drop_sender_loop(), name='drop_sender_loop')
    listener_task = asyncio.create_task(run_listener_bot(), name='listener_bot')

    await asyncio.gather(sender_task, listener_task)


if __name__ == "__main__":
    # Cài đặt thư viện cần thiết
    try:
        import waitress
    except ImportError:
        print("Đang cài đặt waitress...")
        os.system('pip install waitress')
        
    asyncio.run(main())
