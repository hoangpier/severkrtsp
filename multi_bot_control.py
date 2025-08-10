# PHIÊN BẢN CUỐI CÙNG - SỬA LỖI LOG & CẬP NHẬT GIAO DIỆN
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

# --- QUẢN LÝ BOT THREAD-SAFE ---
class ThreadSafeBotManager:
    def __init__(self):
        self._bots = {}
        self._rebooting = set()
        self._lock = threading.RLock()
        self._grab_logs = []
        self._max_logs = 50

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
            if self.is_rebooting(bot_id):
                return False
            self._rebooting.add(bot_id)
            return True

    def end_reboot(self, bot_id):
        with self._lock:
            self._rebooting.discard(bot_id)

    def add_grab_success_log(self, bot_name, card_name, hearts, timestamp=None):
        with self._lock:
            if timestamp is None:
                timestamp = time.time()
            log_entry = {
                'timestamp': timestamp,
                'bot_name': bot_name,
                'card_name': card_name,
                'hearts': hearts,
                'formatted_time': datetime.fromtimestamp(timestamp).strftime('%H:%M:%S')
            }
            self._grab_logs.insert(0, log_entry)
            if len(self._grab_logs) > self._max_logs:
                self._grab_logs = self._grab_logs[:self._max_logs]
            print(f"[GRAB SUCCESS] 🎯 {bot_name} đã nhặt {card_name} với {hearts}♡", flush=True)

    def get_grab_logs(self):
        with self._lock:
            return self._grab_logs.copy()

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
        with open('backup_settings.json', 'w') as f:
            json.dump(settings_data, f, indent=2)
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
                if key in bot_states and isinstance(value, dict):
                    bot_states[key].update(value)
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

# --- HÀM TRỢ GIÚP ---
def get_bot_name(bot_id_str):
    try:
        parts = bot_id_str.split('_')
        b_type, b_index = parts[0], int(parts[1])
        if b_type == 'main':
            return BOT_NAMES[b_index - 1] if 0 < b_index <= len(BOT_NAMES) else f"MAIN_{b_index}"
        return acc_names[b_index - 1] if 0 < b_index <= len(acc_names) else f"SUB_{b_index}"
    except (IndexError, ValueError):
        return bot_id_str.upper()

def safe_message_handler_wrapper(handler_func, bot, msg, *args):
    try:
        return handler_func(bot, msg, *args)
    except Exception as e:
        print(f"[Message Handler] ❌ Error in {handler_func.__name__}: {e}", flush=True)
        print(f"[Message Handler] 🐛 Traceback: {traceback.format_exc()}", flush=True)
        return None

# ======================================================================
# >>>>> HÀM ĐÃ SỬA: LOGIC KIỂM TRA NHẶT THẺ CHÍNH XÁC HƠN <<<<<
# ======================================================================
def check_grab_result(bot, channel_id, drop_msg_id, bot_name, selected_card):
    """Kiểm tra kết quả nhặt thẻ và log nếu thành công (ĐÃ SỬA LỖI)"""
    try:
        time.sleep(2)
        messages = bot.getMessages(channel_id, num=10).json()
        
        if not isinstance(messages, list):
            return False
            
        for msg in messages:
            if msg.get("author", {}).get("id") != karuta_id:
                continue
            
            content = msg.get("content", "").lower()
            
            # --- ĐIỀU KIỆN SỬA ĐỔI ---
            # Phải có từ khóa thành công VÀ tên của bot phải được đề cập
            success_keywords = ["fought off", "took the"]
            if any(keyword in content for keyword in success_keywords) and bot_name.lower() in content:
                
                grabbed_card_name = selected_card['name']
                card_match = re.search(r"took the (.+?) card", content)
                if card_match:
                    grabbed_card_name = card_match.group(1).strip()

                bot_manager.add_grab_success_log(
                    bot_name=bot_name,
                    card_name=grabbed_card_name,
                    hearts=selected_card['hearts']
                )
                return True # Ghi nhận thành công và thoát
                
        return False
        
    except Exception as e:
        print(f"[GRAB CHECK | {bot_name}] ❌ Lỗi kiểm tra kết quả: {e}", flush=True)
        return False

