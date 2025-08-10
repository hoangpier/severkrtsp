# PHIÊN BẢN HOÀN CHỈNH - KẾT HỢP VIP STABLE & LOGGING FEATURE (FIXED)
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
BOT_USER_IDS = {} # FIX: Thêm từ điển toàn cục để lưu ID người dùng của bot
stop_events = {"reboot": threading.Event(), "clan_drop": threading.Event()}
server_start_time = time.time()

# --- CARD GRAB LOGGING SYSTEM (TÍNH NĂNG MỚI ĐÃ SỬA LỖI) ---
class CardGrabLogger:
    def __init__(self, max_logs=200):
        self.logs = deque(maxlen=max_logs)
        self.lock = threading.RLock()
        self.grab_attempts = {}
        
    def log_grab_attempt(self, bot_id, channel_id, message_id, card_line, hearts, emoji):
        with self.lock:
            timestamp = datetime.now()
            self.grab_attempts[message_id] = {'bot_id': bot_id, 'channel_id': channel_id, 'timestamp': timestamp, 'card_line': card_line, 'hearts': hearts, 'emoji': emoji, 'status': 'attempting'}
            self.logs.append({'id': f"attempt_{message_id}_{bot_id}", 'timestamp': timestamp, 'bot_name': get_bot_name(bot_id), 'bot_id': bot_id, 'action': 'grab_attempt', 'hearts': hearts, 'card_line': card_line, 'emoji': emoji, 'status': 'attempting', 'message_id': message_id, 'channel_id': channel_id})
    
    def log_grab_result(self, bot_id, channel_id, message_id, success, result_type, hearts=None, card_info=None):
        with self.lock:
            timestamp = datetime.now()
            attempt = self.grab_attempts.get(message_id, {})
            hearts = hearts or attempt.get('hearts', 0)
            card_info = card_info or f"Line {attempt.get('card_line', '?')}"
            self.logs.append({'id': f"result_{message_id}_{bot_id}", 'timestamp': timestamp, 'bot_name': get_bot_name(bot_id), 'bot_id': bot_id, 'action': 'grab_result', 'hearts': hearts, 'card_info': card_info, 'status': 'success' if success else 'failed', 'result_type': result_type, 'message_id': message_id, 'channel_id': channel_id})
            if message_id in self.grab_attempts: self.grab_attempts[message_id]['status'] = 'success' if success else 'failed'
    
    def log_watermelon_grab(self, bot_id, channel_id, message_id, success):
        with self.lock:
            self.logs.append({'id': f"watermelon_{message_id}_{bot_id}", 'timestamp': datetime.now(), 'bot_name': get_bot_name(bot_id), 'bot_id': bot_id, 'action': 'watermelon_grab', 'hearts': 0, 'card_info': '🍉 Watermelon', 'status': 'success' if success else 'failed', 'result_type': 'watermelon', 'message_id': message_id, 'channel_id': channel_id})
    
    def get_recent_logs(self, limit=50):
        with self.lock: return list(reversed(list(self.logs)))[:limit]
    
    def get_stats(self, hours=24):
        with self.lock:
            cutoff_time = datetime.now() - timedelta(hours=hours)
            recent_logs = [log for log in self.logs if log['timestamp'] > cutoff_time]
            stats = {
                'total_attempts': len([l for l in recent_logs if l['action'] == 'grab_attempt']),
                'successful_grabs': len([l for l in recent_logs if l['action'] == 'grab_result' and l['status'] == 'success']),
                'failed_grabs': len([l for l in recent_logs if l['action'] == 'grab_result' and l['status'] == 'failed']),
                'watermelon_grabs': len([l for l in recent_logs if l['action'] == 'watermelon_grab' and l['status'] == 'success']),
                'bot_stats': {},
                'high_heart_grabs': len([l for l in recent_logs if l['action'] == 'grab_result' and l['status'] == 'success' and l.get('hearts', 0) >= 100])
            }
            for log in recent_logs:
                bot_name = log['bot_name']
                if bot_name not in stats['bot_stats']: stats['bot_stats'][bot_name] = {'attempts': 0, 'successes': 0, 'watermelons': 0}
                if log['action'] == 'grab_attempt': stats['bot_stats'][bot_name]['attempts'] += 1
                elif log['action'] == 'grab_result' and log['status'] == 'success': stats['bot_stats'][bot_name]['successes'] += 1
                elif log['action'] == 'watermelon_grab' and log['status'] == 'success': stats['bot_stats'][bot_name]['watermelons'] += 1
            return stats
card_logger = CardGrabLogger()

# --- QUẢN LÝ BOT THREAD-SAFE ---
class ThreadSafeBotManager:
    def __init__(self):
        self._bots, self._rebooting, self._lock = {}, set(), threading.RLock()
    def add_bot(self, bot_id, bot_instance):
        with self._lock: self._bots[bot_id] = bot_instance; print(f"[Bot Manager] ✅ Added bot {bot_id}", flush=True)
    def remove_bot(self, bot_id):
        with self._lock:
            bot = self._bots.pop(bot_id, None)
            if bot and hasattr(bot, 'gateway') and hasattr(bot.gateway, 'close'):
                try: bot.gateway.close()
                except Exception as e: print(f"[Bot Manager] ⚠️ Error closing gateway for {bot_id}: {e}", flush=True)
            print(f"[Bot Manager] 🗑️ Removed bot {bot_id}", flush=True)
    def get_bot(self, bot_id):
        with self._lock: return self._bots.get(bot_id)
    def get_all_bots(self):
        with self._lock: return list(self._bots.items())
    def get_main_bots_info(self):
        with self._lock: return [(k, v) for k, v in self._bots.items() if k.startswith('main_')]
    def get_sub_bots_info(self):
        with self._lock: return [(k, v) for k, v in self._bots.items() if k.startswith('sub_')]
    def is_rebooting(self, bot_id):
        with self._lock: return bot_id in self._rebooting
    def start_reboot(self, bot_id):
        with self._lock:
            if self.is_rebooting(bot_id): return False
            self._rebooting.add(bot_id); return True
    def end_reboot(self, bot_id):
        with self._lock: self._rebooting.discard(bot_id)
bot_manager = ThreadSafeBotManager()

