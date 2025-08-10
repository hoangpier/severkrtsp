# PHIÊN BẢN COMPACT - LOGIC BACK-END
import discum, threading, time, os, re, requests, json, random, traceback, uuid
from flask import Flask, request, render_template, jsonify
from dotenv import load_dotenv
from datetime import datetime, timedelta
from collections import deque

load_dotenv()

# --- CẤU HÌNH & BIẾN TOÀN CỤC ---
main_tokens = os.getenv("MAIN_TOKENS", "").split(",")
tokens = os.getenv("TOKENS", "").split(",")
karuta_id, karibbit_id = "646937666251915264", "1311684840462225440"
BOT_NAMES = ["ALPHA", "xsyx", "sofa", "dont", "ayaya", "owo", "astra", "singo", "dia pox", "clam", "rambo", "domixi", "dogi", "sicula", "mo turn", "jan taru", "kio sama"]
acc_names = [f"Bot-{i:02d}" for i in range(1, 21)]
servers, BOT_USER_IDS = [], {}
bot_states = {
    "reboot_settings": {}, "active": {}, "watermelon_grab": {}, "health_stats": {},
    "auto_clan_drop": {"enabled": False, "channel_id": "", "ktb_channel_id": "", "last_cycle_start_time": 0, "cycle_interval": 1800, "bot_delay": 140, "heart_thresholds": {}}
}
stop_events = {"reboot": threading.Event(), "clan_drop": threading.Event()}
server_start_time = time.time()

# --- CARD GRAB LOGGING SYSTEM ---
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
            attempt = self.grab_attempts.get(message_id, {})
            hearts = hearts or attempt.get('hearts', 0)
            card_info = card_info or f"Line {attempt.get('card_line', '?')}"
            self.logs.append({'id': f"result_{message_id}_{bot_id}", 'timestamp': datetime.now(), 'bot_name': get_bot_name(bot_id), 'bot_id': bot_id, 'action': 'grab_result', 'hearts': hearts, 'card_info': card_info, 'status': 'success' if success else 'failed', 'result_type': result_type, 'message_id': message_id, 'channel_id': channel_id})
            if message_id in self.grab_attempts: self.grab_attempts[message_id]['status'] = 'success' if success else 'failed'
    def log_watermelon_grab(self, bot_id, channel_id, message_id, success):
        with self.lock:
            self.logs.append({'id': f"watermelon_{message_id}_{bot_id}", 'timestamp': datetime.now(), 'bot_name': get_bot_name(bot_id), 'bot_id': bot_id, 'action': 'watermelon_grab', 'hearts': 0, 'card_info': '🍉 Watermelon', 'status': 'success' if success else 'failed', 'result_type': 'watermelon', 'message_id': message_id, 'channel_id': channel_id})
    def get_recent_logs(self, limit=50):
        with self.lock: return list(reversed(list(self.logs)))[:limit]
    def get_stats(self, hours=24):
        with self.lock:
            cutoff = datetime.now() - timedelta(hours=hours)
            recent = [log for log in self.logs if log['timestamp'] > cutoff]
            stats = {'total_attempts': 0, 'successful_grabs': 0, 'failed_grabs': 0, 'watermelon_grabs': 0, 'bot_stats': {}, 'high_heart_grabs': 0}
            for log in recent:
                if log['action'] == 'grab_attempt': stats['total_attempts'] += 1
                elif log['action'] == 'grab_result':
                    if log['status'] == 'success':
                        stats['successful_grabs'] += 1
                        if log.get('hearts', 0) >= 100: stats['high_heart_grabs'] += 1
                    else: stats['failed_grabs'] += 1
                elif log['action'] == 'watermelon_grab' and log['status'] == 'success': stats['watermelon_grabs'] += 1
                bot_name = log['bot_name']
                if bot_name not in stats['bot_stats']: stats['bot_stats'][bot_name] = {'successes': 0, 'watermelons': 0}
                if log['action'] == 'grab_result' and log['status'] == 'success': stats['bot_stats'][bot_name]['successes'] += 1
                elif log['action'] == 'watermelon_grab' and log['status'] == 'success': stats['bot_stats'][bot_name]['watermelons'] += 1
            return stats
