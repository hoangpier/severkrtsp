# PHIÊN BẢN LITE - ĐÃ TÍCH HỢP LƯU/TẢI JSON - CẬP NHẬT ĐA SERVER - HỖ TRỢ ĐA TÀI KHOẢN CHÍNH
import discum
import threading
import time
import os
import re
import requests
import json
from flask import Flask, request, render_template_string, jsonify
from dotenv import load_dotenv
import uuid

load_dotenv()

# --- CẤU HÌNH ---
main_tokens = os.getenv("MAIN_TOKENS").split(",") if os.getenv("MAIN_TOKENS") else []
tokens = os.getenv("TOKENS").split(",") if os.getenv("TOKENS") else []
karuta_id = "646937666251915264"
karibbit_id = "1311684840462225440"

# --- BIẾN TRẠNG THÁI ---
main_bots = [] # Danh sách chứa các instance của bot chính
bots, acc_names = [], [
    "Blacklist", "Khanh bang", "Dersale", "Venus", "WhyK", "Tan",
    "Ylang", "Nina", "Nathan", "Ofer", "White", "the Wicker", "Leader", "Tess", "Wyatt", "Daisy", "CantStop", "Token",
]

servers = []
auto_reboot_enabled = False
auto_reboot_delay = 3600
last_reboot_cycle_time = 0

auto_reboot_stop_event = threading.Event()
spam_thread, auto_reboot_thread = None, None
bots_lock = threading.Lock()
server_start_time = time.time()
bot_active_states = {}

# --- HÀM LƯU VÀ TẢI CÀI ĐẶT ---
def save_settings():
    """Lưu cài đặt lên JSONBin.io"""
    api_key = os.getenv("JSONBIN_API_KEY")
    bin_id = os.getenv("JSONBIN_BIN_ID")
    if not api_key or not bin_id:
        return

    settings = {
        'servers': servers,
        'auto_reboot_enabled': auto_reboot_enabled,
        'auto_reboot_delay': auto_reboot_delay,
        'bot_active_states': bot_active_states,
        'last_reboot_cycle_time': last_reboot_cycle_time
    }

    headers = {
        'Content-Type': 'application/json',
        'X-Master-Key': api_key
    }
    url = f"https://api.jsonbin.io/v3/b/{bin_id}"

    try:
        req = requests.put(url, json=settings, headers=headers, timeout=10)
        if req.status_code == 200:
            print("[Settings] Đã lưu cài đặt lên JSONBin.io thành công.", flush=True)
        else:
            print(f"[Settings] Lỗi khi lưu cài đặt lên JSONBin.io: {req.status_code} - {req.text}", flush=True)
    except Exception as e:
        print(f"[Settings] Exception khi lưu cài đặt: {e}", flush=True)

def load_settings():
    """Tải cài đặt từ JSONBin.io"""
    global servers, auto_reboot_enabled, auto_reboot_delay, bot_active_states, last_reboot_cycle_time
    api_key = os.getenv("JSONBIN_API_KEY")
    bin_id = os.getenv("JSONBIN_BIN_ID")
    if not api_key or not bin_id:
        print("[Settings] Thiếu API Key hoặc Bin ID của JSONBin. Sử dụng cài đặt mặc định.", flush=True)
        return

    headers = {'X-Master-Key': api_key}
    url = f"https://api.jsonbin.io/v3/b/{bin_id}/latest"

    try:
        req = requests.get(url, headers=headers, timeout=10)
        if req.status_code == 200:
            settings = req.json().get("record", {})
            if settings:
                servers = settings.get('servers', [])
                auto_reboot_enabled = settings.get('auto_reboot_enabled', False)
                auto_reboot_delay = settings.get('auto_reboot_delay', 3600)
                bot_active_states = settings.get('bot_active_states', {})
                last_reboot_cycle_time = settings.get('last_reboot_cycle_time', 0)
                print("[Settings] Đã tải cài đặt từ JSONBin.io.", flush=True)
            else:
                print("[Settings] JSONBin rỗng, bắt đầu với cài đặt mặc định và lưu lại.", flush=True)
                save_settings()
        else:
            print(f"[Settings] Lỗi khi tải cài đặt từ JSONBin.io: {req.status_code} - {req.text}", flush=True)
    except Exception as e:
        print(f"[Settings] Exception khi tải cài đặt: {e}", flush=True)

