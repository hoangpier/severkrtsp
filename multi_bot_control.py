# PHIÊN BẢN TỔNG HỢP CUỐI CÙNG: LÕI LOGIC TỪ FILE LITE + CÁC TÍNH NĂNG MỚI
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

# --- CẤU HÌNH ĐỘNG ---
main_tokens = [token.strip() for token in os.getenv("MAIN_TOKENS", "").split(",") if token.strip()]
sub_tokens = [token.strip() for token in os.getenv("SUB_TOKENS", "").split(",") if token.strip()]
karuta_id = "646937666251915264"
heart_bot_id = os.getenv("HEART_BOT_ID", "1274445226064220273")

# --- BIẾN TRẠNG THÁI TOÀN CỤC ---
main_bots, sub_bots = [], []
servers = []  # Cấu trúc dữ liệu chính, quản lý tất cả server
bot_statuses = {}
bots_lock = threading.Lock()
spam_thread = None
server_start_time = time.time()

# --- HÀM LƯU VÀ TẢI CÀI ĐẶT ---
def save_settings():
    api_key = os.getenv("JSONBIN_API_KEY")
    bin_id = os.getenv("JSONBIN_BIN_ID")
    if not api_key or not bin_id: return
    settings = {'servers': servers}
    headers = {'Content-Type': 'application/json', 'X-Master-Key': api_key}
    url = f"https://api.jsonbin.io/v3/b/{bin_id}"
    try:
        req = requests.put(url, json=settings, headers=headers, timeout=10)
        if req.status_code == 200: print("[Settings] Đã lưu cài đặt.", flush=True)
        else: print(f"[Settings] Lỗi khi lưu: {req.status_code}", flush=True)
    except Exception as e: print(f"[Settings] Exception khi lưu: {e}", flush=True)

def load_settings():
    global servers
    api_key = os.getenv("JSONBIN_API_KEY")
    bin_id = os.getenv("JSONBIN_BIN_ID")
    if not api_key or not bin_id:
        print("[Settings] Thiếu API Key/Bin ID.", flush=True)
        return
    headers = {'X-Master-Key': api_key}
    url = f"https://api.jsonbin.io/v3/b/{bin_id}/latest"
    try:
        req = requests.get(url, headers=headers, timeout=10)
        if req.status_code == 200:
            settings = req.json().get("record", {})
            if settings and 'servers' in settings:
                servers = settings.get('servers', [])
                print("[Settings] Đã tải cài đặt.", flush=True)
            else:
                print("[Settings] JSONBin rỗng, bắt đầu với cấu hình trống.", flush=True)
        else: print(f"[Settings] Lỗi khi tải: {req.status_code}", flush=True)
    except Exception as e: print(f"[Settings] Exception khi tải: {e}", flush=True)

# --- LOGIC BOT ---
def handle_grab(bot, msg, bot_index):
    channel_id = msg.get("channel_id")
    target_server = next((s for s in servers if channel_id in s.get('grab_channel_ids', [])), None)
    if not target_server: return

    settings = target_server.get('main_bot_settings', {}).get(str(bot_index), {})
    if not settings.get('enabled'): return

    heart_threshold = settings.get('threshold', 50)
    ktb_channel_ids = target_server.get('ktb_channel_ids', [])

    if msg.get("author", {}).get("id") == karuta_id and "is dropping" not in msg.get("content", "") and not msg.get("mentions", []):
        last_drop_msg_id = msg["id"]
        def read_heart_and_grab():
            time.sleep(0.7)
            try:
                messages = bot.getMessages(channel_id, num=5).json()
                for msg_item in messages:
                    if msg_item.get("author", {}).get("id") == heart_bot_id and "embeds" in msg_item and msg_item["embeds"]:
                        desc = msg_item["embeds"][0].get("description", "")
                        lines, heart_numbers = desc.split('\n'), [0, 0, 0]
                        for i, line in enumerate(lines[:3]):
                            match = re.search(r'♡\s*(\d+)', line)
                            if match: heart_numbers[i] = int(match.group(1))
                        
                        max_num = max(heart_numbers)
                        if sum(heart_numbers) > 0 and max_num >= heart_threshold:
                            max_index = heart_numbers.index(max_num)
                            emoji, delay = [("1️⃣", 0.5), ("2️⃣", 1.5), ("3️⃣", 2.2)][max_index]
                            final_delay = delay + random.uniform(-0.2, 0.2)
                            print(f"[{target_server['name']}|main_{bot_index}] Chọn dòng {max_index+1} ({max_num} tim). Nhấn {emoji} sau {final_delay:.2f}s", flush=True)
                            
                            def grab_action():
                                bot.addReaction(channel_id, last_drop_msg_id, emoji)
                                time.sleep(2)
                                for ktb_ch_id in ktb_channel_ids:
                                    if ktb_ch_id: bot.sendMessage(ktb_ch_id, "kt b"); time.sleep(0.5)
                                print(f"[{target_server['name']}|main_{bot_index}] Đã gửi 'kt b'.", flush=True)
                            
                            threading.Timer(final_delay, grab_action).start()
                        break
            except Exception as e: print(f"Lỗi khi đọc tim (main_{bot_index} @ {target_server['name']}): {e}", flush=True)
        threading.Thread(target=read_heart_and_grab).start()

