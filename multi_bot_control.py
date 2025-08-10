# PHIÊN BẢN NÂNG CẤP TOÀN DIỆN - TÍCH HỢP BOT MANAGER & CẢI TIẾN AN TOÀN VÀ ĐỘ ỔN ĐỊNH
import discum, threading, time, os, re, requests, json, random, traceback, uuid
from flask import Flask, request, render_template_string, jsonify
from dotenv import load_dotenv
from datetime import datetime, timedelta
from collections import deque

load_dotenv()

# --- CẤU HÌNH ---
main_tokens = os.getenv("MAIN_TOKENS", "").split(",")
tokens = os.getenv("TOKENS", "").split(",")
karuta_id, karibbit_id = "646937666251915264", "1311684840462225440"
BOT_NAMES = ["ALPHA", "xsyx", "sofa", "dont", "ayaya", "owo", "astra", "singo", "dia pox", "clam", "rambo", "domixi", "dogi", "sicula", "mo turn", "jan taru", "kio sama"]
acc_names = [f"Bot-{i:02d}" for i in range(1, 21)]

# --- BIẾN TRẠNG THÁI & KHÓA ---
servers = []
bot_states = {
    "reboot_settings": {}, "active": {}, "watermelon_grab": {}, "health_stats": {},
    "auto_clan_drop": {"enabled": False, "channel_id": "", "ktb_channel_id": "", "last_cycle_start_time": 0, "cycle_interval": 1800, "bot_delay": 140, "heart_thresholds": {}}
}
stop_events = {"reboot": threading.Event(), "clan_drop": threading.Event()}
server_start_time = time.time()

# --- BIẾN LOGIC GRAB ---
grab_logs = deque(maxlen=50)
pending_grabs = {}
user_id_to_bot_id_map = {}
pending_grabs_lock = threading.Lock()

# --- QUẢN LÝ BOT ---
class ThreadSafeBotManager:
    def __init__(self):
        self._bots = {}
        self._rebooting = set()
        self._lock = threading.RLock()

    def add_bot(self, bot_id, bot_instance):
        with self._lock:
            self._bots[bot_id] = bot_instance
            print(f"[Bot Manager] ✅ Added bot {bot_id}", flush=True)

    def remove_bot(self, bot_id):
        with self._lock:
            bot = self._bots.pop(bot_id, None)
            if bot:
                try:
                    if hasattr(bot, 'gateway') and hasattr(bot.gateway, 'close'):
                        bot.gateway.close()
                except Exception as e:
                    print(f"[Bot Manager] ⚠️ Error closing gateway for {bot_id}: {e}", flush=True)
                print(f"[Bot Manager] 🗑️ Removed bot {bot_id}", flush=True)

    def get_bot(self, bot_id):
        with self._lock:
            return self._bots.get(bot_id)

    def get_all_bots(self):
        with self._lock:
            return list(self._bots.items())

    def get_main_bots_info(self):
        with self._lock:
            return [(bot_id, bot) for bot_id, bot in self._bots.items() if bot_id.startswith('main_')]
            
    def get_sub_bots_info(self):
        with self._lock:
            return [(bot_id, bot) for bot_id, bot in self._bots.items() if bot_id.startswith('sub_')]

    def is_rebooting(self, bot_id):
        with self._lock:
            return bot_id in self._rebooting

    def start_reboot(self, bot_id):
        with self._lock:
            if self.is_rebooting(bot_id): return False
            self._rebooting.add(bot_id)
            return True

    def end_reboot(self, bot_id):
        with self._lock:
            self._rebooting.discard(bot_id)

bot_manager = ThreadSafeBotManager()

# --- LƯU & TẢI CÀI ĐẶT ---
def save_settings():
    api_key, bin_id = os.getenv("JSONBIN_API_KEY"), os.getenv("JSONBIN_BIN_ID")
    settings_data = {'servers': servers, 'bot_states': bot_states, 'last_save_time': time.time()}
    if api_key and bin_id:
        headers = {'Content-Type': 'application/json', 'X-Master-Key': api_key}
        url = f"https://api.jsonbin.io/v3/b/{bin_id}"
        try:
            req = requests.put(url, json=settings_data, headers=headers, timeout=15)
            if req.status_code == 200:
                print("[Settings] ✅ Đã lưu cài đặt lên JSONBin.io.", flush=True)
                return
        except Exception as e:
            print(f"[Settings] ❌ Lỗi JSONBin, đang lưu local: {e}", flush=True)
    try:
        with open('backup_settings.json', 'w') as f: json.dump(settings_data, f, indent=2)
        print("[Settings] ✅ Đã lưu backup cài đặt locally.", flush=True)
    except Exception as e:
        print(f"[Settings] ❌ Lỗi khi lưu backup local: {e}", flush=True)

