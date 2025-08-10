# PHIÊN BẢN SỬA LỖI TOÀN DIỆN - 8/2025
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
BOT_USER_IDS = {} # SỬA LỖI: Thêm từ điển toàn cục để lưu ID người dùng của bot
stop_events = {"reboot": threading.Event(), "clan_drop": threading.Event()}
server_start_time = time.time()

# --- CARD GRAB LOGGING SYSTEM ---
class CardGrabLogger:
    def __init__(self, max_logs=200):
        self.logs = deque(maxlen=max_logs)
        self.lock = threading.RLock()
        self.grab_attempts = {}  # Theo dõi các nỗ lực nhặt thẻ bằng message_id
        
    def log_grab_attempt(self, bot_id, channel_id, message_id, card_line, hearts, emoji):
        """Ghi log khi bot cố gắng nhặt thẻ"""
        with self.lock:
            timestamp = datetime.now()
            self.grab_attempts[message_id] = {
                'bot_id': bot_id, 'channel_id': channel_id, 'timestamp': timestamp,
                'card_line': card_line, 'hearts': hearts, 'emoji': emoji, 'status': 'attempting'
            }
            log_entry = {
                'id': f"attempt_{message_id}_{bot_id}", 'timestamp': timestamp, 'bot_name': get_bot_name(bot_id),
                'bot_id': bot_id, 'action': 'grab_attempt', 'hearts': hearts, 'card_line': card_line,
                'emoji': emoji, 'status': 'attempting', 'message_id': message_id, 'channel_id': channel_id
            }
            self.logs.append(log_entry)
    
    def log_grab_result(self, bot_id, channel_id, message_id, success, result_type, hearts=None, card_info=None):
        """Ghi log kết quả nhặt thẻ (thành công hoặc thất bại)"""
        with self.lock:
            timestamp = datetime.now()
            attempt = self.grab_attempts.get(message_id, {})
            hearts = hearts or attempt.get('hearts', 0)
            card_info = card_info or f"Line {attempt.get('card_line', '?')}"
            log_entry = {
                'id': f"result_{message_id}_{bot_id}", 'timestamp': timestamp, 'bot_name': get_bot_name(bot_id),
                'bot_id': bot_id, 'action': 'grab_result', 'hearts': hearts, 'card_info': card_info,
                'status': 'success' if success else 'failed', 'result_type': result_type,
                'message_id': message_id, 'channel_id': channel_id
            }
            self.logs.append(log_entry)
            if message_id in self.grab_attempts:
                self.grab_attempts[message_id]['status'] = 'success' if success else 'failed'
    
    def log_watermelon_grab(self, bot_id, channel_id, message_id, success):
        """Ghi log nhặt dưa hấu"""
        with self.lock:
            timestamp = datetime.now()
            log_entry = {
                'id': f"watermelon_{message_id}_{bot_id}", 'timestamp': timestamp, 'bot_name': get_bot_name(bot_id),
                'bot_id': bot_id, 'action': 'watermelon_grab', 'hearts': 0, 'card_info': '🍉 Watermelon',
                'status': 'success' if success else 'failed', 'result_type': 'watermelon',
                'message_id': message_id, 'channel_id': channel_id
            }
            self.logs.append(log_entry)
    
    def get_recent_logs(self, limit=50):
        with self.lock:
            return list(reversed(list(self.logs)))[:limit]
    
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
                if bot_name not in stats['bot_stats']:
                    stats['bot_stats'][bot_name] = {'attempts': 0, 'successes': 0, 'watermelons': 0}
                if log['action'] == 'grab_attempt':
                    stats['bot_stats'][bot_name]['attempts'] += 1
                elif log['action'] == 'grab_result' and log['status'] == 'success':
                    stats['bot_stats'][bot_name]['successes'] += 1
                elif log['action'] == 'watermelon_grab' and log['status'] == 'success':
                    stats['bot_stats'][bot_name]['watermelons'] += 1
            return stats
card_logger = CardGrabLogger()

# --- QUẢN LÝ BOT THREAD-SAFE (IMPROVED) ---
class ThreadSafeBotManager:
    def __init__(self):
        self._bots, self._rebooting, self._lock = {}, set(), threading.RLock()
    def add_bot(self, bot_id, bot_instance):
        with self._lock: self._bots[bot_id] = bot_instance; print(f"[Bot Manager] ✅ Added bot {bot_id}", flush=True)
    def remove_bot(self, bot_id):
        with self._lock:
            bot = self._bots.pop(bot_id, None)
            if bot:
                try:
                    if hasattr(bot, 'gateway') and hasattr(bot.gateway, 'close'): bot.gateway.close()
                except Exception as e: print(f"[Bot Manager] ⚠️ Error closing gateway for {bot_id}: {e}", flush=True)
                print(f"[Bot Manager] 🗑️ Removed bot {bot_id}", flush=True)
    def get_bot(self, bot_id):
        with self._lock: return self._bots.get(bot_id)
    def get_all_bots(self):
        with self._lock: return list(self._bots.items())
    def get_main_bots_info(self):
        with self._lock: return [(bot_id, bot) for bot_id, bot in self._bots.items() if bot_id.startswith('main_')]
    def get_sub_bots_info(self):
        with self._lock: return [(bot_id, bot) for bot_id, bot in self._bots.items() if bot_id.startswith('sub_')]
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
            if req.status_code == 200: print("[Settings] ✅ Đã lưu cài đặt lên JSONBin.io.", flush=True); return
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
            servers.extend(settings.get('servers', []))
            for key, value in settings.get('bot_states', {}).items():
                if key in bot_states and isinstance(value, dict): bot_states[key].update(value)
            return True
        except Exception as e: print(f"[Settings] ❌ Lỗi parse settings: {e}", flush=True); return False
    if api_key and bin_id:
        try:
            req = requests.get(f"https://api.jsonbin.io/v3/b/{bin_id}/latest", headers={'X-Master-Key': api_key}, timeout=15)
            if req.status_code == 200 and load_from_dict(req.json().get("record", {})): print("[Settings] ✅ Đã tải cài đặt từ JSONBin.io.", flush=True); return
        except Exception as e: print(f"[Settings] ⚠️ Lỗi tải từ JSONBin: {e}", flush=True)
    try:
        with open('backup_settings.json', 'r') as f:
            if load_from_dict(json.load(f)): print("[Settings] ✅ Đã tải cài đặt từ backup file.", flush=True); return
    except FileNotFoundError: print("[Settings] ⚠️ Không tìm thấy backup file, dùng cài đặt mặc định.", flush=True)
    except Exception as e: print(f"[Settings] ⚠️ Lỗi tải backup: {e}", flush=True)

# --- HÀM TRỢ GIÚP CHUNG ---
def get_bot_name(bot_id_str):
    try:
        parts = bot_id_str.split('_'); b_type, b_index = parts[0], int(parts[1])
        if b_type == 'main': return BOT_NAMES[b_index - 1] if 0 < b_index <= len(BOT_NAMES) else f"MAIN_{b_index}"
        return acc_names[b_index] if b_index < len(acc_names) else f"SUB_{b_index+1}"
    except (IndexError, ValueError): return bot_id_str.upper()

def safe_message_handler_wrapper(handler_func, bot, msg, *args):
    try: return handler_func(bot, msg, *args)
    except Exception as e:
        print(f"[Message Handler] ❌ Error in {handler_func.__name__}: {e}", flush=True)
        print(f"[Message Handler] 🐛 Traceback: {traceback.format_exc()}", flush=True)
        return None