def create_bot(token, bot_index, is_main=False):
    bot = discum.Client(token=token, log=False)
    bot_id_str = f"main_{bot_index}" if is_main else f"sub_{bot_index}"

    @bot.gateway.command
    def on_ready(resp):
        if resp.event.ready:
            user = resp.raw.get('user')
            if user:
                bot_statuses[bot_id_str] = 'online'
                print(f"ONLINE: {user.get('username', 'Unknown')} ({user.get('id', 'Unknown')}) - ID: {bot_id_str}", flush=True)
            else:
                bot_statuses[bot_id_str] = 'failed'
                print(f"FAILED: Không thể lấy thông tin cho bot {bot_id_str}. Token có thể không hợp lệ.", flush=True)

    if is_main:
        @bot.gateway.command
        def on_message(resp):
            if resp.event.message: handle_grab(bot, resp.parsed.auto(), bot_index)
            
    threading.Thread(target=bot.gateway.run, daemon=True).start()
    return bot

# --- VÒNG LẶP NỀN ---
def spam_loop():
    while True:
        try:
            bots_to_spam = [bot for i, bot in enumerate(sub_bots) if bot_statuses.get(f"sub_{i}") == 'online']
            for server in servers:
                if server.get('spam_enabled') and server.get('spam_message') and server.get('spam_channel_ids'):
                    last_spam_time = server.get('last_spam_time', 0)
                    spam_delay = server.get('spam_delay', 10)
                    if (time.time() - last_spam_time) >= spam_delay:
                        for bot in bots_to_spam:
                            if not server.get('spam_enabled'): break
                            try:
                                for channel_id in server['spam_channel_ids']:
                                    bot.sendMessage(channel_id, server['spam_message'])
                                    time.sleep(0.5) # Delay nhẹ giữa các kênh
                            except Exception as e: print(f"Lỗi gửi spam tới server {server['name']}: {e}", flush=True)
                            time.sleep(2) # Delay giữa các bot
                        if server.get('spam_enabled'): server['last_spam_time'] = time.time()
            time.sleep(1)
        except Exception as e: print(f"[ERROR in spam_loop] {e}", flush=True); time.sleep(1)