# --- CÁC HÀM LOGIC BOT ---
def handle_grab(bot, msg, bot_num):
    """Xử lý logic grab cho một bot cụ thể."""
    channel_id = msg.get("channel_id")
    target_server = next((s for s in servers if s.get('main_channel_id') == channel_id), None)
    if not target_server:
        return

    auto_grab_enabled = target_server.get(f'auto_grab_enabled_{bot_num}', False)
    heart_threshold = target_server.get(f'heart_threshold_{bot_num}', 50)
    ktb_channel_id = target_server.get('ktb_channel_id')

    if not auto_grab_enabled or not ktb_channel_id:
        return

    if msg.get("author", {}).get("id") == karuta_id and "is dropping" not in msg.get("content", "") and not msg.get("mentions", []):
        last_drop_msg_id = msg["id"]

        def read_karibbit():
            time.sleep(0.5)
            try:
                messages = bot.getMessages(channel_id, num=5).json()
                for msg_item in messages:
                    if msg_item.get("author", {}).get("id") == karibbit_id and "embeds" in msg_item and len(msg_item["embeds"]) > 0:
                        desc = msg_item["embeds"][0].get("description", "")
                        lines = desc.split('\n')
                        heart_numbers = [int(match.group(1)) if (match := re.search(r'♡(\d+)', line)) else 0 for line in lines[:3]]

                        if not any(heart_numbers): break

                        max_num = max(heart_numbers)
                        if max_num >= heart_threshold:
                            max_index = heart_numbers.index(max_num)
                            delays_list = [
                                [0.4, 1.4, 2.1], [0.7, 1.8, 2.4], [0.8, 1.7, 2.5],
                                [0.5, 1.5, 2.2], [0.6, 1.6, 2.3]
                            ]
                            bot_delays = delays_list[min(bot_num - 1, len(delays_list) - 1)]
                            emojis = ["1️⃣", "2️⃣", "3️⃣"]
                            emoji = emojis[max_index]
                            delay = bot_delays[max_index]

                            print(f"[{target_server['name']} | Bot #{bot_num}] Chọn dòng {max_index+1} với {max_num} tim -> Emoji {emoji} sau {delay}s", flush=True)

                            def grab_action():
                                bot.addReaction(channel_id, last_drop_msg_id, emoji)
                                time.sleep(1)
                                bot.sendMessage(ktb_channel_id, "kt b")

                            threading.Timer(delay, grab_action).start()
                        break
            except Exception as e:
                print(f"Lỗi khi đọc tin nhắn Karibbit (Bot {bot_num} @ {target_server['name']}): {e}", flush=True)

        threading.Thread(target=read_karibbit).start()

def create_bot(token, bot_index=None):
    """Tạo một instance bot."""
    bot = discum.Client(token=token, log=False)

    @bot.gateway.command
    def on_ready(resp):
        if resp.event.ready:
            user_data = resp.raw.get("user", {})
            if isinstance(user_data, dict):
                user_id = user_data.get("id")
                if user_id:
                    bot_type = f"(MAIN #{bot_index})" if bot_index is not None else "(SUB)"
                    print(f"Đã đăng nhập: {user_id} {bot_type}", flush=True)

    if bot_index is not None:
        @bot.gateway.command
        def on_message(resp):
            if resp.event.message: handle_grab(bot, resp.parsed.auto(), bot_index)

    threading.Thread(target=bot.gateway.run, daemon=True).start()
    return bot

