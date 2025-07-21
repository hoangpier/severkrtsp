# PHIÊN BẢN HOÀN CHỈNH - HỖ TRỢ ĐA KÊNH CHO CẢ GRAB VÀ SPAM
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

# --- CẤU HÌNH ---
main_tokens = os.getenv("MAIN_TOKENS").split(",") if os.getenv("MAIN_TOKENS") else []
tokens = os.getenv("TOKENS").split(",") if os.getenv("TOKENS") else []
grab_channel_ids = os.getenv("GRAB_CHANNEL_IDS", "").split(',') if os.getenv("GRAB_CHANNEL_IDS") else []
# THAY ĐỔI: Sử dụng danh sách cho kênh spam
spam_channel_ids = os.getenv("SPAM_CHANNEL_IDS", "").split(',') if os.getenv("SPAM_CHANNEL_IDS") else []
check_channel_id = os.getenv("CHECK_CHANNEL_ID")
karuta_id = "646937666251915264"
heart_bot_id = os.getenv("HEART_BOT_ID", "1274445226064220273")

# --- BIẾN TRẠNG THÁI ---
bots, acc_names = [], [
   "accphu1","accphu2","accphu3","accphu4","accphu5","accphu6","accphu7","accphu8","accphu9","accphu10","accphu11","accphu12",
]
main_bot_states = []
spam_enabled = False
spam_message, spam_delay = "", 10
last_spam_time = 0

# Các biến điều khiển
spam_thread = None
bots_lock = threading.Lock()
bot_active_states = {} # Dành cho các acc phụ

# --- HÀM LƯU VÀ TẢI CÀI ĐẶT ---
def save_settings():
    """Lưu cài đặt lên JSONBin.io"""
    api_key = os.getenv("JSONBIN_API_KEY")
    bin_id = os.getenv("JSONBIN_BIN_ID")
    if not api_key or not bin_id: return

    savable_main_bot_states = [{'enabled': s['enabled'], 'threshold': s['threshold']} for s in main_bot_states]
    settings = {
        'main_bot_states': savable_main_bot_states,
        'spam_enabled': spam_enabled, 'spam_message': spam_message, 'spam_delay': spam_delay,
        'bot_active_states': bot_active_states,
        'grab_channel_ids': grab_channel_ids,
        'spam_channel_ids': spam_channel_ids, # THAY ĐỔI
        'check_channel_id': check_channel_id,
    }
    headers = {'Content-Type': 'application/json', 'X-Master-Key': api_key}
    url = f"https://api.jsonbin.io/v3/b/{bin_id}"
    try:
        req = requests.put(url, json=settings, headers=headers, timeout=10)
        if req.status_code == 200:
            print("[Settings] Đã lưu cài đặt lên JSONBin.io.", flush=True)
        else:
            print(f"[Settings] Lỗi khi lưu cài đặt: {req.status_code} - {req.text}", flush=True)
    except Exception as e:
        print(f"[Settings] Exception khi lưu cài đặt: {e}", flush=True)

def load_settings():
    """Tải cài đặt từ JSONBin.io"""
    global main_bot_states, spam_enabled, spam_message, spam_delay
    global bot_active_states, grab_channel_ids, spam_channel_ids, check_channel_id

    api_key = os.getenv("JSONBIN_API_KEY")
    bin_id = os.getenv("JSONBIN_BIN_ID")
    if not api_key or not bin_id: return

    headers = {'X-Master-Key': api_key}
    url = f"https://api.jsonbin.io/v3/b/{bin_id}/latest"
    try:
        req = requests.get(url, headers=headers, timeout=10)
        if req.status_code == 200:
            settings = req.json().get("record", {})
            if settings:
                spam_enabled = settings.get('spam_enabled', False)
                spam_message = settings.get('spam_message', '')
                spam_delay = settings.get('spam_delay', 10)
                bot_active_states = settings.get('bot_active_states', {})
                grab_channel_ids = settings.get('grab_channel_ids', [])
                spam_channel_ids = settings.get('spam_channel_ids', []) # THAY ĐỔI
                check_channel_id = settings.get('check_channel_id', None)
                
                loaded_states = settings.get('main_bot_states', [])
                for i, state in enumerate(main_bot_states):
                    if i < len(loaded_states):
                        state['enabled'] = loaded_states[i].get('enabled', False)
                        state['threshold'] = loaded_states[i].get('threshold', 50)
                print("[Settings] Đã tải cài đặt từ JSONBin.io.", flush=True)
    except Exception as e:
        print(f"[Settings] Exception khi tải cài đặt: {e}", flush=True)