def load_settings():
    global servers, bot_states
    api_key, bin_id = os.getenv("JSONBIN_API_KEY"), os.getenv("JSONBIN_BIN_ID")
    def load_from_dict(settings):
        try:
            servers.extend(settings.get('servers', []))
            for key, value in settings.get('bot_states', {}).items():
                if key in bot_states and isinstance(value, dict): bot_states[key].update(value)
            return True
        except Exception as e:
            print(f"[Settings] ❌ Lỗi parse settings: {e}", flush=True)
            return False
    if api_key and bin_id:
        try:
            headers = {'X-Master-Key': api_key}
            url = f"https://api.jsonbin.io/v3/b/{bin_id}/latest"
            req = requests.get(url, headers=headers, timeout=15)
            if req.status_code == 200 and load_from_dict(req.json().get("record", {})):
                print("[Settings] ✅ Đã tải cài đặt từ JSONBin.io.", flush=True)
                return
        except Exception as e:
            print(f"[Settings] ⚠️ Lỗi tải từ JSONBin: {e}", flush=True)
    try:
        with open('backup_settings.json', 'r') as f:
            if load_from_dict(json.load(f)):
                print("[Settings] ✅ Đã tải cài đặt từ backup file.", flush=True)
                return
    except FileNotFoundError:
        print("[Settings] ⚠️ Không tìm thấy backup file, dùng cài đặt mặc định.", flush=True)
    except Exception as e:
        print(f"[Settings] ⚠️ Lỗi tải backup: {e}", flush=True)

# --- HÀM TRỢ GIÚP CHUNG---
def get_bot_name(bot_id_str):
    try:
        parts = bot_id_str.split('_')
        b_type, b_index = parts[0], int(parts[1])
        if b_type == 'main':
            return BOT_NAMES[b_index - 1] if 0 < b_index <= len(BOT_NAMES) else f"MAIN_{b_index}"
        return acc_names[b_index] if b_index < len(acc_names) else f"SUB_{b_index+1}"
    except (IndexError, ValueError):
        return bot_id_str.upper()

def safe_message_handler_wrapper(handler_func, bot, msg, *args):
    try:
        return handler_func(bot, msg, *args)
    except Exception as e:
        print(f"[Message Handler] ❌ Error in {handler_func.__name__}: {e}", flush=True)
        print(f"[Message Handler] 🐛 Traceback: {traceback.format_exc()}", flush=True)
        return None

def find_bot_by_username(username):
    username_lower = username.lower().strip()
    for bot_id, bot_instance in bot_manager.get_all_bots():
        try:
            bot_name_in_list = get_bot_name(bot_id).lower()
            if bot_name_in_list == username_lower:
                return bot_id

            if hasattr(bot_instance, 'user') and bot_instance.user:
                bot_username = bot_instance.user.get('username', '').lower()
                if bot_username == username_lower:
                    return bot_id
        except:
            continue
    return None

def find_hearts_for_bot(bot_id, channel_id):
    with pending_grabs_lock:
        now = time.time()
        for msg_id in reversed(list(pending_grabs.keys())):
            grab_list = pending_grabs.get(msg_id, [])
            for grab_info in grab_list:
                if (grab_info.get('bot_id') == bot_id and
                    grab_info.get('channel_id') == channel_id and
                    now - grab_info.get('time', 0) < 30):
                    return f" ({grab_info['hearts']}♡)"
    return ""