# --- LOGIC GRAB CARD (ENHANCED WITH LOGGING) ---
def _find_and_select_card(bot, channel_id, last_drop_msg_id, heart_threshold, bot_num, ktb_channel_id):
    bot_id = f'main_{bot_num}'
    for _ in range(7):
        time.sleep(0.5)
        try:
            messages = bot.getMessages(channel_id, num=5).json()
            if not isinstance(messages, list): continue
            for msg_item in messages:
                if msg_item.get("author", {}).get("id") == karibbit_id and int(msg_item.get("id", 0)) > int(last_drop_msg_id):
                    embeds = msg_item.get("embeds", []); desc = embeds[0].get("description", "") if embeds else ""
                    if '♡' not in desc: continue
                    lines = desc.split('\n')[:3]
                    heart_numbers = [int(re.search(r'♡(\d+)', line).group(1)) if re.search(r'♡(\d+)', line) else 0 for line in lines]
                    if not any(heart_numbers): break
                    max_num = max(heart_numbers)
                    if max_num >= heart_threshold:
                        max_index = heart_numbers.index(max_num)
                        delays = {1: [0.4, 1.4, 2.1], 2: [0.7, 1.8, 2.4], 3: [0.7, 1.8, 2.4], 4: [0.8, 1.9, 2.5]}
                        bot_delays = delays.get(bot_num, [0.9, 2.0, 2.6])
                        emoji, delay = ["1️⃣", "2️⃣", "3️⃣"][max_index], bot_delays[max_index]
                        print(f"[CARD GRAB | Bot {bot_num}] Chọn dòng {max_index+1} với {max_num}♡ -> {emoji} sau {delay}s", flush=True)
                        card_logger.log_grab_attempt(bot_id, channel_id, last_drop_msg_id, max_index+1, max_num, emoji)
                        def grab_action():
                            try:
                                bot.addReaction(channel_id, last_drop_msg_id, emoji)
                                time.sleep(1.2)
                                if ktb_channel_id: bot.sendMessage(ktb_channel_id, "kt b")
                            except Exception as e: print(f"[CARD GRAB | Bot {bot_num}] ❌ Lỗi grab: {e}", flush=True)
                        threading.Timer(delay, grab_action).start()
                        return True
            return False
        except Exception as e: print(f"[CARD GRAB | Bot {bot_num}] ❌ Lỗi đọc messages: {e}", flush=True)
    return False

# --- LOGIC BOT (ENHANCED) ---
def handle_clan_drop(bot, msg, bot_num):
    clan_settings = bot_states["auto_clan_drop"]
    if not (clan_settings.get("enabled") and msg.get("channel_id") == clan_settings.get("channel_id")): return
    bot_id_str = f'main_{bot_num}'
    threshold = clan_settings.get("heart_thresholds", {}).get(bot_id_str, 50)
    threading.Thread(target=_find_and_select_card, args=(bot, clan_settings["channel_id"], msg["id"], threshold, bot_num, clan_settings["ktb_channel_id"]), daemon=True).start()

def handle_grab(bot, msg, bot_num):
    channel_id = msg.get("channel_id"); target_server = next((s for s in servers if s.get('main_channel_id') == channel_id), None)
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
                    reactions = target_message.get('reactions', []); watermelon_found = False
                    for reaction in reactions:
                        emoji_name = reaction.get('emoji', {}).get('name', '')
                        if '🍉' in emoji_name or 'watermelon' in emoji_name.lower() or 'dua' in emoji_name.lower():
                            watermelon_found = True
                            print(f"[WATERMELON | Bot {bot_num}] 🎯 PHÁT HIỆN DƯA HẤU!", flush=True)
                            try:
                                bot.addReaction(channel_id, last_drop_msg_id, "🍉")
                                card_logger.log_watermelon_grab(bot_id_str, channel_id, last_drop_msg_id, True)
                            except Exception as e:
                                print(f"[WATERMELON | Bot {bot_num}] ❌ Lỗi react dưa: {e}", flush=True)
                                card_logger.log_watermelon_grab(bot_id_str, channel_id, last_drop_msg_id, False)
                            return
                    if not watermelon_found: print(f"[WATERMELON | Bot {bot_num}] 😞 Không tìm thấy dưa hấu.", flush=True)
                except Exception as e: print(f"[WATERMELON | Bot {bot_num}] ❌ Lỗi check dưa: {e}", flush=True)
            threading.Thread(target=check_for_watermelon_patiently, daemon=True).start()
    threading.Thread(target=grab_logic_thread, daemon=True).start()

def handle_karuta_result(bot, msg, bot_num):
    """SỬA LỖI: Xử lý kết quả từ Karuta mà không gây lỗi"""
    content, mentions, channel_id, bot_id = msg.get("content", "").lower(), msg.get("mentions", []), msg.get("channel_id"), f'main_{bot_num}'
    bot_user_id = BOT_USER_IDS.get(bot_id)
    if not bot_user_id or bot_user_id not in [mention.get("id") for mention in mentions]: return
    success, result_type, hearts, card_info = False, "unknown", 0, "Unknown Card"
    if "fought off" in content or "took the" in content:
        success = True; result_type = "fought_off" if "fought off" in content else "took_the"
        heart_match = re.search(r'♡(\d+)', content)
        if heart_match: hearts = int(heart_match.group(1))
        card_info = "Fought off challengers" if "fought off" in content else "Took the card"
        print(f"[CARD RESULT | Bot {bot_num}] {result_type.upper()} - {hearts}♡", flush=True)
        card_logger.log_grab_result(bot_id, channel_id, str(int(time.time() * 1000)), success, result_type, hearts, card_info)

# --- HỆ THỐNG REBOOT & HEALTH CHECK (IMPROVED) ---
def check_bot_health(bot_instance, bot_id):
    try:
        stats = bot_states["health_stats"].setdefault(bot_id, {'consecutive_failures': 0, 'last_check': 0})
        stats['last_check'] = time.time()
        if not bot_instance or not hasattr(bot_instance, 'gateway'): stats['consecutive_failures'] += 1; return False
        is_connected = hasattr(bot_instance.gateway, 'connected') and bot_instance.gateway.connected
        if is_connected: stats['consecutive_failures'] = 0
        else: stats['consecutive_failures'] += 1; print(f"[Health Check] ⚠️ Bot {bot_id} not connected - failures: {stats['consecutive_failures']}", flush=True)
        return is_connected
    except Exception as e:
        print(f"[Health Check] ❌ Exception for {bot_id}: {e}", flush=True)
        bot_states["health_stats"].setdefault(bot_id, {})['consecutive_failures'] = bot_states["health_stats"][bot_id].get('consecutive_failures', 0) + 1
        return False

def handle_reboot_failure(bot_id):
    settings = bot_states["reboot_settings"].setdefault(bot_id, {'delay': 3600, 'enabled': True})
    failure_count = settings.get('failure_count', 0) + 1; settings['failure_count'] = failure_count
    backoff_multiplier = min(2 ** failure_count, 8); base_delay = settings.get('delay', 3600)
    next_try_delay = max(600, base_delay / backoff_multiplier) * backoff_multiplier
    settings['next_reboot_time'] = time.time() + next_try_delay
    print(f"[Safe Reboot] 🔴 Failure #{failure_count} for {bot_id}. Thử lại sau {next_try_delay/60:.1f} phút.", flush=True)
    if failure_count >= 5: settings['enabled'] = False; print(f"[Safe Reboot] ❌ Tắt auto-reboot cho {bot_id} sau 5 lần thất bại.", flush=True)

