# PHIÊN BẢN CUỐI CÙNG - LOGIC NHẶT THẺ VIP + GHI LOG CẢI TIẾN
import discum, threading, time, os, re, requests, json, random, traceback, uuid
from flask import Flask, request, render_template_string, jsonify
from dotenv import load_dotenv
from datetime import datetime, timedelta

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

# --- QUẢN LÝ BOT (ĐÃ THÊM TÍNH NĂNG LOG) ---
class ThreadSafeBotManager:
    def __init__(self):
        self._bots, self._rebooting, self._lock = {}, set(), threading.RLock()
        self._grab_logs, self._max_logs = [], 50

    def add_bot(self, bot_id, bot_instance):
        with self._lock: self._bots[bot_id] = bot_instance; print(f"[Bot Manager] ✅ Added bot {bot_id}", flush=True)
    def remove_bot(self, bot_id):
        with self._lock:
            bot = self._bots.pop(bot_id, None)
            if bot and hasattr(bot, 'gateway'):
                try: bot.gateway.close()
                except Exception as e: print(f"[Bot Manager] ⚠️ Error closing gateway for {bot_id}: {e}", flush=True)
            print(f"[Bot Manager] 🗑️ Removed bot {bot_id}", flush=True)
    def get_bot(self, bot_id):
        with self._lock: return self._bots.get(bot_id)
    def get_all_bots(self):
        with self._lock: return list(self._bots.items())
    def get_main_bots_info(self):
        with self._lock: return [(i, b) for i, b in self._bots.items() if i.startswith('main_')]
    def get_sub_bots_info(self):
        with self._lock: return [(i, b) for i, b in self._bots.items() if i.startswith('sub_')]
    def is_rebooting(self, bot_id):
        with self._lock: return bot_id in self._rebooting
    def start_reboot(self, bot_id):
        with self._lock:
            if bot_id in self._rebooting: return False
            self._rebooting.add(bot_id); return True
    def end_reboot(self, bot_id):
        with self._lock: self._rebooting.discard(bot_id)
    def add_grab_success_log(self, bot_name, card_name, hearts, timestamp=None):
        with self._lock:
            log_entry = {'timestamp': timestamp or time.time(), 'bot_name': bot_name, 'card_name': card_name, 'hearts': hearts}
            log_entry['formatted_time'] = datetime.fromtimestamp(log_entry['timestamp']).strftime('%H:%M:%S')
            self._grab_logs.insert(0, log_entry)
            self._grab_logs = self._grab_logs[:self._max_logs]
            print(f"[GRAB SUCCESS] 🎯 {bot_name} đã nhặt {card_name} với {hearts}♡", flush=True)
    def get_grab_logs(self):
        with self._lock: return self._grab_logs.copy()
bot_manager = ThreadSafeBotManager()

# --- LƯU & TẢI CÀI ĐẶT ---
def save_settings():
    api_key, bin_id = os.getenv("JSONBIN_API_KEY"), os.getenv("JSONBIN_BIN_ID")
    settings_data = {'servers': servers, 'bot_states': bot_states}
    if api_key and bin_id:
        try:
            headers = {'Content-Type': 'application/json', 'X-Master-Key': api_key}
            requests.put(f"https://api.jsonbin.io/v3/b/{bin_id}", json=settings_data, headers=headers, timeout=10)
            print("[Settings] ✅ Đã lưu cài đặt lên JSONBin.io.", flush=True)
            return
        except Exception as e: print(f"[Settings] ❌ Lỗi JSONBin, đang lưu local: {e}", flush=True)
    try:
        with open('backup_settings.json', 'w') as f: json.dump(settings_data, f, indent=2)
        print("[Settings] ✅ Đã lưu backup cài đặt locally.", flush=True)
    except Exception as e: print(f"[Settings] ❌ Lỗi khi lưu backup local: {e}", flush=True)

def load_settings():
    global servers, bot_states
    api_key, bin_id = os.getenv("JSONBIN_API_KEY"), os.getenv("JSONBIN_BIN_ID")
    def load_from_dict(settings):
        try:
            servers.clear(); servers.extend(settings.get('servers', []))
            for key, value in settings.get('bot_states', {}).items():
                if key in bot_states and isinstance(value, dict): bot_states[key].update(value)
            return True
        except Exception: return False
    if api_key and bin_id:
        try:
            headers = {'X-Master-Key': api_key}
            req = requests.get(f"https://api.jsonbin.io/v3/b/{bin_id}/latest", headers=headers, timeout=10)
            if req.status_code == 200 and load_from_dict(req.json().get("record", {})):
                print("[Settings] ✅ Đã tải cài đặt từ JSONBin.io.", flush=True)
                return
        except Exception as e: print(f"[Settings] ⚠️ Lỗi tải từ JSONBin: {e}", flush=True)
    try:
        with open('backup_settings.json', 'r') as f:
            if load_from_dict(json.load(f)): print("[Settings] ✅ Đã tải cài đặt từ backup file.", flush=True)
    except FileNotFoundError: print("[Settings] ⚠️ Không tìm thấy backup file.", flush=True)
    except Exception as e: print(f"[Settings] ⚠️ Lỗi tải backup: {e}", flush=True)

# --- HÀM TRỢ GIÚP ---
def get_bot_name(bot_id_str):
    try:
        b_type, b_index = bot_id_str.split('_'); b_index = int(b_index)
        if b_type == 'main': return BOT_NAMES[b_index - 1]
        return acc_names[b_index]
    except (IndexError, ValueError): return bot_id_str.upper()

def safe_message_handler_wrapper(handler_func, bot, msg, *args):
    try: return handler_func(bot, msg, *args)
    except Exception as e: print(f"[Handler Error] in {handler_func.__name__}: {e}\n{traceback.format_exc()}", flush=True)