# --- CÁC VÒNG LẶP NỀN ---
def auto_reboot_loop():
    global last_reboot_cycle_time
    while not auto_reboot_stop_event.is_set():
        try:
            interrupted = auto_reboot_stop_event.wait(timeout=60)
            if interrupted: break

            if auto_reboot_enabled and (time.time() - last_reboot_cycle_time) >= auto_reboot_delay:
                print("[Reboot] Hết thời gian chờ, tiến hành reboot các tài khoản chính.", flush=True)
                with bots_lock:
                    for i in range(len(main_bots)):
                        if main_bots[i]:
                            main_bots[i].gateway.close()
                            time.sleep(2)
                            main_bots[i] = create_bot(main_tokens[i].strip(), bot_index=i + 1)
                            time.sleep(5)
                last_reboot_cycle_time = time.time()
                save_settings()
        except Exception as e:
            print(f"[ERROR in auto_reboot_loop] {e}", flush=True)
            time.sleep(60)
    print("[Reboot] Luồng tự động reboot đã dừng.", flush=True)

def spam_loop():
    """Vòng lặp spam với logic đã được tối ưu."""
    INTER_BOT_DELAY = 1  # Delay giữa mỗi lần một bot gửi tin (giây). Thay đổi giá trị này nếu cần.

    while True:
        try:
            bots_to_spam = [bot for i, bot in enumerate(bots) if bot and bot_active_states.get(f'sub_{i}', False)]

            for bot in bots_to_spam:
                for server in servers:
                    if not server.get('spam_enabled'):
                        continue

                    spam_delay = server.get('spam_delay', 10)
                    last_spam_time = server.get('last_spam_time', 0)

                    if (time.time() - last_spam_time) >= spam_delay:
                        try:
                            bot.sendMessage(server['spam_channel_id'], server['spam_message'])
                            print(f"[Spam] Bot đã gửi tin nhắn tới server: {server['name']}", flush=True)
                            server['last_spam_time'] = time.time()
                        except Exception as e:
                            print(f"Lỗi gửi spam tới server {server['name']}: {e}", flush=True)
                
                time.sleep(INTER_BOT_DELAY)
            time.sleep(1)
        except Exception as e:
            print(f"[ERROR in spam_loop] {e}", flush=True)
            time.sleep(1)

def periodic_save_loop():
    """Lưu cài đặt định kỳ 10 tiếng một lần."""
    while True:
        time.sleep(36000)
        print("[Settings] Bắt đầu lưu định kỳ (10 giờ)...", flush=True)
        save_settings()

app = Flask(__name__)