card_logger = CardGrabLogger()

# --- QUẢN LÝ BOT THREAD-SAFE ---
class ThreadSafeBotManager:
    def __init__(self):
        self._bots, self._rebooting, self._lock = {}, set(), threading.RLock()
    def add_bot(self, bot_id, bot_instance):
        with self._lock: self._bots[bot_id] = bot_instance
    def remove_bot(self, bot_id):
        with self._lock:
            bot = self._bots.pop(bot_id, None)
            if bot and hasattr(bot, 'gateway') and hasattr(bot.gateway, 'close'):
                try: bot.gateway.close()
                except Exception as e: print(f"[Bot Manager] ⚠️ Error closing gateway for {bot_id}: {e}", flush=True)
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
    settings_data = {'servers': servers, 'bot_states': bot_states}
    if api_key and bin_id:
        try:
            headers = {'Content-Type': 'application/json', 'X-Master-Key': api_key}
            req = requests.put(f"https://api.jsonbin.io/v3/b/{bin_id}", json=settings_data, headers=headers, timeout=15)
            if req.status_code == 200: return print("[Settings] ✅ Đã lưu cài đặt lên JSONBin.io.", flush=True)
        except Exception as e: print(f"[Settings] ❌ Lỗi JSONBin: {e}, đang lưu local.", flush=True)
    try:
        with open('backup_settings.json', 'w') as f: json.dump(settings_data, f, indent=2)
        print("[Settings] ✅ Đã lưu backup cài đặt locally.", flush=True)
    except Exception as e: print(f"[Settings] ❌ Lỗi khi lưu backup local: {e}", flush=True)

def load_settings():
    def load_from_dict(settings):
        global servers, bot_states
        servers.extend(settings.get('servers', []))
        for key, value in settings.get('bot_states', {}).items():
            if key in bot_states and isinstance(value, dict): bot_states[key].update(value)
        return True
    api_key, bin_id = os.getenv("JSONBIN_API_KEY"), os.getenv("JSONBIN_BIN_ID")
    if api_key and bin_id:
        try:
            headers = {'X-Master-Key': api_key}
            req = requests.get(f"https://api.jsonbin.io/v3/b/{bin_id}/latest", headers=headers, timeout=15)
            if req.status_code == 200 and load_from_dict(req.json().get("record", {})):
                return print("[Settings] ✅ Đã tải cài đặt từ JSONBin.io.", flush=True)
        except Exception as e: print(f"[Settings] ⚠️ Lỗi tải từ JSONBin: {e}", flush=True)
    try:
        with open('backup_settings.json', 'r') as f:
            if load_from_dict(json.load(f)): return print("[Settings] ✅ Đã tải cài đặt từ backup file.", flush=True)
    except FileNotFoundError: print("[Settings] ⚠️ Không tìm thấy backup file, dùng mặc định.", flush=True)
    except Exception as e: print(f"[Settings] ⚠️ Lỗi tải backup: {e}", flush=True)

# --- HÀM TRỢ GIÚP & LOGIC BOT ---
def get_bot_name(bot_id_str):
    try:
        b_type, b_index = bot_id_str.split('_')[0], int(bot_id_str.split('_')[1])
        if b_type == 'main': return BOT_NAMES[b_index - 1] if 0 < b_index <= len(BOT_NAMES) else f"MAIN_{b_index}"
        return acc_names[b_index] if b_index < len(acc_names) else f"SUB_{b_index+1}"
    except: return bot_id_str.upper()