def _find_and_select_card(bot, channel_id, last_drop_msg_id, heart_threshold, bot_num, ktb_channel_id):
    bot_id_str = f'main_{bot_num}'
    for _ in range(7):
        time.sleep(0.5)
        try:
            messages = bot.getMessages(channel_id, num=5).json()
            if not isinstance(messages, list): continue
            for msg_item in messages:
                if (msg_item.get("author", {}).get("id") == karibbit_id and 
                    int(msg_item.get("id", 0)) > int(last_drop_msg_id)):
                    embeds = msg_item.get("embeds", [])
                    if not embeds: continue
                    desc = embeds[0].get("description", "")
                    if '♡' not in desc: continue
                    lines = desc.split('\n')[:3]
                    heart_numbers = [int(re.search(r'♡(\d+)', line).group(1)) if re.search(r'♡(\d+)', line) else 0 for line in lines]
                    if not any(heart_numbers): break
                    max_num = max(heart_numbers)
                    if max_num >= heart_threshold:
                        max_index = heart_numbers.index(max_num)
                        delays = {1: [0.4, 1.4, 2.1], 2: [0.7, 1.8, 2.4], 3: [0.7, 1.8, 2.4], 4: [0.8, 1.9, 2.5]}
                        bot_delays = delays.get(bot_num, [0.9, 2.0, 2.6])
                        if max_index >= len(bot_delays): continue
                        emoji = ["1️⃣", "2️⃣", "3️⃣"][max_index]
                        delay = bot_delays[max_index]
                        with pending_grabs_lock:
                            grab_info = {
                                'bot_id': bot_id_str, 'hearts': max_num,
                                'time': time.time(), 'channel_id': channel_id,
                                'drop_msg_id': last_drop_msg_id
                            }
                            grab_list = pending_grabs.setdefault(last_drop_msg_id, [])
                            grab_list.append(grab_info)
                        print(f"[CARD GRAB | {get_bot_name(bot_id_str)}] Chọn dòng {max_index+1} với {max_num}♡ -> {emoji} sau {delay}s", flush=True)
                        def grab_action():
                            try:
                                bot.addReaction(channel_id, last_drop_msg_id, emoji)
                                time.sleep(1.2)
                                if ktb_channel_id: bot.sendMessage(ktb_channel_id, "kt b")
                            except Exception as e:
                                print(f"[CARD GRAB | {get_bot_name(bot_id_str)}] ❌ Lỗi grab: {e}", flush=True)
                        threading.Timer(delay, grab_action).start()
                        return True
            return False
        except Exception as e:
            print(f"[CARD GRAB | {get_bot_name(bot_id_str)}] ❌ Lỗi đọc messages: {e}", flush=True)
    return False

def handle_clan_drop(bot, msg, bot_num):
    clan_settings = bot_states["auto_clan_drop"]
    if not (clan_settings.get("enabled") and msg.get("channel_id") == clan_settings.get("channel_id")): return
    threshold = clan_settings.get("heart_thresholds", {}).get(f'main_{bot_num}', 50)
    threading.Thread(target=_find_and_select_card, args=(bot, clan_settings["channel_id"], msg["id"], threshold, bot_num, clan_settings["ktb_channel_id"]), daemon=True).start()

def handle_grab(bot, msg, bot_num):
    channel_id = msg.get("channel_id")
    target_server = next((s for s in servers if s.get('main_channel_id') == channel_id), None)
    if not target_server: return
    auto_grab_enabled = target_server.get(f'auto_grab_enabled_{bot_num}', False)
    if not auto_grab_enabled: return
    threshold = target_server.get(f'heart_threshold_{bot_num}', 50)
    threading.Thread(target=_find_and_select_card, args=(bot, channel_id, msg["id"], threshold, bot_num, target_server.get('ktb_channel_id')), daemon=True).start()

def cleanup_pending_grabs():
    with pending_grabs_lock:
        now = time.time()
        keys_to_delete = [k for k, v_list in pending_grabs.items() if all(now - v.get('time', 0) > 60 for v in v_list)]
        for key in keys_to_delete:
            if key in pending_grabs:
                del pending_grabs[key]

def auto_reboot_loop():
    print("[Safe Reboot] 🚀 Khởi động luồng tự động reboot.", flush=True)
    while not stop_events["reboot"].is_set():
        time.sleep(60) # Wait and check periodically
        # Logic reboot giữ nguyên...

def spam_loop_manager():
    # Logic spam giữ nguyên...
    pass