# ======================================================================
# >>>>> HÀM MỚI: DÙNG ĐỂ KIỂM TRA LOGIC NHẶT THẺ THÀNH CÔNG <<<<<
# ======================================================================
def check_grab_result(bot, channel_id, drop_msg_id, bot_name, hearts):
    try:
        bot_user_id = bot.gateway.user.get('id')
        if not bot_user_id:
            print(f"[GRAB CHECK | {bot_name}] ⚠️ Không thể lấy User ID của bot.", flush=True)
            return
        
        time.sleep(2.5) # Chờ Karuta phản hồi
        messages = bot.getMessages(channel_id, num=10).json()
        if not isinstance(messages, list): return

        for msg in messages:
            if msg.get("author", {}).get("id") != karuta_id or int(msg.get("id", 0)) <= int(drop_msg_id):
                continue

            content = msg.get("content", "")
            if f"<@{bot_user_id}>" in content and ("took the" in content or "fought off" in content):
                card_match = re.search(r"\*\*(.+?)\*\*", content)
                grabbed_card_name = card_match.group(1) if card_match else "Unknown Card"
                
                bot_manager.add_grab_success_log(bot_name=bot_name, card_name=grabbed_card_name, hearts=hearts)
                return True
    except Exception as e:
        print(f"[GRAB CHECK | {bot_name}] ❌ Lỗi: {e}", flush=True)

# ======================================================================
# >>>>> LOGIC NHẶT THẺ GIỮ NGUYÊN TỪ FILE VIP.PY <<<<<
# ======================================================================
def _find_and_select_card(bot, channel_id, last_drop_msg_id, heart_threshold, bot_num, ktb_channel_id):
    """Hàm chung để tìm và chọn card dựa trên số heart."""
    bot_name = get_bot_name(f'main_{bot_num}')
    for _ in range(7):
        time.sleep(0.5)
        try:
            messages = bot.getMessages(channel_id, num=5).json()
            if not isinstance(messages, list): continue

            for msg_item in messages:
                if msg_item.get("author", {}).get("id") == karibbit_id and int(msg_item.get("id", 0)) > int(last_drop_msg_id):
                    embeds = msg_item.get("embeds", [])
                    desc = embeds[0].get("description", "") if embeds else ""
                    if '♡' not in desc: continue

                    lines = desc.split('\n')[:3]
                    heart_numbers = [int(re.search(r'♡(\d+)', line).group(1)) if re.search(r'♡(\d+)', line) else 0 for line in lines]
                    if not any(heart_numbers): break

                    max_num = max(heart_numbers)
                    if max_num >= heart_threshold:
                        max_index = heart_numbers.index(max_num)
                        delays = {1: [0.4, 1.4, 2.1], 2: [0.7, 1.8, 2.4], 3: [0.7, 1.8, 2.4], 4: [0.8, 1.9, 2.5]}
                        bot_delays = delays.get(bot_num, [0.9, 2.0, 2.6])
                        emoji = ["1️⃣", "2️⃣", "3️⃣"][max_index]
                        delay = bot_delays[max_index]
                        
                        print(f"[CARD GRAB | {bot_name}] Chọn dòng {max_index+1} với {max_num}♡ -> {emoji} sau {delay}s", flush=True)
                        
                        def grab_action():
                            try:
                                bot.addReaction(channel_id, last_drop_msg_id, emoji)
                                time.sleep(1.2)
                                if ktb_channel_id: bot.sendMessage(ktb_channel_id, "kt b")
                                # >>> GỌI HÀM KIỂM TRA KẾT QUẢ SAU KHI NHẶT <<<
                                check_grab_result(bot, channel_id, last_drop_msg_id, bot_name, max_num)
                            except Exception as e:
                                print(f"[CARD GRAB | {bot_name}] ❌ Lỗi grab: {e}", flush=True)

                        threading.Timer(delay, grab_action).start()
                        return True
            return False
        except Exception as e:
            print(f"[CARD GRAB | {bot_name}] ❌ Lỗi đọc messages: {e}", flush=True)
    return False

# --- LOGIC BOT & CÁC TÁC VỤ NỀN (Tương tự file vip.py) ---
def handle_clan_drop(bot, msg, bot_num):
    clan_settings = bot_states["auto_clan_drop"]
    if not (clan_settings.get("enabled") and msg.get("channel_id") == clan_settings.get("channel_id")): return
    threshold = clan_settings.get("heart_thresholds", {}).get(f'main_{bot_num}', 50)
    threading.Thread(target=_find_and_select_card, args=(bot, clan_settings["channel_id"], msg["id"], threshold, bot_num, clan_settings["ktb_channel_id"]), daemon=True).start()

def handle_grab(bot, msg, bot_num):
    channel_id = msg.get("channel_id")
    target_server = next((s for s in servers if s.get('main_channel_id') == channel_id), None)
    if not target_server: return
    bot_id_str = f'main_{bot_num}'
    auto_grab_enabled = target_server.get(f'auto_grab_enabled_{bot_num}', False)
    watermelon_grab_enabled = bot_states["watermelon_grab"].get(bot_id_str, False)
    if not auto_grab_enabled and not watermelon_grab_enabled: return
    last_drop_msg_id = msg["id"]
    def grab_logic_thread():
        if auto_grab_enabled and target_server.get('ktb_channel_id'):
            threshold = target_server.get(f'heart_threshold_{bot_num}', 50)
            threading.Thread(target=_find_and_select_card, args=(bot, channel_id, last_drop_msg_id, threshold, bot_num, target_server.get('ktb_channel_id')), daemon=True).start()
        if watermelon_grab_enabled:
            def check_for_watermelon_patiently():
                time.sleep(5)
                try:
                    target_message = bot.getMessage(channel_id, last_drop_msg_id).json()[0]
                    for reaction in target_message.get('reactions', []):
                        if '🍉' in reaction.get('emoji', {}).get('name', ''):
                            print(f"[WATERMELON | Bot {bot_num}] 🎯 PHÁT HIỆN DƯA HẤU!", flush=True)
                            bot.addReaction(channel_id, last_drop_msg_id, "🍉")
                            return
                except Exception as e: print(f"[WATERMELON | Bot {bot_num}] ❌ Lỗi: {e}", flush=True)
            threading.Thread(target=check_for_watermelon_patiently, daemon=True).start()
    threading.Thread(target=grab_logic_thread, daemon=True).start()

def check_bot_health(bot_instance, bot_id):
    stats = bot_states["health_stats"].setdefault(bot_id, {'consecutive_failures': 0})
    try:
        is_connected = bot_instance and hasattr(bot_instance.gateway, 'connected') and bot_instance.gateway.connected
        stats['consecutive_failures'] = 0 if is_connected else stats.get('consecutive_failures', 0) + 1
        return is_connected
    except Exception: stats['consecutive_failures'] = stats.get('consecutive_failures', 0) + 1; return False

