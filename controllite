import discord
import asyncio
import threading
import time
import os
from flask import Flask, request, render_template_string, jsonify
from dotenv import load_dotenv

# --- CẤU HÌNH ---
# Load các biến từ file .env
load_dotenv()

# Lấy chuỗi token và tách thành list dựa trên dấu phẩy
token_string = os.getenv("DISCORD_TOKENS", "")
TOKENS = [t.strip() for t in token_string.split(",") if t.strip()]

# Lấy cấu hình delay và port từ env (hoặc dùng giá trị mặc định nếu không có)
try:
    DELAY_SECONDS = int(os.getenv("DELAY_SECONDS", 2))
except ValueError:
    DELAY_SECONDS = 2

# --- KHỞI TẠO ---
app = Flask(__name__)
active_bots = {} 
bot_logs = []

def log_msg(content):
    timestamp = time.strftime("%H:%M:%S")
    entry = f"[{timestamp}] {content}"
    print(entry)
    bot_logs.insert(0, entry)
    if len(bot_logs) > 50: bot_logs.pop()

# --- PHẦN BOT DISCORD ---
class DiscordBot(discord.Client):
    def __init__(self, token_index, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.token_index = token_index

    async def on_ready(self):
        log_msg(f"✅ Bot {self.token_index + 1} đã kết nối: {self.user.name}")
        active_bots[self.token_index] = {
            "client": self,
            "loop": asyncio.get_event_loop(),
            "name": self.user.name
        }

def run_bot(token, index):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    client = DiscordBot(index)
    try:
        loop.run_until_complete(client.start(token))
    except Exception as e:
        log_msg(f"❌ Lỗi login Bot {index + 1}: {e}")

# --- HỆ THỐNG GỬI TIN NHẮN TUẦN TỰ ---
def send_message_worker(channel_id, message):
    log_msg(f"🚀 Bắt đầu chiến dịch gửi tin. Mục tiêu: {channel_id}")
    
    sorted_indexes = sorted(active_bots.keys())
    count = 0

    for index in sorted_indexes:
        bot_data = active_bots[index]
        client = bot_data["client"]
        loop = bot_data["loop"]
        bot_name = bot_data["name"]

        async def task():
            try:
                channel = client.get_channel(int(channel_id))
                if channel:
                    await channel.send(message)
                    return True, "Thành công"
                else:
                    return False, "Không tìm thấy kênh (Bot chưa vào server?)"
            except Exception as e:
                return False, str(e)

        if loop.is_running():
            future = asyncio.run_coroutine_threadsafe(task(), loop)
            try:
                success, status = future.result(timeout=10)
                if success:
                    log_msg(f"📤 [Bot {index+1} | {bot_name}] Đã gửi thành công")
                else:
                    log_msg(f"⚠️ [Bot {index+1} | {bot_name}] Thất bại: {status}")
            except Exception as e:
                log_msg(f"❌ [Bot {index+1}] Lỗi timeout: {e}")
        
        count += 1
        if count < len(sorted_indexes):
            time.sleep(DELAY_SECONDS)

    log_msg(f"🏁 Hoàn tất chiến dịch. Đã chạy qua {count} bots.")

# --- GIAO DIỆN WEB (FLASK) ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Env Commander Control</title>
    <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&display=swap" rel="stylesheet">
    <style>
        :root { --bg: #0f0f13; --panel: #1a1a1f; --accent: #ff9d00; --text: #e0e0e0; }
        body { background-color: var(--bg); color: var(--text); font-family: 'JetBrains Mono', monospace; margin: 0; padding: 20px; }
        .container { max-width: 800px; margin: 0 auto; }
        h1 { text-align: center; color: var(--accent); text-transform: uppercase; letter-spacing: 2px; border-bottom: 2px solid var(--accent); padding-bottom: 10px; }
        .panel { background: var(--panel); padding: 25px; border-radius: 8px; box-shadow: 0 4px 15px rgba(0,0,0,0.5); margin-bottom: 20px; border: 1px solid #333; }
        .input-group { margin-bottom: 20px; }
        label { display: block; margin-bottom: 8px; font-weight: bold; color: #888; }
        input, textarea { width: 100%; background: #000; border: 1px solid #444; color: var(--accent); padding: 12px; font-family: inherit; border-radius: 4px; box-sizing: border-box; }
        .btn { width: 100%; padding: 15px; background: var(--accent); color: #000; border: none; font-weight: bold; font-size: 1.1rem; cursor: pointer; text-transform: uppercase; transition: 0.3s; border-radius: 4px; }
        .btn:hover { background: #ffb74d; }
        .log-box { background: #000; border: 1px solid #333; height: 300px; overflow-y: auto; padding: 10px; font-size: 0.9rem; border-radius: 4px; }
        .log-entry { border-bottom: 1px solid #222; padding: 5px 0; }
        .stats { display: flex; justify-content: space-between; margin-bottom: 10px; font-size: 0.9rem; color: #888; }
        ::-webkit-scrollbar { width: 8px; }
        ::-webkit-scrollbar-track { background: #000; }
        ::-webkit-scrollbar-thumb { background: #333; border-radius: 4px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>⚡ Env Commander</h1>
        
        <div class="panel">
            <div class="stats">
                <span>Delay: {{ delay }}s</span>
                <span id="bot-count">Loaded Tokens: {{ total_tokens }} | Online: 0</span>
            </div>
            <form id="controlForm">
                <div class="input-group">
                    <label>TARGET CHANNEL ID</label>
                    <input type="text" id="channel_id" placeholder="Nhập ID kênh..." required>
                </div>
                <div class="input-group">
                    <label>MESSAGE CONTENT</label>
                    <textarea id="message" rows="3" placeholder="Nhập nội dung..." required></textarea>
                </div>
                <button type="submit" class="btn">GỬI TIN NHẮN</button>
            </form>
        </div>

        <div class="panel">
            <label>LOG HOẠT ĐỘNG</label>
            <div class="log-box" id="log-container"></div>
        </div>
    </div>

    <script>
        document.getElementById('controlForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            const btn = document.querySelector('.btn');
            const originalText = btn.innerText;
            
            const data = {
                channel_id: document.getElementById('channel_id').value,
                message: document.getElementById('message').value
            };

            btn.innerText = "ĐANG XỬ LÝ...";
            btn.disabled = true;
            btn.style.opacity = "0.7";

            try {
                const res = await fetch('/api/send', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(data)
                });
                const result = await res.json();
                alert(result.message);
            } catch (err) {
                alert("Lỗi kết nối!");
            }

            btn.innerText = originalText;
            btn.disabled = false;
            btn.style.opacity = "1";
        });

        setInterval(async () => {
            try {
                const res = await fetch('/api/logs');
                const data = await res.json();
                document.getElementById('log-container').innerHTML = data.logs.map(l => `<div class="log-entry">${l}</div>`).join('');
                document.getElementById('bot-count').innerText = `Loaded Tokens: ${data.total_tokens} | Online: ${data.active_count}`;
            } catch (e) {}
        }, 2000);
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE, delay=DELAY_SECONDS, total_tokens=len(TOKENS))

@app.route('/api/send', methods=['POST'])
def api_send():
    data = request.json
    channel_id = data.get('channel_id')
    message = data.get('message')

    if not channel_id or not message:
        return jsonify({"status": "error", "message": "Thiếu thông tin!"}), 400
    
    if not active_bots:
         return jsonify({"status": "error", "message": "Chưa có bot nào online!"}), 400

    threading.Thread(target=send_message_worker, args=(channel_id, message), daemon=True).start()
    return jsonify({"status": "success", "message": f"Đã bắt đầu gửi trên {len(active_bots)} bot."})

@app.route('/api/logs')
def api_logs():
    return jsonify({
        "logs": bot_logs,
        "active_count": len(active_bots),
        "total_tokens": len(TOKENS)
    })

if __name__ == "__main__":
    print(f"--- LOADED {len(TOKENS)} TOKENS FROM .ENV ---")
    
    for i, token in enumerate(TOKENS):
        t = threading.Thread(target=run_bot, args=(token, i), daemon=True)
        t.start()
        time.sleep(0.5)

    port = int(os.getenv("PORT", 5000))
    print(f"🌐 Panel: http://localhost:{port}")
    app.run(host='0.0.0.0', port=port)