def periodic_save_loop():
    while True: time.sleep(300); save_settings()

# --- CÁC HÀM LOGIC BOT ---
def create_bot(token, bot_index=-1):
    """Tạo một instance bot với khả năng ghi log và xử lý lỗi kết nối tốt hơn."""
    # Bật log của discum để có thêm thông tin gỡ lỗi
    bot = discum.Client(token=token, log=True) 
    bot_type_str = f"(NODE {bot_index + 1})" if bot_index >= 0 else "(Sub)"

    @bot.gateway.command
    def on_ready(resp):
        if resp.event.ready:
            user_data = resp.raw.get("user", {})
            user_id = user_data.get("id")
            if user_id:
                print(f"✅ KẾT NỐI THÀNH CÔNG: {user_id} {bot_type_str}", flush=True)

    # THÊM MỚI: Hàm xử lý khi kết nối bị đóng, giúp nhận diện lỗi rõ ràng hơn
    @bot.gateway.command
    def on_close(resp):
        if resp.event.close:
            close_code = resp.raw.get('code')
            print(f"❌ KẾT NỐI ĐÃ ĐÓNG với bot {bot_type_str}! Mã lỗi: {close_code}", flush=True)
            if close_code == 4004:
                print(f"    --> NGUYÊN NHÂN: TOKEN KHÔNG HỢP LỆ hoặc đã hết hạn. Hãy kiểm tra lại token này.", flush=True)
            elif close_code in [4010, 4011, 4012, 4013, 4014]:
                print(f"    --> NGUYÊN NHÂN: Lỗi từ phía Discord ({close_code}). Thường là tạm thời, hãy thử lại sau.", flush=True)
            else:
                print(f"    --> Không xác định rõ nguyên nhân. Có thể do token sai hoặc kết nối mạng bị chặn.", flush=True)

    # Nếu là bot chính, gán handler auto-grab
    if bot_index >= 0:
        state = main_bot_states[bot_index]
        delay_configs = [[("1️⃣",0.5),("2️⃣",1.5),("3️⃣",2.2)],[("1️⃣",0.8),("2️⃣",1.8),("3️⃣",2.5)],[("1️⃣",1.0),("2️⃣",2.0),("3️⃣",2.7)]]
        reaction_config = delay_configs[bot_index % len(delay_configs)]
        def create_grab_handler(bot_instance, state_dict, bot_name, reaction_conf):
            def on_message(resp):
                if not resp.event.message: return
                msg = resp.parsed.auto(); channel_id_of_drop = msg.get("channel_id")
                if not (msg.get("author", {}).get("id") == karuta_id and channel_id_of_drop in grab_channel_ids and "is dropping" not in msg.get("content", "") and not msg.get("mentions", []) and state_dict['enabled']): return
                last_drop_msg_id = msg["id"]
                def read_heart_bot():
                    time.sleep(0.5)
                    try:
                        messages = bot_instance.getMessages(channel_id_of_drop, num=5).json()
                        for msg_item in messages:
                            if msg_item.get("author", {}).get("id") == heart_bot_id and "embeds" in msg_item and msg_item["embeds"]:
                                desc = msg_item["embeds"][0].get("description", "")
                                heart_numbers = [int(re.search(r'♡\s*(\d+)', line).group(1)) if re.search(r'♡\s*(\d+)', line) else 0 for line in desc.split('\n')[:3]]
                                if sum(heart_numbers) > 0 and max(heart_numbers) >= state_dict['threshold']:
                                    max_index = heart_numbers.index(max(heart_numbers))
                                    emoji, delay = reaction_conf[max_index]
                                    print(f"[{bot_name}] Chọn dòng {max_index+1} ({max(heart_numbers)} tim) -> Grab sau {delay}s tại kênh {channel_id_of_drop}", flush=True)
                                    def grab_and_check():
                                        try:
                                            bot_instance.addReaction(channel_id_of_drop, last_drop_msg_id, emoji)
                                            time.sleep(random.uniform(1.2, 1.8))
                                            if check_channel_id and check_channel_id.isdigit():
                                                bot_instance.sendMessage(check_channel_id, "kt b"); print(f"[{bot_name}] Đã gửi 'kt b' đến kênh check {check_channel_id}", flush=True)
                                        except Exception as e: print(f"Lỗi khi grab và check ({bot_name}): {e}", flush=True)
                                    threading.Timer(delay, lambda: threading.Thread(target=grab_and_check).start()).start()
                                break
                    except Exception as e: print(f"Lỗi đọc tim ({bot_name}): {e}", flush=True)
                threading.Thread(target=read_heart_bot).start()
            return on_message
        bot.gateway.command(create_grab_handler(bot, state, f"NODE {bot_index + 1}", reaction_config))
        
    threading.Thread(target=bot.gateway.run, daemon=True).start()
    return bot