# --- GIAO DIỆN WEB ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Karuta Deep - Shadow Network Control</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700;900&family=Courier+Prime:wght@400;700&family=Nosifer&display=swap" rel="stylesheet">
    <style>
        :root {--primary-bg: #0a0a0a; --secondary-bg: #1a1a1a; --panel-bg: #111111; --border-color: #333333; --blood-red: #8b0000; --dark-red: #550000; --bone-white: #f8f8ff; --necro-green: #228b22; --text-primary: #f0f0f0; --text-secondary: #cccccc;}
        body {font-family: 'Courier Prime', monospace; background: var(--primary-bg); color: var(--text-primary); margin: 0; padding: 0;}
        .container {max-width: 1600px; margin: 0 auto; padding: 20px;}
        .header {text-align: center; margin-bottom: 30px; padding: 20px; border-bottom: 2px solid var(--blood-red);}
        .title {font-family: 'Nosifer', cursive; font-size: 3rem; color: var(--blood-red);}
        .main-grid {display: grid; grid-template-columns: repeat(auto-fit, minmax(450px, 1fr)); gap: 20px;}
        .panel {background: var(--panel-bg); border: 1px solid var(--border-color); border-radius: 10px; padding: 25px; position: relative;}
        h2 {font-family: 'Orbitron', cursive; font-size: 1.4rem; margin-bottom: 20px; text-transform: uppercase; border-bottom: 2px solid; padding-bottom: 10px; color: var(--bone-white);}
        .btn {background: var(--secondary-bg); border: 1px solid var(--border-color); color: var(--text-primary); padding: 10px 15px; border-radius: 4px; cursor: pointer; font-family: 'Orbitron', monospace; font-weight: 700; text-transform: uppercase; width: 100%;}
        .input-group {display: flex; align-items: stretch; gap: 10px; margin-bottom: 15px;}
        .input-group label {background: #000; border: 1px solid var(--border-color); border-right: 0; padding: 10px 15px; border-radius: 4px 0 0 4px; display: flex; align-items: center; min-width: 120px;}
        .input-group input, .input-group textarea {flex-grow: 1; background: #000; border: 1px solid var(--border-color); color: var(--text-primary); padding: 10px 15px; border-radius: 0 4px 4px 0; font-family: 'Courier Prime', monospace;}
        .grab-section {display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; padding: 15px; background: rgba(0,0,0,0.2); border-radius: 8px;}
        .msg-status {text-align: center; color: var(--necro-green); padding: 12px; border: 1px dashed var(--border-color); border-radius: 4px; margin-bottom: 20px; display: none;}
        .status-panel {grid-column: 1 / -1;}
        .status-grid {display: grid; grid-template-columns: 1fr 1fr; gap: 15px;}
        .status-row {display: flex; justify-content: space-between; align-items: center; padding: 12px; background: rgba(0,0,0,0.4); border-radius: 8px;}
        .timer-display {font-size: 1.2em; font-weight: 700;}
        .bot-status-container {display: grid; grid-template-columns: 1fr 2fr; gap: 20px; margin-top: 15px; border-top: 1px solid var(--border-color); padding-top: 15px;}
        .bot-status-grid {display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 8px;}
        .bot-status-item {display: flex; justify-content: space-between; align-items: center; padding: 5px 8px; background: rgba(0,0,0,0.3); border-radius: 4px;}
        .bot-main span:first-child {color: #FF4500; font-weight: 700;}
        .add-server-btn {display: flex; align-items: center; justify-content: center; min-height: 200px; border: 2px dashed var(--border-color); cursor: pointer; transition: all 0.3s ease;}
        .add-server-btn:hover {background: var(--secondary-bg); border-color: var(--blood-red);}
        .btn-delete-server {position: absolute; top: 15px; right: 15px; background: var(--dark-red); border: 1px solid var(--blood-red); color: var(--bone-white); width: auto; padding: 5px 10px; border-radius: 50%;}
        .server-sub-panel {border-top: 1px solid var(--border-color); margin-top: 20px; padding-top: 20px;}
    </style>
</head>
<body>
    <div class="container">
        <div class="header"><h1 class="title">Shadow Network Control</h1></div>
        <div id="msg-status-container" class="msg-status"></div>
        <div class="main-grid">
            <div class="panel status-panel">
                <h2><i class="fas fa-heartbeat"></i> System Status</h2>
                <div class="bot-status-container">
                    <div class="status-grid">
                         <div class="status-row">
                            <span><i class="fas fa-redo"></i> Auto Reboot</span>
                            <div style="display:flex; gap: 10px; align-items: center;">
                                <input type="number" id="auto-reboot-delay" value="{{ auto_reboot_delay }}" style="width: 80px; text-align: right; padding: 5px;">
                                <span id="reboot-timer" class="timer-display">--:--:--</span>
                                <button type="button" id="auto-reboot-toggle-btn" class="btn" style="width:auto; padding: 5px 10px;">{{ 'DISABLE' if auto_reboot_enabled else 'ENABLE' }}</button>
                            </div>
                        </div>
                        <div class="status-row">
                            <span><i class="fas fa-server"></i> Uptime</span>
                            <span id="uptime-timer" class="timer-display">--:--:--</span>
                        </div>
                    </div>
                    <div id="bot-status-list" class="bot-status-grid"></div>
                </div>
            </div>
            {% for server in servers %}
            <div class="panel server-panel" data-server-id="{{ server.id }}">
                <button class="btn-delete-server" title="Delete Server"><i class="fas fa-times"></i></button>
                <h2><i class="fas fa-server"></i> {{ server.name }}</h2>
                <div class="server-sub-panel">
                    <h3><i class="fas fa-cogs"></i> Channel Config</h3>
                    <div class="input-group"><label>Main Channel ID</label><input type="text" class="channel-input" data-field="main_channel_id" value="{{ server.main_channel_id or '' }}"></div>
                    <div class="input-group"><label>KTB Channel ID</label><input type="text" class="channel-input" data-field="ktb_channel_id" value="{{ server.ktb_channel_id or '' }}"></div>
                    <div class="input-group"><label>Spam Channel ID</label><input type="text" class="channel-input" data-field="spam_channel_id" value="{{ server.spam_channel_id or '' }}"></div>
                </div>
                <div class="server-sub-panel">
                    <h3><i class="fas fa-crosshairs"></i> Soul Harvest</h3>
                    {% for i in range(1, num_main_bots + 1) %}
                    <div class="grab-section">
                        <h3>MAIN #{{ i }}</h3>
                        <div class="input-group" style="margin-left:20px; margin-bottom:0;">
                            <input type="number" class="harvest-threshold" data-node="{{ i }}" value="{{ server['heart_threshold_' ~ i] or 50 }}" min="0">
                            <button type="button" class="btn harvest-toggle" data-node="{{ i }}">{{ 'DISABLE' if server['auto_grab_enabled_' ~ i] else 'ENABLE' }}</button>
                        </div>
                    </div>
                    {% endfor %}
                </div>
                <div class="server-sub-panel">
                    <h3><i class="fas fa-paper-plane"></i> Auto Broadcast</h3>
                    <div class="input-group"><label>Message</label><textarea class="spam-message" rows="2">{{ server.spam_message or '' }}</textarea></div>
                    <div class="input-group"><label>Delay (s)</label><input type="number" class="spam-delay" value="{{ server.spam_delay or 10 }}"><span class="timer-display spam-timer">--:--:--</span></div>
                    <button type="button" class="btn broadcast-toggle">{{ 'DISABLE' if server.spam_enabled else 'ENABLE' }}</button>
                </div>
            </div>
            {% endfor %}
            <div class="panel add-server-btn" id="add-server-btn"><i class="fas fa-plus"></i></div>
        </div>
    </div>
    <script>
        document.addEventListener('DOMContentLoaded', function () {
            const msgStatusContainer = document.getElementById('msg-status-container');
            const mainGrid = document.querySelector('.main-grid');

            function showStatusMessage(message, isError = false) {
                if (!message) return;
                msgStatusContainer.textContent = message;
                msgStatusContainer.style.color = isError ? 'var(--blood-red)' : 'var(--necro-green)';
                msgStatusContainer.style.display = 'block';
                setTimeout(() => { msgStatusContainer.style.display = 'none'; }, 4000);
            }

            async function postData(url = '', data = {}) {
                try {
                    const response = await fetch(url, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(data)});
                    const result = await response.json();
                    showStatusMessage(result.message, result.status !== 'success');
                    if (result.status === 'success' && url !== '/api/save_settings') {
                        fetch('/api/save_settings', { method: 'POST' });
                        if (result.reload) setTimeout(() => window.location.reload(), 500);
                    }
                    setTimeout(fetchStatus, 500);
                    return result;
                } catch (error) {
                    showStatusMessage('Server communication error.', true);
                }
            }

            function formatTime(seconds) {
                if (isNaN(seconds) || seconds < 0) return "--:--:--";
                const h = Math.floor(seconds / 3600).toString().padStart(2, '0');
                const m = Math.floor((seconds % 3600) / 60).toString().padStart(2, '0');
                const s = (Math.floor(seconds) % 60).toString().padStart(2, '0');
                return `${h}:${m}:${s}`;
            }

            async function fetchStatus() {
                try {
                    const response = await fetch('/status');
                    const data = await response.json();
                    
                    document.getElementById('reboot-timer').textContent = formatTime(data.reboot_countdown);
                    document.getElementById('auto-reboot-toggle-btn').textContent = data.reboot_enabled ? 'DISABLE' : 'ENABLE';
                    document.getElementById('uptime-timer').textContent = formatTime((Date.now() / 1000) - data.server_start_time);
                    
                    const botListContainer = document.getElementById('bot-status-list');
                    botListContainer.innerHTML = ''; 
                    [...data.bot_statuses.main_bots, ...data.bot_statuses.sub_accounts].forEach(bot => {
                        const item = document.createElement('div');
                        item.className = 'bot-status-item' + (bot.type === 'main' ? ' bot-main' : '');
                        item.innerHTML = `<span>${bot.name}</span><button type="button" data-target="${bot.reboot_id}" style="color: ${bot.is_active ? 'var(--necro-green)' : 'var(--dark-red)'}; background:transparent; border:none; cursor:pointer;">${bot.is_active ? 'ONLINE' : 'OFFLINE'}</button>`;
                        botListContainer.appendChild(item);
                    });

                    data.servers.forEach(serverData => {
                        const serverPanel = document.querySelector(`.server-panel[data-server-id="${serverData.id}"]`);
                        if (!serverPanel) return;
                        serverPanel.querySelectorAll('.harvest-toggle').forEach(btn => {
                            btn.textContent = serverData[`auto_grab_enabled_${btn.dataset.node}`] ? 'DISABLE' : 'ENABLE';
                        });
                        serverPanel.querySelector('.broadcast-toggle').textContent = serverData.spam_enabled ? 'DISABLE' : 'ENABLE';
                        serverPanel.querySelector('.spam-timer').textContent = formatTime(serverData.spam_countdown);
                    });
                } catch (error) { console.error('Error fetching status:', error); }
            }
            setInterval(fetchStatus, 1000);

            mainGrid.addEventListener('click', e => {
                const serverPanel = e.target.closest('.server-panel');
                if (!serverPanel) return;
                const serverId = serverPanel.dataset.serverId;
                
                if (e.target.classList.contains('harvest-toggle')) {
                    const node = e.target.dataset.node;
                    postData('/api/harvest_toggle', { server_id: serverId, node: node, threshold: serverPanel.querySelector(`.harvest-threshold[data-node="${node}"]`).value });
                } else if (e.target.classList.contains('broadcast-toggle')) {
                    postData('/api/broadcast_toggle', { server_id: serverId, message: serverPanel.querySelector('.spam-message').value, delay: serverPanel.querySelector('.spam-delay').value });
                } else if (e.target.closest('.btn-delete-server')) {
                    if (confirm('Are you sure?')) postData('/api/delete_server', { server_id: serverId });
                }
            });

            mainGrid.addEventListener('change', e => {
                const serverPanel = e.target.closest('.server-panel');
                if (!serverPanel || !e.target.classList.contains('channel-input')) return;
                const payload = { server_id: serverPanel.dataset.serverId };
                payload[e.target.dataset.field] = e.target.value;
                postData('/api/update_server_channels', payload);
            });

            document.getElementById('add-server-btn').addEventListener('click', () => {
                const name = prompt("Enter a name for the new server:", "New Server");
                if (name) postData('/api/add_server', { name: name });
            });

            document.getElementById('auto-reboot-toggle-btn').addEventListener('click', () => {
                 postData('/api/reboot_toggle_auto', { delay: document.getElementById('auto-reboot-delay').value });
            });
            
            document.getElementById('bot-status-list').addEventListener('click', e => {
                if(e.target.matches('button[data-target]')) postData('/api/toggle_bot_state', { target: e.target.dataset.target });
            });
        });
    </script>
</body>
</html>
"""

# --- FLASK ROUTES ---
@app.route("/")
def index():
    sorted_servers = sorted(servers, key=lambda s: s.get('name', ''))
    num_bots = len(main_bots)
    for server in sorted_servers:
        for i in range(1, num_bots + 1):
            server.setdefault(f'auto_grab_enabled_{i}', False)
            server.setdefault(f'heart_threshold_{i}', 50)
    return render_template_string(HTML_TEMPLATE, servers=sorted_servers, auto_reboot_enabled=auto_reboot_enabled, auto_reboot_delay=auto_reboot_delay, num_main_bots=num_bots)

@app.route("/api/add_server", methods=['POST'])
def api_add_server():
    data = request.get_json()
    name = data.get('name')
    if not name: return jsonify({'status': 'error', 'message': 'Server name is required.'}), 400
    new_server = {"id": f"server_{uuid.uuid4().hex}", "name": name, "main_channel_id": "", "ktb_channel_id": "", "spam_channel_id": "", "spam_enabled": False, "spam_message": "", "spam_delay": 10, "last_spam_time": 0}
    for i in range(1, len(main_bots) + 1):
        new_server[f'auto_grab_enabled_{i}'] = False
        new_server[f'heart_threshold_{i}'] = 50
    servers.append(new_server)
    return jsonify({'status': 'success', 'message': f'Server "{name}" added.', 'reload': True})

@app.route("/api/delete_server", methods=['POST'])
def api_delete_server():
    global servers
    server_id = request.get_json().get('server_id')
    server_to_delete = next((s for s in servers if s.get('id') == server_id), None)
    if server_to_delete:
        servers = [s for s in servers if s.get('id') != server_id]
        return jsonify({'status': 'success', 'message': f'Server "{server_to_delete.get("name")}" deleted.', 'reload': True})
    return jsonify({'status': 'error', 'message': 'Server not found.'}), 404

@app.route("/api/update_server_channels", methods=['POST'])
def api_update_server_channels():
    data = request.get_json()
    server = next((s for s in servers if s.get('id') == data.get('server_id')), None)
    if not server: return jsonify({'status': 'error', 'message': 'Server not found.'}), 404
    updated_fields = []
    for field in ['main_channel_id', 'ktb_channel_id', 'spam_channel_id']:
        if field in data:
            server[field] = data[field]
            updated_fields.append(field.replace('_', ' ').title())
    return jsonify({'status': 'success', 'message': f'{", ".join(updated_fields)} updated for {server["name"]}.'})

@app.route("/api/harvest_toggle", methods=['POST'])
def api_harvest_toggle():
    data = request.get_json()
    server = next((s for s in servers if s.get('id') == data.get('server_id')), None)
    node = data.get('node')
    if not server or not node: return jsonify({'status': 'error', 'message': 'Invalid request.'}), 400
    grab_key, threshold_key = f'auto_grab_enabled_{node}', f'heart_threshold_{node}'
    server[grab_key] = not server.get(grab_key, False)
    server[threshold_key] = int(data.get('threshold', 50))
    state = "ENABLED" if server[grab_key] else "DISABLED"
    return jsonify({'status': 'success', 'message': f"Harvest Node #{node} was {state} for server {server['name']}."})

@app.route("/api/broadcast_toggle", methods=['POST'])
def api_broadcast_toggle():
    data = request.get_json()
    server = next((s for s in servers if s.get('id') == data.get('server_id')), None)
    if not server: return jsonify({'status': 'error', 'message': 'Server not found.'}), 404
    server.update({'spam_message': data.get("message", "").strip(), 'spam_delay': int(data.get("delay", 10))})
    if not server.get('spam_enabled') and server['spam_message'] and server['spam_channel_id']:
        server.update({'spam_enabled': True, 'last_spam_time': time.time()})
        msg = f"Spam ENABLED for {server['name']}."
    else:
        server['spam_enabled'] = False
        msg = f"Spam DISABLED for {server['name']}."
    return jsonify({'status': 'success', 'message': msg})

@app.route("/api/reboot_toggle_auto", methods=['POST'])
def api_reboot_toggle_auto():
    global auto_reboot_enabled, auto_reboot_delay, auto_reboot_thread, auto_reboot_stop_event, last_reboot_cycle_time
    auto_reboot_enabled = not auto_reboot_enabled
    auto_reboot_delay = int(request.get_json().get("delay", 3600))
    if auto_reboot_enabled:
        last_reboot_cycle_time = time.time()
        if auto_reboot_thread is None or not auto_reboot_thread.is_alive():
            auto_reboot_stop_event.clear()
            auto_reboot_thread = threading.Thread(target=auto_reboot_loop, daemon=True)
            auto_reboot_thread.start()
        msg = "Global Auto Reboot ENABLED."
    else:
        auto_reboot_stop_event.set()
        auto_reboot_thread = None
        msg = "Global Auto Reboot DISABLED."
    return jsonify({'status': 'success', 'message': msg})

@app.route("/api/toggle_bot_state", methods=['POST'])
def api_toggle_bot_state():
    target = request.get_json().get('target')
    if target in bot_active_states:
        bot_active_states[target] = not bot_active_states[target]
        state_text = "AWAKENED" if bot_active_states[target] else "DORMANT"
        return jsonify({'status': 'success', 'message': f"Target {target.upper()} has been set to {state_text}."})
    return jsonify({'status': 'error', 'message': 'Target not found.'}), 404

@app.route("/api/save_settings", methods=['POST'])
def api_save_settings():
    save_settings()
    return jsonify({'status': 'success', 'message': 'Settings saved.'})

@app.route("/status")
def status():
    now = time.time()
    main_bot_statuses = []
    with bots_lock:
        for i, bot in enumerate(main_bots):
            bot_index = i + 1
            main_bot_statuses.append({"name": f"MAIN #{bot_index}", "status": bot is not None, "reboot_id": f"main_{bot_index}", "is_active": bot_active_states.get(f'main_{bot_index}', False), "type": "main"})
        sub_account_statuses = [{"name": acc_names[i] if i < len(acc_names) else f"Sub {i+1}", "status": bot is not None, "reboot_id": f"sub_{i}", "is_active": bot_active_states.get(f'sub_{i}', False), "type": "sub"} for i, bot in enumerate(bots)]
    
    for server in servers:
        server['spam_countdown'] = (server.get('last_spam_time', 0) + server.get('spam_delay', 10) - now) if server.get('spam_enabled') else 0

    return jsonify({
        'reboot_enabled': auto_reboot_enabled, 'reboot_countdown': (last_reboot_cycle_time + auto_reboot_delay - now) if auto_reboot_enabled else 0,
        'bot_statuses': {"main_bots": main_bot_statuses, "sub_accounts": sub_account_statuses},
        'server_start_time': server_start_time, 'servers': servers
    })

# --- MAIN EXECUTION ---
if __name__ == "__main__":
    load_settings()
    
    print("Đang khởi tạo các bot...", flush=True)
    with bots_lock:
        for i, token in enumerate(main_tokens):
            if token.strip():
                bot_index = i + 1
                main_bots.append(create_bot(token.strip(), bot_index=bot_index))
                bot_active_states.setdefault(f'main_{bot_index}', True)
        for i, token in enumerate(tokens):
            if token.strip():
                bots.append(create_bot(token.strip()))
                bot_active_states.setdefault(f'sub_{i}', True)

    print("Đang khởi tạo các luồng nền...", flush=True)
    threading.Thread(target=periodic_save_loop, daemon=True).start()
    spam_thread = threading.Thread(target=spam_loop, daemon=True)
    spam_thread.start()
    if auto_reboot_enabled:
        auto_reboot_thread = threading.Thread(target=auto_reboot_loop, daemon=True)
        auto_reboot_thread.start()
    
    port = int(os.environ.get("PORT", 10000))
    print(f"Khởi động Web Server tại http://0.0.0.0:{port}", flush=True)
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