# --- LƯU & TẢI CÀI ĐẶT ---
def save_settings():
    api_key, bin_id = os.getenv("JSONBIN_API_KEY"), os.getenv("JSONBIN_BIN_ID")
    settings_data = {'servers': servers, 'bot_states': bot_states, 'last_save_time': time.time()}
    if api_key and bin_id:
        try:
            req = requests.put(f"https://api.jsonbin.io/v3/b/{bin_id}", json=settings_data, headers={'Content-Type': 'application/json', 'X-Master-Key': api_key}, timeout=15)
            if req.status_code == 200: return print("[Settings] ✅ Đã lưu cài đặt lên JSONBin.io.", flush=True)
        except Exception as e: print(f"[Settings] ❌ Lỗi JSONBin: {e}, đang lưu local.", flush=True)
    try:
        with open('backup_settings.json', 'w') as f: json.dump(settings_data, f, indent=2)
        print("[Settings] ✅ Đã lưu backup cài đặt locally.", flush=True)
    except Exception as e: print(f"[Settings] ❌ Lỗi khi lưu backup local: {e}", flush=True)

def load_settings():
    global servers, bot_states
    def load_from_dict(settings):
        try:
            servers.extend(settings.get('servers', []))
            for key, value in settings.get('bot_states', {}).items():
                if key in bot_states and isinstance(value, dict): bot_states[key].update(value)
            return True
        except Exception: return False
    api_key, bin_id = os.getenv("JSONBIN_API_KEY"), os.getenv("JSONBIN_BIN_ID")
    if api_key and bin_id:
        try:
            req = requests.get(f"https://api.jsonbin.io/v3/b/{bin_id}/latest", headers={'X-Master-Key': api_key}, timeout=15)
            if req.status_code == 200 and load_from_dict(req.json().get("record", {})):
                return print("[Settings] ✅ Đã tải cài đặt từ JSONBin.io.", flush=True)
        except Exception: pass
    try:
        with open('backup_settings.json', 'r') as f:
            if load_from_dict(json.load(f)): return print("[Settings] ✅ Đã tải cài đặt từ backup file.", flush=True)
    except FileNotFoundError: print("[Settings] ⚠️ Không tìm thấy backup file.", flush=True)
    except Exception: print(f"[Settings] ⚠️ Lỗi tải backup.", flush=True)

# --- HÀM TRỢ GIÚP & LOGIC BOT ---
def get_bot_name(bot_id_str):
    try:
        b_type, b_index = bot_id_str.split('_')[0], int(bot_id_str.split('_')[1])
        if b_type == 'main': return BOT_NAMES[b_index - 1] if 0 < b_index <= len(BOT_NAMES) else f"MAIN_{b_index}"
        return acc_names[b_index] if b_index < len(acc_names) else f"SUB_{b_index+1}"
    except: return bot_id_str.upper()

def _find_and_select_card(bot, channel_id, last_drop_msg_id, heart_threshold, bot_num, ktb_channel_id):
    bot_id = f'main_{bot_num}'
    for _ in range(7):
        time.sleep(0.5)
        try:
            messages = bot.getMessages(channel_id, num=5).json()
            if not isinstance(messages, list): continue
            for msg_item in messages:
                if msg_item.get("author", {}).get("id") == karibbit_id and int(msg_item.get("id", 0)) > int(last_drop_msg_id):
                    desc = msg_item.get("embeds", [{}])[0].get("description", "")
                    if '♡' not in desc: continue
                    lines, hearts = desc.split('\n')[:3], []
                    for line in lines: hearts.append(int(re.search(r'♡(\d+)', line).group(1)) if re.search(r'♡(\d+)', line) else 0)
                    if not any(hearts): break
                    max_h = max(hearts)
                    if max_h >= heart_threshold:
                        idx = hearts.index(max_h)
                        delays = {1: [0.4, 1.4, 2.1], 2: [0.7, 1.8, 2.4], 3: [0.7, 1.8, 2.4], 4: [0.8, 1.9, 2.5]}
                        emoji, delay = ["1️⃣", "2️⃣", "3️⃣"][idx], delays.get(bot_num, [0.9, 2.0, 2.6])[idx]
                        print(f"[CARD GRAB|Bot {bot_num}] Dòng {idx+1} ({max_h}♡) -> {emoji} sau {delay}s", flush=True)
                        card_logger.log_grab_attempt(bot_id, channel_id, last_drop_msg_id, idx+1, max_h, emoji)
                        def grab_action():
                            try:
                                bot.addReaction(channel_id, last_drop_msg_id, emoji)
                                if ktb_channel_id: time.sleep(1.2); bot.sendMessage(ktb_channel_id, "kt b")
                            except Exception: pass
                        threading.Timer(delay, grab_action).start()
                        return
        except Exception: pass

def handle_clan_drop(bot, msg, bot_num):
    clan_settings = bot_states["auto_clan_drop"]
    if clan_settings.get("enabled") and msg.get("channel_id") == clan_settings.get("channel_id"):
        threshold = clan_settings.get("heart_thresholds", {}).get(f'main_{bot_num}', 50)
        threading.Thread(target=_find_and_select_card, args=(bot, clan_settings["channel_id"], msg["id"], threshold, bot_num, clan_settings["ktb_channel_id"]), daemon=True).start()

def handle_grab(bot, msg, bot_num):
    channel_id = msg.get("channel_id")
    server = next((s for s in servers if s.get('main_channel_id') == channel_id), None)
    if not server: return
    bot_id_str = f'main_{bot_num}'
    if server.get(f'auto_grab_enabled_{bot_num}', False):
        threshold = server.get(f'heart_threshold_{bot_num}', 50)
        threading.Thread(target=_find_and_select_card, args=(bot, channel_id, msg["id"], threshold, bot_num, server.get('ktb_channel_id')), daemon=True).start()
    if bot_states["watermelon_grab"].get(bot_id_str, False):
        def check_watermelon():
            time.sleep(5)
            try:
                reactions = bot.getMessage(channel_id, msg["id"]).json()[0].get('reactions', [])
                if any('🍉' in r.get('emoji', {}).get('name', '') for r in reactions):
                    bot.addReaction(channel_id, msg["id"], "🍉")
                    card_logger.log_watermelon_grab(bot_id_str, channel_id, msg["id"], True)
            except Exception: card_logger.log_watermelon_grab(bot_id_str, channel_id, msg["id"], False)
        threading.Thread(target=check_watermelon, daemon=True).start()