def spam_loop():
    global last_spam_time
    while True:
        try:
            # THAY ĐỔI: Kiểm tra danh sách kênh spam
            if spam_enabled and spam_message and spam_channel_ids and (time.time() - last_spam_time) >= spam_delay:
                with bots_lock: bots_to_spam = [bot for i, bot in enumerate(bots) if bot and bot_active_states.get(f'sub_{i}', True)]
                
                print(f"Bắt đầu chu kỳ spam tới {len(spam_channel_ids)} kênh với {len(bots_to_spam)} bots...", flush=True)
                # THAY ĐỔI: Lặp qua từng kênh để spam
                for channel_id in spam_channel_ids:
                    if not spam_enabled: break
                    for idx, bot in enumerate(bots_to_spam):
                        if not spam_enabled: break
                        try:
                            acc_name = acc_names[idx] if idx < len(acc_names) else f"Sub {idx+1}"
                            bot.sendMessage(channel_id, spam_message)
                            print(f"[{acc_name}] đã spam: '{spam_message}' tới kênh {channel_id}", flush=True)
                            time.sleep(random.uniform(1.5, 2.5)) # Delay giữa mỗi tin nhắn
                        except Exception as e: print(f"Lỗi gửi spam từ [{acc_name}] tới kênh {channel_id}: {e}", flush=True)
                
                if spam_enabled: last_spam_time = time.time()
            time.sleep(1)
        except Exception as e: print(f"[ERROR in spam_loop] {e}", flush=True); time.sleep(5)

app = Flask(__name__)