def safe_reboot_bot(bot_id):
    if not bot_manager.start_reboot(bot_id): print(f"[Safe Reboot] ⚠️ Bot {bot_id} đã đang reboot. Bỏ qua.", flush=True); return False
    print(f"[Safe Reboot] 🔄 Bắt đầu reboot bot {bot_id}...", flush=True)
    try:
        match = re.match(r"main_(\d+)", bot_id)
        if not match: raise ValueError("Định dạng bot_id không hợp lệ cho reboot.")
        bot_index = int(match.group(1)) - 1
        if not (0 <= bot_index < len(main_tokens)): raise IndexError("Bot index ngoài phạm vi token.")
        token, bot_name = main_tokens[bot_index].strip(), get_bot_name(bot_id)
        print(f"[Safe Reboot] 🧹 Cleaning up old instance for {bot_name}", flush=True)
        bot_manager.remove_bot(bot_id)
        settings = bot_states["reboot_settings"].get(bot_id, {})
        failure_count = settings.get('failure_count', 0)
        wait_time = random.uniform(20, 40) + min(failure_count * 30, 300)
        print(f"[Safe Reboot] ⏳ Chờ {wait_time:.1f}s để cleanup...", flush=True)
        time.sleep(wait_time)
        print(f"[Safe Reboot] 🏗️ Creating new instance for {bot_name}", flush=True)
        new_bot = create_bot(token, bot_identifier=(bot_index + 1), is_main=True)
        if not new_bot: raise Exception("Không thể tạo instance bot mới hoặc kết nối gateway thất bại.")
        bot_manager.add_bot(bot_id, new_bot)
        settings.update({'next_reboot_time': time.time() + settings.get('delay', 3600), 'failure_count': 0, 'last_reboot_time': time.time()})
        bot_states["health_stats"][bot_id]['consecutive_failures'] = 0
        print(f"[Safe Reboot] ✅ Reboot thành công {bot_name}", flush=True)
        return True
    except Exception as e:
        print(f"[Safe Reboot] ❌ Reboot thất bại cho {bot_id}: {e}", flush=True); traceback.print_exc()
        handle_reboot_failure(bot_id); return False
    finally: bot_manager.end_reboot(bot_id)

# --- VÒNG LẶP NỀN (IMPROVED) ---
def auto_reboot_loop():
    print("[Safe Reboot] 🚀 Khởi động luồng tự động reboot.", flush=True)
    last_global_reboot_time, consecutive_system_failures = 0, 0
    while not stop_events["reboot"].is_set():
        try:
            now = time.time()
            if now - last_global_reboot_time < 600: stop_events["reboot"].wait(60); continue
            bot_to_reboot, highest_priority_score = None, -1
            reboot_settings_copy = dict(bot_states["reboot_settings"].items())
            for bot_id, settings in reboot_settings_copy.items():
                if not settings.get('enabled', False) or bot_manager.is_rebooting(bot_id): continue
                next_reboot_time = settings.get('next_reboot_time', 0)
                if now < next_reboot_time: continue
                failure_count = bot_states["health_stats"].get(bot_id, {}).get('consecutive_failures', 0)
                priority_score = (failure_count * 1000) + (now - next_reboot_time)
                if priority_score > highest_priority_score: highest_priority_score, bot_to_reboot = priority_score, bot_id
            if bot_to_reboot:
                print(f"[Safe Reboot] 🎯 Chọn reboot bot: {bot_to_reboot} (priority: {highest_priority_score:.1f})", flush=True)
                if safe_reboot_bot(bot_to_reboot):
                    last_global_reboot_time = now; consecutive_system_failures = 0
                    wait_time = random.uniform(300, 600)
                    print(f"[Safe Reboot] ⏳ Chờ {wait_time:.0f}s...", flush=True); stop_events["reboot"].wait(wait_time)
                else:
                    consecutive_system_failures += 1; backoff_time = min(120 * (2 ** consecutive_system_failures), 1800)
                    print(f"[Safe Reboot] ❌ Reboot thất bại. Hệ thống backoff: {backoff_time}s", flush=True); stop_events["reboot"].wait(backoff_time)
            else: stop_events["reboot"].wait(60)
        except Exception as e: print(f"[Safe Reboot] ❌ Lỗi nghiêm trọng: {e}", flush=True); traceback.print_exc(); stop_events["reboot"].wait(120)

def run_clan_drop_cycle():
    print("[Clan Drop] 🚀 Bắt đầu chu kỳ drop clan.", flush=True)
    settings = bot_states["auto_clan_drop"]; channel_id = settings.get("channel_id")
    active_main_bots = [(bot, int(bot_id.split('_')[1])) for bot_id, bot in bot_manager.get_main_bots_info() if bot and bot_states["active"].get(bot_id, False)]
    if not active_main_bots: print("[Clan Drop] ⚠️ Không có bot chính nào hoạt động.", flush=True); return
    for bot, bot_num in active_main_bots:
        if stop_events["clan_drop"].is_set(): break
        try:
            print(f"[Clan Drop] 📤 Bot {get_bot_name(f'main_{bot_num}')} đang gửi 'kd'...", flush=True)
            bot.sendMessage(channel_id, "kd"); time.sleep(random.uniform(settings["bot_delay"] * 0.8, settings["bot_delay"] * 1.2))
        except Exception as e: print(f"[Clan Drop] ❌ Lỗi khi gửi 'kd' từ bot {bot_num}: {e}", flush=True)
    settings["last_cycle_start_time"] = time.time(); save_settings()

def auto_clan_drop_loop():
    while not stop_events["clan_drop"].is_set():
        settings = bot_states["auto_clan_drop"]
        if (settings.get("enabled") and settings.get("channel_id") and (time.time() - settings.get("last_cycle_start_time", 0)) >= settings.get("cycle_interval", 1800)):
            run_clan_drop_cycle()
        stop_events["clan_drop"].wait(60)
    print("[Clan Drop] 🛑 Luồng tự động drop clan đã dừng.", flush=True)

def spam_for_server(server_config, stop_event):
    server_name, channel_id, message = server_config.get('name'), server_config.get('spam_channel_id'), server_config.get('spam_message')
    while not stop_event.is_set():
        try:
            bots_to_spam = [bot for bot_id, bot in bot_manager.get_all_bots() if bot and bot_states["active"].get(bot_id)]
            delay = server_config.get('spam_delay', 10)
            for bot in bots_to_spam:
                if stop_event.is_set(): break
                try: bot.sendMessage(channel_id, message); time.sleep(random.uniform(1.5, 2.5))
                except Exception as e: print(f"[Spam] ❌ Lỗi gửi spam từ bot tới {server_name}: {e}", flush=True)
            stop_event.wait(random.uniform(delay * 0.9, delay * 1.1))
        except Exception as e: print(f"[Spam] ❌ ERROR in spam_for_server {server_name}: {e}", flush=True); stop_event.wait(10)

def spam_loop_manager():
    active_threads = {}
    while True:
        try:
            current_ids = {s['id'] for s in servers}
            for server_id in list(active_threads.keys()):
                if server_id not in current_ids: print(f"[Spam] 🛑 Dừng luồng cho server đã xóa: {server_id}", flush=True); active_threads.pop(server_id)[1].set()
            for server in servers:
                server_id = server.get('id')
                spam_on = server.get('spam_enabled') and server.get('spam_message') and server.get('spam_channel_id')
                if spam_on and server_id not in active_threads:
                    print(f"[Spam] 🚀 Bắt đầu luồng cho server: {server.get('name')}", flush=True); stop_event = threading.Event()
                    thread = threading.Thread(target=spam_for_server, args=(server, stop_event), daemon=True); thread.start()
                    active_threads[server_id] = (thread, stop_event)
                elif not spam_on and server_id in active_threads:
                    print(f"[Spam] 🛑 Dừng luồng cho server: {server.get('name')}", flush=True); active_threads.pop(server_id)[1].set()
            time.sleep(5)
        except Exception as e: print(f"[Spam] ❌ ERROR in spam_loop_manager: {e}", flush=True); time.sleep(5)