def handle_karuta_result(bot, msg, bot_num):
    content, mentions, channel_id, bot_id = msg.get("content", "").lower(), msg.get("mentions", []), msg.get("channel_id"), f'main_{bot_num}'
    bot_user_id = BOT_USER_IDS.get(bot_id)
    if not bot_user_id or bot_user_id not in [m.get("id") for m in mentions]: return
    if "fought off" in content or "took the" in content:
        result_type = "fought_off" if "fought off" in content else "took_the"
        hearts = int(re.search(r'♡(\d+)', content).group(1)) if re.search(r'♡(\d+)', content) else 0
        card_logger.log_grab_result(bot_id, channel_id, str(int(time.time() * 1000)), True, result_type, hearts)

# --- HỆ THỐNG REBOOT & HEALTH CHECK ---
def check_bot_health(bot_instance, bot_id):
    stats = bot_states["health_stats"].setdefault(bot_id, {'consecutive_failures': 0})
    is_connected = bot_instance and hasattr(bot_instance.gateway, 'connected') and bot_instance.gateway.connected
    stats['consecutive_failures'] = 0 if is_connected else stats.get('consecutive_failures', 0) + 1
    if not is_connected: print(f"[Health Check] ⚠️ {bot_id} disconnected - fails: {stats['consecutive_failures']}", flush=True)

def handle_reboot_failure(bot_id):
    settings = bot_states["reboot_settings"].setdefault(bot_id, {})
    failures = settings.get('failure_count', 0) + 1; settings['failure_count'] = failures
    backoff = min(2 ** failures, 8); next_delay = max(600, settings.get('delay', 3600) / backoff) * backoff
    settings['next_reboot_time'] = time.time() + next_delay
    print(f"[Safe Reboot] 🔴 #{failures} fails for {bot_id}. Retry in {next_delay/60:.1f}m.", flush=True)
    if failures >= 5: settings['enabled'] = False; print(f"[Safe Reboot] ❌ Disabled for {bot_id} after 5 fails.", flush=True)

def safe_reboot_bot(bot_id):
    if not bot_manager.start_reboot(bot_id): return False
    print(f"[Safe Reboot] 🔄 Rebooting {bot_id}...", flush=True)
    try:
        bot_index = int(bot_id.split('_')[1]) - 1
        if not (0 <= bot_index < len(main_tokens)): raise IndexError("Bot index out of range")
        token = main_tokens[bot_index].strip()
        bot_manager.remove_bot(bot_id)
        settings = bot_states["reboot_settings"].get(bot_id, {})
        wait_time = random.uniform(20, 40) + min(settings.get('failure_count', 0) * 30, 300)
        time.sleep(wait_time)
        new_bot = create_bot(token, bot_identifier=(bot_index + 1), is_main=True)
        if not new_bot: raise Exception("Failed to create new bot instance.")
        bot_manager.add_bot(bot_id, new_bot)
        settings.update({'next_reboot_time': time.time() + settings.get('delay', 3600), 'failure_count': 0})
        bot_states["health_stats"][bot_id]['consecutive_failures'] = 0
        print(f"[Safe Reboot] ✅ {get_bot_name(bot_id)} rebooted.", flush=True)
        return True
    except Exception as e:
        print(f"[Safe Reboot] ❌ Reboot failed for {bot_id}: {e}", flush=True)
        handle_reboot_failure(bot_id); return False
    finally: bot_manager.end_reboot(bot_id)

# --- VÒNG LẶP NỀN ---
def auto_reboot_loop():
    last_reboot_time = 0
    while not stop_events["reboot"].is_set():
        try:
            now = time.time()
            if now - last_reboot_time < 600: time.sleep(60); continue
            bot_to_reboot, highest_priority = None, -1
            for bot_id, settings in dict(bot_states["reboot_settings"]).items():
                if not settings.get('enabled', False) or bot_manager.is_rebooting(bot_id): continue
                next_reboot = settings.get('next_reboot_time', 0)
                if now < next_reboot: continue
                failures = bot_states["health_stats"].get(bot_id, {}).get('consecutive_failures', 0)
                priority = (failures * 1000) + (now - next_reboot)
                if priority > highest_priority: highest_priority, bot_to_reboot = priority, bot_id
            if bot_to_reboot and safe_reboot_bot(bot_to_reboot):
                last_reboot_time = time.time(); time.sleep(random.uniform(300, 600))
            else: time.sleep(60)
        except Exception: time.sleep(120)

def auto_clan_drop_loop():
    while not stop_events["clan_drop"].is_set():
        s = bot_states["auto_clan_drop"]
        if s.get("enabled") and (time.time() - s.get("last_cycle_start_time", 0)) >= s.get("cycle_interval", 1800):
            active_bots = [(b, int(i.split('_')[1])) for i, b in bot_manager.get_main_bots_info() if b and bot_states["active"].get(i, False)]
            for bot, bot_num in active_bots:
                if stop_events["clan_drop"].is_set(): break
                try: bot.sendMessage(s["channel_id"], "kd"); time.sleep(random.uniform(110, 170))
                except Exception: pass
            s["last_cycle_start_time"] = time.time()
        time.sleep(60)

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
                    thread = threading.Thread(target=spam_for_server, args=(server, stop_event), daemon=True)
                    thread.start(); active_threads[server_id] = (thread, stop_event)
                elif not spam_on and server_id in active_threads: active_threads.pop(server_id)[1].set()
            time.sleep(5)
        except Exception: time.sleep(10)

def spam_for_server(server_config, stop_event):
    while not stop_event.is_set():
        try:
            active_bots = [b for i, b in bot_manager.get_all_bots() if b and bot_states["active"].get(i)]
            delay = server_config.get('spam_delay', 10)
            for bot in active_bots:
                if stop_event.is_set(): break
                try: bot.sendMessage(server_config['spam_channel_id'], server_config['spam_message']); time.sleep(random.uniform(1.5, 2.5))
                except Exception: pass
            time.sleep(random.uniform(delay * 0.9, delay * 1.1))
        except Exception: time.sleep(10)

