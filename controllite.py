import discord
import asyncio
import threading
import time
import os
import logging
import random  # Quan trọng cho tính năng login từ từ
from flask import Flask, request, render_template_string, jsonify
from dotenv import load_dotenv

# --- CẤU HÌNH LOGGING ---
# Tắt bớt log rác của thư viện để dễ nhìn lỗi chính
logging.getLogger('discord').setLevel(logging.CRITICAL)
logging.getLogger('discord.http').setLevel(logging.CRITICAL)
logging.getLogger('discord.gateway').setLevel(logging.CRITICAL)
logging.getLogger('aiohttp').setLevel(logging.CRITICAL)

# --- LOAD CONFIG ---
load_dotenv()
token_string = os.getenv("DISCORD_TOKENS", "")
TOKENS = [t.strip() for t in token_string.split(",") if t.strip()]

try:
    DELAY_BETWEEN_MESSAGES = int(os.getenv("DELAY_SECONDS", 2))
except ValueError:
    DELAY_BETWEEN_MESSAGES = 2

# --- GLOBAL VARS ---
app = Flask(__name__)
active_bots = {} 
bot_logs = []

def log_msg(content):
    timestamp = time.strftime("%H:%M:%S")
    entry = f"[{timestamp}] {content}"
    print(entry)
    bot_logs.insert(0, entry)
    if len(bot_logs) > 50: bot_logs.pop()

# --- DISCORD CLIENT (OPTIMIZED) ---
class DiscordBot(discord.Client):
    def __init__(self, token_index, *args, **kwargs):
        # TẮT TẤT CẢ TÍNH NĂNG FETCH DATA TỰ ĐỘNG ĐỂ TRÁNH LỖI SOCKET
        super().__init__(
            fetch_offline_members=False, 
            chunk_guilds_at_startup=False,
            guild_subscriptions=False,
            *args, **kwargs
        )
        self.token_index = token_index

    async def on_ready(self):
        log_msg(f"✅ Bot {self.token_index + 1} Online: {self.user.name}")
        active_bots[self.token_index] = {
            "client": self,
            "loop": asyncio.get_running_loop(),
            "name": self.user.name
        }

# --- LUỒNG CHẠY BOT (AUTO RECONNECT) ---
def run_bot(token, index):
    while True:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            client = DiscordBot(index)
            loop.run_until_complete(client.start(token))
        except SystemExit:
            break
        except Exception as e:
            log_msg(f"⚠️ Bot {index + 1} mất kết nối. Reconnect sau 10s...")
            if index in active_bots: del active_bots[index]
            time.sleep(10)
        finally:
            try: loop.close()
            except: pass

# --- XỬ LÝ GỬI TIN NHẮN (TUẦN TỰ) ---
def send_message_worker(channel_id, message):
    log_msg(f"🚀 Bắt đầu chiến dịch gửi tin đến ID: {channel_id}")
    
    sorted_indexes = sorted(list(active_bots.keys()))
    if not sorted_indexes:
        log_msg("❌ Không có bot nào online!")
        return

    count = 0
    for index in sorted_indexes:
        if index not in active_bots: continue # Bot bị out giữa chừng

        bot_data = active_bots[index]
        client = bot_data["client"]
        loop = bot_data["loop"]
        bot_name = bot_data["name"]

        async def task():
            try:
                channel = client.get_channel(int(channel_id))
                if not channel:
                    try:
                        channel = await client.fetch_channel(int(channel_id))
                    except:
                        return False, "Không tìm thấy kênh/Không có quyền"
                
                await channel.send(message)
                return True, "Success"
            except Exception as e:
                return False, str(e)

        if loop.is_running() and not client.is_closed():
            try:
                future = asyncio.run_coroutine_threadsafe(task(), loop)
                success, status = future.result(timeout=10)
                if success:
                    log_msg(f"📤 [Bot {index+1} | {bot_name}] Đã gửi.")
                else:
                    log_msg(f"⚠️ [Bot {index+1} | {bot_name}] Lỗi: {status}")
            except Exception as e:
                log_msg(f"❌ [Bot {index+1}] Timeout: {e}")
        
        count += 1
        # Delay giữa các acc để tránh spam
        if count < len(sorted_indexes):
            time.sleep(DELAY_BETWEEN_MESSAGES)

    log_msg(f"🏁 Hoàn tất chiến dịch ({count} bots).")