# --- LOGIC GRAB CARD ---
def _find_and_select_card(bot, channel_id, last_drop_msg_id, heart_threshold, bot_num, ktb_channel_id):
    bot_name = get_bot_name(f'main_{bot_num}')
    for attempt in range(7):
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
                    card_info, heart_numbers = [], []
                    for i, line in enumerate(lines):
                        heart_match = re.search(r'♡(\d+)', line)
                        if heart_match:
                            hearts = int(heart_match.group(1))
                            heart_numbers.append(hearts)
                            card_name_part = re.sub(r'^[123]️⃣\s*', '', line.split('♡')[0].strip())
                            card_info.append({'name': card_name_part, 'hearts': hearts, 'position': i + 1})
                        else:
                            heart_numbers.append(0)
                            card_info.append({'name': 'Unknown', 'hearts': 0, 'position': i + 1})
                    if not any(heart_numbers): break
                    max_hearts = max(heart_numbers)
                    if max_hearts >= heart_threshold:
                        max_index = heart_numbers.index(max_hearts)
                        selected_card = card_info[max_index]
                        delays = {1: [0.4, 1.4, 2.1], 2: [0.7, 1.8, 2.4], 3: [0.7, 1.8, 2.4], 4: [0.8, 1.9, 2.5]}
                        emoji = ["1️⃣", "2️⃣", "3️⃣"][max_index]
                        delay = delays.get(bot_num, [0.9, 2.0, 2.6])[max_index]
                        print(f"[CARD GRAB | {bot_name}] 🎯 Chọn {selected_card['name']} ({selected_card['hearts']}♡) -> {emoji} sau {delay}s", flush=True)
                        def grab_action():
                            try:
                                bot.addReaction(channel_id, last_drop_msg_id, emoji)
                                time.sleep(1.2)
                                if ktb_channel_id: bot.sendMessage(ktb_channel_id, "kt b")
                                time.sleep(3)
                                check_grab_result(bot, channel_id, last_drop_msg_id, bot_name, selected_card)
                            except Exception as e:
                                print(f"[CARD GRAB | {bot_name}] ❌ Lỗi grab: {e}", flush=True)
                        threading.Timer(delay, grab_action).start()
                        return True
            return False
        except Exception as e:
            print(f"[CARD GRAB | {bot_name}] ❌ Lỗi đọc messages (attempt {attempt+1}): {e}", flush=True)
    return False

# --- LOGIC BOT ---
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
                print(f"[WATERMELON | Bot {bot_num}] 🍉 Bắt đầu canh dưa (chờ 5 giây)...", flush=True)
                time.sleep(5) 
                try:
                    target_message = bot.getMessage(channel_id, last_drop_msg_id).json()[0]
                    reactions = target_message.get('reactions', [])
                    for reaction in reactions:
                        emoji_name = reaction.get('emoji', {}).get('name', '')
                        if '🍉' in emoji_name or 'watermelon' in emoji_name.lower() or 'dua' in emoji_name.lower():
                            print(f"[WATERMELON | Bot {bot_num}] 🎯 PHÁT HIỆN DƯA HẤU!", flush=True)
                            try:
                                bot.addReaction(channel_id, last_drop_msg_id, "🍉")
                                print(f"[WATERMELON | Bot {bot_num}] ✅ NHẶT DƯA THÀNH CÔNG!", flush=True)
                            except Exception as e:
                                print(f"[WATERMELON | Bot {bot_num}] ❌ Lỗi react khi đã thấy dưa: {e}", flush=True)
                            return
                    print(f"[WATERMELON | Bot {bot_num}] 😞 Không tìm thấy dưa hấu sau khi chờ.", flush=True)
                except Exception as e:
                    print(f"[WATERMELON | Bot {bot_num}] ❌ Lỗi khi lấy tin nhắn để check dưa: {e}", flush=True)
            threading.Thread(target=check_for_watermelon_patiently, daemon=True).start()
    threading.Thread(target=grab_logic_thread, daemon=True).start()

# --- HỆ THỐNG REBOOT & HEALTH CHECK ---
def check_bot_health(bot_instance, bot_id):
    try:
        stats = bot_states["health_stats"].setdefault(bot_id, {'consecutive_failures': 0, 'last_check': 0})
        stats['last_check'] = time.time()
        if not bot_instance or not hasattr(bot_instance, 'gateway'):
            stats['consecutive_failures'] += 1
            return False
        is_connected = hasattr(bot_instance.gateway, 'connected') and bot_instance.gateway.connected
        if is_connected:
            stats['consecutive_failures'] = 0
        else:
            stats['consecutive_failures'] += 1
            print(f"[Health Check] ⚠️ Bot {bot_id} not connected - failures: {stats['consecutive_failures']}", flush=True)
        return is_connected
    except Exception as e:
        print(f"[Health Check] ❌ Exception in health check for {bot_id}: {e}", flush=True)
        bot_states["health_stats"].setdefault(bot_id, {})['consecutive_failures'] = bot_states["health_stats"][bot_id].get('consecutive_failures', 0) + 1
        return False

def handle_reboot_failure(bot_id):
    settings = bot_states["reboot_settings"].setdefault(bot_id, {'delay': 3600, 'enabled': True})
    failure_count = settings.get('failure_count', 0) + 1
    settings['failure_count'] = failure_count
    backoff_multiplier = min(2 ** failure_count, 8)
    base_delay = settings.get('delay', 3600)
    next_try_delay = max(600, base_delay / backoff_multiplier) * backoff_multiplier
    settings['next_reboot_time'] = time.time() + next_try_delay
    print(f"[Safe Reboot] 🔴 Failure #{failure_count} for {bot_id}. Thử lại sau {next_try_delay/60:.1f} phút.", flush=True)
    if failure_count >= 5:
        settings['enabled'] = False
        print(f"[Safe Reboot] ❌ Tắt auto-reboot cho {bot_id} sau 5 lần thất bại.", flush=True)