def periodic_task_runner():
    while True:
        time.sleep(300); health_monitoring_check()
        time.sleep(1500); save_settings()

# --- KHỞI TẠO BOT (FIXED) ---
def create_bot(token, bot_identifier, is_main=False):
    try:
        bot = discum.Client(token=token, log=False)
        bot_id_str = f"main_{bot_identifier}" if is_main else f"sub_{bot_identifier}"
        @bot.gateway.command
        def on_ready(resp):
            if resp.event.ready:
                user = resp.raw.get("user", {})
                user_id = user.get('id', 'Unknown')
                if user_id != 'Unknown': BOT_USER_IDS[bot_id_str] = user_id # FIX: Store user ID in global dict
                print(f"[Bot] ✅ Logged in: {user_id} ({get_bot_name(bot_id_str)})", flush=True)
                bot_states["health_stats"].setdefault(bot_id_str, {}).update({'consecutive_failures': 0})
        if is_main:
            @bot.gateway.command
            def on_message(resp):
                if resp.event.message:
                    try:
                        msg = resp.parsed.auto()
                        author_id, content = msg.get("author", {}).get("id"), msg.get("content", "").lower()
                        if author_id != karuta_id: return
                        if "dropping" in content:
                            handler = handle_clan_drop if msg.get("mentions") else handle_grab
                            handler(bot, msg, bot_identifier)
                        elif ("fought off" in content or "took the" in content) and msg.get("mentions"):
                            handle_karuta_result(bot, msg, bot_identifier)
                    except Exception: pass
        
        threading.Thread(target=bot.gateway.run, kwargs={'auto_reconnect': True}, daemon=True).start()
        start_time = time.time()
        while time.time() - start_time < 20:
            if hasattr(bot.gateway, 'connected') and bot.gateway.connected: return bot
            time.sleep(0.5)
        bot.gateway.close()
        return None
    except Exception: return None

