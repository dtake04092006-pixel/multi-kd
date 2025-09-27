import discord
from discord.ext import commands
import asyncio
import os
import json
import threading
from flask import Flask, render_template_string, request, jsonify, redirect, url_for
import logging

# Disable discord.py logging to reduce RAM usage
logging.getLogger('discord').setLevel(logging.ERROR)
logging.getLogger('discord.http').setLevel(logging.ERROR)

# --- Configuration ---
KARUTA_ID = 646937666251915264
FIXED_EMOJIS = ["1️⃣", "2️⃣", "3️⃣", "1️⃣", "2️⃣", "3️⃣"]
GRAB_TIMES = [1.3, 2.3, 3.2, 1.8, 2.5, 3.5]

# Global variables
panels = {}
bot_instances = {}
current_account_index = 0
drop_task = None

def load_tokens():
    """Load tokens from environment variable"""
    tokens_str = os.getenv('TOKENS', '')
    return [token.strip() for token in tokens_str.split(',') if token.strip()]

def save_panels():
    """Save panels to file (in memory for render)"""
    try:
        with open('panels.json', 'w') as f:
            json.dump(panels, f)
    except:
        pass

def load_panels():
    """Load panels from file"""
    global panels
    try:
        if os.path.exists('panels.json'):
            with open('panels.json', 'r') as f:
                panels = json.load(f)
    except:
        panels = {}

class OptimizedBot(commands.Bot):
    """Optimized bot class to reduce memory usage"""
    def __init__(self, token, *args, **kwargs):
        super().__init__(command_prefix="!", self_bot=True, *args, **kwargs)
        self.token = token
        self.is_ready = False

    async def on_ready(self):
        self.is_ready = True
        print(f"Bot {self.user.name} ready")

    async def on_message(self, message):
        if message.author.id == KARUTA_ID and "is dropping 3 cards!" in message.content:
            channel_id = str(message.channel.id)
            
            # Find which account should react in this channel
            for panel_name, panel_data in panels.items():
                for i, (acc_token, ch_id) in enumerate(zip(panel_data['accounts'], panel_data['channels'])):
                    if ch_id == channel_id and acc_token == self.token:
                        emoji = FIXED_EMOJIS[i]
                        delay = GRAB_TIMES[i]
                        asyncio.create_task(self.react_to_drop(message, emoji, delay))
                        break

    async def react_to_drop(self, message, emoji, delay):
        await asyncio.sleep(delay)
        try:
            await message.add_reaction(emoji)
            print(f"Reacted {emoji} to drop")
        except Exception as e:
            print(f"Reaction error: {e}")

async def create_bot_instance(token):
    """Create and start a bot instance"""
    if token in bot_instances:
        return bot_instances[token]
    
    try:
        bot = OptimizedBot(token)
        bot_instances[token] = bot
        # Start bot in background
        asyncio.create_task(bot.start(token))
        
        # Wait for bot to be ready
        for _ in range(30):  # 30 second timeout
            if bot.is_ready:
                break
            await asyncio.sleep(1)
        
        return bot
    except Exception as e:
        print(f"Failed to create bot: {e}")
        return None

async def drop_cards():
    """Drop cards in rotation across all panels"""
    global current_account_index
    
    while True:
        try:
            if not panels:
                await asyncio.sleep(10)
                continue
                
            # Get all unique channels for current account index
            channels_to_drop = []
            for panel_data in panels.values():
                if current_account_index < len(panel_data['accounts']):
                    token = panel_data['accounts'][current_account_index]
                    channel_id = panel_data['channels'][current_account_index]
                    channels_to_drop.append((token, channel_id))
            
            # Send kd to all channels for current account
            for token, channel_id in channels_to_drop:
                if token in bot_instances:
                    bot = bot_instances[token]
                    if bot.is_ready:
                        try:
                            channel = bot.get_channel(int(channel_id))
                            if channel:
                                await channel.send("kd")
                                print(f"Sent kd to channel {channel_id}")
                        except Exception as e:
                            print(f"Drop error: {e}")
            
            # Move to next account
            current_account_index = (current_account_index + 1) % 6
            
            # Wait 305 seconds
            await asyncio.sleep(305)
            
        except Exception as e:
            print(f"Drop loop error: {e}")
            await asyncio.sleep(10)