# --- GIAO DIỆN WEB ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>K.D. - Control Panel</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700&family=Courier+Prime&family=Nosifer&display=swap" rel="stylesheet">
    <style>
        :root { --primary-bg: #0a0a0a; --panel-bg: #111111; --border-color: #333333; --blood-red: #8b0000; --necro-green: #228b22; --shadow-cyan: #008b8b; --text-primary: #f0f0f0; }
        body { font-family: 'Courier Prime', monospace; background: var(--primary-bg); color: var(--text-primary); margin: 0; padding: 20px; }
        .container { max-width: 1200px; margin: 0 auto; } h1 { font-family: 'Nosifer', cursive; text-align: center; color: var(--blood-red); }
        .main-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(380px, 1fr)); gap: 20px; }
        .panel { background: var(--panel-bg); border: 1px solid var(--border-color); border-radius: 10px; padding: 25px; box-shadow: 0 4px 15px rgba(0,0,0,0.5); }
        .panel h3 { font-family: 'Orbitron', monospace; margin-top: 0; border-bottom: 1px solid var(--border-color); padding-bottom: 10px; }
        .btn { background: #333; border: 1px solid var(--border-color); color: var(--text-primary); padding: 10px 15px; border-radius: 4px; cursor: pointer; font-family: 'Orbitron', monospace; width: 100%; text-transform: uppercase; }
        .btn-blood { border-color: var(--blood-red); color: var(--blood-red); } .btn-blood:hover { background: var(--blood-red); color: var(--text-primary); }
        .btn-necro { border-color: var(--necro-green); color: var(--necro-green); } .btn-necro:hover { background: var(--necro-green); color: var(--text-primary); }
        .input-group { display: flex; gap: 10px; margin-bottom: 15px; align-items: center; }
        .input-group input, .input-group textarea { flex-grow: 1; background: #000; border: 1px solid var(--border-color); color: var(--text-primary); padding: 10px; border-radius: 4px; }
        .grab-section, .spam-section { margin-bottom: 15px; padding: 15px; background: rgba(0,0,0,0.2); border: 1px solid var(--border-color); border-radius: 8px; }
        .grab-section h4, .spam-section h4 { margin: 0 0 10px 0; display: flex; justify-content: space-between; align-items: center; font-family: 'Orbitron'; }
        .status-badge { padding: 4px 10px; border-radius: 15px; font-size: 0.8em; } .status-badge.active { background: var(--necro-green); } .status-badge.inactive { background: var(--blood-red); }
        .msg-status { text-align: center; color: var(--shadow-cyan); padding: 10px; border: 1px dashed var(--border-color); border-radius: 4px; margin-bottom: 20px; background: rgba(0, 139, 139, 0.1); display: none; }
        hr.divider { border: 0; height: 1px; background-color: var(--border-color); margin: 20px 0; }
        .channel-list { list-style: none; padding: 0; max-height: 120px; overflow-y: auto; background: rgba(0,0,0,0.2); border: 1px solid var(--border-color); border-radius: 4px; padding: 10px; margin-top: 10px; }
        .channel-list li { display: flex; justify-content: space-between; align-items: center; padding: 5px; border-bottom: 1px solid var(--border-color); }
        .channel-list li:last-child { border-bottom: none; }
        .btn-delete { background: none; border: none; color: var(--blood-red); cursor: pointer; font-size: 1.2em; }
    </style>
</head>
<body>
    <div class="container">
        <h1><i class="fas fa-skull-crossbones"></i> Control Panel <i class="fas fa-skull-crossbones"></i></h1>
        <div id="msg-status-container" class="msg-status"></div>
        <div class="main-grid">
            <div class="panel">
                <h3><i class="fas fa-crosshairs"></i> Soul Harvest (Auto Grab)</h3>
                <div id="harvest-nodes-container"></div> <hr class="divider">
                <div class="input-group">
                    <input type="text" id="check-channel-id" placeholder="ID Kênh Nhắn 'kt b'...">
                    <button type="button" id="save-check-channel-btn" class="btn btn-necro" style="width: auto;">Lưu</button>
                </div>
            </div>
            <div class="panel">
                <h3><i class="fas fa-broadcast-tower"></i> Shadow Broadcast (Auto Spam)</h3>
                <div class="spam-section">
                    <h4>AUTO SPAM <span id="spam-status-badge"></span></h4>
                    <div class="input-group"><textarea id="spam-message" rows="2" placeholder="Nội dung spam..."></textarea></div>
                    <div class="input-group"><input type="number" id="spam-delay" placeholder="Delay (s)"><button type="button" id="spam-toggle-btn" class="btn"></button></div>
                </div>
            </div>
            <div class="panel">
                <h3><i class="fas fa-server"></i> Quản Lý Kênh</h3>
                <div class="input-group"><input type="text" id="new-grab-channel-id" placeholder="ID Kênh Nhặt Thẻ..."><button type="button" data-type="grab" class="btn-add-channel btn btn-necro" style="width: auto;">Thêm</button></div>
                <ul id="grab-channel-list" class="channel-list"></ul> <hr class="divider">
                <div class="input-group"><input type="text" id="new-spam-channel-id" placeholder="ID Kênh Spam..."><button type="button" data-type="spam" class="btn-add-channel btn btn-necro" style="width: auto;">Thêm</button></div>
                <ul id="spam-channel-list" class="channel-list"></ul>
            </div>
        </div>
    </div>
<script>
    document.addEventListener('DOMContentLoaded', function () {
        const msgStatusContainer = document.getElementById('msg-status-container');
        function showStatusMessage(message) { if (!message) return; msgStatusContainer.textContent = message; msgStatusContainer.style.display = 'block'; setTimeout(() => { msgStatusContainer.style.display = 'none'; }, 4000); }
        async function postData(url = '', data = {}) { try { const response = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) }); const result = await response.json(); showStatusMessage(result.message); setTimeout(fetchStatus, 500); return result; } catch (error) { showStatusMessage('Lỗi giao tiếp với server.'); } }
        function updateElement(id, { textContent, className, value }) { const el = document.getElementById(id); if (!el) return; if (textContent !== undefined) el.textContent = textContent; if (className !== undefined) el.className = className; if (value !== undefined && document.activeElement.id !== id) { el.value = value; } }
        
        function renderChannelList(listId, channelIds, deleteApi) {
            const container = document.getElementById(listId); container.innerHTML = '';
            if (channelIds && channelIds.length > 0) {
                channelIds.forEach(id => { if (!id) return; const li = document.createElement('li'); li.innerHTML = `<span>${id}</span><button class="btn-delete" data-id="${id}" data-api="${deleteApi}" title="Xóa"><i class="fas fa-trash-alt"></i></button>`; container.appendChild(li); });
            } else { container.innerHTML = '<li>Chưa có kênh nào.</li>'; }
        }

        async function fetchStatus() {
            try {
                const response = await fetch('/status'); const data = await response.json();
                const harvestContainer = document.getElementById('harvest-nodes-container'); harvestContainer.innerHTML = '';
                data.main_bot_states.forEach((state, index) => {
                    const nodeDiv = document.createElement('div'); nodeDiv.className = 'grab-section';
                    const statusText = state.enabled ? 'ON' : 'OFF'; const statusClass = state.enabled ? 'active' : 'inactive';
                    const actionText = state.enabled ? 'DISABLE' : 'ENABLE'; const buttonClass = state.enabled ? 'btn-blood' : 'btn-necro';
                    nodeDiv.innerHTML = `<h4>NODE ${index + 1} <span class="status-badge ${statusClass}">${statusText}</span></h4><div class="input-group"><input type="number" id="heart-threshold-${index}" value="${state.threshold}" min="0"><button type="button" data-node-index="${index}" class="btn ${buttonClass} harvest-toggle-btn">${actionText}</button></div>`;
                    harvestContainer.appendChild(nodeDiv);
                });
                updateElement('spam-toggle-btn', { textContent: `${data.ui.spam_action} SPAM`, className: `btn ${data.ui.spam_button_class}`});
                updateElement('spam-status-badge', { textContent: data.spam_enabled ? 'ON' : 'OFF', className: `status-badge ${data.spam_enabled ? 'active' : 'inactive'}`});
                updateElement('spam-message', { value: data.spam_message }); updateElement('spam-delay', { value: data.spam_delay });
                updateElement('check-channel-id', { value: data.check_channel_id });
                renderChannelList('grab-channel-list', data.grab_channel_ids, '/api/delete_grab_channel');
                renderChannelList('spam-channel-list', data.spam_channel_ids, '/api/delete_spam_channel');
            } catch (error) { console.error('Error fetching status:', error); }
        }
        setInterval(fetchStatus, 3000); fetchStatus();
        
        document.body.addEventListener('click', e => {
            if (e.target.classList.contains('harvest-toggle-btn')) {
                const nodeIndex = e.target.dataset.nodeIndex; const threshold = document.getElementById(`heart-threshold-${nodeIndex}`).value;
                postData('/api/harvest_toggle', { node_index: nodeIndex, threshold: threshold });
            }
            if (e.target.id === 'spam-toggle-btn') { postData('/api/spam_toggle', { message: document.getElementById('spam-message').value, delay: document.getElementById('spam-delay').value }); }
            if (e.target.id === 'save-check-channel-btn') { postData('/api/save_check_channel', { channel_id: document.getElementById('check-channel-id').value }); }
            if (e.target.classList.contains('btn-add-channel')) {
                const type = e.target.dataset.type; const inputId = `new-${type}-channel-id`; const channelId = document.getElementById(inputId).value.trim();
                if (channelId) { postData(`/api/add_${type}_channel`, { channel_id: channelId }); document.getElementById(inputId).value = ''; }
            }
            if (e.target.closest('.btn-delete')) {
                const btn = e.target.closest('.btn-delete'); const id = btn.dataset.id; const api = btn.dataset.api;
                if (id && api && confirm(`Bạn có chắc muốn xóa kênh ${id}?`)) { postData(api, { channel_id: id }); }
            }
        });
    });