def _find_and_select_card(bot, channel_id, msg_id, threshold, bot_num, ktb_channel_id):
    bot_id = f'main_{bot_num}'
    for _ in range(7):
        time.sleep(0.5)
        try:
            messages = bot.getMessages(channel_id, num=5).json()
            if not isinstance(messages, list): continue
            for msg_item in messages:
                if msg_item.get("author", {}).get("id") == karibbit_id and int(msg_item.get("id", 0)) > int(msg_id):
                    embed_desc = msg_item.get("embeds", [{}])[0].get("description", "")
                    if '♡' not in embed_desc: continue
                    lines = embed_desc.split('\n')[:3]
                    hearts = [int(re.search(r'♡(\d+)', l).group(1)) if re.search(r'♡(\d+)', l) else 0 for l in lines]
                    if not any(hearts): break
                    max_h = max(hearts)
                    if max_h >= threshold:
                        idx = hearts.index(max_h)
                        delays = {1: [0.4, 1.4, 2.1], 2: [0.7, 1.8, 2.4], 3: [0.7, 1.8, 2.4], 4: [0.8, 1.9, 2.5]}
                        emoji, delay = ["1️⃣", "2️⃣", "3️⃣"][idx], delays.get(bot_num, [0.9, 2.0, 2.6])[idx]
                        print(f"[CARD GRAB|Bot {bot_num}] Dòng {idx+1} ({max_h}♡) -> {emoji} sau {delay}s", flush=True)
                        card_logger.log_grab_attempt(bot_id, channel_id, msg_id, idx+1, max_h, emoji)
                        def grab_action():
                            try:
                                bot.addReaction(channel_id, msg_id, emoji)
                                time.sleep(1.2)
                                if ktb_channel_id: bot.sendMessage(ktb_channel_id, "kt b")
                            except Exception as e: print(f"[CARD GRAB|Bot {bot_num}] ❌ Lỗi grab: {e}", flush=True)
                        threading.Timer(delay, grab_action).start()
                        return True
            return False
        except Exception as e: print(f"[CARD GRAB|Bot {bot_num}] ❌ Lỗi đọc messages: {e}", flush=True)
    return False

def handle_karuta_result(bot, msg, bot_num):
    content, mentions, channel_id = msg.get("content", "").lower(), msg.get("mentions", []), msg.get("channel_id")
    bot_id = f'main_{bot_num}'
    bot_user_id = BOT_USER_IDS.get(bot_id)
    if not bot_user_id or bot_user_id not in [m.get("id") for m in mentions]: return
    success, result_type, hearts = False, "unknown", 0
    if "fought off" in content or "took the" in content:
        success = True
        result_type = "fought_off" if "fought off" in content else "took_the"
        heart_match = re.search(r'♡(\d+)', content)
        if heart_match: hearts = int(heart_match.group(1))
        print(f"[CARD RESULT|Bot {bot_num}] {result_type.upper()} - {hearts}♡", flush=True)
        card_logger.log_grab_result(bot_id, channel_id, str(int(time.time() * 1000)), success, result_type, hearts)

def handle_grab_events(bot, msg, bot_num):
    content = msg.get("content", "").lower()
    author_id = msg.get("author", {}).get("id")
    if author_id != karuta_id: return

    # Karuta Result Handler
    if ("fought off" in content or "took the" in content) and msg.get("mentions"):
        return handle_karuta_result(bot, msg, bot_num)
    
    # Card Drop Handler
    if "dropping" in content:
        is_clan_drop = bool(msg.get("mentions"))
        if is_clan_drop:
            clan_settings = bot_states["auto_clan_drop"]
            if clan_settings.get("enabled") and msg.get("channel_id") == clan_settings.get("channel_id"):
                threshold = clan_settings.get("heart_thresholds", {}).get(f'main_{bot_num}', 50)
                threading.Thread(target=_find_and_select_card, args=(bot, clan_settings["channel_id"], msg["id"], threshold, bot_num, clan_settings["ktb_channel_id"]), daemon=True).start()
        else:
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
                            print(f"[WATERMELON|Bot {bot_num}] 🎯 PHÁT HIỆN DƯA!", flush=True)
                            bot.addReaction(channel_id, msg["id"], "🍉")
                            card_logger.log_watermelon_grab(bot_id_str, channel_id, msg["id"], True)
                    except Exception as e: card_logger.log_watermelon_grab(bot_id_str, channel_id, msg["id"], False); print(f"🍉 Lỗi check dưa: {e}", flush=True)
                threading.Thread(target=check_watermelon, daemon=True).start()

