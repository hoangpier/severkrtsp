# PHIÊN BẢN KẾT HỢP: BACKEND LINH HOẠT + GIAO DIỆN GỐC
import discum
import threading
import time
import os
import random
import re
import requests
import json
from flask import Flask, request, render_template_string, jsonify
from dotenv import load_dotenv

load_dotenv()

# --- CẤU HÌNH ĐỘNG ---
main_tokens = [token.strip() for token in os.getenv("MAIN_TOKENS", "").split(",") if token.strip()]
sub_tokens = [token.strip() for token in os.getenv("SUB_TOKENS", "").split(",") if token.strip()]
karuta_id = "646937666251915264"
heart_bot_id = os.getenv("HEART_BOT_ID", "1274445226064220273")

# --- BIẾN TRẠNG THÁI TOÀN CỤC ---
main_bots, sub_bots = [], []
grab_channel_ids, ktb_channel_ids, spam_channel_ids = [], [], []
main_bot_settings = {}
spam_enabled, spam_message, spam_delay = False, "", 10
bots_lock = threading.Lock()
spam_thread = None
last_spam_time = 0
server_start_time = time.time()

# --- HÀM LƯU VÀ TẢI CÀI ĐẶT ---
def save_settings():
    api_key = os.getenv("JSONBIN_API_KEY")
    bin_id = os.getenv("JSONBIN_BIN_ID")
    if not api_key or not bin_id: return
    settings = {
        'main_bot_settings': main_bot_settings, 'grab_channel_ids': grab_channel_ids,
        'ktb_channel_ids': ktb_channel_ids, 'spam_channel_ids': spam_channel_ids,
        'spam_enabled': spam_enabled, 'spam_message': spam_message, 'spam_delay': spam_delay,
    }
    headers = {'Content-Type': 'application/json', 'X-Master-Key': api_key}
    url = f"https://api.jsonbin.io/v3/b/{bin_id}"
    try:
        req = requests.put(url, json=settings, headers=headers, timeout=10)
        if req.status_code == 200: print("[Settings] Đã lưu cài đặt lên JSONBin.io.", flush=True)
        else: print(f"[Settings] Lỗi khi lưu cài đặt: {req.status_code} - {req.text}", flush=True)
    except Exception as e: print(f"[Settings] Exception khi lưu cài đặt: {e}", flush=True)

def load_settings():
    global main_bot_settings, grab_channel_ids, ktb_channel_ids, spam_channel_ids, spam_enabled, spam_message, spam_delay
    api_key = os.getenv("JSONBIN_API_KEY")
    bin_id = os.getenv("JSONBIN_BIN_ID")
    if not api_key or not bin_id:
        print("[Settings] Thiếu API Key/Bin ID. Dùng cài đặt mặc định.", flush=True)
        return
    headers = {'X-Master-Key': api_key}
    url = f"https://api.jsonbin.io/v3/b/{bin_id}/latest"
    try:
        req = requests.get(url, headers=headers, timeout=10)
        if req.status_code == 200:
            settings = req.json().get("record", {})
            if settings:
                main_bot_settings = {int(k): v for k, v in settings.get('main_bot_settings', {}).items()}
                grab_channel_ids = settings.get('grab_channel_ids', [])
                ktb_channel_ids = settings.get('ktb_channel_ids', [])
                spam_channel_ids = settings.get('spam_channel_ids', [])
                spam_enabled = settings.get('spam_enabled', False)
                spam_message = settings.get('spam_message', "")
                spam_delay = settings.get('spam_delay', 10)
                print("[Settings] Đã tải cài đặt từ JSONBin.io.", flush=True)
            else:
                print("[Settings] JSONBin rỗng. Bắt đầu với cài đặt mặc định.", flush=True)
                save_settings()
        else: print(f"[Settings] Lỗi khi tải cài đặt: {req.status_code} - {req.text}", flush=True)
    except Exception as e: print(f"[Settings] Exception khi tải cài đặt: {e}", flush=True)