# --- FLASK APP & GIAO DIỆN ---
app = Flask(__name__)
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Shadow Network Control - Ultimate</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700;900&family=Courier+Prime:wght@400;700&family=Nosifer&display=swap" rel="stylesheet">
    <style>
        :root{--primary-bg:#0a0a0a;--secondary-bg:#1a1a1a;--panel-bg:#111111;--border-color:#333333;--blood-red:#8b0000;--dark-red:#550000;--bone-white:#f8f8ff;--necro-green:#228b22;--text-primary:#f0f0f0;--text-secondary:#cccccc;--warning-orange:#ff8c00;--success-green:#32cd32;--attempt-blue:#4169e1;--success-gold:#ffd700;--fail-red:#dc143c;--watermelon-pink:#ff69b4}body{font-family:'Courier Prime',monospace;background:var(--primary-bg);color:var(--text-primary);margin:0;padding:0}.container{max-width:1800px;margin:0 auto;padding:20px}.header{text-align:center;margin-bottom:30px;padding:20px;border-bottom:2px solid var(--blood-red)}.title{font-family:'Nosifer',cursive;font-size:3rem;color:var(--blood-red)}.subtitle{font-family:'Orbitron',sans-serif;font-size:1rem;color:var(--necro-green);margin-top:10px}.main-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(500px,1fr));gap:20px}.panel{background:var(--panel-bg);border:1px solid var(--border-color);border-radius:10px;padding:25px;position:relative}.panel h2{font-family:'Orbitron',cursive;font-size:1.4rem;margin-bottom:20px;text-transform:uppercase;border-bottom:2px solid;padding-bottom:10px;color:var(--bone-white)}.panel h2 i{margin-right:10px}.btn{background:var(--secondary-bg);border:1px solid var(--border-color);color:var(--text-primary);padding:10px 15px;border-radius:4px;cursor:pointer;font-family:'Orbitron',monospace;font-weight:700;text-transform:uppercase;width:100%;transition:all .3s ease}.btn:hover{background:var(--dark-red);border-color:var(--blood-red)}.btn-small{padding:5px 10px;font-size:.9em}.input-group{display:flex;align-items:stretch;gap:10px;margin-bottom:15px}.input-group label{background:#000;border:1px solid var(--border-color);border-right:0;padding:10px 15px;border-radius:4px 0 0 4px;display:flex;align-items:center;min-width:120px}.input-group input,.input-group textarea{flex-grow:1;background:#000;border:1px solid var(--border-color);color:var(--text-primary);padding:10px 15px;border-radius:0 4px 4px 0;font-family:'Courier Prime',monospace}.grab-section{display:flex;justify-content:space-between;align-items:center;margin-bottom:15px;padding:15px;background:rgba(0,0,0,.2);border-radius:8px}.grab-section h3{margin:0;width:80px;flex-shrink:0}.grab-section .input-group{margin-bottom:0;flex-grow:1;margin-left:20px}.msg-status{text-align:center;color:var(--necro-green);padding:12px;border:1px dashed var(--border-color);border-radius:4px;margin-bottom:20px;display:none}.msg-status.error{color:var(--blood-red);border-color:var(--blood-red)}.status-panel,.global-settings-panel,.clan-drop-panel,.card-log-panel{grid-column:1 / -1}.status-row{display:flex;justify-content:space-between;align-items:center;padding:12px;background:rgba(0,0,0,.4);border-radius:8px}.timer-display{font-size:1.2em;font-weight:700}.bot-status-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:8px}.btn-toggle-state{padding:3px 5px;font-size:.9em;border-radius:4px;cursor:pointer;text-transform:uppercase;background:transparent;font-weight:700;border:none}.btn-rise{color:var(--success-green)}.btn-rest{color:var(--dark-red)}.add-server-btn{display:flex;align-items:center;justify-content:center;min-height:200px;border:2px dashed var(--border-color);cursor:pointer;transition:all .3s ease}.add-server-btn:hover{background:var(--secondary-bg);border-color:var(--blood-red)}.add-server-btn i{font-size:3rem;color:var(--text-secondary)}.btn-delete-server{position:absolute;top:15px;right:15px;background:var(--dark-red);border:1px solid var(--blood-red);color:var(--bone-white);width:auto;padding:5px 10px;border-radius:50%}.server-sub-panel{border-top:1px solid var(--border-color);margin-top:20px;padding-top:20px}.flex-row{display:flex;gap:10px;align-items:center}.health-indicator{display:inline-block;width:10px;height:10px;border-radius:50%;margin-left:5px}.health-good{background-color:var(--success-green)}.health-warning{background-color:var(--warning-orange)}.health-bad{background-color:var(--blood-red)}.system-stats{font-size:.9em;color:var(--text-secondary);margin-top:10px}.log-container{max-height:500px;overflow-y:auto;border:1px solid var(--border-color);border-radius:8px;padding:15px;background:rgba(0,0,0,.2)}.log-entry{display:flex;justify-content:space-between;align-items:center;padding:8px 12px;margin-bottom:5px;border-radius:6px;font-size:.9em}.log-entry.attempt{background:rgba(65,105,225,.1);border-left:4px solid var(--attempt-blue)}.log-entry.success{background:rgba(255,215,0,.1);border-left:4px solid var(--success-gold)}.log-entry.failed{background:rgba(220,20,60,.1);border-left:4px solid var(--fail-red)}.log-entry.watermelon{background:rgba(255,105,180,.1);border-left:4px solid var(--watermelon-pink)}.log-entry .log-time{font-size:.8em;color:var(--text-secondary)}.log-entry .log-bot{font-weight:bold;color:var(--necro-green)}.log-entry .log-hearts{color:var(--blood-red);font-weight:bold}.log-stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:10px;margin-bottom:20px}.stat-card{background:rgba(0,0,0,.3);padding:15px;border-radius:8px;text-align:center}.stat-number{font-size:2em;font-weight:bold;color:var(--necro-green)}.stat-label{font-size:.9em;color:var(--text-secondary)}.log-controls{display:flex;gap:10px;margin-bottom:20px;align-items:center}
    </style>
</head>
<body>
    <div class="container">
        <div class="header"><h1 class="title">Shadow Network Control</h1><p class="subtitle">Ultimate Bot Management with Card Logging</p></div>
        <div id="msg-status-container" class="msg-status"></div>
        <div class="main-grid">
            <div class="panel card-log-panel">
                <h2><i class="fas fa-scroll"></i> Card Grab Activity Log</h2>
                <div class="log-stats" id="log-stats"></div>
                <div class="log-controls">
                    <button id="refresh-logs-btn" class="btn btn-small">Refresh</button>
                    <span>Auto-refresh: <span id="log-refresh-countdown">15</span>s</span>
                </div>
                <div class="log-container" id="log-container"></div>
            </div>
            <div class="panel status-panel">
                <h2><i class="fas fa-heartbeat"></i> System & Bot Status</h2>
                <div id="bot-control-grid" class="bot-status-grid" style="grid-template-columns: repeat(auto-fit, minmax(350px, 1fr));"></div>
            </div>
            <div class="panel clan-drop-panel">
                <h2><i class="fas fa-users"></i> Clan Auto Drop</h2>
                <div class="status-row">
                    <span>Next Cycle: <span id="clan-drop-timer" class="timer-display">--:--:--</span></span>
                    <button id="clan-drop-toggle-btn" class="btn btn-small"></button>
                </div>
                <div class="server-sub-panel">
                    <h3><i class="fas fa-cogs"></i> Configuration</h3>
                    <div class="input-group"><label>Drop Channel ID</label><input id="clan-drop-channel-id"></div>
                    <div class="input-group"><label>KTB Channel ID</label><input id="clan-drop-ktb-channel-id"></div>
                    <h3><i class="fas fa-crosshairs"></i> Heart Thresholds</h3>
                    {% for bot in main_bots_info %}<div class="grab-section"><h3>{{ bot.name }}</h3><div class="input-group"><input type="number" class="clan-drop-threshold" data-node="main_{{ bot.id }}"></div></div>{% endfor %}
                </div>
                <button id="clan-drop-save-btn" class="btn" style="margin-top: 20px;">Save Clan Settings</button>
            </div>
            <div class="panel global-settings-panel">
                <h2><i class="fas fa-globe"></i> Global Settings</h2>
                <div class="server-sub-panel">
                    <h3><i class="fas fa-seedling"></i> Watermelon Grab</h3>
                    <div id="global-watermelon-grid" class="bot-status-grid" style="grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));"></div>
                </div>
            </div>
            {% for server in servers %}
            <div class="panel server-panel" data-server-id="{{ server.id }}">
                <button class="btn-delete-server" title="Delete Server"><i class="fas fa-times"></i></button>
                <h2><i class="fas fa-server"></i> {{ server.name }}</h2>
                <div class="server-sub-panel">
                    <h3>Channel Config</h3>
                    <div class="input-group"><label>Main Channel</label><input class="channel-input" data-field="main_channel_id" value="{{ server.main_channel_id or '' }}"></div>
                    <div class="input-group"><label>KTB Channel</label><input class="channel-input" data-field="ktb_channel_id" value="{{ server.ktb_channel_id or '' }}"></div>
                    <div class="input-group"><label>Spam Channel</label><input class="channel-input" data-field="spam_channel_id" value="{{ server.spam_channel_id or '' }}"></div>
                </div>
                <div class="server-sub-panel">
                    <h3>Card Grab</h3>
                    {% for bot in main_bots_info %}<div class="grab-section"><h3>{{ bot.name }}</h3><div class="input-group"><input type="number" class="harvest-threshold" data-node="{{ bot.id }}" value="{{ server['heart_threshold_' + bot.id|string] or 50 }}"><button class="btn harvest-toggle" data-node="{{ bot.id }}"></button></div></div>{% endfor %}
                </div>
                <div class="server-sub-panel">
                    <h3>Auto Broadcast</h3>
                    <div class="input-group"><label>Message</label><textarea class="spam-message">{{ server.spam_message or '' }}</textarea></div>
                    <div class="input-group"><label>Delay(s)</label><input type="number" class="spam-delay" value="{{ server.spam_delay or 10 }}"></div>
                    <button class="btn broadcast-toggle"></button>
                </div>
            </div>
            {% endfor %}
            <div class="panel add-server-btn" id="add-server-btn"><i class="fas fa-plus"></i></div>
        </div>
    </div>
<script>
document.addEventListener('DOMContentLoaded', () => {
    const el = (selector) => document.querySelector(selector);
    const els = (selector) => document.querySelectorAll(selector);
    const msgContainer = el('#msg-status-container');
    let logRefreshInterval;

    const showMsg = (msg, type = 'success') => {
        if (!msg) return;
        msgContainer.textContent = msg;
        msgContainer.className = `msg-status ${type}`;
        msgContainer.style.display = 'block';
        setTimeout(() => msgContainer.style.display = 'none', 4000);
    };

    const post = async (endpoint, data) => {
        try {
            const res = await fetch(endpoint, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) });
            const result = await res.json();
            showMsg(result.message, result.status);
            if (result.status === 'success') {
                if(endpoint !== '/api/save_settings') post('/api/save_settings');
                if(result.reload) setTimeout(() => location.reload(), 500);
            }
            fetchStatus();
        } catch { showMsg('Server communication error', 'error'); }
    };

    const formatTime = (s) => isNaN(s) || s < 0 ? '--:--:--' : new Date(s * 1000).toISOString().substr(11, 8);

    const updateLogs = async () => {
        try {
            const res = await fetch('/api/card_logs');
            const { logs, stats } = await res.json();
            el('#log-stats').innerHTML = `
                <div class="stat-card"><div class="stat-number">${stats.total_attempts}</div><div class="stat-label">Attempts</div></div>
                <div class="stat-card"><div class="stat-number" style="color:var(--success-gold)">${stats.successful_grabs}</div><div class="stat-label">Success</div></div>
                <div class="stat-card"><div class="stat-number" style="color:var(--watermelon-pink)">${stats.watermelon_grabs}</div><div class="stat-label">Watermelons</div></div>
                <div class="stat-card"><div class="stat-number" style="color:var(--fail-red)">${stats.failed_grabs}</div><div class="stat-label">Fails</div></div>`;
            const logContainer = el('#log-container');
            logContainer.innerHTML = logs.length ? logs.map(l => {
                let icon = '', action = '', typeClass = l.action.includes('result') ? l.status : 'attempt';
                if(l.action === 'grab_attempt') { icon = 'fa-crosshairs'; action = `Try line ${l.card_line} ${l.emoji}`; }
                else if (l.action === 'grab_result') { icon = l.status === 'success' ? 'fa-trophy' : 'fa-times-circle'; action = `${l.result_type.replace('_', ' ')}`; }
                else if (l.action === 'watermelon_grab') { icon = 'fa-seedling'; action = 'Watermelon Grab'; typeClass = 'watermelon'; }
                return `<div class="log-entry ${typeClass}"><i class="fas ${icon}"></i><span class="log-bot">${l.bot_name}</span><span>${action}</span>${l.hearts ? `<span class="log-hearts">♡${l.hearts}</span>` : ''}<span class="log-time">${new Date(l.timestamp).toLocaleTimeString()}</span></div>`;
            }).join('') : '<p style="text-align:center">No grab activity recorded.</p>';
        } catch { console.error('Failed to fetch logs'); }
    };
    
    const startLogTimer = () => {
        if(logRefreshInterval) clearInterval(logRefreshInterval);
        let count = 15;
        const countdownEl = el('#log-refresh-countdown');
        logRefreshInterval = setInterval(() => {
            count--;
            countdownEl.textContent = count;
            if(count <= 0) { updateLogs(); count = 15; }
        }, 1000);
    };

    const fetchStatus = async () => {
        try {
            const res = await fetch('/status');
            const data = await res.json();
            
            el('#clan-drop-timer').textContent = formatTime(data.auto_clan_drop_status.countdown);
            el('#clan-drop-toggle-btn').textContent = data.auto_clan_drop_status.enabled ? 'DISABLE' : 'ENABLE';
            el('#clan-drop-channel-id').value = data.auto_clan_drop.channel_id || '';
            el('#clan-drop-ktb-channel-id').value = data.auto_clan_drop.ktb_channel_id || '';
            els('.clan-drop-threshold').forEach(i => i.value = data.auto_clan_drop.heart_thresholds[i.dataset.node] || 50);

            const botGrid = el('#bot-control-grid');
            const allBots = [...data.bot_statuses.main_bots, ...data.bot_statuses.sub_accounts];
            const activeBotIds = new Set();
            allBots.forEach(b => {
                const id = b.reboot_id;
                activeBotIds.add(id);
                let cont = el(`#bot-cont-${id}`) || document.createElement('div');
                cont.id = `bot-cont-${id}`;
                cont.className = 'status-row';
                let rebootHtml = '';
                if(b.type === 'main') {
                    const r = data.bot_reboot_settings[id] || {};
                    rebootHtml = `<div class="input-group" style="margin:5px 0 0 0"><input type="number" class="bot-reboot-delay" data-bot-id="${id}" value="${r.delay || 3600}" style="width:70px"><span class="timer-display">${formatTime(r.countdown)}</span><button class="btn btn-small bot-reboot-toggle" data-bot-id="${id}">${r.enabled ? 'AUTO' : 'MANUAL'}</button></div>`;
                }
                cont.innerHTML = `<div style="flex-grow:1"><span style="font-weight:bold;${b.type==='main'?'color:#FF4500':''}">${b.name} <span class="health-indicator health-${b.health_status}"></span> ${b.is_rebooting ? '<i class="fas fa-sync-alt fa-spin"></i>' : ''}</span></div><button class="btn-toggle-state" data-target="${id}">${b.is_active ? 'ONLINE' : 'OFFLINE'}</button>${rebootHtml}`;
                if(!cont.parentNode) botGrid.appendChild(cont);
            });
            els('#bot-control-grid .status-row').forEach(c => { if(!activeBotIds.has(c.id.replace('bot-cont-',''))) c.remove(); });
            
            const wmGrid = el('#global-watermelon-grid');
            wmGrid.innerHTML = data.bot_statuses.main_bots.map(b => `<div class="status-row"><span>${b.name}</span><button class="btn watermelon-toggle" data-node="${b.reboot_id}">${data.watermelon_grab_states[b.reboot_id] ? 'ON' : 'OFF'}</button></div>`).join('');
            
            data.servers.forEach(s => {
                const p = el(`.server-panel[data-server-id="${s.id}"]`);
                if(!p) return;
                p.querySelectorAll('.harvest-toggle').forEach(b => b.textContent = s[`auto_grab_enabled_${b.dataset.node}`] ? 'ON' : 'OFF');
                p.querySelector('.broadcast-toggle').textContent = s.spam_enabled ? 'ON' : 'OFF';
            });
        } catch { console.error('Failed to fetch status'); }
    };

    document.body.addEventListener('click', (e) => {
        const t = e.target;
        if(t.matches('#clan-drop-toggle-btn')) post('/api/clan_drop_toggle');
        if(t.matches('#clan-drop-save-btn')) {
            const thresholds = {};
            els('.clan-drop-threshold').forEach(i => thresholds[i.dataset.node] = parseInt(i.value));
            post('/api/clan_drop_update', { channel_id: el('#clan-drop-channel-id').value, ktb_channel_id: el('#clan-drop-ktb-channel-id').value, heart_thresholds: thresholds });
        }
        if(t.matches('.btn-toggle-state')) post('/api/toggle_bot_state', { target: t.dataset.target });
        if(t.matches('.bot-reboot-toggle')) post('/api/bot_reboot_toggle', { bot_id: t.dataset.botId, delay: t.closest('.input-group').querySelector('.bot-reboot-delay').value });
        if(t.matches('.watermelon-toggle')) post('/api/watermelon_toggle', { node: t.dataset.node });
        if(t.matches('.btn-delete-server')) if(confirm('Are you sure?')) post('/api/delete_server', { server_id: t.closest('.server-panel').dataset.serverId });
        if(t.matches('#add-server-btn')) { const name = prompt('New server name:'); if(name) post('/api/add_server', { name }); }
        if(t.matches('#refresh-logs-btn')) updateLogs();

        const serverPanel = t.closest('.server-panel');
        if(!serverPanel) return;
        if(t.matches('.harvest-toggle')) post('/api/harvest_toggle', { server_id: serverPanel.dataset.serverId, node: t.dataset.node, threshold: t.previousElementSibling.value });
        if(t.matches('.broadcast-toggle')) post('/api/broadcast_toggle', { server_id: serverPanel.dataset.serverId, message: serverPanel.querySelector('.spam-message').value, delay: serverPanel.querySelector('.spam-delay').value });
    });
    
    document.body.addEventListener('change', e => {
        const t = e.target;
        const serverPanel = t.closest('.server-panel');
        if(serverPanel && t.matches('.channel-input')) {
            const payload = { server_id: serverPanel.dataset.serverId };
            payload[t.dataset.field] = t.value;
            post('/api/update_server_channels', payload);
        }
    });

    fetchStatus(); updateLogs(); startLogTimer();
    setInterval(fetchStatus, 5000);
});
</script>
</body>
</html>
"""

# --- FLASK ROUTES ---
@app.route("/")
def index():
    main_bots_info = sorted([{"id": int(i.split('_')[1]), "name": get_bot_name(i)} for i, _ in bot_manager.get_main_bots_info()], key=lambda x: x['id'])
    return render_template_string(HTML_TEMPLATE, servers=sorted(servers, key=lambda s: s.get('name', '')), main_bots_info=main_bots_info, auto_clan_drop=bot_states["auto_clan_drop"])

@app.route("/api/card_logs")
def api_card_logs():
    logs = card_logger.get_recent_logs(limit=50)
    for log in logs:
        if isinstance(log['timestamp'], datetime): log['timestamp'] = log['timestamp'].isoformat()
    return jsonify({'logs': logs, 'stats': card_logger.get_stats(hours=24)})

# Các route API khác giữ nguyên như file của bạn
@app.route("/api/clan_drop_toggle", methods=['POST'])
def api_clan_drop_toggle():
    s = bot_states["auto_clan_drop"]
    s['enabled'] = not s.get('enabled', False)
    if s['enabled'] and (not s.get('channel_id') or not s.get('ktb_channel_id')):
        s['enabled'] = False; return jsonify({'status': 'error', 'message': 'Clan Drop & KTB Channel ID must be set.'})
    msg = f"Clan Auto Drop {'ENABLED' if s['enabled'] else 'DISABLED'}."
    return jsonify({'status': 'success', 'message': msg})

@app.route("/api/clan_drop_update", methods=['POST'])
def api_clan_drop_update():
    data = request.json
    s = bot_states["auto_clan_drop"]
    s.update({'channel_id': data.get('channel_id', '').strip(), 'ktb_channel_id': data.get('ktb_channel_id', '').strip()})
    s.setdefault('heart_thresholds', {}).update({k: int(v) for k, v in data.get('heart_thresholds', {}).items()})
    return jsonify({'status': 'success', 'message': 'Clan Drop settings updated.'})

@app.route("/api/add_server", methods=['POST'])
def api_add_server():
    name = request.json.get('name')
    if not name: return jsonify({'status': 'error', 'message': 'Server name is required.'}), 400
    new_server = {"id": f"server_{uuid.uuid4().hex}", "name": name, "spam_delay": 10}
    for i in range(len(main_tokens)): new_server.update({f'auto_grab_enabled_{i+1}': False, f'heart_threshold_{i+1}': 50})
    servers.append(new_server)
    return jsonify({'status': 'success', 'message': f'Server "{name}" added.', 'reload': True})

@app.route("/api/delete_server", methods=['POST'])
def api_delete_server():
    server_id = request.json.get('server_id')
    servers[:] = [s for s in servers if s.get('id') != server_id]
    return jsonify({'status': 'success', 'message': 'Server deleted.', 'reload': True})

@app.route("/api/update_server_channels", methods=['POST'])
def api_update_server_channels():
    data = request.json
    server = next((s for s in servers if s.get('id') == data.get('server_id')), None)
    if not server: return jsonify({'status': 'error', 'message': 'Server not found.'}), 404
    for field in ['main_channel_id', 'ktb_channel_id', 'spam_channel_id']:
        if field in data: server[field] = data[field]
    return jsonify({'status': 'success', 'message': 'Channels updated.'})

@app.route("/api/harvest_toggle", methods=['POST'])
def api_harvest_toggle():
    data = request.json
    server = next((s for s in servers if s.get('id') == data.get('server_id')), None)
    if not server: return jsonify({'status': 'error', 'message': 'Invalid request.'}), 400
    node = data.get('node'); key = f'auto_grab_enabled_{node}'
    server[key] = not server.get(key, False)
    server[f'heart_threshold_{node}'] = int(data.get('threshold', 50))
    return jsonify({'status': 'success', 'message': f"Card Grab for Bot {node} {'ENABLED' if server[key] else 'DISABLED'}."})

@app.route("/api/watermelon_toggle", methods=['POST'])
def api_watermelon_toggle():
    node = request.json.get('node')
    bot_states["watermelon_grab"][node] = not bot_states["watermelon_grab"].get(node, False)
    return jsonify({'status': 'success', 'message': f"Watermelon Grab for {get_bot_name(node)} {'ENABLED' if bot_states['watermelon_grab'][node] else 'DISABLED'}."})

@app.route("/api/broadcast_toggle", methods=['POST'])
def api_broadcast_toggle():
    data = request.json
    server = next((s for s in servers if s.get('id') == data.get('server_id')), None)
    if not server: return jsonify({'status': 'error', 'message': 'Server not found.'}), 404
    server['spam_enabled'] = not server.get('spam_enabled', False)
    server.update({'spam_message': data.get("message", "").strip(), 'spam_delay': int(data.get("delay", 10))})
    return jsonify({'status': 'success', 'message': f"Broadcast for {server['name']} {'ENABLED' if server['spam_enabled'] else 'DISABLED'}."})

@app.route("/api/bot_reboot_toggle", methods=['POST'])
def api_bot_reboot_toggle():
    data = request.json; bot_id, delay = data.get('bot_id'), int(data.get("delay", 3600))
    s = bot_states["reboot_settings"].get(bot_id)
    s.update({'enabled': not s.get('enabled', False), 'delay': delay, 'failure_count': 0})
    if s['enabled']: s['next_reboot_time'] = time.time() + delay
    return jsonify({'status': 'success', 'message': f"Auto-Reboot for {get_bot_name(bot_id)} {'ENABLED' if s['enabled'] else 'DISABLED'}."})

@app.route("/api/toggle_bot_state", methods=['POST'])
def api_toggle_bot_state():
    target = request.json.get('target')
    bot_states["active"][target] = not bot_states["active"][target]
    return jsonify({'status': 'success', 'message': f"Bot {get_bot_name(target)} is now {'ONLINE' if bot_states['active'][target] else 'OFFLINE'}."})

@app.route("/api/save_settings", methods=['POST'])
def api_save_settings():
    save_settings(); return jsonify({'status': 'success', 'message': 'Settings saved.'})

@app.route("/status")
def status_endpoint():
    now = time.time()
    def get_bot_status_list(bot_info, type_prefix):
        return sorted([{
            "name": get_bot_name(i), "reboot_id": i, "is_active": bot_states["active"].get(i, False), "type": type_prefix,
            "health_status": ('bad' if bot_states["health_stats"].get(i, {}).get('consecutive_failures', 0) >= 3 else 'warning' if bot_states["health_stats"].get(i, {}).get('consecutive_failures', 0) > 0 else 'good'),
            "is_rebooting": bot_manager.is_rebooting(i)
        } for i, b in bot_info], key=lambda x: int(x['reboot_id'].split('_')[1]))
    
    clan_s = bot_states["auto_clan_drop"]
    reboot_s = bot_states["reboot_settings"].copy()
    for i, s in reboot_s.items(): s['countdown'] = max(0, s.get('next_reboot_time', 0) - now) if s.get('enabled') else 0
        
    return jsonify({
        'bot_reboot_settings': reboot_s,
        'bot_statuses': {"main_bots": get_bot_status_list(bot_manager.get_main_bots_info(), "main"), "sub_accounts": get_bot_status_list(bot_manager.get_sub_bots_info(), "sub")},
        'server_start_time': server_start_time, 'servers': servers, 'watermelon_grab_states': bot_states["watermelon_grab"],
        'auto_clan_drop_status': {"enabled": clan_s.get("enabled", False), "countdown": (clan_s.get("last_cycle_start_time", 0) + clan_s.get("cycle_interval", 1800) - now) if clan_s.get("enabled") else 0},
        'auto_clan_drop': clan_s
    })

# --- MAIN EXECUTION ---
if __name__ == "__main__":
    print("🚀 Shadow Network Control - Final Version Starting...", flush=True)
    load_settings()
    print("🔌 Initializing bots...", flush=True)
    
    all_tokens = [(t.strip(), i + 1, True) for i, t in enumerate(main_tokens) if t.strip()] + \
                 [(t.strip(), i, False) for i, t in enumerate(tokens) if t.strip()]

    for token, identifier, is_main in all_tokens:
        bot_id = f"main_{identifier}" if is_main else f"sub_{identifier}"
        bot = create_bot(token, identifier, is_main)
        if bot: bot_manager.add_bot(bot_id, bot)
        bot_states["active"].setdefault(bot_id, True)
        bot_states["health_stats"].setdefault(bot_id, {'consecutive_failures': 0})
        if is_main:
            bot_states["watermelon_grab"].setdefault(bot_id, False)
            bot_states["auto_clan_drop"]["heart_thresholds"].setdefault(bot_id, 50)
            bot_states["reboot_settings"].setdefault(bot_id, {'enabled': False, 'delay': 3600, 'next_reboot_time': 0, 'failure_count': 0})

    print("🔧 Starting background threads...", flush=True)
    threading.Thread(target=periodic_task_runner, daemon=True).start()
    threading.Thread(target=spam_loop_manager, daemon=True).start()
    threading.Thread(target=auto_reboot_loop, daemon=True).start()
    threading.Thread(target=auto_clan_drop_loop, daemon=True).start()
    
    port = int(os.environ.get("PORT", 10000))
    print(f"🌐 Web Server running at http://0.0.0.0:{port}", flush=True)
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