async def start_bots_for_panel(panel_data):
    """Start bots for a specific panel"""
    for token in panel_data['accounts']:
        if token and token not in bot_instances:
            await create_bot_instance(token)

# Flask Web Interface
app = Flask(__name__)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Discord Bot Manager</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }

        .container {
            max-width: 1200px;
            margin: 0 auto;
        }

        .header {
            text-align: center;
            margin-bottom: 40px;
        }

        .header h1 {
            color: white;
            font-size: 2.5em;
            margin-bottom: 10px;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
        }

        .header p {
            color: rgba(255,255,255,0.8);
            font-size: 1.1em;
        }

        .panel-creator, .panel-item {
            background: rgba(255,255,255,0.95);
            border-radius: 15px;
            padding: 25px;
            margin-bottom: 25px;
            box-shadow: 0 8px 32px rgba(0,0,0,0.1);
            backdrop-filter: blur(10px);
        }

        .panel-creator h2, .panel-item h3 {
            color: #333;
            margin-bottom: 20px;
            font-size: 1.5em;
        }

        .form-group {
            margin-bottom: 20px;
        }

        .form-group label {
            display: block;
            margin-bottom: 8px;
            color: #555;
            font-weight: 600;
        }

        .form-group input, .form-group select {
            width: 100%;
            padding: 12px 15px;
            border: 2px solid #e0e0e0;
            border-radius: 8px;
            font-size: 16px;
            transition: border-color 0.3s ease;
        }

        .form-group input:focus, .form-group select:focus {
            outline: none;
            border-color: #667eea;
            box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
        }

        .accounts-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 15px;
            margin-bottom: 20px;
        }

        .account-pair {
            background: #f8f9fa;
            padding: 15px;
            border-radius: 8px;
            border-left: 4px solid #667eea;
        }

        .account-pair h4 {
            color: #333;
            margin-bottom: 10px;
            font-size: 1.1em;
        }

        .btn {
            padding: 12px 30px;
            border: none;
            border-radius: 8px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s ease;
            text-decoration: none;
            display: inline-block;
            text-align: center;
        }

        .btn-primary {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
        }

        .btn-primary:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(102, 126, 234, 0.3);
        }

        .btn-danger {
            background: linear-gradient(135deg, #ff6b6b 0%, #ee5a52 100%);
            color: white;
        }

        .btn-danger:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(238, 90, 82, 0.3);
        }

        .panel-actions {
            display: flex;
            gap: 10px;
            justify-content: flex-end;
            margin-top: 20px;
        }

        .status-badge {
            display: inline-block;
            padding: 5px 12px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: 600;
            text-transform: uppercase;
        }

        .status-active {
            background: #d4edda;
            color: #155724;
        }

        .status-inactive {
            background: #f8d7da;
            color: #721c24;
        }

        .panels-list {
            margin-top: 30px;
        }

        .no-panels {
            text-align: center;
            color: rgba(255,255,255,0.8);
            font-size: 1.2em;
            margin: 40px 0;
        }

        @media (max-width: 768px) {
            .accounts-grid {
                grid-template-columns: 1fr;
            }
            
            .panel-actions {
                flex-direction: column;
            }
            
            .btn {
                width: 100%;
                margin-bottom: 10px;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🚀 Discord Bot Manager</h1>
            <p>Multi-Server Multi-Account Management System</p>
        </div>

        <div class="panel-creator">
            <h2>Create New Panel</h2>
            <form method="POST" action="/create">
                <div class="form-group">
                    <label for="panel_name">Panel Name</label>
                    <input type="text" id="panel_name" name="panel_name" placeholder="Enter panel name" required>
                </div>

                <div class="accounts-grid">
                    {% for i in range(6) %}
                    <div class="account-pair">
                        <h4>Account {{ i + 1 }}</h4>
                        <div class="form-group">
                            <label>Token</label>
                            <select name="account_{{ i }}" required>
                                <option value="">Select Token</option>
                                {% for j, token in enumerate(tokens) %}
                                <option value="{{ token }}">Token {{ j + 1 }} ({{ token[:10] }}...)</option>
                                {% endfor %}
                            </select>
                        </div>
                        <div class="form-group">
                            <label>Channel ID</label>
                            <input type="text" name="channel_{{ i }}" placeholder="Discord Channel ID" required>
                        </div>
                    </div>
                    {% endfor %}
                </div>

                <button type="submit" class="btn btn-primary">Create Panel</button>
            </form>
        </div>

        <div class="panels-list">
            <h2 style="color: white; margin-bottom: 20px;">Active Panels</h2>
            
            {% if panels %}
                {% for panel_name, panel_data in panels.items() %}
                <div class="panel-item">
                    <div style="display: flex; justify-content: between; align-items: center; margin-bottom: 15px;">
                        <h3>{{ panel_name }}</h3>
                        <span class="status-badge status-active">Active</span>
                    </div>
                    
                    <div class="accounts-grid">
                        {% for i in range(6) %}
                        <div class="account-pair">
                            <h4>Account {{ i + 1 }}</h4>
                            <p><strong>Token:</strong> {{ panel_data.accounts[i][:10] }}...</p>
                            <p><strong>Channel:</strong> {{ panel_data.channels[i] }}</p>
                        </div>
                        {% endfor %}
                    </div>
                    
                    <div class="panel-actions">
                        <a href="/delete/{{ panel_name }}" class="btn btn-danger" 
                           onclick="return confirm('Are you sure you want to delete this panel?')">
                            Delete Panel
                        </a>
                    </div>
                </div>
                {% endfor %}
            {% else %}
                <div class="no-panels">
                    <p>No panels created yet. Create your first panel above! 👆</p>
                </div>
            {% endif %}
        </div>
    </div>
</body>
</html>
"""

@app.route('/')
def index():
    tokens = load_tokens()
    return render_template_string(HTML_TEMPLATE, panels=panels, tokens=tokens, enumerate=enumerate, range=range)

@app.route('/create', methods=['POST'])
def create_panel():
    panel_name = request.form['panel_name']
    
    if panel_name in panels:
        return redirect(url_for('index'))
    
    accounts = []
    channels = []
    
    for i in range(6):
        account = request.form[f'account_{i}']
        channel = request.form[f'channel_{i}']
        accounts.append(account)
        channels.append(channel)
    
    panels[panel_name] = {
        'accounts': accounts,
        'channels': channels
    }
    
    save_panels()
    
    # Start bots for this panel in background
    asyncio.create_task(start_bots_for_panel(panels[panel_name]))
    
    return redirect(url_for('index'))

@app.route('/delete/<panel_name>')
def delete_panel(panel_name):
    if panel_name in panels:
        del panels[panel_name]
        save_panels()
    return redirect(url_for('index'))

def run_flask():
    """Run Flask in a separate thread"""
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=False)

async def main():
    """Main function"""
    global drop_task
    
    # Load existing panels
    load_panels()
    
    # Start Flask in background thread
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    
    # Start existing bots
    for panel_data in panels.values():
        await start_bots_for_panel(panel_data)
    
    # Start drop loop
    drop_task = asyncio.create_task(drop_cards())
    
    # Keep the main loop running
    while True:
        await asyncio.sleep(10)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Shutting down...")
    except Exception as e:
        print(f"Error: {e}")