def safe_reboot_bot(bot_id):
    if not bot_manager.start_reboot(bot_id):
        print(f"[Safe Reboot] ⚠️ Bot {bot_id} đã đang trong quá trình reboot. Bỏ qua.", flush=True)
        return False
    print(f"[Safe Reboot] 🔄 Bắt đầu reboot bot {bot_id}...", flush=True)
    try:
        match = re.match(r"main_(\d+)", bot_id)
        if not match: raise ValueError("Định dạng bot_id không hợp lệ cho reboot.")
        bot_index = int(match.group(1)) - 1
        if not (0 <= bot_index < len(main_tokens)): raise IndexError("Bot index ngoài phạm vi danh sách token.")
        token = main_tokens[bot_index].strip()
        bot_name = get_bot_name(bot_id)
        print(f"[Safe Reboot] 🧹 Cleaning up old bot instance for {bot_name}", flush=True)
        bot_manager.remove_bot(bot_id)
        settings = bot_states["reboot_settings"].get(bot_id, {})
        failure_count = settings.get('failure_count', 0)
        wait_time = random.uniform(20, 40) + min(failure_count * 30, 300)
        print(f"[Safe Reboot] ⏳ Chờ {wait_time:.1f}s để cleanup và tránh rate limit...", flush=True)
        time.sleep(wait_time)
        print(f"[Safe Reboot] 🏗️ Creating new bot instance for {bot_name}", flush=True)
        new_bot = create_bot(token, bot_identifier=(bot_index + 1), is_main=True)
        if not new_bot: raise Exception("Không thể tạo instance bot mới hoặc kết nối gateway thất bại.")
        bot_manager.add_bot(bot_id, new_bot)
        settings.update({'next_reboot_time': time.time() + settings.get('delay', 3600), 'failure_count': 0, 'last_reboot_time': time.time()})
        bot_states["health_stats"][bot_id]['consecutive_failures'] = 0
        print(f"[Safe Reboot] ✅ Reboot thành công {bot_name}", flush=True)
        return True
    except Exception as e:
        print(f"[Safe Reboot] ❌ Reboot thất bại cho {bot_id}: {e}", flush=True)
        traceback.print_exc()
        handle_reboot_failure(bot_id)
        return False
    finally:
        bot_manager.end_reboot(bot_id)

# --- VÒNG LẶP NỀN ---
def auto_reboot_loop():
    print("[Safe Reboot] 🚀 Khởi động luồng tự động reboot.", flush=True)
    last_global_reboot_time = 0
    consecutive_system_failures = 0
    while not stop_events["reboot"].is_set():
        try:
            now = time.time()
            min_global_interval = 600
            if now - last_global_reboot_time < min_global_interval:
                stop_events["reboot"].wait(60)
                continue
            bot_to_reboot, highest_priority_score = None, -1
            reboot_settings_copy = dict(bot_states["reboot_settings"].items())
            for bot_id, settings in reboot_settings_copy.items():
                if not settings.get('enabled', False) or bot_manager.is_rebooting(bot_id): continue
                next_reboot_time = settings.get('next_reboot_time', 0)
                if now < next_reboot_time: continue
                health_stats = bot_states["health_stats"].get(bot_id, {})
                failure_count = health_stats.get('consecutive_failures', 0)
                priority_score = (failure_count * 1000) + (now - next_reboot_time)
                if priority_score > highest_priority_score:
                    highest_priority_score, bot_to_reboot = priority_score, bot_id
            if bot_to_reboot:
                print(f"[Safe Reboot] 🎯 Chọn reboot bot: {bot_to_reboot} (priority: {highest_priority_score:.1f})", flush=True)
                if safe_reboot_bot(bot_to_reboot):
                    last_global_reboot_time = now
                    consecutive_system_failures = 0
                    wait_time = random.uniform(300, 600)
                    print(f"[Safe Reboot] ⏳ Chờ {wait_time:.0f}s trước khi tìm bot reboot tiếp theo.", flush=True)
                    stop_events["reboot"].wait(wait_time)
                else:
                    consecutive_system_failures += 1
                    backoff_time = min(120 * (2 ** consecutive_system_failures), 1800)
                    print(f"[Safe Reboot] ❌ Reboot thất bại. Hệ thống backoff: {backoff_time}s", flush=True)
                    stop_events["reboot"].wait(backoff_time)
            else:
                stop_events["reboot"].wait(60)
        except Exception as e:
            print(f"[Safe Reboot] ❌ Lỗi nghiêm trọng trong reboot loop: {e}", flush=True)
            traceback.print_exc()
            stop_events["reboot"].wait(120)

def run_clan_drop_cycle():
    print("[Clan Drop] 🚀 Bắt đầu chu kỳ drop clan.", flush=True)
    settings = bot_states["auto_clan_drop"]
    active_main_bots = [(bot, int(bot_id.split('_')[1])) for bot_id, bot in bot_manager.get_main_bots_info() if bot and bot_states["active"].get(bot_id, False)]
    if not active_main_bots:
        print("[Clan Drop] ⚠️ Không có bot chính nào hoạt động.", flush=True)
        return
    for bot, bot_num in active_main_bots:
        if stop_events["clan_drop"].is_set(): break
        try:
            print(f"[Clan Drop] 📤 Bot {get_bot_name(f'main_{bot_num}')} đang gửi 'kd'...", flush=True)
            bot.sendMessage(settings.get("channel_id"), "kd")
            time.sleep(random.uniform(settings["bot_delay"] * 0.8, settings["bot_delay"] * 1.2))
        except Exception as e:
            print(f"[Clan Drop] ❌ Lỗi khi gửi 'kd' từ bot {bot_num}: {e}", flush=True)
    settings["last_cycle_start_time"] = time.time()
    save_settings()

