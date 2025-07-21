# PHIÊN BẢN ĐÃ TÁI CẤU TRÚC - LINH HOẠT VÀ MỞ RỘNG
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
# Tải token từ file .env, phân tách bằng dấu phẩy
main_tokens = [token.strip() for token in os.getenv("MAIN_TOKENS", "").split(",") if token.strip()]
sub_tokens = [token.strip() for token in os.getenv("SUB_TOKENS", "").split(",") if token.strip()]

# Các biến ID cố định
karuta_id = "646937666251915264"
heart_bot_id = os.getenv("HEART_BOT_ID", "1274445226064220273")
other_channel_id = os.getenv("OTHER_CHANNEL_ID") # Giữ lại cho các chức năng cũ nếu cần

# --- BIẾN TRẠNG THÁI TOÀN CỤC (Sẽ được quản lý bởi load/save settings) ---
# Danh sách các đối tượng bot
main_bots = []
sub_bots = []

# Danh sách các channel ID (sẽ được quản lý trên web)
grab_channel_ids = []
ktb_channel_ids = []
spam_channel_ids = []

# Cấu hình cho từng tài khoản chính (sẽ được quản lý trên web)
# Ví dụ: {0: {'enabled': True, 'threshold': 50, 'name': 'Main 0'}, 1: ...}
main_bot_settings = {}

# Trạng thái các chức năng khác
spam_enabled = False
spam_message = ""
spam_delay = 10

# Các biến điều khiển và timestamp
bots_lock = threading.Lock()
spam_thread = None
last_spam_time = 0
server_start_time = time.time()