# --- LOGIC BOT ---
def create_bot(token, bot_index, is_main=False):
    bot = discum.Client(token=token, log=False)
    @bot.gateway.command
    def on_ready(resp):
        if resp.event.ready:
            user = resp.raw.get('user')
            if user:
                bot_type = "Main" if is_main else "Sub"
                print(f"Đã đăng nhập: {user.get('username', 'Unknown')} ({user.get('id', 'Unknown')}) - Loại: {bot_type} #{bot_index}", flush=True)
            else:
                print(f"[LỖI] Không thể lấy thông tin người dùng cho bot #{bot_index}. Token có thể không hợp lệ.", flush=True)

    if is_main:
        @bot.gateway.command
        def on_message_main(resp):
            try:
                settings = main_bot_settings.get(bot_index, {'enabled': False, 'threshold': 50})
                if not settings.get('enabled'): return
                if resp.event.message:
                    msg = resp.parsed.auto()
                    if (msg.get("author", {}).get("id") == karuta_id and
                        msg.get("channel_id") in grab_channel_ids and
                        "is dropping" not in msg.get("content", "") and
                        not msg.get("mentions", [])):
                        last_drop_msg_id, drop_channel_id = msg["id"], msg["channel_id"]
                        def read_heart_and_grab():
                            try:
                                time.sleep(0.7)
                                messages_response = bot.getMessages(drop_channel_id, num=5)
                                if not messages_response.ok: return
                                messages = messages_response.json()
                                if not isinstance(messages, list): return
                                for msg_item in messages:
                                    if (msg_item.get("author", {}).get("id") == heart_bot_id and 
                                        isinstance(msg_item.get("embeds"), list) and len(msg_item["embeds"]) > 0):
                                        desc = msg_item["embeds"][0].get("description", "")
                                        lines, heart_numbers = desc.split('\n'), [0, 0, 0]
                                        for i, line in enumerate(lines[:3]):
                                            match = re.search(r'♡\s*(\d+)', line)
                                            if match: heart_numbers[i] = int(match.group(1))
                                        max_num = max(heart_numbers)
                                        if sum(heart_numbers) > 0 and max_num >= settings.get('threshold', 50):
                                            max_index = heart_numbers.index(max_num)
                                            emoji, delay = [("1️⃣", 0.5), ("2️⃣", 1.5), ("3️⃣", 2.2)][max_index]
                                            final_delay = delay + random.uniform(-0.2, 0.2)
                                            print(f"[Main Bot #{bot_index}] Chọn dòng {max_index+1} ({max_num} tim). Nhấn {emoji} sau {final_delay:.2f}s", flush=True)
                                            def grab_action():
                                                try:
                                                    bot.addReaction(drop_channel_id, last_drop_msg_id, emoji)
                                                    time.sleep(2)
                                                    for ktb_ch_id in ktb_channel_ids:
                                                        if ktb_ch_id: bot.sendMessage(ktb_ch_id, "kt b"); time.sleep(0.5)
                                                    print(f"[Main Bot #{bot_index}] Đã gửi 'kt b'.", flush=True)
                                                except Exception as e_grab: print(f"[Main Bot #{bot_index}] Lỗi grab_action: {e_grab}", flush=True)
                                            threading.Timer(final_delay, grab_action).start()
                                        break
                            except Exception as e_read: print(f"[Main Bot #{bot_index}] Lỗi read_heart: {e_read}", flush=True)
                        threading.Thread(target=read_heart_and_grab).start()
            except Exception as e_main: print(f"[Main Bot #{bot_index}] Lỗi on_message: {e_main}", flush=True)
    threading.Thread(target=bot.gateway.run, daemon=True).start()
    return bot