def periodic_task(interval, task_func, task_name):
    print(f"[{task_name}] 🚀 Khởi động luồng định kỳ.", flush=True)
    while True: time.sleep(interval);
    try: task_func()
    except Exception as e: print(f"[{task_name}] ❌ Lỗi: {e}", flush=True)

def health_monitoring_check():
    for bot_id, bot in bot_manager.get_all_bots(): check_bot_health(bot, bot_id)

# --- KHỞI TẠO BOT (SỬA LỖI) ---
def create_bot(token, bot_identifier, is_main=False):
    try:
        bot = discum.Client(token=token, log=False)
        bot_id_str = f"main_{bot_identifier}" if is_main else f"sub_{bot_identifier}"
        @bot.gateway.command
        def on_ready(resp):
            try:
                if resp.event.ready:
                    user = resp.raw.get("user", {})
                    user_id, username = user.get('id', 'Unknown'), user.get('username', 'Unknown')
                    if user_id != 'Unknown': BOT_USER_IDS[bot_id_str] = user_id  # Sửa lỗi: Lưu vào dict toàn cục
                    print(f"[Bot] ✅ Đăng nhập: {user_id} ({get_bot_name(bot_id_str)}) - {username}", flush=True)
                    bot_states["health_stats"].setdefault(bot_id_str, {}).update({'created_time': time.time(), 'consecutive_failures': 0})
            except Exception as e: print(f"[Bot] ❌ Error in on_ready for {bot_id_str}: {e}", flush=True)
        if is_main:
            @bot.gateway.command
            def on_message(resp):
                try:
                    if resp.event.message:
                        msg = resp.parsed.auto(); author_id = msg.get("author", {}).get("id"); content = msg.get("content", "").lower()
                        if author_id == karuta_id:
                            if "dropping" in content:
                                handler = handle_clan_drop if msg.get("mentions") else handle_grab
                                safe_message_handler_wrapper(handler, bot, msg, bot_identifier)
                            elif ("fought off" in content or "took the" in content) and msg.get("mentions"):
                                safe_message_handler_wrapper(handle_karuta_result, bot, msg, bot_identifier)
                except Exception as e: print(f"[Bot] ❌ Error in on_message for {bot_id_str}: {e}", flush=True)
        def start_gateway():
            try: bot.gateway.run(auto_reconnect=True)
            except Exception as e: print(f"[Bot] ❌ Gateway error for {bot_id_str}: {e}", flush=True)
        threading.Thread(target=start_gateway, daemon=True).start()
        connection_timeout = 20; start_time = time.time()
        while time.time() - start_time < connection_timeout:
            if hasattr(bot.gateway, 'connected') and bot.gateway.connected: print(f"[Bot] ✅ Gateway connected for {bot_id_str}", flush=True); return bot
            time.sleep(0.5)
        print(f"[Bot] ⚠️ Gateway connection timeout for {bot_id_str}. Closing gateway.", flush=True); bot.gateway.close(); return None
    except Exception as e:
        print(f"[Bot] ❌ Lỗi nghiêm trọng khi tạo bot {bot_identifier}: {e}", flush=True); traceback.print_exc(); return None