# --- HỆ THỐNG REBOOT & HEALTH CHECK ---
def check_bot_health(bot_instance, bot_id):
    stats = bot_states["health_stats"].setdefault(bot_id, {'consecutive_failures': 0})
    is_connected = bot_instance and hasattr(bot_instance.gateway, 'connected') and bot_instance.gateway.connected
    stats['consecutive_failures'] = 0 if is_connected else stats.get('consecutive_failures', 0) + 1
    if not is_connected: print(f"[Health Check] ⚠️ {bot_id} disconnected - fails: {stats['consecutive_failures']}", flush=True)

def handle_reboot_failure(bot_id):
    settings = bot_states["reboot_settings"].setdefault(bot_id, {})
    failures = settings.get('failure_count', 0) + 1
    settings['failure_count'] = failures
    backoff = min(2 ** failures, 8)
    next_delay = max(600, settings.get('delay', 3600) / backoff) * backoff
    settings['next_reboot_time'] = time.time() + next_delay
    print(f"[Safe Reboot] 🔴 #{failures} fails for {bot_id}. Retry in {next_delay/60:.1f}m.", flush=True)
    if failures >= 5: settings['enabled'] = False; print(f"[Safe Reboot] ❌ Disabled for {bot_id} after 5 fails.", flush=True)

def safe_reboot_bot(bot_id):
    if not bot_manager.start_reboot(bot_id): return False
    print(f"[Safe Reboot] 🔄 Rebooting {bot_id}...", flush=True)
    try:
        bot_index = int(bot_id.split('_')[1]) - 1
        if not (0 <= bot_index < len(main_tokens)): raise IndexError("Bot index out of range")
        token, bot_name = main_tokens[bot_index].strip(), get_bot_name(bot_id)
        bot_manager.remove_bot(bot_id)
        settings = bot_states["reboot_settings"].get(bot_id, {})
        wait_time = random.uniform(20, 40) + min(settings.get('failure_count', 0) * 30, 300)
        print(f"[Safe Reboot] ⏳ Waiting {wait_time:.1f}s...", flush=True)
        time.sleep(wait_time)
        new_bot = create_bot(token, bot_identifier=(bot_index + 1), is_main=True)
        if not new_bot: raise Exception("Failed to create new bot instance.")
        bot_manager.add_bot(bot_id, new_bot)
        settings.update({'next_reboot_time': time.time() + settings.get('delay', 3600), 'failure_count': 0, 'last_reboot_time': time.time()})
        bot_states["health_stats"][bot_id]['consecutive_failures'] = 0
        print(f"[Safe Reboot] ✅ {bot_name} rebooted successfully.", flush=True)
        return True
    except Exception as e:
        print(f"[Safe Reboot] ❌ Reboot failed for {bot_id}: {e}", flush=True); traceback.print_exc()
        handle_reboot_failure(bot_id)
        return False
    finally: bot_manager.end_reboot(bot_id)

# --- VÒNG LẶP NỀN ---
def auto_reboot_loop():
    print("[Safe Reboot] 🚀 Reboot loop started.", flush=True)
    last_reboot_time = 0
    while not stop_events["reboot"].is_set():
        try:
            now = time.time()
            if now - last_reboot_time < 600:
                stop_events["reboot"].wait(60); continue
            bot_to_reboot, highest_priority = None, -1
            for bot_id, settings in dict(bot_states["reboot_settings"]).items():
                if not settings.get('enabled', False) or bot_manager.is_rebooting(bot_id): continue
                next_reboot = settings.get('next_reboot_time', 0)
                if now < next_reboot: continue
                failures = bot_states["health_stats"].get(bot_id, {}).get('consecutive_failures', 0)
                priority = (failures * 1000) + (now - next_reboot)
                if priority > highest_priority: highest_priority, bot_to_reboot = priority, bot_id
            if bot_to_reboot:
                print(f"[Safe Reboot] 🎯 Selected {bot_to_reboot} for reboot (priority: {highest_priority:.1f})", flush=True)
                if safe_reboot_bot(bot_to_reboot):
                    last_reboot_time = time.time()
                    stop_events["reboot"].wait(random.uniform(300, 600))
                else: stop_events["reboot"].wait(120)
            else: stop_events["reboot"].wait(60)
        except Exception as e: print(f"❌ CRITICAL REBOOT LOOP ERROR: {e}", flush=True); stop_events["reboot"].wait(120)