def auto_clan_drop_loop():
    while not stop_events["clan_drop"].is_set():
        settings = bot_states["auto_clan_drop"]
        if (settings.get("enabled") and settings.get("channel_id") and (time.time() - settings.get("last_cycle_start_time", 0)) >= settings.get("cycle_interval", 1800)):
            run_clan_drop_cycle()
        stop_events["clan_drop"].wait(60)

def spam_for_server(server_config, stop_event):
    server_name = server_config.get('name')
    channel_id = server_config.get('spam_channel_id')
    message = server_config.get('spam_message')
    while not stop_event.is_set():
        try:
            bots_to_spam = [bot for bot_id, bot in bot_manager.get_all_bots() if bot and bot_states["active"].get(bot_id)]
            delay = server_config.get('spam_delay', 10)
            for bot in bots_to_spam:
                if stop_event.is_set(): break
                try:
                    bot.sendMessage(channel_id, message)
                    time.sleep(random.uniform(1.5, 2.5))
                except Exception as e:
                    print(f"[Spam] ❌ Lỗi gửi spam từ bot tới server {server_name}: {e}", flush=True)
            stop_event.wait(random.uniform(delay * 0.9, delay * 1.1))
        except Exception as e:
            print(f"[Spam] ❌ ERROR in spam_for_server {server_name}: {e}", flush=True)
            stop_event.wait(10)

def spam_loop_manager():
    active_threads = {}
    while True:
        try:
            current_ids = {s['id'] for s in servers}
            for server_id in list(active_threads.keys()):
                if server_id not in current_ids:
                    print(f"[Spam] 🛑 Dừng luồng cho server đã xóa: {server_id}", flush=True)
                    active_threads.pop(server_id)[1].set()
            for server in servers:
                server_id = server.get('id')
                spam_on = server.get('spam_enabled') and server.get('spam_message') and server.get('spam_channel_id')
                if spam_on and server_id not in active_threads:
                    print(f"[Spam] 🚀 Bắt đầu luồng cho server: {server.get('name')}", flush=True)
                    stop_event = threading.Event()
                    thread = threading.Thread(target=spam_for_server, args=(server, stop_event), daemon=True)
                    thread.start()
                    active_threads[server_id] = (thread, stop_event)
                elif not spam_on and server_id in active_threads:
                    print(f"[Spam] 🛑 Dừng luồng cho server: {server.get('name')}", flush=True)
                    active_threads.pop(server_id)[1].set()
            time.sleep(5)
        except Exception as e:
            print(f"[Spam] ❌ ERROR in spam_loop_manager: {e}", flush=True)
            time.sleep(5)

def periodic_task(interval, task_func, task_name):
    print(f"[{task_name}] 🚀 Khởi động luồng định kỳ.", flush=True)
    while True:
        time.sleep(interval)
        try:
            task_func()
        except Exception as e:
            print(f"[{task_name}] ❌ Lỗi: {e}", flush=True)

def health_monitoring_check():
    all_bots = bot_manager.get_all_bots()
    for bot_id, bot in all_bots:
        check_bot_health(bot, bot_id)

# --- KHỞI TẠO BOT ---
def create_bot(token, bot_identifier, is_main=False):
    try:
        bot = discum.Client(token=token, log=False)
        bot_id_str = f"main_{bot_identifier}" if is_main else f"sub_{bot_identifier}"
        @bot.gateway.command
        def on_ready(resp):
            try:
                if resp.event.ready:
                    user = resp.raw.get("user", {})
                    print(f"[Bot] ✅ Đăng nhập: {user.get('id', 'Unknown')} ({get_bot_name(bot_id_str)}) - {user.get('username', 'Unknown')}", flush=True)
                    bot_states["health_stats"].setdefault(bot_id_str, {})
                    bot_states["health_stats"][bot_id_str].update({'created_time': time.time(), 'consecutive_failures': 0})
            except Exception as e:
                print(f"[Bot] ❌ Error in on_ready for {bot_id_str}: {e}", flush=True)
        if is_main:
            @bot.gateway.command
            def on_message(resp):
                try:
                    if resp.event.message:
                        msg = resp.parsed.auto()
                        if msg.get("author", {}).get("id") == karuta_id and "dropping" in msg.get("content", "").lower():
                            handler = handle_clan_drop if msg.get("mentions") else handle_grab
                            safe_message_handler_wrapper(handler, bot, msg, bot_identifier)
                except Exception as e:
                    print(f"[Bot] ❌ Error in on_message for {bot_id_str}: {e}", flush=True)
        def start_gateway():
            try:
                bot.gateway.run(auto_reconnect=True)
            except Exception as e:
                print(f"[Bot] ❌ Gateway error for {bot_id_str}: {e}", flush=True)
        threading.Thread(target=start_gateway, daemon=True).start()
        start_time = time.time()
        while time.time() - start_time < 20:
            if hasattr(bot.gateway, 'connected') and bot.gateway.connected:
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