# --- FLASK APP & GIAO DIỆN ---
app = Flask(__name__)
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Shadow Network Control - Enhanced with Card Logging</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <link href="https://fonts.googleapis.com/css2?family=Creepster&family=Orbitron:wght@400;700;900&family=Courier+Prime:wght@400;700&family=Nosifer&display=swap" rel="stylesheet">
    <style>
        :root{--primary-bg:#0a0a0a;--secondary-bg:#1a1a1a;--panel-bg:#111111;--border-color:#333333;--blood-red:#8b0000;--dark-red:#550000;--bone-white:#f8f8ff;--necro-green:#228b22;--text-primary:#f0f0f0;--text-secondary:#cccccc;--warning-orange:#ff8c00;--success-green:#32cd32;--attempt-blue:#4169e1;--success-gold:#ffd700;--fail-red:#dc143c;--watermelon-pink:#ff69b4}body{font-family:'Courier Prime',monospace;background:var(--primary-bg);color:var(--text-primary);margin:0;padding:0}.container{max-width:1800px;margin:0 auto;padding:20px}.header{text-align:center;margin-bottom:30px;padding:20px;border-bottom:2px solid var(--blood-red);position:relative}.title{font-family:'Nosifer',cursive;font-size:3rem;color:var(--blood-red)}.subtitle{font-family:'Orbitron',sans-serif;font-size:1rem;color:var(--necro-green);margin-top:10px}.main-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(500px,1fr));gap:20px}.panel{background:var(--panel-bg);border:1px solid var(--border-color);border-radius:10px;padding:25px;position:relative}.panel h2{font-family:'Orbitron',cursive;font-size:1.4rem;margin-bottom:20px;text-transform:uppercase;border-bottom:2px solid;padding-bottom:10px;color:var(--bone-white)}.panel h2 i{margin-right:10px}.btn{background:var(--secondary-bg);border:1px solid var(--border-color);color:var(--text-primary);padding:10px 15px;border-radius:4px;cursor:pointer;font-family:'Orbitron',monospace;font-weight:700;text-transform:uppercase;width:100%;transition:all .3s ease}.btn:hover{background:var(--dark-red);border-color:var(--blood-red)}.btn-small{padding:5px 10px;font-size:.9em}.input-group{display:flex;align-items:stretch;gap:10px;margin-bottom:15px}.input-group label{background:#000;border:1px solid var(--border-color);border-right:0;padding:10px 15px;border-radius:4px 0 0 4px;display:flex;align-items:center;min-width:120px}.input-group input,.input-group textarea{flex-grow:1;background:#000;border:1px solid var(--border-color);color:var(--text-primary);padding:10px 15px;border-radius:0 4px 4px 0;font-family:'Courier Prime',monospace}.grab-section{display:flex;justify-content:space-between;align-items:center;margin-bottom:15px;padding:15px;background:rgba(0,0,0,.2);border-radius:8px}.grab-section h3{margin:0;display:flex;align-items:center;gap:10px;width:80px;flex-shrink:0}.grab-section .input-group{margin-bottom:0;flex-grow:1;margin-left:20px}.msg-status{text-align:center;color:var(--necro-green);padding:12px;border:1px dashed var(--border-color);border-radius:4px;margin-bottom:20px;display:none}.msg-status.error{color:var(--blood-red);border-color:var(--blood-red)}.msg-status.warning{color:var(--warning-orange);border-color:var(--warning-orange)}.status-panel,.global-settings-panel,.clan-drop-panel,.card-log-panel{grid-column:1 / -1}.status-grid{display:grid;grid-template-columns:1fr 1fr;gap:15px}.status-row{display:flex;justify-content:space-between;align-items:center;padding:12px;background:rgba(0,0,0,.4);border-radius:8px}.timer-display{font-size:1.2em;font-weight:700}.bot-status-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:8px}.bot-status-item{display:flex;justify-content:space-between;align-items:center;padding:5px 8px;background:rgba(0,0,0,.3);border-radius:4px}.btn-toggle-state{padding:3px 5px;font-size:.9em;border-radius:4px;cursor:pointer;text-transform:uppercase;background:transparent;font-weight:700;border:none}.btn-rise{color:var(--success-green)}.btn-rest{color:var(--dark-red)}.btn-warning{color:var(--warning-orange)}.add-server-btn{display:flex;align-items:center;justify-content:center;min-height:200px;border:2px dashed var(--border-color);cursor:pointer;transition:all .3s ease}.add-server-btn:hover{background:var(--secondary-bg);border-color:var(--blood-red)}.add-server-btn i{font-size:3rem;color:var(--text-secondary)}.btn-delete-server{position:absolute;top:15px;right:15px;background:var(--dark-red);border:1px solid var(--blood-red);color:var(--bone-white);width:auto;padding:5px 10px;border-radius:50%}.server-sub-panel{border-top:1px solid var(--border-color);margin-top:20px;padding-top:20px}.flex-row{display:flex;gap:10px;align-items:center}.health-indicator{display:inline-block;width:10px;height:10px;border-radius:50%;margin-left:5px}.health-good{background-color:var(--success-green)}.health-warning{background-color:var(--warning-orange)}.health-bad{background-color:var(--blood-red)}.system-stats{font-size:.9em;color:var(--text-secondary);margin-top:10px}.log-container{max-height:500px;overflow-y:auto;border:1px solid var(--border-color);border-radius:8px;padding:15px;background:rgba(0,0,0,.2)}.log-entry{display:flex;justify-content:space-between;align-items:center;padding:8px 12px;margin-bottom:5px;border-radius:6px;font-size:.9em}.log-entry.attempt{background:rgba(65,105,225,.1);border-left:4px solid var(--attempt-blue)}.log-entry.success{background:rgba(255,215,0,.1);border-left:4px solid var(--success-gold)}.log-entry.failed{background:rgba(220,20,60,.1);border-left:4px solid var(--fail-red)}.log-entry.watermelon{background:rgba(255,105,180,.1);border-left:4px solid var(--watermelon-pink)}.log-entry .log-time{font-size:.8em;color:var(--text-secondary)}.log-entry .log-bot{font-weight:bold;color:var(--necro-green)}.log-entry .log-hearts{color:var(--blood-red);font-weight:bold}.log-entry .log-action{color:var(--text-primary)}.log-stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:10px;margin-bottom:20px}.stat-card{background:rgba(0,0,0,.3);padding:15px;border-radius:8px;text-align:center}.stat-number{font-size:2em;font-weight:bold;color:var(--necro-green)}.stat-label{font-size:.9em;color:var(--text-secondary)}.log-controls{display:flex;gap:10px;margin-bottom:20px;align-items:center}
    </style>
</head>
<body>
    <div class=container>
        <div class=header>
            <h1 class=title>Shadow Network Control</h1>
            <div class=subtitle>Enhanced with Real-time Card Grab Logging</div>
        </div>
        <div id=msg-status-container class=msg-status><span id=msg-status-text></span></div>
        <div class=main-grid>
            <div class="panel card-log-panel">
                <h2><i class="fas fa-scroll"></i> Card Grab Activity Log</h2>
                <div class=log-stats id=log-stats></div>
                <div class=log-controls>
                    <button type=button id=clear-logs-btn class="btn btn-small">Clear Logs</button>
                    <button type=button id=refresh-logs-btn class="btn btn-small">Refresh</button>
                    <span class=timer-display>Auto-refresh: <span id=log-refresh-countdown>10</span>s</span>
                </div>
                <div class=log-container id=log-container></div>
            </div>
            <div class="panel status-panel">
                <h2><i class="fas fa-heartbeat"></i> System Status & Enhanced Reboot Control</h2>
                <div class=status-row style=margin-bottom:20px><span><i class="fas fa-server"></i> System Uptime</span>
                    <div><span id=uptime-timer class=timer-display>--:--:--</span></div>
                </div>
                <div class=status-row style=margin-bottom:20px><span><i class="fas fa-shield-alt"></i> Safe Reboot Status</span>
                    <div><span id=reboot-status class=timer-display>ACTIVE</span></div>
                </div>
                <div class=server-sub-panel>
                    <h3><i class="fas fa-robot"></i> Enhanced Bot Control Matrix</h3>
                    <div class=system-stats>
                        <div>🔒 Safety Features: Health Checks, Exponential Backoff, Rate Limiting</div>
                        <div>⏱️ Min Reboot Interval: 10 minutes | Max Failures: 5 attempts</div>
                        <div>🎯 Reboot Strategy: Priority-based, one-at-a-time with cleanup delay</div>
                    </div>
                    <div id=bot-control-grid class=bot-status-grid style=grid-template-columns:repeat(auto-fit,minmax(380px,1fr))></div>
                </div>
            </div>
            <div class="panel clan-drop-panel">
                <h2><i class="fas fa-users"></i> Clan Auto Drop</h2>
                <div class=status-grid style=grid-template-columns:1fr>
                    <div class=status-row><span><i class="fas fa-hourglass-half"></i> Next Drop Cycle</span>
                        <div class=flex-row><span id=clan-drop-timer class=timer-display>--:--:--</span> <button type=button id=clan-drop-toggle-btn class="btn btn-small">{{ 'DISABLE' if auto_clan_drop.enabled else 'ENABLE' }}</button></div>
                    </div>
                </div>
                <div class=server-sub-panel>
                    <h3><i class="fas fa-cogs"></i> Configuration</h3>
                    <div class=input-group><label>Drop Channel ID</label><input type=text id=clan-drop-channel-id value="{{ auto_clan_drop.channel_id or '' }}"></div>
                    <div class=input-group><label>KTB Channel ID</label><input type=text id=clan-drop-ktb-channel-id value="{{ auto_clan_drop.ktb_channel_id or '' }}"></div>
                </div>
                <div class=server-sub-panel>
                    <h3><i class="fas fa-crosshairs"></i> Soul Harvest (Clan Drop)</h3>
                    {% for bot in main_bots_info %}
                    <div class=grab-section>
                        <h3>{{ bot.name }}</h3>
                        <div class=input-group><input type=number class=clan-drop-threshold data-node=main_{{bot.id}} value="{{ auto_clan_drop.heart_thresholds[('main_' + bot.id|string)]|default(50) }}" min=0></div>
                    </div>
                    {% endfor %}
                </div><button type=button id=clan-drop-save-btn class=btn style=margin-top:20px>Save Clan Drop Settings</button>
            </div>
            <div class="panel global-settings-panel">
                <h2><i class="fas fa-globe"></i> Global Event Settings</h2>
                <div class=server-sub-panel>
                    <h3><i class="fas fa-seedling"></i> Watermelon Grab (All Servers)</h3>
                    <div id=global-watermelon-grid class=bot-status-grid style=grid-template-columns:repeat(auto-fit,minmax(200px,1fr))></div>
                </div>
            </div>
            {% for server in servers %}
            <div class="panel server-panel" data-server-id={{server.id}}>
                <button class=btn-delete-server title="Delete Server"><i class="fas fa-times"></i></button>
                <h2><i class="fas fa-server"></i> {{ server.name }}</h2>
                <div class=server-sub-panel>
                    <h3><i class="fas fa-cogs"></i> Channel Config</h3>
                    <div class=input-group><label>Main Channel ID</label><input type=text class=channel-input data-field=main_channel_id value="{{ server.main_channel_id or '' }}"></div>
                    <div class=input-group><label>KTB Channel ID</label><input type=text class=channel-input data-field=ktb_channel_id value="{{ server.ktb_channel_id or '' }}"></div>
                    <div class=input-group><label>Spam Channel ID</label><input type=text class=channel-input data-field=spam_channel_id value="{{ server.spam_channel_id or '' }}"></div>
                </div>
                <div class=server-sub-panel>
                    <h3><i class="fas fa-crosshairs"></i> Soul Harvest (Card Grab)</h3>
                    {% for bot in main_bots_info %}
                    <div class=grab-section>
                        <h3>{{ bot.name }}</h3>
                        <div class=input-group><input type=number class=harvest-threshold data-node={{bot.id}} value="{{ server['heart_threshold_' + bot.id|string] or 50 }}" min=0> <button type=button class="btn harvest-toggle" data-node={{bot.id}}>{{ 'DISABLE' if server['auto_grab_enabled_' + bot.id|string] else 'ENABLE' }}</button></div>
                    </div>
                    {% endfor %}
                </div>
                <div class=server-sub-panel>
                    <h3><i class="fas fa-paper-plane"></i> Auto Broadcast</h3>
                    <div class=input-group><label>Message</label><textarea class=spam-message rows=2>{{ server.spam_message or '' }}</textarea></div>
                    <div class=input-group><label>Delay (s)</label> <input type=number class=spam-delay value="{{ server.spam_delay or 10 }}"> <span class="timer-display spam-timer">--:--:--</span></div><button type=button class="btn broadcast-toggle">{{ 'DISABLE' if server.spam_enabled else 'ENABLE' }}</button>
                </div>
            </div>
            {% endfor %}
            <div class="panel add-server-btn" id=add-server-btn><i class="fas fa-plus"></i></div>
        </div>
    </div>
    <script>document.addEventListener('DOMContentLoaded',function(){const e=document.getElementById('msg-status-container'),t=document.getElementById('msg-status-text');let n;function s(n,s='success'){n&&(t.textContent=n,e.className=`msg-status ${'error'===s?'error':'warning'===s?'warning':''}`,e.style.display='block',setTimeout(()=>{e.style.display='none'},4e3))}async function a(e='',t={}){try{const n=await fetch(e,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(t)}),a=await n.json();return s(a.message,'success'!==a.status?'error':'success'),'success'===a.status&&'/api/save_settings'!==e&&(fetch('/api/save_settings',{method:'POST'}),a.reload&&setTimeout(()=>window.location.reload(),500)),setTimeout(c,500),a}catch(e){return console.error('Error:',e),s('Server communication error.','error'),undefined}}function o(e){return isNaN(e)||e<0?'--:--:--':(e=Math.floor(e),`${Math.floor(e/3600).toString().padStart(2,'0')}:${Math.floor(e%3600/60).toString().padStart(2,'0')}:${(e%60).toString().padStart(2,'0')}`)}function i(e){return e.toLocaleTimeString('vi-VN',{hour:'2-digit',minute:'2-digit',second:'2-digit'})}function l(e,{textContent:t,className:n,value:s,innerHTML:a}){e&&(t!==undefined&&(e.textContent=t),n!==undefined&&(e.className=n),s!==undefined&&(e.value=s),a!==undefined&&(e.innerHTML=a))}function d(e,t){document.getElementById('log-stats').innerHTML=`
                <div class=stat-card><div class=stat-number>${t.total_attempts}</div><div class=stat-label>Grab Attempts</div></div>
                <div class=stat-card><div class=stat-number style="color: var(--success-gold)">${t.successful_grabs}</div><div class=stat-label>Successful Grabs</div></div>
                <div class=stat-card><div class=stat-number style="color: var(--watermelon-pink)">${t.watermelon_grabs}</div><div class=stat-label>Watermelons</div></div>
                <div class=stat-card><div class=stat-number style="color: var(--warning-orange)">${t.high_heart_grabs}</div><div class=stat-label>100+ Hearts</div></div>`;const n=document.getElementById('log-container');if(0===e.length)return void(n.innerHTML='<div style="text-align: center; color: var(--text-secondary); padding: 20px;">No card grab activity yet...</div>');n.innerHTML=e.map(e=>{let t,n,s,a=new Date(e.timestamp);switch(a=i(a),s='log-entry',t='',n='',e.action){case'grab_attempt':s+=' attempt',t='<i class="fas fa-crosshairs"></i>',n=`Attempting Line ${e.card_line} (${e.emoji})`;break;case'grab_result':s+='success'===e.status?' success':' failed',t='success'===e.status?'<i class="fas fa-trophy"></i>':'<i class="fas fa-times-circle"></i>',n='success'===e.status?'fought_off'===e.result_type?'Fought off challengers!':'Took the card!':'Grab failed';break;case'watermelon_grab':s+=' watermelon',t='<i class="fas fa-seedling"></i>',n='success'===e.status?'Watermelon grabbed!':'Watermelon attempt failed'}return`
                    <div class="${s}">
                        <div style="display: flex; align-items: center; gap: 10px;">
                            ${t}
                            <span class=log-bot>${e.bot_name}</span>
                            <span class=log-action>${n}</span>
                            ${e.hearts?`<span class=log-hearts>♡${e.hearts}</span>`:''}
                        </div>
                        <div class=log-time>${a}</div>
                    </div>`}).join('')}async function r(){try{const e=await fetch('/api/card_logs'),t=await e.json();d(t.logs,t.stats)}catch(e){console.error('Error fetching logs:',e)}}function u(){n&&clearInterval(n);let e=10;n=setInterval(()=>{e--,document.getElementById('log-refresh-countdown').textContent=e,e<=0&&(r(),e=10)},1e3)}async function c(){try{const e=await fetch('/status'),t=await e.json();l(document.getElementById('uptime-timer'),{textContent:o((Date.now()/1e3)-t.server_start_time)}),t.auto_clan_drop_status&&(l(document.getElementById('clan-drop-timer'),{textContent:o(t.auto_clan_drop_status.countdown)}),l(document.getElementById('clan-drop-toggle-btn'),{textContent:t.auto_clan_drop_status.enabled?'DISABLE':'ENABLE'}));const n=document.getElementById('bot-control-grid'),s=[...t.bot_statuses.main_bots,...t.bot_statuses.sub_accounts],a=new Set;s.forEach(e=>{const s=e.reboot_id;a.add(`bot-container-${s}`);let i=document.getElementById(`bot-container-${s}`);i||(i=document.createElement('div'),i.id=`bot-container-${s}`,i.className='status-row',i.style.cssText='flex-direction: column; align-items: stretch; padding: 10px;',n.appendChild(i));let d='health-good';'warning'===e.health_status?d='health-warning':'bad'===e.health_status&&(d='health-bad');let r=e.is_rebooting?' <i class="fas fa-sync-alt fa-spin"></i>':'';let c=`
                        <div style="display: flex; justify-content: space-between; align-items: center; width: 100%;">
                           <span style="font-weight: bold; ${'main'===e.type?'color: #FF4500;':''}">${e.name}<span class="health-indicator ${d}"></span>${r}</span>
                           <button type=button id=toggle-state-${s} data-target=${s} class="btn-toggle-state ${e.is_active?'btn-rise':'btn-rest'}">
                               ${e.is_active?'ONLINE':'OFFLINE'}
                           </button>
                        </div>`;if('main'===e.type){const e=t.bot_reboot_settings[s]||{delay:3600,enabled:!1,failure_count:0},n=e.failure_count>0?'btn-warning':e.enabled?'btn-rise':'btn-rest',a=e.failure_count>0?`FAIL(${e.failure_count})`:e.enabled?'AUTO':'MANUAL',i=o(e.countdown);c+=`
                        <div class=input-group style=margin-top:10px;margin-bottom:0>
                             <input type=number class=bot-reboot-delay value=${e.delay} data-bot-id=${s} style="width: 80px; text-align: right; flex-grow: 0;">
                             <span id=timer-${s} class="timer-display bot-reboot-timer" style="padding: 0 10px;">${i}</span>
                             <button type=button id=toggle-reboot-${s} class="btn btn-small bot-reboot-toggle ${n}" data-bot-id=${s}>
                                 ${a}
                             </button>
                        </div>`}i.innerHTML=c}),Array.from(n.children).forEach(e=>{a.has(e.id)||e.remove()});const i=document.getElementById('global-watermelon-grid');i.innerHTML='',t.watermelon_grab_states&&t.bot_statuses&&t.bot_statuses.main_bots.forEach(e=>{const n=e.reboot_id,s=t.watermelon_grab_states[n],a=document.createElement('div');a.className='bot-status-item',a.innerHTML=`<span>${e.name}</span>
                            <button type=button class="btn btn-small watermelon-toggle" data-node=${n}><i class="fas fa-seedling"></i>&nbsp;${s?'DISABLE':'ENABLE'}</button>`,i.appendChild(a)}),t.servers.forEach(e=>{const t=document.querySelector(`.server-panel[data-server-id="${e.id}"]`);t&&(t.querySelectorAll('.harvest-toggle').forEach(t=>{const n=t.dataset.node;l(t,{textContent:e[`auto_grab_enabled_${n}`]?'DISABLE':'ENABLE'})}),l(t.querySelector('.broadcast-toggle'),{textContent:e.spam_enabled?'DISABLE':'ENABLE'}),l(t.querySelector('.spam-timer'),{textContent:o(e.spam_countdown)}))})}catch(e){console.error('Error fetching status:',e)}}c(),r(),u(),setInterval(c,1e3),document.querySelector('.container').addEventListener('click',e=>{const t=e.target.closest('button');if(!t)return;const n=t.closest('.server-panel'),s=n?n.dataset.serverId:null,o={'bot-reboot-toggle':()=>a('/api/bot_reboot_toggle',{bot_id:t.dataset.botId,delay:document.querySelector(`.bot-reboot-delay[data-bot-id="${t.dataset.botId}"]`).value}),'btn-toggle-state':()=>a('/api/toggle_bot_state',{target:t.dataset.target}),'clan-drop-toggle-btn':()=>a('/api/clan_drop_toggle'),'clan-drop-save-btn':()=>{const e={};document.querySelectorAll('.clan-drop-threshold').forEach(t=>{e[t.dataset.node]=parseInt(t.value,10)}),a('/api/clan_drop_update',{channel_id:document.getElementById('clan-drop-channel-id').value,ktb_channel_id:document.getElementById('clan-drop-ktb-channel-id').value,heart_thresholds:e})},'watermelon-toggle':()=>a('/api/watermelon_toggle',{node:t.dataset.node}),'harvest-toggle':()=>s&&a('/api/harvest_toggle',{server_id:s,node:t.dataset.node,threshold:n.querySelector(`.harvest-threshold[data-node="${t.dataset.node}"]`).value}),'broadcast-toggle':()=>s&&a('/api/broadcast_toggle',{server_id:s,message:n.querySelector('.spam-message').value,delay:n.querySelector('.spam-delay').value}),'btn-delete-server':()=>s&&confirm('Are you sure?')&&a('/api/delete_server',{server_id:s}),'clear-logs-btn':()=>a('/api/clear_logs').then(()=>r()),'refresh-logs-btn':()=>r()};for(const e in o)if(t.classList.contains(e)||t.id===e)return void o[e]()}),document.querySelector('.main-grid').addEventListener('change',e=>{const t=e.target,n=t.closest('.server-panel');if(n&&t.classList.contains('channel-input')){const e={server_id:n.dataset.serverId};e[t.dataset.field]=t.value,a('/api/update_server_channels',e)}}),document.getElementById('add-server-btn').addEventListener('click',()=>{const e=prompt('Enter a name for the new server:','New Server');e&&a('/api/add_server',{name:e})})})</script>