# --- WEB INTERFACE ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Shadow Controller</title>
    <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&display=swap" rel="stylesheet">
    <style>
        :root { --bg: #121212; --panel: #1e1e1e; --accent: #bb86fc; --text: #e0e0e0; --success: #03dac6; }
        body { background: var(--bg); color: var(--text); font-family: 'JetBrains Mono', monospace; margin: 0; padding: 20px; }
        .container { max-width: 800px; margin: 0 auto; }
        h1 { text-align: center; color: var(--accent); border-bottom: 2px solid var(--accent); padding-bottom: 15px; }
        .panel { background: var(--panel); padding: 20px; border-radius: 8px; margin-bottom: 20px; border: 1px solid #333; }
        input, textarea { width: 100%; background: #000; border: 1px solid #444; color: var(--success); padding: 12px; font-family: inherit; border-radius: 4px; box-sizing: border-box; margin-bottom: 15px; }
        .btn { width: 100%; padding: 15px; background: var(--accent); color: #000; border: none; font-weight: bold; cursor: pointer; border-radius: 4px; font-size: 1.1rem; }
        .btn:hover { filter: brightness(1.2); }
        .log-box { background: #000; height: 350px; overflow-y: auto; padding: 10px; border: 1px solid #333; border-radius: 4px; font-size: 0.9rem; }
        .log-entry { padding: 4px 0; border-bottom: 1px solid #222; }
        .stats { display: flex; justify-content: space-between; color: #888; margin-bottom: 10px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🎮 Shadow Controller</h1>
        <div class="panel">
            <div class="stats">
                <span>Message Delay: {{ delay }}s</span>
                <span id="bot-count">Tokens: {{ total }} | Online: 0</span>
            </div>
            <form id="form">
                <input type="text" id="channel_id" placeholder="Channel ID (e.g. 12938...)" required>
                <textarea id="message" rows="3" placeholder="Nhập nội dung tin nhắn..." required></textarea>
                <button type="submit" class="btn">GỬI TIN (SEQUENTIAL)</button>
            </form>
        </div>
        <div class="panel">
            <div class="log-box" id="logs"></div>
        </div>
    </div>
    <script>
        document.getElementById('form').addEventListener('submit', async (e) => {
            e.preventDefault();
            const btn = document.querySelector('.btn');
            btn.disabled = true; btn.innerText = "ĐANG GỬI...";
            try {
                const res = await fetch('/api/send', {
                    method: 'POST', headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        channel_id: document.getElementById('channel_id').value,
                        message: document.getElementById('message').value
                    })
                });
                const d = await res.json(); alert(d.message);
            } catch { alert("Lỗi kết nối!"); }
            btn.disabled = false; btn.innerText = "GỬI TIN (SEQUENTIAL)";
        });
        setInterval(async () => {
            try {
                const r = await fetch('/api/logs'); const d = await r.json();
                document.getElementById('logs').innerHTML = d.logs.map(l => `<div class="log-entry">${l}</div>`).join('');
                document.getElementById('bot-count').innerText = `Tokens: ${d.total} | Online: ${d.active}`;
            } catch {}
        }, 2000);
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE, delay=DELAY_BETWEEN_MESSAGES, total=len(TOKENS))

@app.route('/api/send', methods=['POST'])
def api_send():
    data = request.json
    threading.Thread(target=send_message_worker, args=(data.get('channel_id'), data.get('message')), daemon=True).start()
    return jsonify({"message": "Đã bắt đầu lệnh gửi!"})

@app.route('/api/logs')
def api_logs():
    return jsonify({"logs": bot_logs, "active": len(active_bots), "total": len(TOKENS)})

# --- MAIN EXECUTION ---
if __name__ == "__main__":
    print(f"--- SYSTEM STARTED: {len(TOKENS)} TOKENS DETECTED ---")
    print("--- SOCKET FIX: ON | SLOW LOGIN: ON ---")

    for i, token in enumerate(TOKENS):
        # Khởi chạy luồng Bot
        t = threading.Thread(target=run_bot, args=(token, i), daemon=True)
        t.start()
        
        # TÍNH NĂNG SLOW LOGIN (NHƯ BẠN YÊU CẦU)
        if i < len(TOKENS) - 1: # Nếu chưa phải acc cuối thì mới delay
            wait_time = random.uniform(3, 8) # Random từ 3 đến 8 giây
            print(f"⏳ Acc {i+1} đang boot... Chờ {wait_time:.1f}s cho acc tiếp theo.")
            time.sleep(wait_time)
        else:
            print(f"🚀 Acc cuối ({i+1}) đang boot.")

    port = int(os.getenv("PORT", 5000))
    print(f"🌐 WEB PANEL: http://0.0.0.0:{port}")
    from waitress import serve # Dùng waitress cho ổn định nếu có
    try:
        serve(app, host="0.0.0.0", port=port)
    except ImportError:
        app.run(host='0.0.0.0', port=port)