# --- VÒNG LẶP NỀN ---
def spam_loop():
    global last_spam_time
    while True:
        try:
            if spam_enabled and spam_message and (time.time() - last_spam_time) >= spam_delay:
                with bots_lock: bots_to_spam = list(sub_bots)
                for i, bot in enumerate(bots_to_spam):
                    if not spam_enabled: break
                    try:
                        for channel_id in spam_channel_ids:
                            if channel_id:
                                bot.sendMessage(channel_id, spam_message)
                                print(f"[Sub Bot #{i}] Đã spam '{spam_message}' đến kênh {channel_id}", flush=True)
                                time.sleep(1)
                        time.sleep(2)
                    except Exception as e: print(f"[Sub Bot #{i}] Lỗi gửi spam: {e}", flush=True)
                if spam_enabled: last_spam_time = time.time()
            time.sleep(1)
        except Exception as e: print(f"[ERROR in spam_loop] {e}", flush=True); time.sleep(1)

def periodic_save_loop():
    while True:
        time.sleep(300)
        print("[Settings] Tự động lưu cài đặt...", flush=True)
        save_settings()

# --- GIAO DIỆN WEB (FLASK) ---
app = Flask(__name__)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Shadow Network Control</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <link href="https://fonts.googleapis.com/css2?family=Nosifer&family=Orbitron:wght@400;700&family=Courier+Prime&display=swap" rel="stylesheet">
    <style>
        :root {
            --primary-bg: #0a0a0a; --secondary-bg: #1a1a1a; --panel-bg: #111111; --border-color: #333333;
            --blood-red: #8b0000; --deep-purple: #2d1b69; --necro-green: #228b22;
            --text-primary: #f0f0f0; --text-secondary: #cccccc;
            --shadow-red: 0 0 20px rgba(139, 0, 0, 0.5); --shadow-purple: 0 0 20px rgba(45, 27, 105, 0.5);
        }
        body { font-family: 'Courier Prime', monospace; background: var(--primary-bg); color: var(--text-primary); margin: 0; padding: 20px; }
        .container { max-width: 1600px; margin: 0 auto; }
        .header { text-align: center; margin-bottom: 30px; padding: 20px; background: linear-gradient(135deg, #000, rgba(139, 0, 0, 0.2)); border: 2px solid var(--blood-red); border-radius: 15px; box-shadow: var(--shadow-red); }
        .title { font-family: 'Nosifer', cursive; font-size: 3rem; color: var(--blood-red); text-shadow: 0 0 20px var(--blood-red); }
        .subtitle { font-size: 1.2rem; color: var(--text-secondary); font-family: 'Orbitron', monospace; }
        .main-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(450px, 1fr)); gap: 20px; }
        .panel { background: linear-gradient(135deg, var(--panel-bg), rgba(26, 26, 26, 0.9)); border: 1px solid var(--border-color); border-radius: 10px; padding: 25px; box-shadow: 0 4px 15px rgba(0, 0, 0, 0.5); }
        .panel h2 { font-family: 'Nosifer', cursive; font-size: 1.4rem; margin-bottom: 20px; border-bottom: 2px solid; padding-bottom: 10px; }
        .panel h2 i { margin-right: 10px; }
        .blood-panel { border-color: var(--blood-red); box-shadow: var(--shadow-red); }
        .blood-panel h2 { color: var(--blood-red); border-color: var(--blood-red); }
        .dark-panel { border-color: var(--deep-purple); box-shadow: var(--shadow-purple); }
        .dark-panel h2 { color: var(--deep-purple); border-color: var(--deep-purple); }
        .btn { background: linear-gradient(135deg, var(--secondary-bg), #333); border: 1px solid var(--border-color); color: var(--text-primary); padding: 10px 15px; border-radius: 4px; cursor: pointer; font-family: 'Orbitron', monospace; font-weight: 700; text-transform: uppercase; }
        .btn-blood { border-color: var(--blood-red); color: var(--blood-red); } .btn-blood:hover { background: var(--blood-red); color: var(--primary-bg); box-shadow: var(--shadow-red); }
        .btn-necro { border-color: var(--necro-green); color: var(--necro-green); } .btn-necro:hover { background: var(--necro-green); color: var(--primary-bg); }
        .input-group { display: flex; flex-direction: column; gap: 5px; margin-bottom: 15px; }
        .input-group label { color: var(--text-secondary); font-weight: 600; font-family: 'Orbitron', monospace; }
        .input-group input, .input-group textarea { width: 100%; box-sizing: border-box; background: rgba(0, 0, 0, 0.8); border: 1px solid var(--border-color); color: var(--text-primary); padding: 10px; border-radius: 5px; font-family: 'Courier Prime', monospace; }
        .grab-section { margin-bottom: 15px; padding: 15px; background: rgba(0,0,0,0.2); border: 1px solid var(--border-color); border-radius: 8px;}
        .grab-section h3 { color: var(--text-secondary); margin-top:0; margin-bottom: 10px; font-family: 'Orbitron', monospace; }
        .grab-controls { display: flex; align-items: center; gap: 10px; }
        .grab-controls input { flex-grow: 1; }
        .status-badge { padding: 4px 10px; border-radius: 15px; text-transform: uppercase; font-size: 0.8em; }
        .status-badge.active { background: var(--necro-green); color: var(--primary-bg); }
        .status-badge.inactive { background: var(--blood-red); color: var(--text-secondary); }
        .msg-status { text-align: center; color: #00e5ff; padding: 12px; border: 1px dashed #00e5ff; border-radius: 4px; margin: 0 0 20px 0; display: none; background: rgba(0, 229, 255, 0.1); }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1 class="title">SHADOW NETWORK</h1>
            <p class="subtitle">Karuta Control Interface</p>
        </div>
        <div id="msg-status-container" class="msg-status"></div>
        <div class="main-grid">
            <div class="panel blood-panel">
                <h2 data-text="Soul Harvest"><i class="fas fa-crosshairs"></i> Soul Harvest</h2>
                <div id="main-bots-container"></div>
            </div>
            <div class="panel dark-panel">
                <h2 data-text="Shadow Broadcast"><i class="fas fa-broadcast-tower"></i> Shadow Broadcast</h2>
                <div class="input-group"><label for="spam-message">Spam Message</label><textarea id="spam-message" rows="2">{{ spam_message }}</textarea></div>
                <div class="input-group"><label for="spam-delay">Cycle Delay (s)</label><input type="number" id="spam-delay" value="{{ spam_delay }}"></div>
                <button type="button" id="spam-toggle-btn" class="btn {{ 'btn-blood' if spam_enabled else 'btn-necro' }}">{{ 'DISABLE SPAM' if spam_enabled else 'ENABLE SPAM' }}</button>
            </div>
            <div class="panel" style="grid-column: 1 / -1;">
                <h2><i class="fas fa-network-wired"></i> Channel Matrix</h2>
                <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 20px;">
                    <div class="input-group"><label>Grab Channel IDs</label><textarea id="grab-channels-input" rows="4" placeholder="Phẩy để ngăn cách">{{ grab_channel_ids|join(',') }}</textarea></div>
                    <div class="input-group"><label>KTB Channel IDs</label><textarea id="ktb-channels-input" rows="4" placeholder="Phẩy để ngăn cách">{{ ktb_channel_ids|join(',') }}</textarea></div>
                    <div class="input-group"><label>Spam Channel IDs</label><textarea id="spam-channels-input" rows="4" placeholder="Phẩy để ngăn cách">{{ spam_channel_ids|join(',') }}</textarea></div>
                </div>
                <button type="button" id="save-channels-btn" class="btn btn-blood" style="width: 100%; margin-top: 10px;">Save Channel Matrix</button>
            </div>
        </div>
    </div>
<script>
document.addEventListener('DOMContentLoaded', function () {
    const msgStatusContainer = document.getElementById('msg-status-container');
    function showStatusMessage(message) {
        if (!message) return;
        msgStatusContainer.textContent = message;
        msgStatusContainer.style.display = 'block';
        setTimeout(() => { msgStatusContainer.style.display = 'none'; }, 4000);
    }

    async function postData(url = '', data = {}) {
        try {
            const response = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) });
            const result = await response.json();
            if (result.message) showStatusMessage(result.message);
            fetchStatus();
            return result;
        } catch (error) { console.error('Error:', error); showStatusMessage('Lỗi giao tiếp với server.'); }
    }

    function renderMainBots(settings) {
        const container = document.getElementById('main-bots-container');
        container.innerHTML = '';
        if (Object.keys(settings).length === 0) {
            container.innerHTML = '<p>Không tìm thấy tài khoản chính nào. Hãy thêm token vào file .env.</p>';
            return;
        }
        const sortedIndices = Object.keys(settings).sort((a, b) => a - b);
        for (const index of sortedIndices) {
            const botSetting = settings[index];
            const botDiv = document.createElement('div');
            botDiv.className = 'grab-section';
            const buttonClass = botSetting.enabled ? 'btn-blood' : 'btn-necro';
            const buttonText = botSetting.enabled ? 'DISABLE' : 'ENABLE';
            const statusClass = botSetting.enabled ? 'active' : 'inactive';
            const statusText = botSetting.enabled ? 'ON' : 'OFF';

            botDiv.innerHTML = `
                <h3>${botSetting.name || `Main Bot #${index}`} <span class="status-badge ${statusClass}">${statusText}</span></h3>
                <div class="grab-controls">
                    <input type="number" id="heart-threshold-${index}" value="${botSetting.threshold || 50}" title="Ngưỡng tim">
                    <button data-index="${index}" class="btn btn-toggle-grab ${buttonClass}">${buttonText}</button>
                </div>
            `;
            container.appendChild(botDiv);
        }
    }

    async function fetchStatus() {
        try {
            const response = await fetch('/status');
            const data = await response.json();
            renderMainBots(data.main_bot_settings);
            document.getElementById('spam-message').value = data.spam_message;
            document.getElementById('spam-delay').value = data.spam_delay;
            const spamBtn = document.getElementById('spam-toggle-btn');
            spamBtn.textContent = data.spam_enabled ? 'DISABLE SPAM' : 'ENABLE SPAM';
            spamBtn.className = `btn ${data.spam_enabled ? 'btn-blood' : 'btn-necro'}`;
            document.getElementById('grab-channels-input').value = data.grab_channel_ids.join(',');
            document.getElementById('ktb-channels-input').value = data.ktb_channel_ids.join(',');
            document.getElementById('spam-channels-input').value = data.spam_channel_ids.join(',');
        } catch (error) { console.error('Error fetching status:', error); }
    }

    document.getElementById('main-bots-container').addEventListener('click', function(e) {
        if (e.target && e.target.classList.contains('btn-toggle-grab')) {
            const index = e.target.dataset.index;
            const threshold = document.getElementById(`heart-threshold-${index}`).value;
            postData('/api/main_bot_toggle', { index: parseInt(index), threshold: parseInt(threshold) });
        }
    });

    document.getElementById('spam-toggle-btn').addEventListener('click', function() {
        postData('/api/spam_toggle', {
            message: document.getElementById('spam-message').value,
            delay: parseInt(document.getElementById('spam-delay').value)
        });
    });

    document.getElementById('save-channels-btn').addEventListener('click', function() {
        postData('/api/update_channels', {
            grab_channels: document.getElementById('grab-channels-input').value,
            ktb_channels: document.getElementById('ktb-channels-input').value,
            spam_channels: document.getElementById('spam-channels-input').value
        });
    });

    fetchStatus();
    setInterval(fetchStatus, 5000);
});
</script>
</body>
</html>
"""

# --- FLASK API ENDPOINTS ---
@app.route("/")
def index():
    return render_template_string(HTML_TEMPLATE,
        spam_enabled=spam_enabled, spam_message=spam_message, spam_delay=spam_delay,
        grab_channel_ids=grab_channel_ids, ktb_channel_ids=ktb_channel_ids, spam_channel_ids=spam_channel_ids
    )

@app.route("/status")
def status():
    return jsonify({
        'main_bot_settings': main_bot_settings, 'spam_enabled': spam_enabled,
        'spam_message': spam_message, 'spam_delay': spam_delay,
        'grab_channel_ids': grab_channel_ids, 'ktb_channel_ids': ktb_channel_ids,
        'spam_channel_ids': spam_channel_ids, 'server_start_time': server_start_time,
    })

@app.route("/api/main_bot_toggle", methods=['POST'])
def api_main_bot_toggle():
    data = request.get_json()
    index, threshold = data.get('index'), data.get('threshold')
    if index in main_bot_settings:
        main_bot_settings[index]['enabled'] = not main_bot_settings[index].get('enabled', False)
        main_bot_settings[index]['threshold'] = threshold
        state = "BẬT" if main_bot_settings[index]['enabled'] else "TẮT"
        msg = f"{main_bot_settings[index].get('name', f'Main Bot #{index}')} đã được {state}."
        save_settings()
    else: msg = "Lỗi: Không tìm thấy bot."
    return jsonify({'status': 'success', 'message': msg})

@app.route("/api/spam_toggle", methods=['POST'])
def api_spam_toggle():
    global spam_enabled, spam_message, spam_delay, spam_thread, last_spam_time
    data = request.get_json()
    spam_enabled = not spam_enabled
    if spam_enabled:
        spam_message, spam_delay = data.get("message", "").strip(), data.get("delay", 10)
        if not spam_message:
            spam_enabled = False
            return jsonify({'status': 'error', 'message': 'Nội dung spam không được để trống.'})
        last_spam_time = time.time()
        if spam_thread is None or not spam_thread.is_alive():
            spam_thread = threading.Thread(target=spam_loop, daemon=True); spam_thread.start()
        msg = "Chức năng spam đã được BẬT."
    else: msg = "Chức năng spam đã được TẮT."
    save_settings()
    return jsonify({'status': 'success', 'message': msg})

@app.route("/api/update_channels", methods=['POST'])
def api_update_channels():
    global grab_channel_ids, ktb_channel_ids, spam_channel_ids
    data = request.get_json()
    grab_channel_ids = [ch_id.strip() for ch_id in data.get('grab_channels', '').split(',') if ch_id.strip()]
    ktb_channel_ids = [ch_id.strip() for ch_id in data.get('ktb_channels', '').split(',') if ch_id.strip()]
    spam_channel_ids = [ch_id.strip() for ch_id in data.get('spam_channels', '').split(',') if ch_id.strip()]
    save_settings()
    return jsonify({'status': 'success', 'message': 'Đã cập nhật cấu hình kênh.'})

# --- KHỞI ĐỘNG ---
if __name__ == "__main__":
    load_settings()
    print("Đang khởi tạo các bot...", flush=True)
    with bots_lock:
        for i, token in enumerate(main_tokens):
            main_bots.append(create_bot(token, bot_index=i, is_main=True))
            if i not in main_bot_settings:
                main_bot_settings[i] = {'enabled': False, 'threshold': 50, 'name': f'Main Account #{i+1}'}
            elif 'name' not in main_bot_settings[i]:
                 main_bot_settings[i]['name'] = f'Main Account #{i+1}'
        for i, token in enumerate(sub_tokens):
            sub_bots.append(create_bot(token, bot_index=i, is_main=False))
    print("Đang khởi tạo các luồng nền...", flush=True)
    threading.Thread(target=periodic_save_loop, daemon=True).start()
    if spam_enabled:
        if spam_thread is None or not spam_thread.is_alive():
            spam_thread = threading.Thread(target=spam_loop, daemon=True); spam_thread.start()
    port = int(os.environ.get("PORT", 10000))
    print(f"Khởi động Web Server tại http://0.0.0.0:{port}", flush=True)
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