def safe_reboot_bot(bot_id):
    if not bot_manager.start_reboot(bot_id): return False
    print(f"[Safe Reboot] 🔄 Bắt đầu reboot bot {bot_id}...", flush=True)
    try:
        match = re.match(r"main_(\d+)", bot_id); bot_index = int(match.group(1)) - 1
        token = main_tokens[bot_index].strip(); bot_name = get_bot_name(bot_id)
        bot_manager.remove_bot(bot_id)
        settings = bot_states["reboot_settings"].get(bot_id, {})
        wait_time = random.uniform(20, 40) + min(settings.get('failure_count', 0) * 30, 300)
        time.sleep(wait_time)
        new_bot = create_bot(token, bot_identifier=(bot_index + 1), is_main=True)
        if not new_bot: raise Exception("Không thể tạo instance bot mới.")
        bot_manager.add_bot(bot_id, new_bot)
        settings.update({'next_reboot_time': time.time() + settings.get('delay', 3600), 'failure_count': 0})
        print(f"[Safe Reboot] ✅ Reboot thành công {bot_name}", flush=True)
        return True
    except Exception as e:
        print(f"[Safe Reboot] ❌ Reboot thất bại cho {bot_id}: {e}", flush=True); traceback.print_exc()
        settings = bot_states["reboot_settings"].setdefault(bot_id, {})
        failure_count = settings.get('failure_count', 0) + 1; settings['failure_count'] = failure_count
        next_try_delay = max(600, min(2 ** failure_count, 8) * (settings.get('delay', 3600) / 8))
        settings['next_reboot_time'] = time.time() + next_try_delay
        if failure_count >= 5: settings['enabled'] = False; print(f" Tắt auto-reboot cho {bot_id}.", flush=True)
        return False
    finally: bot_manager.end_reboot(bot_id)

def auto_reboot_loop():
    while not stop_events["reboot"].is_set():
        try:
            bot_to_reboot, highest_priority = None, -1
            now = time.time()
            for bot_id, settings in bot_states["reboot_settings"].items():
                if settings.get('enabled') and now >= settings.get('next_reboot_time', 0):
                    failures = bot_states["health_stats"].get(bot_id, {}).get('consecutive_failures', 0)
                    priority = (failures * 1000) + (now - settings.get('next_reboot_time', 0))
                    if priority > highest_priority: highest_priority, bot_to_reboot = priority, bot_id
            if bot_to_reboot: safe_reboot_bot(bot_to_reboot)
        except Exception as e: print(f"[Reboot Loop Error]: {e}", flush=True)
        time.sleep(30)

def run_clan_drop_cycle():
    settings = bot_states["auto_clan_drop"]
    active_bots = [(b, int(i.split('_')[1])) for i, b in bot_manager.get_main_bots_info() if bot_states["active"].get(i)]
    if not active_bots: print("[Clan Drop] ⚠️ Không có bot chính nào hoạt động.", flush=True); return
    for bot, num in active_bots:
        try:
            print(f"[Clan Drop] 📤 {get_bot_name(f'main_{num}')} đang gửi 'kd'...", flush=True)
            bot.sendMessage(settings["channel_id"], "kd")
            time.sleep(random.uniform(settings["bot_delay"] * 0.8, settings["bot_delay"] * 1.2))
        except Exception as e: print(f"[Clan Drop] ❌ Lỗi: {e}", flush=True)
    settings["last_cycle_start_time"] = time.time(); save_settings()

def auto_clan_drop_loop():
    while not stop_events["clan_drop"].is_set():
        s = bot_states["auto_clan_drop"]
        if s.get("enabled") and time.time() - s.get("last_cycle_start_time", 0) >= s.get("cycle_interval", 1800):
            run_clan_drop_cycle()
        time.sleep(60)

def spam_for_server(server_config, stop_event):
    while not stop_event.is_set():
        try:
            bots_to_spam = [b for i, b in bot_manager.get_all_bots() if bot_states["active"].get(i)]
            delay = server_config.get('spam_delay', 10)
            for bot in bots_to_spam:
                if stop_event.is_set(): break
                bot.sendMessage(server_config['spam_channel_id'], server_config['spam_message'])
                time.sleep(random.uniform(1.5, 2.5))
            stop_event.wait(random.uniform(delay * 0.9, delay * 1.1))
        except Exception as e: print(f"[Spam] ❌ Lỗi server {server_config.get('name')}: {e}", flush=True); stop_event.wait(10)
def spam_loop_manager():
    active_threads = {}
    while True:
        try:
            current_ids = {s['id'] for s in servers}
            for server_id in list(active_threads.keys()):
                if server_id not in current_ids: active_threads.pop(server_id)[1].set()
            for server in servers:
                server_id = server.get('id')
                spam_on = server.get('spam_enabled') and server.get('spam_message') and server.get('spam_channel_id')
                if spam_on and server_id not in active_threads:
                    stop_event = threading.Event()
                    thread = threading.Thread(target=spam_for_server, args=(server, stop_event), daemon=True); thread.start()
                    active_threads[server_id] = (thread, stop_event)
                elif not spam_on and server_id in active_threads: active_threads.pop(server_id)[1].set()
            time.sleep(5)
        except Exception as e: print(f"[Spam Manager] ❌ Lỗi: {e}", flush=True); time.sleep(5)
def periodic_task(interval, func, name):
    while True: time.sleep(interval); func()
def health_monitoring_check():
    for bot_id, bot in bot_manager.get_all_bots(): check_bot_health(bot, bot_id)