def auto_clan_drop_loop():
    while not stop_events["clan_drop"].is_set():
        settings = bot_states["auto_clan_drop"]
        if settings.get("enabled") and (time.time() - settings.get("last_cycle_start_time", 0)) >= settings.get("cycle_interval", 1800):
            print("[Clan Drop] 🚀 Starting clan drop cycle.", flush=True)
            active_bots = [(b, int(i.split('_')[1])) for i, b in bot_manager.get_main_bots_info() if b and bot_states["active"].get(i, False)]
            if not active_bots: print("[Clan Drop] ⚠️ No active main bots.", flush=True)
            for bot, bot_num in active_bots:
                if stop_events["clan_drop"].is_set(): break
                try: bot.sendMessage(settings["channel_id"], "kd"); time.sleep(random.uniform(110, 170))
                except Exception as e: print(f"[Clan Drop] ❌ Error sending 'kd' from bot {bot_num}: {e}", flush=True)
            settings["last_cycle_start_time"] = time.time()
        stop_events["clan_drop"].wait(60)

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
        except Exception as e: print(f"❌ SPAM MANAGER ERROR: {e}", flush=True); time.sleep(10)

def spam_for_server(server_config, stop_event):
    while not stop_event.is_set():
        try:
            active_bots = [b for i, b in bot_manager.get_all_bots() if b and bot_states["active"].get(i)]
            delay = server_config.get('spam_delay', 10)
            for bot in active_bots:
                if stop_event.is_set(): break
                try: bot.sendMessage(server_config['spam_channel_id'], server_config['spam_message']); time.sleep(random.uniform(1.5, 2.5))
                except Exception: pass
            stop_event.wait(random.uniform(delay * 0.9, delay * 1.1))
        except Exception as e: print(f"❌ SPAM THREAD ERROR: {e}", flush=True); stop_event.wait(10)

def periodic_task_runner():
    while True:
        time.sleep(300) # 5 minutes
        try: 
            for bot_id, bot in bot_manager.get_all_bots(): check_bot_health(bot, bot_id)
        except Exception as e: print(f"[Health] ❌ Error: {e}", flush=True)
        time.sleep(1500) # 25 minutes, total 30 mins
        try: save_settings()
        except Exception as e: print(f"[Save] ❌ Error: {e}", flush=True)

# --- KHỞI TẠO BOT ---
def create_bot(token, bot_identifier, is_main=False):
    try:
        bot = discum.Client(token=token, log=False)
        bot_id_str = f"main_{bot_identifier}" if is_main else f"sub_{bot_identifier}"
        @bot.gateway.command
        def on_ready(resp):
            if resp.event.ready:
                user = resp.raw.get("user", {})
                user_id, username = user.get('id', 'Unknown'), user.get('username', 'Unknown')
                if user_id != 'Unknown': BOT_USER_IDS[bot_id_str] = user_id
                print(f"[Bot] ✅ Logged in: {user_id} ({get_bot_name(bot_id_str)})", flush=True)
                bot_states["health_stats"].setdefault(bot_id_str, {}).update({'consecutive_failures': 0})
        if is_main:
            @bot.gateway.command
            def on_message(resp):
                if resp.event.message:
                    try: handle_grab_events(bot, resp.parsed.auto(), bot_identifier)
                    except Exception as e: print(f"❌ Message handler error: {e}", flush=True)
        bot.gateway.run(auto_reconnect=True)
    except Exception as e:
        print(f"❌ Gateway error for {bot_id_str}: {e}", flush=True)
        