def periodic_save_loop():
    while True: time.sleep(300); save_settings()
        
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
    <link href="https://fonts.googleapis.com/css2?family=Nosifer&family=Orbitron:wght@400;700&family=Courier+Prime&display=swap" rel="stylesheet">
    <style>
        :root {
            --primary-bg: #0a0a0a; --panel-bg: #111111; --border-color: #333333;
            --blood-red: #8b0000; --deep-purple: #2d1b69; --necro-green: #228b22; --gold-yellow: #ffc107;
            --text-primary: #f0f0f0; --text-secondary: #cccccc;
            --shadow-red: 0 0 20px rgba(139, 0, 0, 0.5);
        }
        body { font-family: 'Courier Prime', monospace; background: var(--primary-bg); color: var(--text-primary); margin: 0; padding: 20px; }
        .container { max-width: 1600px; margin: 0 auto; }
        .header { text-align: center; margin-bottom: 30px; padding: 20px; background: linear-gradient(135deg, #000, rgba(139, 0, 0, 0.2)); border: 2px solid var(--blood-red); border-radius: 15px; box-shadow: var(--shadow-red); }
        .title { font-family: 'Nosifer', cursive; font-size: 3rem; color: var(--blood-red); text-shadow: 0 0 20px var(--blood-red); }
        .main-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(450px, 1fr)); gap: 20px; }
        .panel { background: var(--panel-bg); border: 1px solid var(--border-color); border-radius: 10px; padding: 25px; position: relative;}
        .panel h2 { font-family: 'Orbitron', cursive; font-size: 1.4rem; margin-bottom: 20px; text-transform: uppercase; border-bottom: 1px solid; padding-bottom: 10px; color: var(--bone-white); }
        .panel h3 { font-family: 'Orbitron', monospace; }
        .panel h2 i, .panel h3 i { margin-right: 10px; }
        .btn { background: #1a1a1a; border: 1px solid var(--border-color); color: var(--text-primary); padding: 10px 15px; border-radius: 4px; cursor: pointer; font-family: 'Orbitron', monospace; font-weight: 700; text-transform: uppercase; width: 100%; }
        .btn-blood { border-color: var(--blood-red); color: var(--blood-red); } .btn-blood:hover { background: var(--blood-red); color: var(--primary-bg); }
        .btn-necro { border-color: var(--necro-green); color: var(--necro-green); } .btn-necro:hover { background: var(--necro-green); color: var(--primary-bg); }
        .input-group { display: flex; flex-direction: column; gap: 5px; margin-bottom: 15px; }
        .input-group label { color: var(--text-secondary); }
        .input-group input, .input-group textarea { width: 100%; box-sizing: border-box; background: #000; border: 1px solid var(--border-color); color: var(--text-primary); padding: 10px; border-radius: 5px; font-family: 'Courier Prime', monospace; }
        .grab-section { margin-bottom: 15px; padding: 15px; background: rgba(0,0,0,0.2); border-radius: 8px;}
        .grab-section h4 { margin: 0 0 10px 0; display: flex; align-items: center; gap: 10px; }
        .grab-controls { display: flex; align-items: center; gap: 10px; }
        .grab-controls input { flex-grow: 1; }
        .msg-status { text-align: center; color: var(--necro-green); padding: 12px; border: 1px dashed var(--border-color); border-radius: 4px; margin-bottom: 20px; display: none; }
        .status-panel { grid-column: 1 / -1; }
        .bot-status-list { max-height: 200px; overflow-y: auto; padding: 10px; background: rgba(0,0,0,0.2); border-radius: 5px; }
        .bot-status-item { display: flex; justify-content: space-between; align-items: center; padding: 5px; border-bottom: 1px solid var(--border-color); font-size: 0.9em; }
        .bot-status-item:last-child { border-bottom: none; }
        .bot-status-name { text-transform: capitalize; }
        .bot-status-indicator { font-weight: bold; }
        .bot-status-indicator.online { color: var(--necro-green); }
        .bot-status-indicator.connecting { color: var(--gold-yellow); }
        .bot-status-indicator.failed { color: var(--blood-red); }
        .add-server-btn { display: flex; align-items: center; justify-content: center; min-height: 200px; border: 2px dashed var(--border-color); cursor: pointer; transition: all 0.3s ease; }
        .add-server-btn:hover { background: #1a1a1a; border-color: var(--blood-red); }
        .add-server-btn i { font-size: 3rem; color: var(--text-secondary); }
        .btn-delete-server { position: absolute; top: 15px; right: 15px; background: var(--blood-red); border: 1px solid var(--blood-red); color: #fff; width: 30px; height: 30px; padding: 0; border-radius: 50%; }
        .server-sub-panel { border-top: 1px solid var(--border-color); margin-top: 20px; padding-top: 20px;}
    </style>
</head>
<body>
    <div class="container">
        <div class="header"> <h1 class="title">Shadow Network Control</h1> </div>
        <div id="msg-status-container" class="msg-status"> <span id="msg-status-text"></span></div>
        <div class="main-grid">
            <div class="panel status-panel">
                <h2><i class="fas fa-heartbeat"></i> System Status</h2>
                <div class="bot-status-list" id="bot-status-container"></div>
            </div>

            {% for server in servers %}
            <div class="panel server-panel" data-server-id="{{ server.id }}">
                <button class="btn-delete-server" title="Delete Server"><i class="fas fa-times"></i></button>
                <h2><i class="fas fa-server"></i> {{ server.name }}</h2>
                
                <div class="server-sub-panel">
                    <h3><i class="fas fa-cogs"></i> Channel Config</h3>
                    <div class="input-group"><label>Grab Channel IDs (phẩy để ngăn cách)</label><textarea class="channel-input" data-field="grab_channel_ids" rows="2">{{ server.grab_channel_ids|join(',') }}</textarea></div>
                    <div class="input-group"><label>KTB Channel IDs (phẩy để ngăn cách)</label><textarea class="channel-input" data-field="ktb_channel_ids" rows="2">{{ server.ktb_channel_ids|join(',') }}</textarea></div>
                    <div class="input-group"><label>Spam Channel IDs (phẩy để ngăn cách)</label><textarea class="channel-input" data-field="spam_channel_ids" rows="2">{{ server.spam_channel_ids|join(',') }}</textarea></div>
                </div>

                <div class="server-sub-panel">
                    <h3><i class="fas fa-crosshairs"></i> Soul Harvest</h3>
                    <div id="main-bots-controls-{{server.id}}"></div>
                </div>
                
                <div class="server-sub-panel">
                    <h3><i class="fas fa-paper-plane"></i> Auto Broadcast</h3>
                    <div class="input-group"><label>Message</label><textarea class="spam-message" rows="2">{{ server.spam_message or '' }}</textarea></div>
                    <div class="input-group"><label>Delay (s)</label><input type="number" class="spam-delay" value="{{ server.spam_delay or 10 }}"></div>
                    <button type="button" class="btn broadcast-toggle">{{ 'DISABLE' if server.spam_enabled else 'ENABLE' }}</button>
                </div>
            </div>
            {% endfor %}

            <div class="panel add-server-btn" id="add-server-btn">
                <i class="fas fa-plus"></i>
            </div>
        </div>
    </div>
<script>
    document.addEventListener('DOMContentLoaded', function () {
        const msgStatusContainer = document.getElementById('msg-status-container');
        const mainGrid = document.querySelector('.main-grid');

        function showStatusMessage(message, isError = false) {
            if (!message) return;
            msgStatusText.textContent = message;
            msgStatusContainer.style.color = isError ? 'var(--blood-red)' : 'var(--necro-green)';
            msgStatusContainer.style.display = 'block';
            setTimeout(() => { msgStatusContainer.style.display = 'none'; }, 4000);
        }

        async function postData(url = '', data = {}) {
            try {
                const response = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) });
                const result = await response.json();
                showStatusMessage(result.message, result.status !== 'success');
                if (result.status === 'success') {
                    if (result.reload) { setTimeout(() => window.location.reload(), 500); }
                    else { setTimeout(fetchStatus, 500); }
                }
                return result;
            } catch (error) { console.error('Error:', error); showStatusMessage('Server communication error.', true); }
        }

        const updateInputValue = (element, newValue) => {
            if (element && document.activeElement !== element) {
                element.value = newValue;
            }
        };

        function renderBotStatus(statuses) {
            const container = document.getElementById('bot-status-container');
            container.innerHTML = '';
            const sortedKeys = Object.keys(statuses).sort();
            if (sortedKeys.length === 0) {
                container.innerHTML = '<p>Đang chờ khởi tạo bot...</p>'; return;
            }
            for(const botId of sortedKeys) {
                const status = statuses[botId];
                const item = document.createElement('div');
                item.className = 'bot-status-item';
                item.innerHTML = `<span class="bot-status-name">${botId.replace('_', ' #')}</span> <span class="bot-status-indicator ${status}">${status.toUpperCase()}</span>`;
                container.appendChild(item);
            }
        }

        async function fetchStatus() {
            try {
                const response = await fetch('/status');
                const data = await response.json();
                renderBotStatus(data.bot_statuses);

                data.servers.forEach(serverData => {
                    const serverPanel = document.querySelector(`.server-panel[data-server-id="${serverData.id}"]`);
                    if (!serverPanel) return;

                    const mainBotsContainer = document.getElementById(`main-bots-controls-${serverData.id}`);
                    const mainBotSettings = serverData.main_bot_settings || {};
                    
                    if (mainBotsContainer.children.length !== Object.keys(mainBotSettings).length) {
                        mainBotsContainer.innerHTML = '';
                        Object.keys(mainBotSettings).sort((a,b) => parseInt(a) - parseInt(b)).forEach(botIndex => {
                             mainBotsContainer.innerHTML += `
                                <div class="grab-section">
                                    <h4>Main Account #${parseInt(botIndex)+1}</h4>
                                    <div class="grab-controls">
                                        <input type="number" class="harvest-threshold" data-node="${botIndex}" value="${mainBotSettings[botIndex].threshold || 50}" min="0">
                                        <button type="button" class="btn harvest-toggle" data-node="${botIndex}">
                                            ${mainBotSettings[botIndex].enabled ? 'DISABLE' : 'ENABLE'}
                                        </button>
                                    </div>
                                </div>`;
                        });
                    } else {
                         Object.keys(mainBotSettings).forEach(botIndex => {
                            const btn = serverPanel.querySelector(`.harvest-toggle[data-node="${botIndex}"]`);
                            if(btn) btn.textContent = mainBotSettings[botIndex].enabled ? 'DISABLE' : 'ENABLE';
                            const thresholdInput = serverPanel.querySelector(`.harvest-threshold[data-node="${botIndex}"]`);
                            updateInputValue(thresholdInput, mainBotSettings[botIndex].threshold || 50);
                        });
                    }
                    
                    const spamToggleBtn = serverPanel.querySelector('.broadcast-toggle');
                    if(spamToggleBtn) spamToggleBtn.textContent = serverData.spam_enabled ? 'DISABLE' : 'ENABLE';
                    updateInputValue(serverPanel.querySelector('.spam-message'), serverData.spam_message || '');
                    updateInputValue(serverPanel.querySelector('.spam-delay'), serverData.spam_delay || 10);
                });

            } catch (error) { console.error('Error fetching status:', error); }
        }
        setInterval(fetchStatus, 3000);

        mainGrid.addEventListener('click', e => {
            const target = e.target;
            const serverPanel = target.closest('.server-panel');
            if (!serverPanel) return;
            const serverId = serverPanel.dataset.serverId;
            
            if (target.classList.contains('harvest-toggle')) {
                const node = target.dataset.node;
                const thresholdInput = serverPanel.querySelector(`.harvest-threshold[data-node="${node}"]`);
                postData('/api/harvest_toggle', { server_id: serverId, node: node, threshold: thresholdInput.value });
            }
            if (target.classList.contains('broadcast-toggle')) {
                const message = serverPanel.querySelector('.spam-message').value;
                const delay = serverPanel.querySelector('.spam-delay').value;
                postData('/api/broadcast_toggle', { server_id: serverId, message: message, delay: delay });
            }
            if (target.closest('.btn-delete-server')) {
                if(confirm('Are you sure you want to delete this server configuration?')) {
                    postData('/api/delete_server', { server_id: serverId });
                }
            }
        });

        mainGrid.addEventListener('change', e => {
            const target = e.target;
            const serverPanel = target.closest('.server-panel');
            if (serverPanel && target.classList.contains('channel-input')) {
                const payload = { server_id: serverPanel.dataset.serverId };
                payload[target.dataset.field] = target.value;
                postData('/api/update_server_channels', payload).then(() => save_settings());
            }
        });

        document.getElementById('add-server-btn').addEventListener('click', () => {
            const name = prompt("Enter a name for the new server:", "New Server");
            if (name) { postData('/api/add_server', { name: name }); }
        });

        function save_settings() { postData('/api/save_settings'); }
    });
</script>
</body>
</html>
"""

# --- FLASK API ENDPOINTS ---
@app.route("/")
def index():
    sorted_servers = sorted(servers, key=lambda s: s.get('name', ''))
    return render_template_string(HTML_TEMPLATE, servers=sorted_servers)

@app.route("/status")
def status():
    # Add countdown to each server object for UI
    for server in servers:
        if server.get('spam_enabled'):
            server['spam_countdown'] = (server.get('last_spam_time', 0) + server.get('spam_delay', 10) - time.time())
        else:
            server['spam_countdown'] = 0
    return jsonify({'servers': servers, 'bot_statuses': bot_statuses})

# --- SERVER MANAGEMENT API ---
@app.route("/api/add_server", methods=['POST'])
def api_add_server():
    data = request.get_json()
    name = data.get('name')
    if not name: return jsonify({'status': 'error', 'message': 'Server name is required.'}), 400
    
    new_server = {
        "id": f"server_{uuid.uuid4().hex}", "name": name,
        "grab_channel_ids": [], "ktb_channel_ids": [], "spam_channel_ids": [],
        "main_bot_settings": {str(i): {"enabled": False, "threshold": 50} for i in range(len(main_tokens))},
        "spam_enabled": False, "spam_message": "", "spam_delay": 10, "last_spam_time": 0
    }
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
    server_id = data.get('server_id')
    server = next((s for s in servers if s.get('id') == server_id), None)
    if not server: return jsonify({'status': 'error', 'message': 'Server not found.'}), 404
    
    for field in ['grab_channel_ids', 'ktb_channel_ids', 'spam_channel_ids']:
        if field in data:
            server[field] = [cid.strip() for cid in data[field].split(',') if cid.strip()]
    
    return jsonify({'status': 'success', 'message': f'Channels updated for {server["name"]}.'})

# --- CONTROL APIs ---
@app.route("/api/harvest_toggle", methods=['POST'])
def api_harvest_toggle():
    data = request.get_json()
    server_id, node, threshold = data.get('server_id'), data.get('node'), int(data.get('threshold', 50))
    server = next((s for s in servers if s.get('id') == server_id), None)
    if not server or node is None: return jsonify({'status': 'error', 'message': 'Invalid request.'}), 400
        
    node_str = str(node)
    if node_str not in server['main_bot_settings']: server['main_bot_settings'][node_str] = {}
    
    server['main_bot_settings'][node_str]['enabled'] = not server['main_bot_settings'][node_str].get('enabled', False)
    server['main_bot_settings'][node_str]['threshold'] = threshold
    
    state = "ENABLED" if server['main_bot_settings'][node_str]['enabled'] else "DISABLED"
    msg = f"Harvest Node {int(node)+1} was {state} for server {server['name']}."
    return jsonify({'status': 'success', 'message': msg})

@app.route("/api/broadcast_toggle", methods=['POST'])
def api_broadcast_toggle():
    data = request.get_json()
    server_id = data.get('server_id')
    server = next((s for s in servers if s.get('id') == server_id), None)
    if not server: return jsonify({'status': 'error', 'message': 'Server not found.'}), 404

    server['spam_enabled'] = not server.get('spam_enabled', False)
    if server['spam_enabled']:
        server['spam_message'] = data.get("message", "").strip()
        server['spam_delay'] = int(data.get("delay", 10))
        if not server['spam_message'] or not server['spam_channel_ids']:
            server['spam_enabled'] = False
            return jsonify({'status': 'error', 'message': 'Spam message and channel ID cannot be empty.'})
        server['last_spam_time'] = time.time()
        msg = f"Spam ENABLED for {server['name']}."
    else:
        msg = f"Spam DISABLED for {server['name']}."
    return jsonify({'status': 'success', 'message': msg})

@app.route("/api/save_settings", methods=['POST'])
def api_save_settings():
    save_settings()
    return jsonify({'status': 'success', 'message': 'Settings saved.'})

# --- MAIN EXECUTION ---
if __name__ == "__main__":
    load_settings()
    
    def initialize_bots():
        print("Bắt đầu quá trình khởi tạo bot tuần tự...", flush=True)
        with bots_lock:
            for i, token in enumerate(main_tokens):
                bot_statuses[f'main_{i}'] = 'connecting'
                main_bots.append(create_bot(token, bot_index=i, is_main=True))
                time.sleep(random.uniform(3, 6))

            for i, token in enumerate(sub_tokens):
                bot_statuses[f'sub_{i}'] = 'connecting'
                sub_bots.append(create_bot(token, bot_index=i, is_main=False))
                time.sleep(random.uniform(3, 6))
        print("Tất cả các bot đã được đưa vào hàng đợi khởi tạo.", flush=True)

    threading.Thread(target=initialize_bots, daemon=True).start()
    threading.Thread(target=periodic_save_loop, daemon=True).start()
    spam_thread = threading.Thread(target=spam_loop, daemon=True)
    spam_thread.start()
    
    port = int(os.environ.get("PORT", 10000))
    print(f"Khởi động Web Server tại http://0.0.0.0:{port}", flush=True)
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