# --- HÀM LƯU VÀ TẢI CÀI ĐẶT ---
def save_settings():
    """Lưu các cài đặt quan trọng lên JSONBin.io"""
    api_key = os.getenv("JSONBIN_API_KEY")
    bin_id = os.getenv("JSONBIN_BIN_ID")
    if not api_key or not bin_id:
        return

    settings = {
        'main_bot_settings': main_bot_settings,
        'grab_channel_ids': grab_channel_ids,
        'ktb_channel_ids': ktb_channel_ids,
        'spam_channel_ids': spam_channel_ids,
        'spam_enabled': spam_enabled,
        'spam_message': spam_message,
        'spam_delay': spam_delay,
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
    """Tải cài đặt từ JSONBin.io khi khởi động"""
    global main_bot_settings, grab_channel_ids, ktb_channel_ids, spam_channel_ids
    global spam_enabled, spam_message, spam_delay

    api_key = os.getenv("JSONBIN_API_KEY")
    bin_id = os.getenv("JSONBIN_BIN_ID")
    if not api_key or not bin_id:
        print("[Settings] Thiếu API Key hoặc Bin ID. Sử dụng cài đặt mặc định.", flush=True)
        return

    headers = {'X-Master-Key': api_key}
    url = f"https://api.jsonbin.io/v3/b/{bin_id}/latest"
    try:
        req = requests.get(url, headers=headers, timeout=10)
        if req.status_code == 200:
            settings = req.json().get("record", {})
            if settings:
                main_bot_settings = settings.get('main_bot_settings', {})
                # Chuyển đổi key từ string (JSON) về integer
                main_bot_settings = {int(k): v for k, v in main_bot_settings.items()}

                grab_channel_ids = settings.get('grab_channel_ids', [])
                ktb_channel_ids = settings.get('ktb_channel_ids', [])
                spam_channel_ids = settings.get('spam_channel_ids', [])
                spam_enabled = settings.get('spam_enabled', False)
                spam_message = settings.get('spam_message', "")
                spam_delay = settings.get('spam_delay', 10)
                print("[Settings] Đã tải cài đặt từ JSONBin.io.", flush=True)
            else:
                print("[Settings] JSONBin rỗng, bắt đầu với cài đặt mặc định.", flush=True)
                save_settings() # Lưu cài đặt mặc định lên
        else:
            print(f"[Settings] Lỗi khi tải cài đặt: {req.status_code} - {req.text}", flush=True)
    except Exception as e:
        print(f"[Settings] Exception khi tải cài đặt: {e}", flush=True)

# --- LOGIC BOT ---
def create_bot(token, bot_index, is_main=False):
    """Tạo một instance bot, gán logic dựa trên loại bot (main/sub)."""
    bot = discum.Client(token=token, log=False)

    @bot.gateway.command
    def on_ready(resp):
        if resp.event.ready:
            user = resp.raw['user']
            bot_type = "Main" if is_main else "Sub"
            print(f"Đã đăng nhập: {user['username']} ({user['id']}) - Loại: {bot_type} #{bot_index}", flush=True)

    if is_main:
        @bot.gateway.command
        def on_message_main(resp):
            # Lấy cài đặt cho bot này từ biến toàn cục
            settings = main_bot_settings.get(bot_index, {'enabled': False, 'threshold': 50})

            # Nếu bot không được bật thì không làm gì cả
            if not settings.get('enabled'):
                return

            if resp.event.message:
                msg = resp.parsed.auto()
                # KIỂM TRA:
                # 1. Tác giả là Karuta
                # 2. Channel ID nằm trong danh sách kênh để nhặt
                # 3. Không phải tin nhắn "is dropping" (là tin nhắn drop thật)
                # 4. Không có mention (thường là drop cho người khác)
                if (msg.get("author", {}).get("id") == karuta_id and
                    msg.get("channel_id") in grab_channel_ids and
                    "is dropping" not in msg.get("content", "") and
                    not msg.get("mentions", [])):

                    last_drop_msg_id = msg["id"]
                    drop_channel_id = msg["channel_id"]

                    def read_heart_and_grab():
                        time.sleep(0.7) # Chờ bot tim phản hồi
                        try:
                            messages = bot.getMessages(drop_channel_id, num=5).json()
                            for msg_item in messages:
                                if msg_item.get("author", {}).get("id") == heart_bot_id and "embeds" in msg_item:
                                    desc = msg_item["embeds"][0].get("description", "")
                                    lines = desc.split('\n')
                                    heart_numbers = [0, 0, 0]
                                    for i, line in enumerate(lines[:3]):
                                        match = re.search(r'♡\s*(\d+)', line)
                                        if match:
                                            heart_numbers[i] = int(match.group(1))

                                    max_num = max(heart_numbers)
                                    if sum(heart_numbers) > 0 and max_num >= settings.get('threshold', 50):
                                        max_index = heart_numbers.index(max_num)
                                        emoji, delay = [("1️⃣", 0.5), ("2️⃣", 1.5), ("3️⃣", 2.2)][max_index]
                                        final_delay = delay + random.uniform(-0.2, 0.2)

                                        print(f"[Main Bot #{bot_index}] Chọn dòng {max_index+1} ({max_num} tim). Nhấn {emoji} sau {final_delay:.2f}s", flush=True)

                                        def grab_action():
                                            bot.addReaction(drop_channel_id, last_drop_msg_id, emoji)
                                            print(f"[Main Bot #{bot_index}] ĐÃ NHẤN REACTION.", flush=True)
                                            time.sleep(2)
                                            # Gửi "kt b" đến TẤT CẢ các kênh trong danh sách ktb_channel_ids
                                            for ktb_ch_id in ktb_channel_ids:
                                                if ktb_ch_id:
                                                    bot.sendMessage(ktb_ch_id, "kt b")
                                                    time.sleep(0.5)
                                            print(f"[Main Bot #{bot_index}] Đã gửi 'kt b' đến các kênh.", flush=True)

                                        threading.Timer(final_delay, grab_action).start()
                                    break # Đã tìm thấy và xử lý tin nhắn bot tim
                        except Exception as e:
                            print(f"[Main Bot #{bot_index}] Lỗi khi đọc tim: {e}", flush=True)

                    threading.Thread(target=read_heart_and_grab).start()

    threading.Thread(target=bot.gateway.run, daemon=True).start()
    return bot

# --- VÒNG LẶP NỀN ---
def spam_loop():
    """Vòng lặp gửi tin nhắn spam từ các tài khoản phụ."""
    global last_spam_time
    while True:
        try:
            if spam_enabled and spam_message and (time.time() - last_spam_time) >= spam_delay:
                with bots_lock:
                    bots_to_spam = list(sub_bots) # Tạo bản sao để tránh race condition

                for i, bot in enumerate(bots_to_spam):
                    if not spam_enabled: break
                    try:
                        # Gửi tin nhắn đến TẤT CẢ các kênh trong danh sách spam
                        for channel_id in spam_channel_ids:
                            if channel_id:
                                bot.sendMessage(channel_id, spam_message)
                                print(f"[Sub Bot #{i}] Đã spam '{spam_message}' đến kênh {channel_id}", flush=True)
                                time.sleep(1) # Delay giữa các kênh
                        time.sleep(2) # Delay giữa các bot
                    except Exception as e:
                        print(f"[Sub Bot #{i}] Lỗi gửi spam: {e}", flush=True)

                if spam_enabled:
                    last_spam_time = time.time()
            time.sleep(1)
        except Exception as e:
            print(f"[ERROR in spam_loop] {e}", flush=True)
            time.sleep(1)

def periodic_save_loop():
    """Tự động lưu cài đặt 5 phút một lần."""
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
    <title>Bot Controller</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700&family=Courier+Prime&display=swap" rel="stylesheet">
    <style>
        body { font-family: 'Courier Prime', monospace; background-color: #0d1117; color: #c9d1d9; margin: 0; padding: 20px; }
        .container { max-width: 1400px; margin: auto; }
        .header { text-align: center; margin-bottom: 20px; }
        .header h1 { font-family: 'Orbitron', sans-serif; color: #58a6ff; }
        .grid-container { display: grid; grid-template-columns: repeat(auto-fit, minmax(400px, 1fr)); gap: 20px; }
        .panel { background-color: #161b22; border: 1px solid #30363d; border-radius: 6px; padding: 20px; }
        .panel h2 { margin-top: 0; border-bottom: 1px solid #30363d; padding-bottom: 10px; font-family: 'Orbitron', sans-serif; font-size: 1.2em; }
        .input-group { margin-bottom: 15px; display: flex; flex-direction: column; }
        .input-group label { margin-bottom: 5px; font-weight: bold; color: #8b949e; }
        .input-group input, .input-group textarea { background-color: #0d1117; border: 1px solid #30363d; color: #c9d1d9; padding: 8px 12px; border-radius: 6px; font-family: inherit; }
        .btn { background-color: #238636; color: white; border: 1px solid #2ea043; padding: 10px 16px; border-radius: 6px; cursor: pointer; font-weight: bold; transition: background-color 0.2s; }
        .btn:hover { background-color: #2ea043; }
        .btn-danger { background-color: #da3633; border-color: #f85149; }
        .btn-danger:hover { background-color: #f85149; }
        .btn-secondary { background-color: #21262d; border-color: #30363d;}
        .btn-secondary:hover { border-color: #8b949e; }
        .status-badge { padding: 4px 8px; border-radius: 10px; font-size: 0.8em; text-transform: uppercase; }
        .status-badge.active { background-color: #238636; color: white; }
        .status-badge.inactive { background-color: #da3633; color: white; }
        .main-bot-controls { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
        .main-bot-controls .input-group { flex-grow: 1; margin-bottom: 0; }
        .msg-status { text-align: center; color: #58a6ff; padding: 12px; border: 1px dashed #30363d; border-radius: 6px; margin-bottom: 20px; display: none; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1><i class="fas fa-robot"></i> Bot Control Panel</h1>
        </div>
        <div id="msg-status-container" class="msg-status"></div>

        <div class="grid-container">
            <!-- Panel điều khiển các tài khoản chính -->
            <div class="panel">
                <h2><i class="fas fa-crosshairs"></i> Main Accounts - Auto Grab</h2>
                <div id="main-bots-container">
                    <!-- Các control cho bot chính sẽ được render ở đây bằng JS -->
                </div>
            </div>

            <!-- Panel điều khiển spam -->
            <div class="panel">
                <h2><i class="fas fa-broadcast-tower"></i> Sub Accounts - Auto Spam</h2>
                <div class="input-group">
                    <label for="spam-message">Nội dung Spam</label>
                    <textarea id="spam-message" rows="3">{{ spam_message }}</textarea>
                </div>
                <div class="input-group">
                    <label for="spam-delay">Delay giữa các chu kỳ (giây)</label>
                    <input type="number" id="spam-delay" value="{{ spam_delay }}">
                </div>
                <button id="spam-toggle-btn" class="btn {{ 'btn-danger' if spam_enabled else '' }}">
                    {{ 'TẮT SPAM' if spam_enabled else 'BẬT SPAM' }}
                </button>
                <span id="spam-status-badge" class="status-badge {{ 'active' if spam_enabled else 'inactive' }}" style="margin-left: 10px;">
                    {{ 'ON' if spam_enabled else 'OFF' }}
                </span>
            </div>

            <!-- Panel cấu hình Channel ID -->
            <div class="panel" style="grid-column: 1 / -1;">
                <h2><i class="fas fa-network-wired"></i> Channel ID Configuration</h2>
                <div class="grid-container" style="grid-template-columns: 1fr 1fr 1fr;">
                    <div class="input-group">
                        <label for="grab-channels-input">Grab Channel IDs (cách nhau bằng dấu phẩy)</label>
                        <textarea id="grab-channels-input" rows="4">{{ grab_channel_ids|join(',') }}</textarea>
                    </div>
                    <div class="input-group">
                        <label for="ktb-channels-input">KTB Channel IDs (cách nhau bằng dấu phẩy)</label>
                        <textarea id="ktb-channels-input" rows="4">{{ ktb_channel_ids|join(',') }}</textarea>
                    </div>
                    <div class="input-group">
                        <label for="spam-channels-input">Spam Channel IDs (cách nhau bằng dấu phẩy)</label>
                        <textarea id="spam-channels-input" rows="4">{{ spam_channel_ids|join(',') }}</textarea>
                    </div>
                </div>
                <button id="save-channels-btn" class="btn" style="width: 100%; margin-top: 10px;">Lưu Cấu Hình Kênh</button>
            </div>
        </div>
    </div>

<script>
document.addEventListener('DOMContentLoaded', function () {
    const msgStatusContainer = document.getElementById('msg-status-container');

    function showStatusMessage(message, isError = false) {
        if (!message) return;
        msgStatusContainer.textContent = message;
        msgStatusContainer.style.color = isError ? '#f85149' : '#58a6ff';
        msgStatusContainer.style.display = 'block';
        setTimeout(() => { msgStatusContainer.style.display = 'none'; }, 4000);
    }

    async function postData(url = '', data = {}) {
        try {
            const response = await fetch(url, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });
            const result = await response.json();
            if (result.message) {
                showStatusMessage(result.message);
            }
            fetchStatus(); // Cập nhật lại giao diện sau mỗi hành động
            return result;
        } catch (error) {
            console.error('Error:', error);
            showStatusMessage('Lỗi giao tiếp với server.', true);
        }
    }

    function renderMainBots(settings) {
        const container = document.getElementById('main-bots-container');
        container.innerHTML = ''; // Xóa nội dung cũ
        if (Object.keys(settings).length === 0) {
            container.innerHTML = '<p>Không tìm thấy tài khoản chính nào. Hãy thêm token vào file .env.</p>';
            return;
        }
        // Sắp xếp các bot theo index
        const sortedIndices = Object.keys(settings).sort((a, b) => a - b);

        for (const index of sortedIndices) {
            const botSetting = settings[index];
            const botDiv = document.createElement('div');
            botDiv.className = 'input-group';
            botDiv.innerHTML = `
                <label for="heart-threshold-${index}">${botSetting.name || `Main Bot #${index}`}</label>
                <div class="main-bot-controls">
                    <div class="input-group">
                        <input type="number" id="heart-threshold-${index}" value="${botSetting.threshold || 50}" title="Ngưỡng tim">
                    </div>
                    <button data-index="${index}" class="btn btn-toggle-grab ${botSetting.enabled ? 'btn-danger' : ''}">
                        ${botSetting.enabled ? 'TẮT' : 'BẬT'}
                    </button>
                    <span class="status-badge ${botSetting.enabled ? 'active' : 'inactive'}">
                        ${botSetting.enabled ? 'ON' : 'OFF'}
                    </span>
                </div>
            `;
            container.appendChild(botDiv);
        }
    }

    async function fetchStatus() {
        try {
            const response = await fetch('/status');
            const data = await response.json();

            // Render main bots
            renderMainBots(data.main_bot_settings);

            // Update spam controls
            document.getElementById('spam-message').value = data.spam_message;
            document.getElementById('spam-delay').value = data.spam_delay;
            const spamBtn = document.getElementById('spam-toggle-btn');
            const spamBadge = document.getElementById('spam-status-badge');
            spamBtn.textContent = data.spam_enabled ? 'TẮT SPAM' : 'BẬT SPAM';
            spamBtn.className = `btn ${data.spam_enabled ? 'btn-danger' : ''}`;
            spamBadge.textContent = data.spam_enabled ? 'ON' : 'OFF';
            spamBadge.className = `status-badge ${data.spam_enabled ? 'active' : 'inactive'}`;

            // Update channel IDs
            document.getElementById('grab-channels-input').value = data.grab_channel_ids.join(',');
            document.getElementById('ktb-channels-input').value = data.ktb_channel_ids.join(',');
            document.getElementById('spam-channels-input').value = data.spam_channel_ids.join(',');

        } catch (error) {
            console.error('Error fetching status:', error);
        }
    }

    // --- EVENT LISTENERS ---

    // Listener cho các nút Bật/Tắt của từng bot chính (sử dụng event delegation)
    document.getElementById('main-bots-container').addEventListener('click', function(e) {
        if (e.target && e.target.classList.contains('btn-toggle-grab')) {
            const index = e.target.dataset.index;
            const threshold = document.getElementById(`heart-threshold-${index}`).value;
            postData('/api/main_bot_toggle', { index: parseInt(index), threshold: parseInt(threshold) });
        }
    });

    // Listener cho nút Spam
    document.getElementById('spam-toggle-btn').addEventListener('click', function() {
        postData('/api/spam_toggle', {
            message: document.getElementById('spam-message').value,
            delay: parseInt(document.getElementById('spam-delay').value)
        });
    });

    // Listener cho nút lưu cấu hình kênh
    document.getElementById('save-channels-btn').addEventListener('click', function() {
        postData('/api/update_channels', {
            grab_channels: document.getElementById('grab-channels-input').value,
            ktb_channels: document.getElementById('ktb-channels-input').value,
            spam_channels: document.getElementById('spam-channels-input').value
        });
    });

    // Tải trạng thái lần đầu và cập nhật mỗi 5 giây
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
    """Render giao diện web chính."""
    return render_template_string(HTML_TEMPLATE,
        main_bot_settings=main_bot_settings,
        spam_enabled=spam_enabled,
        spam_message=spam_message,
        spam_delay=spam_delay,
        grab_channel_ids=grab_channel_ids,
        ktb_channel_ids=ktb_channel_ids,
        spam_channel_ids=spam_channel_ids
    )

@app.route("/status")
def status():
    """Cung cấp trạng thái hiện tại của bot dưới dạng JSON cho frontend."""
    return jsonify({
        'main_bot_settings': main_bot_settings,
        'spam_enabled': spam_enabled,
        'spam_message': spam_message,
        'spam_delay': spam_delay,
        'grab_channel_ids': grab_channel_ids,
        'ktb_channel_ids': ktb_channel_ids,
        'spam_channel_ids': spam_channel_ids,
        'server_start_time': server_start_time,
    })

@app.route("/api/main_bot_toggle", methods=['POST'])
def api_main_bot_toggle():
    """API để bật/tắt và cập nhật ngưỡng tim cho một bot chính."""
    data = request.get_json()
    index = data.get('index')
    threshold = data.get('threshold')

    if index in main_bot_settings:
        # Đảo ngược trạng thái enabled
        main_bot_settings[index]['enabled'] = not main_bot_settings[index].get('enabled', False)
        main_bot_settings[index]['threshold'] = threshold
        state = "BẬT" if main_bot_settings[index]['enabled'] else "TẮT"
        msg = f"{main_bot_settings[index].get('name', f'Main Bot #{index}')} đã được {state}."
        save_settings()
    else:
        msg = "Lỗi: Không tìm thấy bot."
    return jsonify({'status': 'success', 'message': msg})

@app.route("/api/spam_toggle", methods=['POST'])
def api_spam_toggle():
    """API để bật/tắt chức năng spam."""
    global spam_enabled, spam_message, spam_delay, spam_thread, last_spam_time
    data = request.get_json()

    spam_enabled = not spam_enabled
    if spam_enabled:
        spam_message = data.get("message", "").strip()
        spam_delay = data.get("delay", 10)
        if not spam_message:
            spam_enabled = False # Không bật spam nếu không có tin nhắn
            return jsonify({'status': 'error', 'message': 'Nội dung spam không được để trống.'})

        last_spam_time = time.time()
        # Khởi động luồng spam nếu nó chưa chạy
        if spam_thread is None or not spam_thread.is_alive():
            spam_thread = threading.Thread(target=spam_loop, daemon=True)
            spam_thread.start()
        msg = "Chức năng spam đã được BẬT."
    else:
        msg = "Chức năng spam đã được TẮT."

    save_settings()
    return jsonify({'status': 'success', 'message': msg})

@app.route("/api/update_channels", methods=['POST'])
def api_update_channels():
    """API để cập nhật và lưu danh sách các channel ID."""
    global grab_channel_ids, ktb_channel_ids, spam_channel_ids
    data = request.get_json()

    # Cập nhật và lọc bỏ các giá trị rỗng
    grab_channel_ids = [ch_id.strip() for ch_id in data.get('grab_channels', '').split(',') if ch_id.strip()]
    ktb_channel_ids = [ch_id.strip() for ch_id in data.get('ktb_channels', '').split(',') if ch_id.strip()]
    spam_channel_ids = [ch_id.strip() for ch_id in data.get('spam_channels', '').split(',') if ch_id.strip()]

    save_settings()
    return jsonify({'status': 'success', 'message': 'Đã cập nhật và lưu cấu hình kênh thành công.'})


# --- KHỞI ĐỘNG ---
if __name__ == "__main__":
    load_settings() # Tải cài đặt đã lưu trước

    print("Đang khởi tạo các bot...", flush=True)
    with bots_lock:
        # Khởi tạo các tài khoản chính
        for i, token in enumerate(main_tokens):
            main_bots.append(create_bot(token, bot_index=i, is_main=True))
            # Khởi tạo cài đặt mặc định nếu chưa có
            if i not in main_bot_settings:
                main_bot_settings[i] = {'enabled': False, 'threshold': 50, 'name': f'Main Account #{i+1}'}
            elif 'name' not in main_bot_settings[i]: # Đảm bảo có tên
                 main_bot_settings[i]['name'] = f'Main Account #{i+1}'


        # Khởi tạo các tài khoản phụ
        for i, token in enumerate(sub_tokens):
            sub_bots.append(create_bot(token, bot_index=i, is_main=False))

    print("Đang khởi tạo các luồng nền...", flush=True)
    # Luồng tự động lưu
    threading.Thread(target=periodic_save_loop, daemon=True).start()

    # Khởi động luồng spam nếu nó được bật từ lần chạy trước
    if spam_enabled:
        if spam_thread is None or not spam_thread.is_alive():
            spam_thread = threading.Thread(target=spam_loop, daemon=True)
            spam_thread.start()

    port = int(os.environ.get("PORT", 10000))
    print(f"Khởi động Web Server tại http://0.0.0.0:{port}", flush=True)
    # Chạy Flask server, tắt reloader để tránh chạy script 2 lần
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