</script>
</body>
</html>
"""

# --- FLASK ROUTES & API ---
@app.route("/")
def index(): return render_template_string(HTML_TEMPLATE)
@app.route("/status")
def status():
    return jsonify({
        'main_bot_states': [{'enabled': s['enabled'], 'threshold': s['threshold']} for s in main_bot_states],
        'spam_enabled': spam_enabled, 'spam_message': spam_message, 'spam_delay': spam_delay,
        'spam_channel_ids': spam_channel_ids, 'grab_channel_ids': grab_channel_ids, 'check_channel_id': check_channel_id,
        'ui': {"spam_action": "DISABLE" if spam_enabled else "ENABLE", "spam_button_class": "btn-blood" if spam_enabled else "btn-necro"}
    })
@app.route("/api/harvest_toggle", methods=['POST'])
def api_harvest_toggle():
    data = request.get_json(); node_index = int(data.get('node_index')); threshold = int(data.get('threshold', 50))
    if 0 <= node_index < len(main_bot_states):
        state = main_bot_states[node_index]; state['enabled'] = not state['enabled']; state['threshold'] = threshold
        save_settings(); return jsonify({'status': 'success', 'message': f"Node {node_index + 1} đã {'BẬT' if state['enabled'] else 'TẮT'}"})
    return jsonify({'status': 'error', 'message': 'Node không hợp lệ'})
@app.route("/api/spam_toggle", methods=['POST'])
def api_spam_toggle():
    global spam_enabled, spam_message, spam_delay, spam_thread, last_spam_time
    data = request.get_json(); spam_message = data.get("message", "").strip(); spam_delay = int(data.get("delay", 10))
    if not spam_enabled and spam_message and spam_channel_ids:
        spam_enabled = True; last_spam_time = time.time(); msg = "Auto Spam ĐÃ BẬT."
        if spam_thread is None or not spam_thread.is_alive():
            spam_thread = threading.Thread(target=spam_loop, daemon=True); spam_thread.start()
    else: spam_enabled = False; msg = "Auto Spam ĐÃ TẮT."
    save_settings(); return jsonify({'status': 'success', 'message': msg})
@app.route("/api/save_check_channel", methods=['POST'])
def api_save_check_channel():
    global check_channel_id; new_id = request.get_json().get('channel_id', '').strip()
    if new_id and new_id.isdigit(): check_channel_id = new_id; msg = f'Đã lưu kênh check: {new_id}'
    else: check_channel_id = None; msg = 'Đã xóa kênh check.'
    save_settings(); return jsonify({'status': 'success', 'message': msg})
@app.route("/api/add_grab_channel", methods=['POST'])
def api_add_grab_channel():
    channel_id = request.get_json().get('channel_id');
    if channel_id and channel_id.isdigit():
        if channel_id not in grab_channel_ids: grab_channel_ids.append(channel_id); save_settings(); return jsonify({'status': 'success', 'message': f'Đã thêm kênh nhặt thẻ.'})
        return jsonify({'status': 'error', 'message': f'Kênh đã tồn tại.'})
    return jsonify({'status': 'error', 'message': 'ID kênh không hợp lệ.'})
@app.route("/api/delete_grab_channel", methods=['POST'])
def api_delete_grab_channel():
    channel_id = request.get_json().get('channel_id')
    if channel_id in grab_channel_ids: grab_channel_ids.remove(channel_id); save_settings(); return jsonify({'status': 'success', 'message': f'Đã xóa kênh nhặt thẻ.'})
    return jsonify({'status': 'error', 'message': 'Không tìm thấy kênh.'})
@app.route("/api/add_spam_channel", methods=['POST'])
def api_add_spam_channel():
    channel_id = request.get_json().get('channel_id');
    if channel_id and channel_id.isdigit():
        if channel_id not in spam_channel_ids: spam_channel_ids.append(channel_id); save_settings(); return jsonify({'status': 'success', 'message': f'Đã thêm kênh spam.'})
        return jsonify({'status': 'error', 'message': f'Kênh đã tồn tại.'})
    return jsonify({'status': 'error', 'message': 'ID kênh không hợp lệ.'})
@app.route("/api/delete_spam_channel", methods=['POST'])
def api_delete_spam_channel():
    channel_id = request.get_json().get('channel_id')
    if channel_id in spam_channel_ids: spam_channel_ids.remove(channel_id); save_settings(); return jsonify({'status': 'success', 'message': f'Đã xóa kênh spam.'})
    return jsonify({'status': 'error', 'message': 'Không tìm thấy kênh.'})

# --- MAIN EXECUTION ---
if __name__ == "__main__":
    for i, token in enumerate(main_tokens):
        if token.strip(): main_bot_states.append({'token': token.strip(), 'bot_instance': None, 'enabled': False, 'threshold': 50})
    load_settings()
    grab_channel_ids = [cid for cid in grab_channel_ids if cid]
    spam_channel_ids = [cid for cid in spam_channel_ids if cid]
    print("--- KHỞI TẠO BOT ---", flush=True)
    for i, state in enumerate(main_bot_states): state['bot_instance'] = create_bot(state['token'], bot_index=i)
    for i, token in enumerate(tokens):
        if token.strip(): bots.append(create_bot(token.strip())); bot_active_states.setdefault(f'sub_{i}', True)
    print("--- KHỞI TẠO CÁC LUỒNG NỀN ---", flush=True)
    threading.Thread(target=periodic_save_loop, daemon=True).start()
    spam_thread = threading.Thread(target=spam_loop, daemon=True); spam_thread.start()
    port = int(os.environ.get("PORT", 10000))
    print(f"--- WEB SERVER ĐANG CHẠY TẠI http://0.0.0.0:{port} ---", flush=True)
    from waitress import serve
    serve(app, host="0.0.0.0", port=port)