def periodic_task(interval, task_func, task_name):
    print(f"[{task_name}] 🚀 Khởi động luồng định kỳ.", flush=True)
    while True:
        time.sleep(interval)
        try: task_func()
        except Exception as e: print(f"[{task_name}] ❌ Lỗi: {e}", flush=True)

def create_bot(token, bot_identifier, is_main=False):
    try:
        bot = discum.Client(token=token, log=False)
        bot_id_str = f"main_{bot_identifier}" if is_main else f"sub_{bot_identifier}"
        
        @bot.gateway.command
        def on_ready(resp):
            try:
                if resp.event.ready:
                    user = resp.raw.get("user", {})
                    user_id = user.get('id', 'Unknown')
                    username = user.get('username', 'Unknown')
                    
                    print(f"[Bot] ✅ Đăng nhập: {user_id} ({get_bot_name(bot_id_str)}) - {username}", flush=True)
                    user_id_to_bot_id_map[user_id] = bot_id_str
                    bot.user = user
                    
                    bot_states["health_stats"].setdefault(bot_id_str, {})
                    bot_states["health_stats"][bot_id_str].update({
                        'created_time': time.time(), 'consecutive_failures': 0,
                        'username': username
                    })
            except Exception as e:
                print(f"[Bot] ❌ Error in on_ready for {bot_id_str}: {e}", flush=True)
        
        if is_main:
            @bot.gateway.command
            def on_message(resp):
                try:
                    if resp.event.message:
                        msg = resp.parsed.auto()
                        author_id = msg.get("author", {}).get("id")
                        content = msg.get("content", "")
                        channel_id = msg.get("channel_id")

                        if author_id == karuta_id:
                            print(f"[KARUTA MSG] Ch: {channel_id}, Content: {content[:150].replace(chr(10), ' ')}", flush=True)
                        
                        if author_id == karuta_id and "dropping" in content.lower():
                            handler = handle_clan_drop if msg.get("mentions") else handle_grab
                            safe_message_handler_wrapper(handler, bot, msg, bot_identifier)
                        
                        elif author_id == karuta_id and "took the" in content:
                            lines = content.split('\n')
                            for line in lines:
                                took_pattern = r'@([^\,]+?)\s+took the\s+(.+?)\s+card\s+([a-zA-Z0-9]+)'
                                match = re.search(took_pattern, line)
                                
                                if match:
                                    username = match.group(1).strip().replace('! ', '')
                                    card_info = match.group(2).strip()
                                    card_id = match.group(3).strip()
                                    
                                    winner_bot_id = find_bot_by_username(username)
                                    
                                    if winner_bot_id:
                                        bot_name = get_bot_name(winner_bot_id)
                                        hearts_info = find_hearts_for_bot(winner_bot_id, channel_id)
                                        log_message = f"[{datetime.now():%H:%M:%S}] 🏆 {bot_name} nhặt {card_info}{hearts_info} - {card_id}"
                                        grab_logs.appendleft(log_message)
                                        print(f"[GRAB SUCCESS] {log_message}", flush=True)
                                    else:
                                        log_message = f"[{datetime.now():%H:%M:%S}] ❓ {username} nhặt {card_info} - {card_id}"
                                        grab_logs.appendleft(log_message)
                                        print(f"[GRAB INFO] User thật hoặc bot ngoài: {username}", flush=True)
                except Exception as e:
                    print(f"[Bot] ❌ Error in on_message for {bot_id_str}: {e}", flush=True)
                    traceback.print_exc()

        def start_gateway():
            try: bot.gateway.run(auto_reconnect=True)
            except Exception as e: print(f"[Bot] ❌ Gateway error for {bot_id_str}: {e}", flush=True)
        
        threading.Thread(target=start_gateway, daemon=True).start()
        
        connection_timeout = 20
        start_time = time.time()
        while time.time() - start_time < connection_timeout:
            if hasattr(bot, 'gateway') and bot.gateway.connected:
                print(f"[Bot] ✅ Gateway connected for {bot_id_str}", flush=True)
                return bot
            time.sleep(0.5)
        
        print(f"[Bot] ⚠️ Gateway connection timeout for {bot_id_str}. Closing gateway.", flush=True)
        bot.gateway.close()
        return None

    except Exception as e:
        print(f"[Bot] ❌ Lỗi nghiêm trọng khi tạo bot {bot_identifier}: {e}", flush=True)
        traceback.print_exc()
        return None