# --- FLASK APP & GIAO DIỆN ---
app = Flask(__name__)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Shadow Network Control</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700;900&family=Courier+Prime:wght@400;700&family=Nosifer&display=swap" rel="stylesheet">
    <style>
        :root { --primary-bg: #0a0a0a; --secondary-bg: #1a1a1a; --panel-bg: #111111; --border-color: #333333; --blood-red: #8b0000; --dark-red: #550000; --bone-white: #f8f8ff; --necro-green: #228b22; --text-primary: #f0f0f0; --text-secondary: #cccccc; --warning-orange: #ff8c00; --success-green: #32cd32; }
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
        .bot-status-item { display: flex; align-items: center; padding: 5px 8px; background: rgba(0,0,0,0.3); border-radius: 4px; margin-bottom: 5px; }
        .btn-toggle-state { padding: 3px 8px; font-size: 0.9em; border-radius: 4px; cursor: pointer; text-transform: uppercase; background: transparent; font-weight: 700; border: none; }
        .btn-rise { color: var(--success-green); }
        .btn-rest { color: var(--dark-red); }
        .btn-warning { color: var(--warning-orange); }
        .add-server-btn { display: flex; align-items: center; justify-content: center; min-height: 200px; border: 2px dashed var(--border-color); cursor: pointer; transition: all 0.3s ease; }
        .add-server-btn:hover { background: var(--secondary-bg); border-color: var(--blood-red); }
        .btn-delete-server { position: absolute; top: 15px; right: 15px; background: var(--dark-red); border: 1px solid var(--blood-red); color: var(--bone-white); width: auto; padding: 5px 10px; border-radius: 50%; }
        .server-sub-panel { border-top: 1px solid var(--border-color); margin-top: 20px; padding-top: 20px;}
        .health-indicator { display: inline-block; width: 10px; height: 10px; border-radius: 50%; }
        .health-good { background-color: var(--success-green); }
        .health-warning { background-color: var(--warning-orange); }
        .health-bad { background-color: var(--blood-red); }
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
            <h1 class="title">SHADOW NETWORK CONTROL</h1>
            <div class="subtitle">Enhanced Safe Reboot System + Grab Success Logging</div>
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
                    <div id="uptime-timer">--:--:--</div>
                </div>
                <div class="server-sub-panel">
                    <h3><i class="fas fa-robot"></i> Bot Control</h3>
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
                        <span id="clan-drop-timer">--:--:--</span>
                        <button type="button" id="clan-drop-toggle-btn" class="btn" style="width:auto;padding:5px 10px;font-size:0.9em;"></button>
                    </div>
                </div>
                <div class="server-sub-panel">
                    <h3><i class="fas fa-cogs"></i> Configuration</h3>
                    <div class="input-group"><label>Drop Channel ID</label><input type="text" id="clan-drop-channel-id"></div>
                    <div class="input-group"><label>KTB Channel ID</label><input type="text" id="clan-drop-ktb-channel-id"></div>
                </div>
                <div class="server-sub-panel">
                    <h3><i class="fas fa-crosshairs"></i> Soul Harvest (Clan Drop)</h3>
                    <div id="clan-drop-thresholds-container"></div>
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
            <div id="servers-container" class="main-grid" style="grid-column: 1 / -1;"></div>
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
        el.className = `msg-status ${type}`;
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
                if (result.reload) setTimeout(() => window.location.reload(), 500);
            }
            setTimeout(fetchStatus, 500);
        } catch (error) {
            showStatusMessage('Server communication error.', 'error');
        }
    }

    function formatTime(seconds) {
        if (isNaN(seconds) || seconds < 0) return "--:--:--";
        const h = Math.floor(seconds / 3600).toString().padStart(2, '0');
        const m = Math.floor((seconds % 3600) / 60).toString().padStart(2, '0');
        const s = Math.floor(seconds % 60).toString().padStart(2, '0');
        return `${h}:${m}:${s}`;
    }

    function updateElement(el, text, value) {
        if (!el) return;
        if (text !== undefined) el.textContent = text;
        if (value !== undefined) el.value = value;
    }
    
    // ======================================================================
    // >>>>> HÀM ĐÃ SỬA: TẠO GIAO DIỆN BOT CONTROL ĐƠN GIẢN HƠN <<<<<
    // ======================================================================
    function updateBotControlGrid(botStatuses) {
        const grid = $('#bot-control-grid');
        if (!grid || !botStatuses) return;

        grid.style.gridTemplateColumns = '1fr'; // Ensure single column layout
        const allBots = [...botStatuses.main_bots, ...botStatuses.sub_accounts];
        
        let gridHtml = '';
        allBots.forEach(bot => {
            const healthClass = bot.consecutive_failures === 0 ? 'health-good' : bot.consecutive_failures < 3 ? 'health-warning' : 'health-bad';
            const activeText = bot.is_active ? 'RISE' : 'REST';
            const activeClass = bot.is_active ? 'btn-rise' : 'btn-rest';
            const rebootEnabled = bot.reboot_enabled ? 'ON' : 'OFF';
            const rebootClass = bot.reboot_enabled ? 'btn-rise' : 'btn-rest';
            
            gridHtml += `
                <div class="bot-status-item" style="padding: 8px 12px; justify-content: flex-start; gap: 12px;">
                    <span class="health-indicator ${healthClass}" title="Failures: ${bot.consecutive_failures}"></span>
                    <strong style="min-width: 80px; color: #fff;">${bot.name}</strong>
                    <button class="btn-toggle-state ${activeClass}" data-bot-id="${bot.reboot_id}" data-action="toggle_active">${activeText}</button>
                    <button class="btn-toggle-state ${rebootClass}" data-bot-id="${bot.reboot_id}" data-action="toggle_reboot">RBT: ${rebootEnabled}</button>
                    <button class="btn-toggle-state btn-warning" data-bot-id="${bot.reboot_id}" data-action="force_reboot">FORCE</button>
                    <span style="font-size: 0.85em; color: #aaa; margin-left: auto;">Next Reboot: ${bot.next_reboot}</span>
                </div>
            `;
        });
        grid.innerHTML = gridHtml;
    }

    function renderGrabLogs(logs) {
        $('#grab-logs-container').innerHTML = (!logs || logs.length === 0)
            ? '<div style="text-align:center;color:#ccc;">Chưa có log nhặt thẻ thành công...</div>'
            : logs.map(log => `
                <div class="grab-log-item">
                    <span class="grab-log-time">${log.formatted_time}</span>
                    <span class="grab-log-bot">${log.bot_name}</span>
                    <span class="grab-log-card">${log.card_name}</span>
                    <span class="grab-log-hearts">${log.hearts}♡</span>
                </div>`).join('');
    }

    function renderServer(server, botStatuses) {
        const grabSettingsHtml = botStatuses.main_bots.map(bot => {
            const botNum = bot.reboot_id.split('_')[1];
            const threshold = server[`heart_threshold_${botNum}`] || 50;
            const enabled = server[`auto_grab_enabled_${botNum}`] || false;
            return `
                <div class="grab-section">
                    <h3>${bot.name}</h3>
                    <div class="input-group">
                        <input type="number" class="harvest-threshold" data-node="${botNum}" value="${threshold}" min="0">
                        <button type="button" class="btn harvest-toggle" data-node="${botNum}">${enabled ? 'DISABLE' : 'ENABLE'}</button>
                    </div>
                </div>`;
        }).join('');

        return `
            <div class="panel server-panel" data-server-id="${server.id}">
                <button class="btn-delete-server" title="Delete Server"><i class="fas fa-times"></i></button>
                <h2><i class="fas fa-server"></i> ${server.name}</h2>
                <div class="server-sub-panel">
                    <h3><i class="fas fa-cogs"></i> Channel Config</h3>
                    <div class="input-group"><label>Main Channel</label><input type="text" class="server-input" data-field="main_channel_id" value="${server.main_channel_id || ''}"></div>
                    <div class="input-group"><label>KTB Channel</label><input type="text" class="server-input" data-field="ktb_channel_id" value="${server.ktb_channel_id || ''}"></div>
                    <div class="input-group"><label>Spam Channel</label><input type="text" class="server-input" data-field="spam_channel_id" value="${server.spam_channel_id || ''}"></div>
                </div>
                <div class="server-sub-panel"><h3><i class="fas fa-crosshairs"></i> Soul Harvest</h3>${grabSettingsHtml}</div>
                <div class="server-sub-panel">
                    <h3><i class="fas fa-paper-plane"></i> Auto Broadcast</h3>
                    <div class="input-group"><label>Message</label><textarea class="server-input" data-field="spam_message" rows="2">${server.spam_message || ''}</textarea></div>
                    <div class="input-group"><label>Delay (s)</label><input type="number" class="server-input" data-field="spam_delay" value="${server.spam_delay || 10}"></div>
                    <button type="button" class="btn broadcast-toggle">${server.spam_enabled ? 'DISABLE' : 'ENABLE'}</button>
                </div>
            </div>`;
    }

    async function fetchStatus() {
        try {
            const data = await fetch('/status').then(res => res.json());
            updateElement($('#uptime-timer'), formatTime((Date.now() / 1000) - data.server_start_time));
            renderGrabLogs(data.grab_success_logs);
            updateBotControlGrid(data.bot_statuses);

            const clanDropStatus = data.auto_clan_drop_status;
            if (clanDropStatus) {
                updateElement($('#clan-drop-timer'), formatTime(clanDropStatus.countdown));
                updateElement($('#clan-drop-toggle-btn'), clanDropStatus.enabled ? 'DISABLE' : 'ENABLE');
                updateElement($('#clan-drop-channel-id'), undefined, clanDropStatus.channel_id || '');
                updateElement($('#clan-drop-ktb-channel-id'), undefined, clanDropStatus.ktb_channel_id || '');
                $('#clan-drop-thresholds-container').innerHTML = data.bot_statuses.main_bots.map(bot => {
                    const threshold = clanDropStatus.heart_thresholds?.[bot.reboot_id] || 50;
                    return `<div class="grab-section"><h3>${bot.name}</h3><div class="input-group"><input type="number" class="clan-drop-threshold" data-node="${bot.reboot_id}" value="${threshold}" min="0"></div></div>`;
                }).join('');
            }
            
            $('#global-watermelon-grid').innerHTML = data.bot_statuses.main_bots.map(bot => {
                const enabled = bot.watermelon_enabled;
                return `<div class="bot-status-item" style="justify-content:space-between;"><span>${bot.name}</span><button class="btn-toggle-state ${enabled ? 'btn-rise' : 'btn-rest'}" data-bot-id="${bot.reboot_id}" data-action="toggle_watermelon">${enabled ? 'ON' : 'OFF'}</button></div>`;
            }).join('');
            
            $('#servers-container').innerHTML = (data.servers || []).map(server => renderServer(server, data.bot_statuses)).join('');

        } catch (error) { console.error('Error fetching status:', error); }
    }

    doc.addEventListener('click', function(e) {
        const target = e.target.closest('[data-action], .btn-delete-server, #clan-drop-toggle-btn, #clan-drop-save-btn, #add-server-btn, .harvest-toggle, .broadcast-toggle');
        if (!target) return;
        
        const serverPanel = e.target.closest('.server-panel');
        const serverId = serverPanel ? serverPanel.dataset.serverId : null;

        if (target.dataset.action) {
            postData('/api/' + target.dataset.action, { bot_id: target.dataset.botId });
        } else if (target.id === 'add-server-btn') {
            const name = prompt('Enter server name:');
            if (name) postData('/api/add_server', { name });
        } else if (target.matches('.btn-delete-server')) {
            if (confirm('Delete this server?')) postData('/api/delete_server', { server_id: serverId });
        } else if (target.matches('.harvest-toggle')) {
            postData('/api/toggle_harvest', { server_id: serverId, bot_num: target.dataset.node });
        } else if (target.matches('.broadcast-toggle')) {
            postData('/api/toggle_broadcast', { server_id: serverId });
        } else if (target.id === 'clan-drop-toggle-btn') {
            postData('/api/toggle_clan_drop', {});
        } else if (target.id === 'clan-drop-save-btn') {
            const thresholds = {};
            $$('.clan-drop-threshold').forEach(i => { thresholds[i.dataset.node] = parseInt(i.value) || 50; });
            postData('/api/save_clan_drop_settings', {
                channel_id: $('#clan-drop-channel-id').value,
                ktb_channel_id: $('#clan-drop-ktb-channel-id').value,
                heart_thresholds: thresholds
            });
        }
    });

    doc.addEventListener('change', function(e) {
        const target = e.target.closest('.server-input, .harvest-threshold');
        if (!target) return;
        const serverId = e.target.closest('.server-panel').dataset.serverId;
        if (target.matches('.server-input')) {
            postData('/api/update_server_field', { server_id: serverId, field: target.dataset.field, value: target.value });
        } else if (target.matches('.harvest-threshold')) {
            postData('/api/update_harvest_threshold', { server_id: serverId, bot_num: target.dataset.node, threshold: parseInt(target.value) || 50 });
        }
    });

    fetchStatus();
    setInterval(fetchStatus, 5000);
});
</script>
</body>
</html>
"""

# --- FLASK ROUTES & API ENDPOINTS ---
@app.route('/')
def dashboard():
    return render_template_string(HTML_TEMPLATE)

@app.route('/status')
def status():
    try:
        main_bots, sub_accounts = [], []
        for i in range(1, len(main_tokens) + 1):
            bot_id = f'main_{i}'
            bot_instance = bot_manager.get_bot(bot_id)
            health_stats = bot_states["health_stats"].get(bot_id, {})
            reboot_settings = bot_states["reboot_settings"].get(bot_id, {})
            next_reboot_time = reboot_settings.get('next_reboot_time', 0)
            next_reboot_str = "Ready" if time.time() >= next_reboot_time else formatTime(next_reboot_time - time.time())
            main_bots.append({
                'name': get_bot_name(bot_id), 'reboot_id': bot_id,
                'is_active': bot_states["active"].get(bot_id, False),
                'consecutive_failures': health_stats.get('consecutive_failures', 0),
                'watermelon_enabled': bot_states["watermelon_grab"].get(bot_id, False),
                'reboot_enabled': reboot_settings.get('enabled', True),
                'next_reboot': next_reboot_str,
                'is_connected': check_bot_health(bot_instance, bot_id) if bot_instance else False
            })
        for i in range(1, len(tokens) + 1):
            bot_id = f'sub_{i}'
            bot_instance = bot_manager.get_bot(bot_id)
            health_stats = bot_states["health_stats"].get(bot_id, {})
            sub_accounts.append({
                'name': get_bot_name(bot_id), 'reboot_id': bot_id,
                'is_active': bot_states["active"].get(bot_id, False),
                'consecutive_failures': health_stats.get('consecutive_failures', 0),
                'reboot_enabled': False, 'next_reboot': 'N/A',
                'is_connected': check_bot_health(bot_instance, bot_id) if bot_instance else False
            })
        clan_drop = bot_states["auto_clan_drop"]
        next_cycle = clan_drop.get("last_cycle_start_time", 0) + clan_drop.get("cycle_interval", 1800)
        return jsonify({
            'server_start_time': server_start_time,
            'bot_statuses': {'main_bots': main_bots, 'sub_accounts': sub_accounts},
            'auto_clan_drop_status': {
                'enabled': clan_drop.get('enabled', False),
                'countdown': max(0, next_cycle - time.time()),
                'channel_id': clan_drop.get('channel_id', ''),
                'ktb_channel_id': clan_drop.get('ktb_channel_id', ''),
                'heart_thresholds': clan_drop.get('heart_thresholds', {})
            },
            'servers': servers, 'grab_success_logs': bot_manager.get_grab_logs()
        })
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

def formatTime(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:02d}:{m:02d}:{s:02d}"

@app.route('/api/<action>', methods=['POST'])
def handle_api_action(action):
    try:
        data = request.get_json()
        bot_id = data.get('bot_id')
        server_id = data.get('server_id')
        bot_num = data.get('bot_num')
        
        if action == 'toggle_bot_active':
            state = bot_states["active"].get(bot_id, False)
            bot_states["active"][bot_id] = not state
            return jsonify({'status': 'success', 'message': f'{get_bot_name(bot_id)} is now {"RISEN" if not state else "RESTING"}'})
        
        if action == 'toggle_reboot':
            settings = bot_states["reboot_settings"].setdefault(bot_id, {'enabled': True, 'delay': 3600})
            state = settings.get('enabled', True)
            settings['enabled'] = not state
            return jsonify({'status': 'success', 'message': f'Auto-reboot for {get_bot_name(bot_id)} is now {"ENABLED" if not state else "DISABLED"}'})

        if action == 'force_reboot':
            bot_states["reboot_settings"].setdefault(bot_id, {})['next_reboot_time'] = time.time() - 1
            return jsonify({'status': 'success', 'message': f'Force reboot scheduled for {get_bot_name(bot_id)}'})
        
        if action == 'toggle_watermelon':
            state = bot_states["watermelon_grab"].get(bot_id, False)
            bot_states["watermelon_grab"][bot_id] = not state
            return jsonify({'status': 'success', 'message': f'Watermelon grab for {get_bot_name(bot_id)} is now {"ENABLED" if not state else "DISABLED"}'})
        
        if action == 'toggle_clan_drop':
            state = bot_states["auto_clan_drop"].get('enabled', False)
            bot_states["auto_clan_drop"]['enabled'] = not state
            return jsonify({'status': 'success', 'message': f'Clan Auto Drop is now {"ENABLED" if not state else "DISABLED"}'})

        if action == 'save_clan_drop_settings':
            bot_states["auto_clan_drop"].update(data)
            return jsonify({'status': 'success', 'message': 'Clan Drop settings saved'})

        if action == 'add_server':
            new_server = {'id': str(uuid.uuid4()), 'name': data.get('name'), 'spam_delay': 10}
            for i in range(1, len(main_tokens) + 1):
                new_server[f'auto_grab_enabled_{i}'] = False
                new_server[f'heart_threshold_{i}'] = 50
            servers.append(new_server)
            return jsonify({'status': 'success', 'message': f'Server "{data.get("name")}" added', 'reload': True})

        if action == 'delete_server':
            global servers
            servers = [s for s in servers if s.get('id') != server_id]
            return jsonify({'status': 'success', 'message': 'Server deleted', 'reload': True})

        server = next((s for s in servers if s.get('id') == server_id), None)
        if not server: return jsonify({'status': 'error', 'message': 'Server not found'})

        if action == 'update_server_field':
            server[data.get('field')] = int(data.get('value')) if data.get('field') == 'spam_delay' else data.get('value')
        elif action == 'toggle_harvest':
            field = f'auto_grab_enabled_{bot_num}'
            state = server.get(field, False)
            server[field] = not state
        elif action == 'update_harvest_threshold':
            server[f'heart_threshold_{bot_num}'] = max(0, int(data.get('threshold', 50)))
        elif action == 'toggle_broadcast':
            state = server.get('spam_enabled', False)
            server['spam_enabled'] = not state
        elif action == 'save_settings':
            save_settings()
        
        return jsonify({'status': 'success', 'message': 'Action completed'})

    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

# --- KHỞI ĐỘNG HỆ THỐNG ---
def initialize_bots():
    print("[System] 🚀 Initializing Shadow Network...", flush=True)
    load_settings()
    for i, token in enumerate(main_tokens, 1):
        if token.strip() and create_bot(token.strip(), i, is_main=True):
            bot_manager.add_bot(f'main_{i}', _)
            bot_states["active"].setdefault(f'main_{i}', False)
            bot_states["watermelon_grab"].setdefault(f'main_{i}', False)
            bot_states["reboot_settings"].setdefault(f'main_{i}', {'enabled': True, 'delay': 3600, 'next_reboot_time': time.time() + 3600, 'failure_count': 0})
    for i, token in enumerate(tokens, 1):
        if token.strip() and create_bot(token.strip(), i, is_main=False):
            bot_manager.add_bot(f'sub_{i}', _)
            bot_states["active"].setdefault(f'sub_{i}', False)
            bot_states["reboot_settings"].setdefault(f'sub_{i}', {'enabled': False})
    
    threads = [
        threading.Thread(target=auto_reboot_loop, daemon=True),
        threading.Thread(target=auto_clan_drop_loop, daemon=True),
        threading.Thread(target=spam_loop_manager, daemon=True),
        threading.Thread(target=periodic_task, args=(300, save_settings, "Auto Save"), daemon=True),
        threading.Thread(target=periodic_task, args=(60, health_monitoring_check, "Health Monitor"), daemon=True)
    ]
    for thread in threads: thread.start()
    print("[System] ✅ Shadow Network initialized successfully!", flush=True)

if __name__ == "__main__":
    try:
        initialize_bots()
        port = int(os.getenv("PORT", 10000))
        print(f"[Flask] 🌐 Starting web interface on port {port}...", flush=True)
        app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
    except KeyboardInterrupt:
        print("\n[System] 🛑 Shutting down...", flush=True)
        stop_events["reboot"].set()
        stop_events["clan_drop"].set()
        for bot_id, _ in bot_manager.get_all_bots(): bot_manager.remove_bot(bot_id)
        save_settings()
        print("[System] 💤 Terminated.", flush=True)
    except Exception as e:
        print(f"[System] ❌ Critical error: {e}", flush=True)
        traceback.print_exc()