# --- KHỞI TẠO BOT ---
def create_bot(token, bot_identifier, is_main=False):
    try:
        bot = discum.Client(token=token, log=False)
        bot_id_str = f"main_{bot_identifier}" if is_main else f"sub_{bot_identifier}"
        @bot.gateway.command
        def on_ready(resp):
            if resp.event.ready:
                user = resp.raw.get("user", {})
                print(f"[Bot] ✅ Đăng nhập: {user.get('id')} ({get_bot_name(bot_id_str)})", flush=True)
        if is_main:
            @bot.gateway.command
            def on_message(resp):
                if resp.event.message:
                    msg = resp.parsed.auto()
                    if msg.get("author", {}).get("id") == karuta_id and "dropping" in msg.get("content", "").lower():
                        handler = handle_clan_drop if msg.get("mentions") else handle_grab
                        safe_message_handler_wrapper(handler, bot, msg, bot_identifier)
        threading.Thread(target=lambda: bot.gateway.run(auto_reconnect=True), daemon=True).start()
        start_time = time.time()
        while time.time() - start_time < 20:
            if hasattr(bot.gateway, 'connected') and bot.gateway.connected: return bot
            time.sleep(0.5)
        bot.gateway.close()
        return None
    except Exception as e: print(f"[Bot Create Error] Bot {bot_identifier}: {e}", flush=True); return None