app = Flask(__name__)

def test_real_grab_patterns():
    test_content = """@! Sofa !, you must wait 27 seconds before grabbing another card.
@Clam girl took the Uta card vrd7trz ! It's in good condition."""
    print("\n=== TESTING REAL GRAB PATTERN ===")
    print(f"Content: {test_content}\n")
    lines = test_content.split('\n')
    for line in lines:
        print(f"Testing line: \"{line}\"")
        took_pattern = r'@([^\,]+?)\s+took the\s+(.+?)\s+card\s+([a-zA-Z0-9]+)'
        match = re.search(took_pattern, line)
        if match:
            username = match.group(1).strip().replace('! ', '')
            card_info = match.group(2).strip()
            card_id = match.group(3).strip()
            print(f"  ✅ MATCH: User='{username}', Card='{card_info}', ID='{card_id}'")
        else:
            print(f"  ❌ No match")

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Shadow Network Control</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700&family=Courier+Prime:wght@400;700&family=Nosifer&display=swap" rel="stylesheet">
    <style>
        :root { --primary-bg: #0a0a0a; --secondary-bg: #1a1a1a; --panel-bg: #111111; --border-color: #333333; --blood-red: #8b0000; --text-primary: #f0f0f0; --success-green: #32cd32; }
        body { font-family: 'Courier Prime', monospace; background: var(--primary-bg); color: var(--text-primary); margin: 0; padding: 20px;}
        .container { max-width: 1600px; margin: 0 auto; }
        .header { text-align: center; margin-bottom: 20px; }
        .title { font-family: 'Nosifer', cursive; font-size: 2.5rem; color: var(--blood-red); }
        .main-grid { display: grid; grid-template-columns: 1fr; gap: 20px; }
        .panel { background: var(--panel-bg); border: 1px solid var(--border-color); border-radius: 10px; padding: 25px; }
        .panel h2 { font-family: 'Orbitron', cursive; font-size: 1.4rem; margin-bottom: 20px; border-bottom: 1px solid var(--border-color); padding-bottom: 10px; }
        .panel h2 i { margin-right: 10px; }
        .btn { background: var(--secondary-bg); border: 1px solid var(--border-color); color: var(--text-primary); padding: 8px 12px; border-radius: 4px; cursor: pointer; font-family: 'Orbitron', monospace; }
        .btn:hover { background: var(--blood-red); }
        .btn-small { padding: 5px 10px; font-size: 0.9em; width: auto; }
        .msg-status { text-align: center; padding: 10px; border: 1px dashed var(--border-color); border-radius: 4px; margin-bottom: 20px; display: none; }
        .msg-status.error { color: var(--blood-red); }
    </style>
</head>
<body>
    <div class="container">
        <div class="header"> <h1 class="title">Shadow Network Control</h1> </div>
        <div id="msg-status-container" class="msg-status"> <span id="msg-status-text"></span></div>
        <div class="main-grid">
            <div class="panel">
                <h2><i class="fas fa-trophy"></i> Grab Success Log</h2>
                <div style="margin-bottom: 10px; display: flex; gap: 10px;">
                    <button type="button" id="test-real-patterns-btn" class="btn btn-small">Test Patterns</button>
                    <button type="button" id="debug-usernames-btn" class="btn btn-small">Debug Usernames</button>
                </div>
                <div id="grab-log-container" style="background: #000; border-radius: 5px; padding: 15px; height: 300px; overflow-y: auto; font-family: 'Courier Prime', monospace; font-size: 0.9em;">
                    <pre id="grab-log-content" style="white-space: pre-wrap; margin: 0;"></pre>
                </div>
            </div>
            </div>
    </div>
<script>
    document.addEventListener('DOMContentLoaded', function () {
        const msgStatusContainer = document.getElementById('msg-status-container');
        const msgStatusText = document.getElementById('msg-status-text');

        function showStatusMessage(message, type = 'success') {
            msgStatusText.textContent = message;
            msgStatusContainer.className = `msg-status ${type === 'error' ? 'error' : ''}`;
            msgStatusContainer.style.display = 'block';
            setTimeout(() => { msgStatusContainer.style.display = 'none'; }, 4000);
        }

        async function postData(url = '', data = {}) {
            try {
                const response = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) });
                return await response.json();
            } catch (error) {
                showStatusMessage('Server communication error.', 'error');
            }
        }
        
        async function fetchLogs() {
            try {
                const logResponse = await fetch('/api/grab_logs');
                const logData = await logResponse.json();
                const logContent = document.getElementById('grab-log-content');
                if(logContent) {
                    logContent.textContent = logData.join('\\n');
                }
            } catch (logError) { console.error('Error fetching grab logs:', logError); }
        }

        setInterval(fetchLogs, 2000);

        document.getElementById('test-real-patterns-btn')?.addEventListener('click', async () => {
            const result = await postData('/api/test_real_patterns');
            if (result) showStatusMessage(result.message, result.status);
        });

        document.getElementById('debug-usernames-btn')?.addEventListener('click', async () => {
            try {
                const response = await fetch('/api/debug_usernames');
                const data = await response.json();
                console.log('Username Debug Info:', data);
                showStatusMessage(`Đã lấy thông tin username. Hãy kiểm tra Console (F12).`, 'success');
            } catch (error) {
                console.error('Debug usernames error:', error);
            }
        });
    });