</body>
</html>
"""

# --- FLASK ROUTES ---
@app.route("/")
def index():
    main_bots_info = [{"id": int(bot_id.split('_')[1]), "name": get_bot_name(bot_id)} for bot_id, _ in bot_manager.get_main_bots_info()]
    main_bots_info.sort(key=lambda x: x['id'])
    return render_template_string(HTML_TEMPLATE, servers=sorted(servers, key=lambda s: s.get('name', '')), main_bots_info=main_bots_info, auto_clan_drop=bot_states["auto_clan_drop"])

@app.route("/api/card_logs")
def api_card_logs():
    logs = card_logger.get_recent_logs(limit=50); stats = card_logger.get_stats(hours=24)
    for log in logs:
        if isinstance(log['timestamp'], datetime): log['timestamp'] = log['timestamp'].isoformat()
    return jsonify({'logs': logs, 'stats': stats})

@app.route("/api/clear_logs", methods=['POST'])
def api_clear_logs():
    card_logger.logs.clear(); card_logger.grab_attempts.clear()
    return jsonify({'status': 'success', 'message': '🗑️ Logs cleared successfully'})

@app.route("/api/clan_drop_toggle", methods=['POST'])
def api_clan_drop_toggle():
    settings = bot_states["auto_clan_drop"]; settings['enabled'] = not settings.get('enabled', False)
    if settings['enabled']:
        if not settings.get('channel_id') or not settings.get('ktb_channel_id'):
            settings['enabled'] = False; return jsonify({'status': 'error', 'message': 'Clan Drop & KTB Channel ID phải được cài đặt.'})
        threading.Thread(target=run_clan_drop_cycle).start(); msg = "✅ Clan Auto Drop ENABLED & First cycle triggered."
    else: msg = "🛑 Clan Auto Drop DISABLED."
    return jsonify({'status': 'success', 'message': msg})

@app.route("/api/clan_drop_update", methods=['POST'])
def api_clan_drop_update():
    data = request.get_json(); thresholds = bot_states["auto_clan_drop"].setdefault('heart_thresholds', {})
    for key, value in data.get('heart_thresholds', {}).items():
        if isinstance(value, int): thresholds[key] = value
    bot_states["auto_clan_drop"].update({'channel_id': data.get('channel_id', '').strip(), 'ktb_channel_id': data.get('ktb_channel_id', '').strip()})
    return jsonify({'status': 'success', 'message': '💾 Clan Drop settings updated.'})

@app.route("/api/add_server", methods=['POST'])
def api_add_server():
    name = request.json.get('name')
    if not name: return jsonify({'status': 'error', 'message': 'Tên server là bắt buộc.'}), 400
    new_server = {"id": f"server_{uuid.uuid4().hex}", "name": name, "spam_delay": 10}
    main_bots_count = len([t for t in main_tokens if t.strip()])
    for i in range(main_bots_count): new_server[f'auto_grab_enabled_{i+1}'], new_server[f'heart_threshold_{i+1}'] = False, 50
    servers.append(new_server)
    return jsonify({'status': 'success', 'message': f'✅ Server "{name}" đã được thêm.', 'reload': True})

@app.route("/api/delete_server", methods=['POST'])
def api_delete_server():
    server_id = request.json.get('server_id'); servers[:] = [s for s in servers if s.get('id') != server_id]
    return jsonify({'status': 'success', 'message': f'🗑️ Server đã được xóa.', 'reload': True})

def find_server(server_id): return next((s for s in servers if s.get('id') == server_id), None)

@app.route("/api/update_server_channels", methods=['POST'])
def api_update_server_channels():
    data = request.json; server = find_server(data.get('server_id'))
    if not server: return jsonify({'status': 'error', 'message': 'Không tìm thấy server.'}), 404
    for field in ['main_channel_id', 'ktb_channel_id', 'spam_channel_id']:
        if field in data: server[field] = data[field]
    return jsonify({'status': 'success', 'message': f'🔧 Kênh đã được cập nhật cho {server["name"]}.'})

@app.route("/api/harvest_toggle", methods=['POST'])
def api_harvest_toggle():
    data = request.json; server, node_str = find_server(data.get('server_id')), data.get('node')
    if not server or not node_str: return jsonify({'status': 'error', 'message': 'Yêu cầu không hợp lệ.'}), 400
    node = str(node_str); grab_key, threshold_key = f'auto_grab_enabled_{node}', f'heart_threshold_{node}'
    server[grab_key] = not server.get(grab_key, False); server[threshold_key] = int(data.get('threshold', 50))
    status_msg = 'ENABLED' if server[grab_key] else 'DISABLED'; bot_id = f'main_{node}'
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
    data = request.json; server = find_server(data.get('server_id'))
    if not server: return jsonify({'status': 'error', 'message': 'Không tìm thấy server.'}), 404
    server['spam_enabled'] = not server.get('spam_enabled', False)
    server['spam_message'], server['spam_delay'] = data.get("message", "").strip(), int(data.get("delay", 10))
    if server['spam_enabled'] and (not server['spam_message'] or not server['spam_channel_id']):
        server['spam_enabled'] = False; return jsonify({'status': 'error', 'message': f'❌ Cần có message/channel spam cho {server["name"]}.'})
    status_msg = 'ENABLED' if server['spam_enabled'] else 'DISABLED'
    return jsonify({'status': 'success', 'message': f"📢 Auto Broadcast đã {status_msg} cho {server['name']}."})

@app.route("/api/bot_reboot_toggle", methods=['POST'])
def api_bot_reboot_toggle():
    data = request.json; bot_id, delay = data.get('bot_id'), int(data.get("delay", 3600))
    if not re.match(r"main_\d+", bot_id): return jsonify({'status': 'error', 'message': '❌ Invalid Bot ID Format.'}), 400
    settings = bot_states["reboot_settings"].get(bot_id)
    if not settings: return jsonify({'status': 'error', 'message': '❌ Invalid Bot ID.'}), 400
    settings.update({'enabled': not settings.get('enabled', False), 'delay': delay, 'failure_count': 0})
    if settings['enabled']: settings['next_reboot_time'] = time.time() + delay; msg = f"🔄 Safe Auto-Reboot ENABLED cho {get_bot_name(bot_id)} (mỗi {delay}s)"
    else: msg = f"🛑 Auto-Reboot DISABLED cho {get_bot_name(bot_id)}"
    return jsonify({'status': 'success', 'message': msg})

@app.route("/api/toggle_bot_state", methods=['POST'])
def api_toggle_bot_state():
    target = request.json.get('target')
    if target in bot_states["active"]:
        bot_states["active"][target] = not bot_states["active"][target]
        state_text = "🟢 ONLINE" if bot_states["active"][target] else "🔴 OFFLINE"
        return jsonify({'status': 'success', 'message': f"Bot {get_bot_name(target)} đã được set thành {state_text}"})
    return jsonify({'status': 'error', 'message': 'Không tìm thấy target.'}), 404

@app.route("/api/save_settings", methods=['POST'])
def api_save_settings():
    save_settings(); return jsonify({'status': 'success', 'message': '💾 Settings saved.'})

@app.route("/status")
def status_endpoint():
    now = time.time()
    def get_bot_status_list(bot_info_list, type_prefix):
        status_list = []
        for bot_id, bot_instance in bot_info_list:
            failures = bot_states["health_stats"].get(bot_id, {}).get('consecutive_failures', 0)
            health_status = 'bad' if failures >= 3 else 'warning' if failures > 0 else 'good'
            status_list.append({"name": get_bot_name(bot_id), "status": bot_instance is not None, "reboot_id": bot_id, "is_active": bot_states["active"].get(bot_id, False), "type": type_prefix, "health_status": health_status, "is_rebooting": bot_manager.is_rebooting(bot_id)})
        return sorted(status_list, key=lambda x: int(x['reboot_id'].split('_')[1]))
    bot_statuses = {"main_bots": get_bot_status_list(bot_manager.get_main_bots_info(), "main"), "sub_accounts": get_bot_status_list(bot_manager.get_sub_bots_info(), "sub")}
    clan_settings = bot_states["auto_clan_drop"]
    clan_drop_status = {"enabled": clan_settings.get("enabled", False), "countdown": (clan_settings.get("last_cycle_start_time", 0) + clan_settings.get("cycle_interval", 1800) - now) if clan_settings.get("enabled") else 0}
    reboot_settings_copy = bot_states["reboot_settings"].copy()
    for bot_id, settings in reboot_settings_copy.items(): settings['countdown'] = max(0, settings.get('next_reboot_time', 0) - now) if settings.get('enabled') else 0
    return jsonify({'bot_reboot_settings': reboot_settings_copy, 'bot_statuses': bot_statuses, 'server_start_time': server_start_time, 'servers': servers, 'watermelon_grab_states': bot_states["watermelon_grab"], 'auto_clan_drop_status': clan_drop_status})

# --- MAIN EXECUTION ---
if __name__ == "__main__":
    print("🚀 Shadow Network Control - V4.1 Fixed Version Starting...", flush=True)
    load_settings()
    print("🔌 Initializing bots using Bot Manager...", flush=True)
    for i, token in enumerate(t for t in main_tokens if t.strip()):
        bot_num = i + 1; bot_id = f"main_{bot_num}"; bot = create_bot(token.strip(), bot_identifier=bot_num, is_main=True)
        if bot: bot_manager.add_bot(bot_id, bot)
        bot_states["active"].setdefault(bot_id, True); bot_states["watermelon_grab"].setdefault(bot_id, False)
        bot_states["auto_clan_drop"]["heart_thresholds"].setdefault(bot_id, 50)
        bot_states["reboot_settings"].setdefault(bot_id, {'enabled': False, 'delay': 3600, 'next_reboot_time': 0, 'failure_count': 0})
        bot_states["health_stats"].setdefault(bot_id, {'consecutive_failures': 0})
    for i, token in enumerate(t for t in tokens if t.strip()):
        bot_id = f"sub_{i}"; bot = create_bot(token.strip(), bot_identifier=i, is_main=False)
        if bot: bot_manager.add_bot(bot_id, bot)
        bot_states["active"].setdefault(bot_id, True); bot_states["health_stats"].setdefault(bot_id, {'consecutive_failures': 0})
    print("🔧 Starting background threads...", flush=True)
    threading.Thread(target=periodic_task, args=(1800, save_settings, "Save"), daemon=True).start()
    threading.Thread(target=periodic_task, args=(300, health_monitoring_check, "Health"), daemon=True).start()
    threading.Thread(target=spam_loop_manager, daemon=True).start()
    threading.Thread(target=auto_reboot_loop, daemon=True).start()
    threading.Thread(target=auto_clan_drop_loop, daemon=True).start()
    port = int(os.environ.get("PORT", 10000))
    print(f"🌐 Web Server running at http://0.0.0.0:{port}", flush=True)
    print("📊 Real-time Card Grab Logging System Activated!", flush=True)
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