def initialize_bot_in_thread(token, bot_identifier, is_main):
    try:
        bot = discum.Client(token=token, log=False)
        bot_id_str = f"main_{bot_identifier}" if is_main else f"sub_{bot_identifier}"
        
        @bot.gateway.command
        def on_ready(resp):
            if resp.event.ready:
                user = resp.raw.get("user", {})
                user_id, username = user.get('id', 'Unknown'), user.get('username', 'Unknown')
                if user_id != 'Unknown': BOT_USER_IDS[bot_id_str] = user_id
                print(f"[Bot] ✅ Logged in: {user_id} ({get_bot_name(bot_id_str)})", flush=True)
                bot_states["health_stats"].setdefault(bot_id_str, {}).update({'consecutive_failures': 0})

        if is_main:
            @bot.gateway.command
            def on_message(resp):
                if resp.event.message:
                    try: handle_grab_events(bot, resp.parsed.auto(), bot_identifier)
                    except Exception as e: print(f"❌ Message handler error: {e}", flush=True)

        # Use a thread to run the gateway to not block the main startup
        threading.Thread(target=bot.gateway.run, kwargs={'auto_reconnect': True}, daemon=True).start()

        # Wait for connection
        start_time = time.time()
        while time.time() - start_time < 20:
            if hasattr(bot.gateway, 'connected') and bot.gateway.connected:
                return bot
            time.sleep(0.5)
        
        print(f"[Bot] ⚠️ Connection timeout for {bot_id_str}. Closing gateway.", flush=True)
        bot.gateway.close()
        return None
    except Exception as e:
        print(f"❌ Bot creation failed for {bot_identifier}: {e}", flush=True)
        return None

# --- FLASK APP ---
app = Flask(__name__)

@app.route("/")
def index():
    main_bots_info = sorted([{"id": int(i.split('_')[1]), "name": get_bot_name(i)} for i, _ in bot_manager.get_main_bots_info()], key=lambda x: x['id'])
    return render_template("index.html", servers=sorted(servers, key=lambda s: s.get('name', '')), main_bots_info=main_bots_info, auto_clan_drop=bot_states["auto_clan_drop"])

@app.route("/api/card_logs")
def api_card_logs():
    logs = card_logger.get_recent_logs(limit=50)
    for log in logs:
        if isinstance(log['timestamp'], datetime): log['timestamp'] = log['timestamp'].isoformat()
    return jsonify({'logs': logs, 'stats': card_logger.get_stats(hours=24)})

@app.route("/api/save_settings", methods=['POST'])
def api_save_settings(): save_settings(); return jsonify({'status': 'success', 'message': '💾 Settings saved.'})
@app.route("/api/clear_logs", methods=['POST'])
def api_clear_logs(): card_logger.logs.clear(); card_logger.grab_attempts.clear(); return jsonify({'status': 'success', 'message': '🗑️ Logs cleared.'})