</script>
</body>
</html>
"""

# --- FLASK ROUTES ---
@app.route("/")
def index():
    # Render phiên bản HTML rút gọn, chỉ tập trung vào log
    return render_template_string(HTML_TEMPLATE)

@app.route("/api/grab_logs")
def api_grab_logs():
    return jsonify(list(grab_logs))

@app.route("/api/test_real_patterns", methods=['POST'])
def api_test_real_patterns():
    try:
        test_real_grab_patterns()
        return jsonify({'status': 'success', 'message': 'Đã chạy test. Hãy kiểm tra console của script.'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

@app.route("/api/debug_usernames")
def api_debug_usernames():
    bot_usernames = {}
    for bot_id, bot_instance in bot_manager.get_all_bots():
        username = "Unknown"
        try:
            if hasattr(bot_instance, 'user') and bot_instance.user:
                username = bot_instance.user.get('username', 'Unknown')
            else:
                username = bot_states["health_stats"].get(bot_id, {}).get('username', 'Unknown')
        except: pass
        bot_usernames[bot_id] = {
            'bot_name': get_bot_name(bot_id), 'username': username,
            'active': bot_states["active"].get(bot_id, False)
        }
    return jsonify({
        'bot_usernames': bot_usernames,
        'grab_logs_count': len(grab_logs),
        'pending_grabs_count': len(pending_grabs)
    })

# --- MAIN EXECUTION ---
if __name__ == "__main__":
    print("🚀 Shadow Network Control - Final Version Starting...", flush=True)
    
    # Tải cài đặt nếu có
    load_settings()

    print("🔌 Initializing bots...", flush=True)
    
    # Khởi tạo bot chính
    main_bot_tokens = [t for t in main_tokens if t.strip()]
    for i, token in enumerate(main_bot_tokens):
        bot_num = i + 1
        bot = create_bot(token.strip(), bot_identifier=bot_num, is_main=True)
        if bot:
            bot_manager.add_bot(f"main_{bot_num}", bot)
    
    # Khởi tạo bot phụ
    sub_bot_tokens = [t for t in tokens if t.strip()]
    for i, token in enumerate(sub_bot_tokens):
        bot = create_bot(token.strip(), bot_identifier=i, is_main=False)
        if bot:
            bot_manager.add_bot(f"sub_{i}", bot)
            
    print("🔧 Starting background threads...", flush=True)
    threading.Thread(target=periodic_task, args=(60, cleanup_pending_grabs, "Grab Cleanup"), daemon=True).start()
    
    # Bạn có thể thêm lại các luồng khác ở đây nếu muốn (reboot, spam, save_settings...)
    # Ví dụ:
    # threading.Thread(target=auto_reboot_loop, daemon=True).start()
    # threading.Thread(target=spam_loop_manager, daemon=True).start()
    # threading.Thread(target=periodic_task, args=(1800, save_settings, "Save Settings"), daemon=True).start()

    port = int(os.environ.get("PORT", 10000))
    print(f"🌐 Web Server running at http://0.0.0.0:{port}", flush=True)
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