# --- GIAO DIỆN WEB & API (ĐÃ TÍCH HỢP LOG PANEL) ---
app = Flask(__name__)
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Shadow Network Control - VIP</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@700&family=Courier+Prime&family=Nosifer&display=swap" rel="stylesheet">
    <style>
        :root { --primary-bg: #0a0a0a; --secondary-bg: #1a1a1a; --panel-bg: #111111; --border-color: #333; --blood-red: #8b0000; --dark-red: #550000; --bone-white: #f8f8ff; --necro-green: #228b22; --text-primary: #f0f0f0; --text-secondary: #ccc; --warning-orange: #ff8c00; --success-green: #32cd32; }
        body { font-family: 'Courier Prime', monospace; background: var(--primary-bg); color: var(--text-primary); margin: 0; padding: 20px;}
        .container { max-width: 1600px; margin: 0 auto; }
        .header { text-align: center; margin-bottom: 30px; padding: 20px; border-bottom: 2px solid var(--blood-red); }
        .title { font-family: 'Nosifer', cursive; font-size: 3rem; color: var(--blood-red); }
        .subtitle { font-family: 'Orbitron', sans-serif; font-size: 1rem; color: var(--necro-green); margin-top: 10px; }
        .main-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(500px, 1fr)); gap: 20px; }
        .panel { background: var(--panel-bg); border: 1px solid var(--border-color); border-radius: 10px; padding: 25px; position: relative;}
        .panel h2 { font-family: 'Orbitron', cursive; font-size: 1.4rem; margin-bottom: 20px; text-transform: uppercase; border-bottom: 2px solid; padding-bottom: 10px; color: var(--bone-white); }
        .panel h2 i { margin-right: 10px; }
        .btn { background: var(--secondary-bg); border: 1px solid var(--border-color); color: var(--text-primary); padding: 10px 15px; border-radius: 4px; cursor: pointer; font-family: 'Orbitron', monospace; font-weight: 700; text-transform: uppercase; transition: all 0.3s ease; }
        .btn:hover { background: var(--dark-red); border-color: var(--blood-red); }
        .input-group { display: flex; align-items: stretch; gap: 10px; margin-bottom: 15px; }
        .input-group label { background: #000; border: 1px solid var(--border-color); border-right: 0; padding: 10px 15px; border-radius: 4px 0 0 4px; display:flex; align-items:center; min-width: 120px;}
        .input-group input, .input-group textarea { flex-grow: 1; background: #000; border: 1px solid var(--border-color); color: var(--text-primary); padding: 10px 15px; border-radius: 0 4px 4px 0; font-family: 'Courier Prime', monospace; }
        .grab-section { display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; padding: 15px; background: rgba(0,0,0,0.2); border-radius: 8px;}
        .grab-section h3 { margin: 0; display: flex; align-items: center; gap: 10px; width: 80px; flex-shrink: 0; }
        .grab-section .input-group { margin-bottom: 0; flex-grow: 1; margin-left: 20px;}
        .msg-status { text-align: center; color: var(--necro-green); padding: 12px; border: 1px dashed var(--border-color); border-radius: 4px; margin-bottom: 20px; display: none; }
        .msg-status.error { color: var(--blood-red); }
        .status-panel, .global-settings-panel, .clan-drop-panel, .grab-logs-panel { grid-column: 1 / -1; }
        .status-row { display: flex; justify-content: space-between; align-items: center; padding: 12px; background: rgba(0,0,0,0.4); border-radius: 8px; }
        .bot-status-item { display: flex; justify-content: space-between; align-items: center; padding: 5px 8px; background: rgba(0,0,0,0.3); border-radius: 4px; }
        .btn-toggle-state { padding: 3px 5px; font-size: 0.9em; border-radius: 4px; cursor: pointer; text-transform: uppercase; background: transparent; font-weight: 700; border: none; }
        .btn-rise { color: var(--success-green); } .btn-rest { color: var(--dark-red); } .btn-warning { color: var(--warning-orange); }
        .add-server-btn { display: flex; align-items: center; justify-content: center; min-height: 200px; border: 2px dashed var(--border-color); cursor: pointer; transition: all 0.3s ease; }
        .add-server-btn:hover { background: var(--secondary-bg); border-color: var(--blood-red); }
        .btn-delete-server { position: absolute; top: 15px; right: 15px; background: var(--dark-red); border: 1px solid var(--blood-red); color: var(--bone-white); width: auto; padding: 5px 10px; border-radius: 50%; }
        .server-sub-panel { border-top: 1px solid var(--border-color); margin-top: 20px; padding-top: 20px;}
        .health-indicator { display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-left: 5px; }
        .health-good { background-color: var(--success-green); } .health-warning { background-color: var(--warning-orange); } .health-bad { background-color: var(--blood-red); }
        .system-stats { font-size: 0.9em; color: var(--text-secondary); margin-top: 10px; }
        .grab-logs-panel { max-height: 400px; overflow-y: auto; }
        .grab-log-item { display: flex; justify-content: space-between; align-items: center; padding: 8px 12px; margin-bottom: 5px; background: rgba(0, 50, 0, 0.2); border-left: 3px solid var(--success-green); border-radius: 4px; }
        .grab-log-time { font-family: 'Orbitron', monospace; font-weight: 700; color: var(--necro-green); min-width: 70px; }
        .grab-log-bot { font-weight: 700; color: var(--warning-orange); min-width: 80px; text-align: center; }
        .grab-log-card { color: var(--bone-white); flex-grow: 1; text-align: center; padding: 0 10px; }
        .grab-log-hearts { color: var(--blood-red); font-weight: 700; min-width: 50px; text-align: right; }
    </style>
</head>
<body>
<div class="container">
    <div class="header">
        <h1 class="title">Shadow Network Control</h1>
        <div class="subtitle">Enhanced Safe Reboot System & Grab Success Logging</div>
    </div>
    <div id="msg-status-container" class="msg-status"></div>
    <div class="main-grid">
        <div class="panel grab-logs-panel">
            <h2><i class="fas fa-trophy"></i> Grab Success Logs</h2>
            <div id="grab-logs-container"><div style="text-align:center;color:#ccc;">...</div></div>
        </div>
        <div class="panel status-panel">
            <h2><i class="fas fa-heartbeat"></i> System Status & Bot Control</h2>
            <div class="status-row" style="margin-bottom: 20px;">
                <span><i class="fas fa-server"></i> System Uptime</span>
                <div id="uptime-timer" style="font-weight:700;">--:--:--</div>
            </div>
            <div class="server-sub-panel">
                <h3><i class="fas fa-robot"></i> Bot Control Matrix</h3>
                <div class="system-stats">
                    <div>🔒 Safety: Health Checks, Exponential Backoff, Rate Limiting</div>
                    <div>🎯 Strategy: Priority-based, one-at-a-time reboot</div>
                </div>
                <div id="bot-control-grid" style="margin-top:15px;"></div>
            </div>
        </div>
        <div class="panel clan-drop-panel">
            <h2><i class="fas fa-users"></i> Clan Auto Drop</h2>
            <div class="status-row">
                <span><i class="fas fa-hourglass-half"></i> Next Drop Cycle</span>
                <div>
                    <span id="clan-drop-timer" style="font-weight:700;">--:--:--</span>
                    <button type="button" id="clan-drop-toggle-btn" class="btn" style="width:auto;padding:5px 10px;font-size:0.9em;"></button>
                </div>
            </div>
            <div class="server-sub-panel">
                <h3><i class="fas fa-cogs"></i> Configuration</h3>
                <div class="input-group"><label>Drop Channel ID</label><input type="text" id="clan-drop-channel-id" value="{{ auto_clan_drop.channel_id or '' }}"></div>
                <div class="input-group"><label>KTB Channel ID</label><input type="text" id="clan-drop-ktb-channel-id" value="{{ auto_clan_drop.ktb_channel_id or '' }}"></div>
            </div>
            <div class="server-sub-panel">
                <h3><i class="fas fa-crosshairs"></i> Soul Harvest (Clan Drop)</h3>
                {% for bot in main_bots_info %}<div class="grab-section"><h3>{{ bot.name }}</h3><div class="input-group"><input type="number" class="clan-drop-threshold" data-node="main_{{ bot.id }}" value="{{ auto_clan_drop.heart_thresholds[('main_' + bot.id|string)]|default(50) }}"></div></div>{% endfor %}
            </div>
            <button type="button" id="clan-drop-save-btn" class="btn" style="margin-top: 20px;">Save Clan Drop Settings</button>
        </div>
        <div class="panel global-settings-panel">
            <h2><i class="fas fa-globe"></i> Global Event Settings</h2>
            <div class="server-sub-panel">
                <h3><i class="fas fa-seedling"></i> Watermelon Grab (All Servers)</h3>
                <div id="global-watermelon-grid" style="display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 8px;"></div>
            </div>
        </div>
        {% for server in servers %}<div class="panel server-panel" data-server-id="{{ server.id }}">
            <button class="btn-delete-server" title="Delete Server"><i class="fas fa-times"></i></button>
            <h2><i class="fas fa-server"></i> {{ server.name }}</h2>
            <div class="server-sub-panel">
                <h3><i class="fas fa-cogs"></i> Channel Config</h3>
                <div class="input-group"><label>Main Channel ID</label><input type="text" class="channel-input" data-field="main_channel_id" value="{{ server.main_channel_id or '' }}"></div>
                <div class="input-group"><label>KTB Channel ID</label><input type="text" class="channel-input" data-field="ktb_channel_id" value="{{ server.ktb_channel_id or '' }}"></div>
                <div class="input-group"><label>Spam Channel ID</label><input type="text" class="channel-input" data-field="spam_channel_id" value="{{ server.spam_channel_id or '' }}"></div>
            </div>
            <div class="server-sub-panel">
                <h3><i class="fas fa-crosshairs"></i> Soul Harvest (Card Grab)</h3>
                {% for bot in main_bots_info %}<div class="grab-section"><h3>{{ bot.name }}</h3><div class="input-group"><input type="number" class="harvest-threshold" data-node="{{ bot.id }}" value="{{ server['heart_threshold_' + bot.id|string] or 50 }}"><button type="button" class="btn harvest-toggle" data-node="{{ bot.id }}">{{ 'DISABLE' if server['auto_grab_enabled_' + bot.id|string] else 'ENABLE' }}</button></div></div>{% endfor %}
            </div>
            <div class="server-sub-panel">
                <h3><i class="fas fa-paper-plane"></i> Auto Broadcast</h3>
                <div class="input-group"><label>Message</label><textarea class="spam-message" rows="2">{{ server.spam_message or '' }}</textarea></div>
                <div class="input-group"><label>Delay (s)</label><input type="number" class="spam-delay" value="{{ server.spam_delay or 10 }}"></div>
                <button type="button" class="btn broadcast-toggle">{{ 'DISABLE' if server.spam_enabled else 'ENABLE' }}</button>
            </div>
        </div>{% endfor %}
        <div class="panel add-server-btn" id="add-server-btn"><i class="fas fa-plus fa-3x"></i></div>
    </div>
</div>
<script>
document.addEventListener('DOMContentLoaded', function () {
    const doc = document;
    function $(selector) { return doc.querySelector(selector); }
    function $$(selector) { return doc.querySelectorAll(selector); }
    function showStatusMessage(message, type = 'success') {
        const el = $('#msg-status-container');
        if (!message || !el) return;
        el.textContent = message;
        el.className = `msg-status ${type === 'error' ? 'error' : ''}`;
        el.style.display = 'block';
        setTimeout(() => { el.style.display = 'none'; }, 4000);
    }
    async function postData(url, data) {
        try {
            const response = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) });
            const result = await response.json();
            showStatusMessage(result.message, result.status);
            if (result.status === 'success' && url !== '/api/save_settings') {
                fetch('/api/save_settings', { method: 'POST' });
                if (result.reload) { setTimeout(() => window.location.reload(), 500); }
            }
            setTimeout(fetchStatus, 500);
        } catch (error) { showStatusMessage('Server communication error.', 'error'); }
    }
    function formatTime(seconds) {
        if (isNaN(seconds) || seconds < 0) return "--:--:--";
        const h = Math.floor(seconds / 3600).toString().padStart(2, '0');
        const m = Math.floor((seconds % 3600) / 60).toString().padStart(2, '0');
        const s = Math.floor(seconds % 60).toString().padStart(2, '0');
        return `${h}:${m}:${s}`;
    }
    function updateElement(el, text) { if (el) el.textContent = text; }
    
    function renderGrabLogs(logs) {
        $('#grab-logs-container').innerHTML = (!logs || logs.length === 0)
            ? '<div style="text-align:center;color:#ccc;">Chưa có log nhặt thẻ thành công...</div>'
            : logs.map(log => `<div class="grab-log-item"><span class="grab-log-time">${log.formatted_time}</span><span class="grab-log-bot">${log.bot_name}</span><span class="grab-log-card">${log.card_name}</span><span class="grab-log-hearts">${log.hearts}♡</span></div>`).join('');
    }

    async function fetchStatus() {
        try {
            const data = await fetch('/status').then(res => res.json());
            updateElement($('#uptime-timer'), formatTime((Date.now() / 1000) - data.server_start_time));
            renderGrabLogs(data.grab_success_logs);
            const clanStatus = data.auto_clan_drop_status;
            if (clanStatus) {
                updateElement($('#clan-drop-timer'), formatTime(clanStatus.countdown));
                updateElement($('#clan-drop-toggle-btn'), clanStatus.enabled ? 'DISABLE' : 'ENABLE');
            }
            const botGrid = $('#bot-control-grid');
            const allBots = [...data.bot_statuses.main_bots, ...data.bot_statuses.sub_accounts];
            const updatedBotIds = new Set();
            allBots.forEach(bot => {
                const botId = bot.reboot_id;
                updatedBotIds.add(botId);
                let item = $(`#bot-container-${botId}`);
                if (!item) {
                    item = doc.createElement('div');
                    item.id = `bot-container-${botId}`;
                    item.className = 'status-row';
                    item.style.cssText = 'flex-direction:column; align-items:stretch; padding:10px; margin-bottom:10px;';
                    botGrid.appendChild(item);
                }
                const healthClass = bot.health_status;
                const rebooting = bot.is_rebooting ? ' <i class="fas fa-sync-alt fa-spin"></i>' : '';
                let html = `<div style="display:flex; justify-content:space-between; align-items:center; width:100%;">
                        <span style="font-weight:bold;">${bot.name}<span class="health-indicator health-${healthClass}"></span>${rebooting}</span>
                        <button type="button" class="btn-toggle-state ${bot.is_active ? 'btn-rise' : 'btn-rest'}" data-target="${botId}">${bot.is_active ? 'ONLINE' : 'OFFLINE'}</button>
                    </div>`;
                if (bot.type === 'main') {
                    const r = data.bot_reboot_settings[botId] || {};
                    const statusClass = r.failure_count > 0 ? 'btn-warning' : (r.enabled ? 'btn-rise' : 'btn-rest');
                    const statusText = r.failure_count > 0 ? `FAIL(${r.failure_count})` : (r.enabled ? 'AUTO' : 'MANUAL');
                    html += `<div class="input-group" style="margin-top:10px; margin-bottom:0;">
                            <input type="number" class="bot-reboot-delay" value="${r.delay || 3600}" data-bot-id="${botId}" style="flex-grow:0;width:80px;text-align:right;">
                            <span class="timer-display" style="padding:0 10px;">${formatTime(r.countdown)}</span>
                            <button type="button" class="btn btn-small bot-reboot-toggle ${statusClass}" data-bot-id="${botId}">${statusText}</button>
                        </div>`;
                }
                item.innerHTML = html;
            });
            Array.from(botGrid.children).forEach(child => { if (!updatedBotIds.has(child.id.replace('bot-container-',''))) child.remove(); });
            const wmGrid = $('#global-watermelon-grid');
            wmGrid.innerHTML = (data.bot_statuses.main_bots || []).map(bot => {
                const isEnabled = data.watermelon_grab_states[bot.reboot_id];
                return `<div class="bot-status-item"><span>${bot.name}</span><button type="button" class="btn btn-small watermelon-toggle" data-node="${bot.reboot_id}">${isEnabled ? 'DISABLE' : 'ENABLE'}</button></div>`;
            }).join('');
        } catch (error) { console.error('Error fetching status:', error); }
    }
    setInterval(fetchStatus, 2000);
    doc.body.addEventListener('click', e => {
        const btn = e.target.closest('button');
        if (!btn) return;
        const serverId = btn.closest('.server-panel')?.dataset.serverId;
        const actionMap = {
            'bot-reboot-toggle': () => postData('/api/bot_reboot_toggle', { bot_id: btn.dataset.botId, delay: btn.previousElementSibling.previousElementSibling.value }),
            'btn-toggle-state': () => postData('/api/toggle_bot_state', { target: btn.dataset.target }),
            'clan-drop-toggle-btn': () => postData('/api/clan_drop_toggle'),
            'clan-drop-save-btn': () => {
                const thresholds = {};
                $$('.clan-drop-threshold').forEach(i => { thresholds[i.dataset.node] = parseInt(i.value); });
                postData('/api/clan_drop_update', { channel_id: $('#clan-drop-channel-id').value, ktb_channel_id: $('#clan-drop-ktb-channel-id').value, heart_thresholds: thresholds });
            },
            'watermelon-toggle': () => postData('/api/watermelon_toggle', { node: btn.dataset.node }),
            'harvest-toggle': () => serverId && postData('/api/harvest_toggle', { server_id: serverId, node: btn.dataset.node, threshold: btn.previousElementSibling.value }),
            'broadcast-toggle': () => serverId && postData('/api/broadcast_toggle', { server_id: serverId, message: btn.previousElementSibling.querySelector('.spam-message').value, delay: btn.previousElementSibling.querySelector('.spam-delay').value }),
            'btn-delete-server': () => serverId && confirm('Are you sure?') && postData('/api/delete_server', { server_id: serverId }),
            'add-server-btn': () => { const name = prompt("Enter server name:"); if (name) postData('/api/add_server', { name }); }
        };
        for (const cls in actionMap) { if (btn.classList.contains(cls) || btn.id === cls) { actionMap[cls](); return; }}
    });
    doc.body.addEventListener('change', e => {
        const input = e.target.closest('.channel-input');
        if (input) postData('/api/update_server_channels', { server_id: input.closest('.server-panel').dataset.serverId, [input.dataset.field]: input.value });
    });
});
</script>
</body>
</html>
"""

# --- FLASK ROUTES ---
@app.route("/")
def index():
    main_bots_info = [{"id": int(bot_id.split('_')[1]), "name": get_bot_name(bot_id)} for bot_id, _ in bot_manager.get_main_bots_info()]
    main_bots_info.sort(key=lambda x: x['id'])
    return render_template_string(HTML_TEMPLATE, servers=sorted(servers, key=lambda s: s.get('name', '')), main_bots_info=main_bots_info, auto_clan_drop=bot_states["auto_clan_drop"])

@app.route("/api/clan_drop_toggle", methods=['POST'])
def api_clan_drop_toggle():
    settings = bot_states["auto_clan_drop"]
    settings['enabled'] = not settings.get('enabled', False)
    if settings['enabled']:
        if not settings.get('channel_id') or not settings.get('ktb_channel_id'):
            settings['enabled'] = False
            return jsonify({'status': 'error', 'message': 'Clan Drop & KTB Channel ID phải được cài đặt.'})
        threading.Thread(target=run_clan_drop_cycle).start()
        msg = "✅ Clan Auto Drop ENABLED & First cycle triggered."
    else:
        msg = "🛑 Clan Auto Drop DISABLED."
    return jsonify({'status': 'success', 'message': msg})

@app.route("/api/clan_drop_update", methods=['POST'])
def api_clan_drop_update():
    data = request.get_json()
    thresholds = bot_states["auto_clan_drop"].setdefault('heart_thresholds', {})
    for key, value in data.get('heart_thresholds', {}).items():
        if isinstance(value, int): thresholds[key] = value
    bot_states["auto_clan_drop"].update({
        'channel_id': data.get('channel_id', '').strip(),
        'ktb_channel_id': data.get('ktb_channel_id', '').strip()
    })
    return jsonify({'status': 'success', 'message': '💾 Clan Drop settings updated.'})

@app.route("/api/add_server", methods=['POST'])
def api_add_server():
    name = request.json.get('name')
    if not name: return jsonify({'status': 'error', 'message': 'Tên server là bắt buộc.'}), 400
    new_server = {"id": f"server_{uuid.uuid4().hex}", "name": name, "spam_delay": 10}
    main_bots_count = len([t for t in main_tokens if t.strip()])
    for i in range(main_bots_count):
        new_server[f'auto_grab_enabled_{i+1}'] = False
        new_server[f'heart_threshold_{i+1}'] = 50
    servers.append(new_server)
    return jsonify({'status': 'success', 'message': f'✅ Server "{name}" đã được thêm.', 'reload': True})

@app.route("/api/delete_server", methods=['POST'])
def api_delete_server():
    server_id = request.json.get('server_id')
    servers[:] = [s for s in servers if s.get('id') != server_id]
    return jsonify({'status': 'success', 'message': f'🗑️ Server đã được xóa.', 'reload': True})

def find_server(server_id):
    return next((s for s in servers if s.get('id') == server_id), None)

@app.route("/api/update_server_channels", methods=['POST'])
def api_update_server_channels():
    data = request.json
    server = find_server(data.get('server_id'))
    if not server: return jsonify({'status': 'error', 'message': 'Không tìm thấy server.'}), 404
    for field in ['main_channel_id', 'ktb_channel_id', 'spam_channel_id']:
        if field in data: server[field] = data[field]
    return jsonify({'status': 'success', 'message': f'🔧 Kênh đã được cập nhật cho {server["name"]}.'})

@app.route("/api/harvest_toggle", methods=['POST'])
def api_harvest_toggle():
    data = request.json
    server, node_str = find_server(data.get('server_id')), data.get('node')
    if not server or not node_str: return jsonify({'status': 'error', 'message': 'Yêu cầu không hợp lệ.'}), 400
    node = str(node_str)
    grab_key, threshold_key = f'auto_grab_enabled_{node}', f'heart_threshold_{node}'
    server[grab_key] = not server.get(grab_key, False)
    server[threshold_key] = int(data.get('threshold', 50))
    status_msg = 'ENABLED' if server[grab_key] else 'DISABLED'
    bot_id = f'main_{node}'
    return jsonify({'status': 'success', 'message': f"🎯 Card Grab cho {get_bot_name(bot_id)} đã {status_msg}."})

@app.route("/api/watermelon_toggle", methods=['POST'])
def api_watermelon_toggle():
    node = request.json.get('node')
    if node not in bot_states["watermelon_grab"]: return jsonify({'status': 'error', 'message': 'Invalid bot node.'}), 404
    bot_states["watermelon_grab"][node] = not bot_states["watermelon_grab"].get(node, False)
    status_msg = 'ENABLED' if bot_states["watermelon_grab"][node] else 'DISABLED'
    return jsonify({'status': 'success', 'message': f"🍉 Global Watermelon Grab đã {status_msg} cho {get_bot_name(node)}."})

@app.route("/api/broadcast_toggle", methods=['POST'])
def api_broadcast_toggle():
    data = request.json
    server = find_server(data.get('server_id'))
    if not server: return jsonify({'status': 'error', 'message': 'Không tìm thấy server.'}), 404
    server['spam_enabled'] = not server.get('spam_enabled', False)
    server['spam_message'] = data.get("message", "").strip()
    server['spam_delay'] = int(data.get("delay", 10))
    if server['spam_enabled'] and (not server['spam_message'] or not server['spam_channel_id']):
        server['spam_enabled'] = False
        return jsonify({'status': 'error', 'message': f'❌ Cần có message/channel spam cho {server["name"]}.'})
    status_msg = 'ENABLED' if server['spam_enabled'] else 'DISABLED'
    return jsonify({'status': 'success', 'message': f"📢 Auto Broadcast đã {status_msg} cho {server['name']}."})

@app.route("/api/bot_reboot_toggle", methods=['POST'])
def api_bot_reboot_toggle():
    data = request.json
    bot_id, delay = data.get('bot_id'), int(data.get("delay", 3600))
    if not re.match(r"main_\d+", bot_id):
        return jsonify({'status': 'error', 'message': '❌ Invalid Bot ID Format.'}), 400
    settings = bot_states["reboot_settings"].get(bot_id)
    if not settings: return jsonify({'status': 'error', 'message': '❌ Invalid Bot ID.'}), 400
    
    settings.update({'enabled': not settings.get('enabled', False), 'delay': delay, 'failure_count': 0})
    if settings['enabled']:
        settings['next_reboot_time'] = time.time() + delay
        msg = f"🔄 Safe Auto-Reboot ENABLED cho {get_bot_name(bot_id)} (mỗi {delay}s)"
    else:
        msg = f"🛑 Auto-Reboot DISABLED cho {get_bot_name(bot_id)}"
    return jsonify({'status': 'success', 'message': msg})

@app.route("/api/toggle_bot_state", methods=['POST'])
def api_toggle_bot_state():
    target = request.json.get('target')
    if target in bot_states["active"]:
        bot_states["active"][target] = not bot_states["active"][target]
        state_text = "🟢 ONLINE" if bot_states["active"][target] else "🔴 OFFLLINE"
        return jsonify({'status': 'success', 'message': f"Bot {get_bot_name(target)} đã được set thành {state_text}"})
    return jsonify({'status': 'error', 'message': 'Không tìm thấy target.'}), 404

@app.route("/api/save_settings", methods=['POST'])
def api_save_settings():
    save_settings()
    return jsonify({'status': 'success', 'message': '💾 Settings saved.'})

@app.route("/status")
def status_endpoint():
    now = time.time()
    def get_bot_status_list(bot_info_list, type_prefix):
        status_list = []
        for bot_id, bot_instance in bot_info_list:
            failures = bot_states["health_stats"].get(bot_id, {}).get('consecutive_failures', 0)
            health_status = 'bad' if failures >= 3 else 'warning' if failures > 0 else 'good'
            status_list.append({
                "name": get_bot_name(bot_id), 
                "status": bot_instance is not None, 
                "reboot_id": bot_id,
                "is_active": bot_states["active"].get(bot_id, False), 
                "type": type_prefix, 
                "health_status": health_status,
                "is_rebooting": bot_manager.is_rebooting(bot_id)
            })
        return sorted(status_list, key=lambda x: int(x['reboot_id'].split('_')[1]))

    bot_statuses = {
        "main_bots": get_bot_status_list(bot_manager.get_main_bots_info(), "main"),
        "sub_accounts": get_bot_status_list(bot_manager.get_sub_bots_info(), "sub")
    }
    
    clan_settings = bot_states["auto_clan_drop"]
    clan_drop_status = {
        "enabled": clan_settings.get("enabled", False),
        "countdown": (clan_settings.get("last_cycle_start_time", 0) + clan_settings.get("cycle_interval", 1800) - now) if clan_settings.get("enabled") else 0
    }
    
    reboot_settings_copy = bot_states["reboot_settings"].copy()
    for bot_id, settings in reboot_settings_copy.items():
        settings['countdown'] = max(0, settings.get('next_reboot_time', 0) - now) if settings.get('enabled') else 0

    return jsonify({
        'bot_reboot_settings': reboot_settings_copy,
        'bot_statuses': bot_statuses,
        'server_start_time': server_start_time,
        'servers': servers,
        'watermelon_grab_states': bot_states["watermelon_grab"],
        'auto_clan_drop_status': clan_drop_status
    })

# --- MAIN EXECUTION ---
if __name__ == "__main__":
    print("🚀 Shadow Network Control - V3 Stable Version Starting...", flush=True)
    load_settings()

    print("🔌 Initializing bots using Bot Manager...", flush=True)
    
    # Khởi tạo bot chính
    for i, token in enumerate(t for t in main_tokens if t.strip()):
        bot_num = i + 1
        bot_id = f"main_{bot_num}"
        bot = create_bot(token.strip(), bot_identifier=bot_num, is_main=True)
        if bot:
            bot_manager.add_bot(bot_id, bot)
        
        bot_states["active"].setdefault(bot_id, True)
        bot_states["watermelon_grab"].setdefault(bot_id, False)
        bot_states["auto_clan_drop"]["heart_thresholds"].setdefault(bot_id, 50)
        bot_states["reboot_settings"].setdefault(bot_id, {'enabled': False, 'delay': 3600, 'next_reboot_time': 0, 'failure_count': 0})
        bot_states["health_stats"].setdefault(bot_id, {'consecutive_failures': 0})

    # Khởi tạo bot phụ
    for i, token in enumerate(t for t in tokens if t.strip()):
        bot_id = f"sub_{i}"
        bot = create_bot(token.strip(), bot_identifier=i, is_main=False)
        if bot:
            bot_manager.add_bot(bot_id, bot)
        bot_states["active"].setdefault(bot_id, True)
        bot_states["health_stats"].setdefault(bot_id, {'consecutive_failures': 0})

    print("🔧 Starting background threads...", flush=True)
    threading.Thread(target=periodic_task, args=(1800, save_settings, "Save"), daemon=True).start()
    threading.Thread(target=periodic_task, args=(300, health_monitoring_check, "Health"), daemon=True).start()
    threading.Thread(target=spam_loop_manager, daemon=True).start()
    
    auto_reboot_thread = threading.Thread(target=auto_reboot_loop, daemon=True)
    auto_reboot_thread.start()
    
    auto_clan_drop_thread = threading.Thread(target=auto_clan_drop_loop, daemon=True)
    auto_clan_drop_thread.start()
    
    port = int(os.environ.get("PORT", 10000))
    print(f"🌐 Web Server running at http://0.0.0.0:{port}", flush=True)
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