@app.route("/api/update_settings", methods=['POST'])
def api_update_settings():
    data = request.json
    server_id = data.get('server_id')
    server = next((s for s in servers if s.get('id') == server_id), None) if server_id else None
    action = data.get('action')
    
    if action == 'toggle_clan_drop':
        s = bot_states["auto_clan_drop"]
        s['enabled'] = not s.get('enabled', False)
        if s['enabled'] and (not s.get('channel_id') or not s.get('ktb_channel_id')):
            s['enabled'] = False; return jsonify({'status': 'error', 'message': 'Clan Drop & KTB Channel ID must be set.'})
        msg = f"✅ Clan Auto Drop {'ENABLED' if s['enabled'] else 'DISABLED'}."
    elif action == 'update_clan_drop':
        s = bot_states["auto_clan_drop"]
        s.update({'channel_id': data.get('channel_id', '').strip(), 'ktb_channel_id': data.get('ktb_channel_id', '').strip()})
        s.setdefault('heart_thresholds', {}).update({k: int(v) for k, v in data.get('heart_thresholds', {}).items()})
        msg = '💾 Clan Drop settings updated.'
    elif action == 'toggle_bot_active':
        bot_id = data.get('target')
        bot_states["active"][bot_id] = not bot_states["active"].get(bot_id, False)
        msg = f"Bot {get_bot_name(bot_id)} is now {'ONLINE' if bot_states['active'][bot_id] else 'OFFLINE'}."
    elif action == 'toggle_bot_reboot':
        bot_id, delay = data.get('bot_id'), int(data.get("delay", 3600))
        s = bot_states["reboot_settings"][bot_id]
        s.update({'enabled': not s.get('enabled', False), 'delay': delay, 'failure_count': 0})
        if s['enabled']: s['next_reboot_time'] = time.time() + delay
        msg = f"🔄 Auto-Reboot {'ENABLED' if s['enabled'] else 'DISABLED'} for {get_bot_name(bot_id)}."
    elif action == 'toggle_watermelon':
        node = data.get('node')
        bot_states["watermelon_grab"][node] = not bot_states["watermelon_grab"].get(node, False)
        msg = f"🍉 Watermelon Grab {'ENABLED' if bot_states['watermelon_grab'][node] else 'DISABLED'} for {get_bot_name(node)}."
    elif server and action == 'toggle_harvest':
        node = data.get('node')
        key = f'auto_grab_enabled_{node}'
        server[key] = not server.get(key, False)
        server[f'heart_threshold_{node}'] = int(data.get('threshold', 50))
        msg = f"🎯 Card Grab {'ENABLED' if server[key] else 'DISABLED'} for {get_bot_name(f'main_{node}')}."
    elif server and action == 'toggle_broadcast':
        server['spam_enabled'] = not server.get('spam_enabled', False)
        server.update({'spam_message': data.get("message", "").strip(), 'spam_delay': int(data.get("delay", 10))})
        if server['spam_enabled'] and (not server['spam_message'] or not server['spam_channel_id']):
            server['spam_enabled'] = False; return jsonify({'status': 'error', 'message': 'Message/Channel is required.'})
        msg = f"📢 Broadcast {'ENABLED' if server['spam_enabled'] else 'DISABLED'} for {server['name']}."
    elif server and action == 'update_channels':
        server.update({k: v for k, v in data.items() if k in ['main_channel_id', 'ktb_channel_id', 'spam_channel_id']})
        msg = f"🔧 Channels updated for {server['name']}."
    elif action == 'add_server':
        name = data.get('name')
        if not name: return jsonify({'status': 'error', 'message': 'Server name is required.'}), 400
        new_server = {"id": f"server_{uuid.uuid4().hex}", "name": name, "spam_delay": 10}
        for i in range(len(main_tokens)): new_server.update({f'auto_grab_enabled_{i+1}': False, f'heart_threshold_{i+1}': 50})
        servers.append(new_server)
        return jsonify({'status': 'success', 'message': f'✅ Server "{name}" added.', 'reload': True})
    elif action == 'delete_server':
        servers[:] = [s for s in servers if s.get('id') != server_id]
        return jsonify({'status': 'success', 'message': f'🗑️ Server deleted.', 'reload': True})
    else:
        return jsonify({'status': 'error', 'message': 'Invalid action.'}), 400

    return jsonify({'status': 'success', 'message': msg})

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
    for bot_id, settings in reboot_s.items():
        settings['countdown'] = max(0, settings.get('next_reboot_time', 0) - now) if settings.get('enabled') else 0
        
    return jsonify({
        'bot_reboot_settings': reboot_s,
        'bot_statuses': {"main_bots": get_bot_status_list(bot_manager.get_main_bots_info(), "main"), "sub_accounts": get_bot_status_list(bot_manager.get_sub_bots_info(), "sub")},
        'server_start_time': server_start_time, 'servers': servers, 'watermelon_grab_states': bot_states["watermelon_grab"],
        'auto_clan_drop_status': {"enabled": clan_s.get("enabled", False), "countdown": (clan_s.get("last_cycle_start_time", 0) + clan_s.get("cycle_interval", 1800) - now) if clan_s.get("enabled") else 0}
    })

# --- MAIN EXECUTION ---
if __name__ == "__main__":
    print("🚀 Shadow Network Control - Compact Version Starting...", flush=True)
    load_settings()
    print("🔌 Initializing bots...", flush=True)
    
    all_tokens = [(t.strip(), i + 1, True) for i, t in enumerate(main_tokens) if t.strip()] + \
                 [(t.strip(), i, False) for i, t in enumerate(tokens) if t.strip()]

    for token, identifier, is_main in all_tokens:
        bot_id = f"main_{identifier}" if is_main else f"sub_{identifier}"
        bot = initialize_bot_in_thread(token, identifier, is_main)
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
