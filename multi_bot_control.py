# PHIÊN BẢN NÂNG CẤP TOÀN DIỆN - KẾT HỢP TỪ 3 ĐOẠN MÃ
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

# --- QUẢN LÝ BOT THREAD-SAFE (IMPROVED WITH LOGGING) ---
class ThreadSafeBotManager:
    def __init__(self):
        self._bots = {}
        self._rebooting = set()
        self._lock = threading.RLock()
        self._grab_logs = []  # Log nhặt thẻ thành công
        self._max_logs = 50

    def add_bot(self, bot_id, bot_instance):
        with self._lock:
            self._bots[bot_id] = bot_instance
            print(f"[Bot Manager] ✅ Added bot {bot_id}", flush=True)

    def remove_bot(self, bot_id):
        with self._lock:
            bot = self._bots.pop(bot_id, None)
            if bot:
                # Đảm bảo cleanup gateway một cách an toàn
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
        """Thêm log khi nhặt thẻ thành công"""
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
            
            self._grab_logs.insert(0, log_entry)  # Thêm vào đầu list
            
            # Giới hạn số lượng log
            if len(self._grab_logs) > self._max_logs:
                self._grab_logs = self._grab_logs[:self._max_logs]
            
            print(f"[GRAB SUCCESS] 🎯 {bot_name} đã nhặt {card_name} với {hearts}♡", flush=True)

    def get_grab_logs(self):
        """Lấy danh sách log nhặt thẻ"""
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

# --- HÀM TRỢ GIÚP CHUNG ---
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
    """Wrapper để handle exceptions trong message processing, tránh crash gateway."""
    try:
        return handler_func(bot, msg, *args)
    except Exception as e:
        print(f"[Message Handler] ❌ Error in {handler_func.__name__}: {e}", flush=True)
        print(f"[Message Handler] 🐛 Traceback: {traceback.format_exc()}", flush=True)
        return None

def check_grab_result(bot, channel_id, drop_msg_id, bot_name, selected_card):
    """Kiểm tra kết quả nhặt thẻ và log nếu thành công"""
    try:
        # Đợi Karuta phản hồi
        time.sleep(2)
        messages = bot.getMessages(channel_id, num=10).json()
        
        if not isinstance(messages, list):
            return False
            
        # Tìm tin nhắn từ Karuta sau khi drop
        for msg in messages:
            if msg.get("author", {}).get("id") != karuta_id:
                continue
                
            msg_timestamp = int(msg.get("id", 0))
            drop_timestamp = int(drop_msg_id)
            
            # Chỉ check tin nhắn sau khi drop
            if msg_timestamp <= drop_timestamp:
                continue
                
            content = msg.get("content", "").lower()
            
            # Kiểm tra các từ khóa thành công: "fought off", "took the"
            success_keywords = ["fought off", "took the"]
            
            if any(keyword in content for keyword in success_keywords):
                # Tìm tên thẻ trong tin nhắn
                grabbed_card_name = selected_card['name']
                
                # Thử extract tên thẻ từ tin nhắn Karuta nếu có
                if "took the" in content:
                    # Pattern: "took the [CardName] card"
                    card_match = re.search(r"took the (.+?) card", content)
                    if card_match:
                        grabbed_card_name = card_match.group(1).strip()
                elif "fought off" in content:
                    # Thử extract từ "fought off" message
                    card_match = re.search(r"and took the (.+?) card", content)
                    if card_match:
                        grabbed_card_name = card_match.group(1).strip()
                
                # Log thành công
                bot_manager.add_grab_success_log(
                    bot_name=bot_name,
                    card_name=grabbed_card_name,
                    hearts=selected_card['hearts']
                )
                return True
                
        return False
        
    except Exception as e:
        print(f"[GRAB CHECK | {bot_name}] ❌ Lỗi kiểm tra kết quả: {e}", flush=True)
        return False

# --- LOGIC GRAB CARD (UPDATED WITH LOGGING) ---
def _find_and_select_card(bot, channel_id, last_drop_msg_id, heart_threshold, bot_num, ktb_channel_id):
    """Hàm chung để tìm và chọn card dựa trên số heart với enhanced logging."""
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

                    # Parse card info và hearts
                    lines = desc.split('\n')[:3]
                    card_info = []
                    heart_numbers = []
                    
                    for i, line in enumerate(lines):
                        heart_match = re.search(r'♡(\d+)', line)
                        if heart_match:
                            hearts = int(heart_match.group(1))
                            heart_numbers.append(hearts)
                            # Extract card name (phần trước dấu ♡)
                            card_name_part = line.split('♡')[0].strip()
                            # Loại bỏ số thứ tự ở đầu (1️⃣, 2️⃣, 3️⃣)
                            card_name_part = re.sub(r'^[123]️⃣\s*', '', card_name_part)
                            card_info.append({
                                'name': card_name_part,
                                'hearts': hearts,
                                'position': i + 1
                            })
                        else:
                            heart_numbers.append(0)
                            card_info.append({'name': 'Unknown', 'hearts': 0, 'position': i + 1})

                    if not any(heart_numbers): break

                    max_hearts = max(heart_numbers)
                    if max_hearts >= heart_threshold:
                        max_index = heart_numbers.index(max_hearts)
                        selected_card = card_info[max_index]
                        
                        delays = {1: [0.4, 1.4, 2.1], 2: [0.7, 1.8, 2.4], 3: [0.7, 1.8, 2.4], 4: [0.8, 1.9, 2.5]}
                        bot_delays = delays.get(bot_num, [0.9, 2.0, 2.6])
                        emoji = ["1️⃣", "2️⃣", "3️⃣"][max_index]
                        delay = bot_delays[max_index]
                        
                        print(f"[CARD GRAB | {bot_name}] 🎯 Chọn {selected_card['name']} ({selected_card['hearts']}♡) -> {emoji} sau {delay}s", flush=True)
                        
                        def grab_action():
                            try:
                                bot.addReaction(channel_id, last_drop_msg_id, emoji)
                                time.sleep(1.2)
                                if ktb_channel_id: 
                                    bot.sendMessage(ktb_channel_id, "kt b")
                                
                                # Chờ một chút rồi check kết quả
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
    if not (clan_settings.get("enabled") and msg.get("channel_id") == clan_settings.get("channel_id")):
        return
    bot_id_str = f'main_{bot_num}'
    threshold = clan_settings.get("heart_thresholds", {}).get(bot_id_str, 50)
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

# --- HỆ THỐNG REBOOT & HEALTH CHECK (IMPROVED) ---
def check_bot_health(bot_instance, bot_id):
    """Improved health check with better error handling."""
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
        bot_states["health_stats"].setdefault(bot_id, {})['consecutive_failures'] = \
            bot_states["health_stats"][bot_id].get('consecutive_failures', 0) + 1
        return False

def handle_reboot_failure(bot_id):
    settings = bot_states["reboot_settings"].setdefault(bot_id, {'delay': 3600, 'enabled': True})
    failure_count = settings.get('failure_count', 0) + 1
    settings['failure_count'] = failure_count
    
    # Exponential Backoff
    backoff_multiplier = min(2 ** failure_count, 8)
    # Ensure delay is not excessively long for the first few failures
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
        if not match:
             # For simplicity, we assume only main bots are rebootable this way.
             # You could expand this to handle sub_bots if needed.
            raise ValueError("Định dạng bot_id không hợp lệ cho reboot.")
        
        bot_index = int(match.group(1)) - 1
        if not (0 <= bot_index < len(main_tokens)):
            raise IndexError("Bot index ngoài phạm vi danh sách token.")

        token = main_tokens[bot_index].strip()
        bot_name = get_bot_name(bot_id)

        # Cleanup bot cũ
        print(f"[Safe Reboot] 🧹 Cleaning up old bot instance for {bot_name}", flush=True)
        bot_manager.remove_bot(bot_id) # remove_bot đã bao gồm gateway.close()

        # Exponential backoff delay
        settings = bot_states["reboot_settings"].get(bot_id, {})
        failure_count = settings.get('failure_count', 0)
        wait_time = random.uniform(20, 40) + min(failure_count * 30, 300)
        print(f"[Safe Reboot] ⏳ Chờ {wait_time:.1f}s để cleanup và tránh rate limit...", flush=True)
        time.sleep(wait_time)

        # Tạo bot mới với logic kết nối đáng tin cậy hơn
        print(f"[Safe Reboot] 🏗️ Creating new bot instance for {bot_name}", flush=True)
        new_bot = create_bot(token, bot_identifier=(bot_index + 1), is_main=True)
        if not new_bot:
            raise Exception("Không thể tạo instance bot mới hoặc kết nối gateway thất bại.")

        bot_manager.add_bot(bot_id, new_bot)
        
        settings.update({
            'next_reboot_time': time.time() + settings.get('delay', 3600),
            'failure_count': 0,
            'last_reboot_time': time.time()
        })
        bot_states["health_stats"][bot_id]['consecutive_failures'] = 0
        print(f"[Safe Reboot] ✅ Reboot thành công {bot_name}", flush=True)
        return True
    except Exception as e:
        print(f"[Safe Reboot] ❌ Reboot thất bại cho {bot_id}: {e}", flush=True)
        traceback.print_exc()
        handle_reboot_failure(bot_id)
        return False
    finally:
        bot_manager.end_reboot(bot_id) # Luôn đảm bảo cờ reboot được gỡ

# --- VÒNG LẶP NỀN (IMPROVED) ---
def auto_reboot_loop():
    print("[Safe Reboot] 🚀 Khởi động luồng tự động reboot với cải tiến.", flush=True)
    last_global_reboot_time = 0
    consecutive_system_failures = 0
    
    while not stop_events["reboot"].is_set():
        try:
            now = time.time()
            
            # Global rate limiting
            min_global_interval = 600 # Tối thiểu 10 phút giữa các lần reboot
            if now - last_global_reboot_time < min_global_interval:
                stop_events["reboot"].wait(60)
                continue

            bot_to_reboot = None
            highest_priority_score = -1
            
            reboot_settings_copy = dict(bot_states["reboot_settings"].items())
            
            for bot_id, settings in reboot_settings_copy.items():
                if not settings.get('enabled', False) or bot_manager.is_rebooting(bot_id):
                    continue
                
                next_reboot_time = settings.get('next_reboot_time', 0)
                if now < next_reboot_time:
                    continue
                    
                # Tính điểm ưu tiên
                health_stats = bot_states["health_stats"].get(bot_id, {})
                failure_count = health_stats.get('consecutive_failures', 0)
                time_overdue = now - next_reboot_time
                
                priority_score = (failure_count * 1000) + time_overdue
                
                if priority_score > highest_priority_score:
                    highest_priority_score = priority_score
                    bot_to_reboot = bot_id
            
            if bot_to_reboot:
                print(f"[Safe Reboot] 🎯 Chọn reboot bot: {bot_to_reboot} (priority: {highest_priority_score:.1f})", flush=True)
                
                if safe_reboot_bot(bot_to_reboot):
                    last_global_reboot_time = now
                    consecutive_system_failures = 0
                    # Chờ lâu hơn nếu không có bot nào khác cần reboot gấp
                    wait_time = random.uniform(300, 600)
                    print(f"[Safe Reboot] ⏳ Chờ {wait_time:.0f}s trước khi tìm bot reboot tiếp theo.", flush=True)
                    stop_events["reboot"].wait(wait_time)
                else:
                    # Nếu reboot thất bại, backoff để tránh spam
                    consecutive_system_failures += 1
                    backoff_time = min(120 * (2 ** consecutive_system_failures), 1800) # Max 30 phút
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
    channel_id = settings.get("channel_id")
    
    active_main_bots = [
        (bot, int(bot_id.split('_')[1])) 
        for bot_id, bot in bot_manager.get_main_bots_info() 
        if bot and bot_states["active"].get(bot_id, False)
    ]

    if not active_main_bots:
        print("[Clan Drop] ⚠️ Không có bot chính nào hoạt động.", flush=True)
        return

    for bot, bot_num in active_main_bots:
        if stop_events["clan_drop"].is_set(): break
        try:
            print(f"[Clan Drop] 📤 Bot {get_bot_name(f'main_{bot_num}')} đang gửi 'kd'...", flush=True)
            bot.sendMessage(channel_id, "kd")
            time.sleep(random.uniform(settings["bot_delay"] * 0.8, settings["bot_delay"] * 1.2))
        except Exception as e:
            print(f"[Clan Drop] ❌ Lỗi khi gửi 'kd' từ bot {bot_num}: {e}", flush=True)
    
    settings["last_cycle_start_time"] = time.time()
    save_settings()

def auto_clan_drop_loop():
    while not stop_events["clan_drop"].is_set():
        settings = bot_states["auto_clan_drop"]
        if (settings.get("enabled") and settings.get("channel_id") and 
            (time.time() - settings.get("last_cycle_start_time", 0)) >= settings.get("cycle_interval", 1800)):
            run_clan_drop_cycle()
        stop_events["clan_drop"].wait(60)
    print("[Clan Drop] 🛑 Luồng tự động drop clan đã dừng.", flush=True)

def spam_for_server(server_config, stop_event):
    server_name = server_config.get('name')
    channel_id = server_config.get('spam_channel_id')
    message = server_config.get('spam_message')
    
    while not stop_event.is_set():
        try:
            all_bots = bot_manager.get_all_bots()
            bots_to_spam = [
                bot for bot_id, bot in all_bots if bot and bot_states["active"].get(bot_id)
            ]

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

# --- KHỞI TẠO BOT (IMPROVED) ---
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
                    
                    bot_states["health_stats"].setdefault(bot_id_str, {})
                    bot_states["health_stats"][bot_id_str].update({
                        'created_time': time.time(),
                        'consecutive_failures': 0,
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
                        content = msg.get("content", "").lower()
                        
                        if author_id == karuta_id and "dropping" in content:
                            handler = handle_clan_drop if msg.get("mentions") else handle_grab
                            # Sử dụng wrapper để tăng độ an toàn
                            safe_message_handler_wrapper(handler, bot, msg, bot_identifier)
                except Exception as e:
                    print(f"[Bot] ❌ Error in on_message for {bot_id_str}: {e}", flush=True)

        def start_gateway():
            try:
                bot.gateway.run(auto_reconnect=True)
            except Exception as e:
                print(f"[Bot] ❌ Gateway error for {bot_id_str}: {e}", flush=True)
        
        threading.Thread(target=start_gateway, daemon=True).start()
        
        # Chờ kết nối với timeout để xác nhận bot hoạt động
        connection_timeout = 20
        start_time = time.time()
        while time.time() - start_time < connection_timeout:
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
    <title>Shadow Network Control - Enhanced with Grab Logging</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <link href="https://fonts.googleapis.com/css2?family=Creepster&family=Orbitron:wght@400;700;900&family=Courier+Prime:wght@400;700&family=Nosifer&display=swap" rel="stylesheet">
    <style>
        :root { --primary-bg: #0a0a0a; --secondary-bg: #1a1a1a; --panel-bg: #111111; --border-color: #333333; --blood-red: #8b0000; --dark-red: #550000; --bone-white: #f8f8ff; --necro-green: #228b22; --text-primary: #f0f0f0; --text-secondary: #cccccc; --warning-orange: #ff8c00; --success-green: #32cd32; }
        body { font-family: 'Courier Prime', monospace; background: var(--primary-bg); color: var(--text-primary); margin: 0; padding: 0;}
        .container { max-width: 1600px; margin: 0 auto; padding: 20px; }
        .header { text-align: center; margin-bottom: 30px; padding: 20px; border-bottom: 2px solid var(--blood-red); position: relative; }
        .title { font-family: 'Nosifer', cursive; font-size: 3rem; color: var(--blood-red); }
        .subtitle { font-family: 'Orbitron', sans-serif; font-size: 1rem; color: var(--necro-green); margin-top: 10px; }
        .main-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(500px, 1fr)); gap: 20px; }
        .panel { background: var(--panel-bg); border: 1px solid var(--border-color); border-radius: 10px; padding: 25px; position: relative;}
        .panel h2 { font-family: 'Orbitron', cursive; font-size: 1.4rem; margin-bottom: 20px; text-transform: uppercase; border-bottom: 2px solid; padding-bottom: 10px; color: var(--bone-white); }
        .panel h2 i { margin-right: 10px; }
        .btn { background: var(--secondary-bg); border: 1px solid var(--border-color); color: var(--text-primary); padding: 10px 15px; border-radius: 4px; cursor: pointer; font-family: 'Orbitron', monospace; font-weight: 700; text-transform: uppercase; width: 100%; transition: all 0.3s ease; }
        .btn:hover { background: var(--dark-red); border-color: var(--blood-red); }
        .btn-small { padding: 5px 10px; font-size: 0.9em;}
        .input-group { display: flex; align-items: stretch; gap: 10px; margin-bottom: 15px; }
        .input-group label { background: #000; border: 1px solid var(--border-color); border-right: 0; padding: 10px 15px; border-radius: 4px 0 0 4px; display:flex; align-items:center; min-width: 120px;}
        .input-group input, .input-group textarea { flex-grow: 1; background: #000; border: 1px solid var(--border-color); color: var(--text-primary); padding: 10px 15px; border-radius: 0 4px 4px 0; font-family: 'Courier Prime', monospace; }
        .grab-section { display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; padding: 15px; background: rgba(0,0,0,0.2); border-radius: 8px;}
        .grab-section h3 { margin: 0; display: flex; align-items: center; gap: 10px; width: 80px; flex-shrink: 0; }
        .grab-section .input-group { margin-bottom: 0; flex-grow: 1; margin-left: 20px;}
        .msg-status { text-align: center; color: var(--necro-green); padding: 12px; border: 1px dashed var(--border-color); border-radius: 4px; margin-bottom: 20px; display: none; }
        .msg-status.error { color: var(--blood-red); border-color: var(--blood-red); }
        .msg-status.warning { color: var(--warning-orange); border-color: var(--warning-orange); }
        .status-panel, .global-settings-panel, .clan-drop-panel, .grab-logs-panel { grid-column: 1 / -1; }
        .status-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 15px; }
        .status-row { display: flex; justify-content: space-between; align-items: center; padding: 12px; background: rgba(0,0,0,0.4); border-radius: 8px; }
        .timer-display { font-size: 1.2em; font-weight: 700; }
        .bot-status-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 8px; }
        .bot-status-item { display: flex; justify-content: space-between; align-items: center; padding: 5px 8px; background: rgba(0,0,0,0.3); border-radius: 4px; }
        .btn-toggle-state { padding: 3px 5px; font-size: 0.9em; border-radius: 4px; cursor: pointer; text-transform: uppercase; background: transparent; font-weight: 700; border: none; }
        .btn-rise { color: var(--success-green); }
        .btn-rest { color: var(--dark-red); }
        .btn-warning { color: var(--warning-orange); }
        .add-server-btn { display: flex; align-items: center; justify-content: center; min-height: 200px; border: 2px dashed var(--border-color); cursor: pointer; transition: all 0.3s ease; }
        .add-server-btn:hover { background: var(--secondary-bg); border-color: var(--blood-red); }
        .add-server-btn i { font-size: 3rem; color: var(--text-secondary); }
        .btn-delete-server { position: absolute; top: 15px; right: 15px; background: var(--dark-red); border: 1px solid var(--blood-red); color: var(--bone-white); width: auto; padding: 5px 10px; border-radius: 50%; }
        .server-sub-panel { border-top: 1px solid var(--border-color); margin-top: 20px; padding-top: 20px;}
        .flex-row { display:flex; gap: 10px; align-items: center;}
        .health-indicator { display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-left: 5px; }
        .health-good { background-color: var(--success-green); }
        .health-warning { background-color: var(--warning-orange); }
        .health-bad { background-color: var(--blood-red); }
        .system-stats { font-size: 0.9em; color: var(--text-secondary); margin-top: 10px; }
        
        /* Grab Logs Styles */
        .grab-logs-panel { 
            max-height: 400px; 
            overflow-y: auto; 
        }
        .grab-log-item { 
            display: flex; 
            justify-content: space-between; 
            align-items: center; 
            padding: 8px 12px; 
            margin-bottom: 5px; 
            background: rgba(0, 50, 0, 0.2); 
            border-left: 3px solid var(--success-green); 
            border-radius: 4px; 
        }
        .grab-log-time { 
            font-family: 'Orbitron', monospace; 
            font-weight: 700; 
            color: var(--necro-green); 
            min-width: 70px;
        }
        .grab-log-bot { 
            font-weight: 700; 
            color: var(--warning-orange); 
            min-width: 80px;
            text-align: center;
        }
        .grab-log-card { 
            color: var(--bone-white); 
            flex-grow: 1; 
            text-align: center; 
            padding: 0 10px;
        }
        .grab-log-hearts { 
            color: var(--blood-red); 
            font-weight: 700; 
            min-width: 50px;
            text-align: right;
        }
        .no-logs-message { 
            text-align: center; 
            color: var(--text-secondary); 
            padding: 20px; 
            font-style: italic; 
        }
        
        .bot-control-item {
            background: rgba(0,0,0,0.4);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 15px;
            margin-bottom: 10px;
        }
        
        .bot-control-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 10px;
        }
        
        .bot-control-name {
            font-weight: 700;
            color: var(--bone-white);
        }
        
        .bot-control-actions {
            display: flex;
            gap: 5px;
            align-items: center;
        }
        
        .bot-control-details {
            font-size: 0.9em;
            color: var(--text-secondary);
            line-height: 1.4;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1 class="title">Shadow Network Control</h1>
            <div class="subtitle">Enhanced Safe Reboot System + Grab Success Logging</div>
        </div>
        <div id="msg-status-container" class="msg-status"> 
            <span id="msg-status-text"></span>
        </div>
        
        <div class="main-grid">
            <div class="panel grab-logs-panel">
                <h2><i class="fas fa-trophy"></i> Grab Success Logs</h2>
                <div id="grab-logs-container">
                    <div class="no-logs-message">Chưa có log nhặt thẻ thành công nào...</div>
                </div>
            </div>

            <div class="panel status-panel">
                <h2><i class="fas fa-heartbeat"></i> System Status & Enhanced Reboot Control</h2>
                <div class="status-row" style="margin-bottom: 20px;">
                    <span><i class="fas fa-server"></i> System Uptime</span>
                    <div><span id="uptime-timer" class="timer-display">--:--:--</span></div>
                </div>
                <div class="status-row" style="margin-bottom: 20px;">
                    <span><i class="fas fa-shield-alt"></i> Safe Reboot Status</span>
                    <div><span id="reboot-status" class="timer-display">ACTIVE</span></div>
                </div>
                <div class="server-sub-panel">
                    <h3><i class="fas fa-robot"></i> Enhanced Bot Control Matrix</h3>
                    <div class="system-stats">
                        <div>🔒 Safety Features: Health Checks, Exponential Backoff, Rate Limiting</div>
                        <div>⏱️ Min Reboot Interval: 10 minutes | Max Failures: 5 attempts</div>
                        <div>🎯 Reboot Strategy: Priority-based, one-at-a-time with cleanup delay</div>
                        <div>🎯 New: Auto-detect grab success with "fought off" & "took the"</div>
                    </div>
                    <div id="bot-control-grid" class="bot-status-grid" style="grid-template-columns: repeat(auto-fit, minmax(380px, 1fr));">
                    </div>
                </div>
            </div>

            <div class="panel clan-drop-panel">
                <h2><i class="fas fa-users"></i> Clan Auto Drop</h2>
                <div class="status-grid" style="grid-template-columns: 1fr;">
                    <div class="status-row">
                        <span><i class="fas fa-hourglass-half"></i> Next Drop Cycle</span>
                        <div class="flex-row">
                            <span id="clan-drop-timer" class="timer-display">--:--:--</span>
                            <button type="button" id="clan-drop-toggle-btn" class="btn btn-small">ENABLE</button>
                        </div>
                    </div>
                </div>
                <div class="server-sub-panel">
                    <h3><i class="fas fa-cogs"></i> Configuration</h3>
                    <div class="input-group">
                        <label>Drop Channel ID</label>
                        <input type="text" id="clan-drop-channel-id" value="">
                    </div>
                    <div class="input-group">
                        <label>KTB Channel ID</label>
                        <input type="text" id="clan-drop-ktb-channel-id" value="">
                    </div>
                </div>
                <div class="server-sub-panel">
                    <h3><i class="fas fa-crosshairs"></i> Soul Harvest (Clan Drop)</h3>
                    <div id="clan-drop-thresholds-container">
                        </div>
                </div>
                <button type="button" id="clan-drop-save-btn" class="btn" style="margin-top: 20px;">Save Clan Drop Settings</button>
            </div>

            <div class="panel global-settings-panel">
                <h2><i class="fas fa-globe"></i> Global Event Settings</h2>
                <div class="server-sub-panel">
                    <h3><i class="fas fa-seedling"></i> Watermelon Grab (All Servers)</h3>
                    <div id="global-watermelon-grid" class="bot-status-grid" style="grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));">
                    </div>
                </div>
            </div>

            <div id="servers-container">
                </div>

            <div class="panel add-server-btn" id="add-server-btn">
                <i class="fas fa-plus"></i>
            </div>
        </div>
    </div>

<script>
document.addEventListener('DOMContentLoaded', function () {
    const msgStatusContainer = document.getElementById('msg-status-container');
    const msgStatusText = document.getElementById('msg-status-text');

    function showStatusMessage(message, type = 'success') {
        if (!message) return;
        msgStatusText.textContent = message;
        msgStatusContainer.className = `msg-status ${type === 'error' ? 'error' : type === 'warning' ? 'warning' : ''}`;
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
            showStatusMessage(result.message, result.status !== 'success' ? 'error' : 'success');
            if (result.status === 'success' && url !== '/api/save_settings') {
                fetch('/api/save_settings', { method: 'POST' });
                if (result.reload) { 
                    setTimeout(() => window.location.reload(), 500); 
                }
            }
            setTimeout(fetchStatus, 500);
            return result;
        } catch (error) {
            console.error('Error:', error);
            showStatusMessage('Server communication error.', 'error');
        }
    }

    function formatTime(seconds) {
        if (isNaN(seconds) || seconds < 0) return "--:--:--";
        seconds = Math.floor(seconds);
        const h = Math.floor(seconds / 3600).toString().padStart(2, '0');
        const m = Math.floor((seconds % 3600) / 60).toString().padStart(2, '0');
        const s = (seconds % 60).toString().padStart(2, '0');
        return `${h}:${m}:${s}`;
    }

    function updateElement(element, { textContent, className, value, innerHTML }) {
        if (!element) return;
        if (textContent !== undefined) element.textContent = textContent;
        if (className !== undefined) element.className = className;
        if (value !== undefined) element.value = value;
        if (innerHTML !== undefined) element.innerHTML = innerHTML;
    }

    function updateGrabLogs(logs) {
        const container = document.getElementById('grab-logs-container');
        if (!container) return;
        
        if (!logs || logs.length === 0) {
            container.innerHTML = '<div class="no-logs-message">Chưa có log nhặt thẻ thành công nào...</div>';
            return;
        }
        
        let logsHtml = '';
        logs.forEach(log => {
            logsHtml += `
                <div class="grab-log-item">
                    <span class="grab-log-time">${log.formatted_time}</span>
                    <span class="grab-log-bot">${log.bot_name}</span>
                    <span class="grab-log-card">${log.card_name}</span>
                    <span class="grab-log-hearts">${log.hearts}♡</span>
                </div>
            `;
        });
        
        container.innerHTML = logsHtml;
    }

    function updateBotControlGrid(botStatuses) {
        const grid = document.getElementById('bot-control-grid');
        if (!grid || !botStatuses) return;

        const allBots = [...botStatuses.main_bots, ...botStatuses.sub_accounts];
        
        let gridHtml = '';
        allBots.forEach(bot => {
            const healthClass = bot.consecutive_failures === 0 ? 'health-good' : 
                                  bot.consecutive_failures < 3 ? 'health-warning' : 'health-bad';
            
            const activeText = bot.is_active ? 'RISE' : 'REST';
            const activeClass = bot.is_active ? 'btn-rise' : 'btn-rest';
            
            const rebootEnabled = bot.reboot_enabled ? 'ON' : 'OFF';
            const rebootClass = bot.reboot_enabled ? 'btn-rise' : 'btn-rest';
            
            gridHtml += `
                <div class="bot-control-item">
                    <div class="bot-control-header">
                        <span class="bot-control-name">${bot.name}</span>
                        <span class="health-indicator ${healthClass}"></span>
                    </div>
                    <div class="bot-control-actions">
                        <button class="btn-toggle-state ${activeClass}" data-bot-id="${bot.reboot_id}" data-action="toggle_active">
                            ${activeText}
                        </button>
                        <button class="btn-toggle-state ${rebootClass}" data-bot-id="${bot.reboot_id}" data-action="toggle_reboot">
                            RBT: ${rebootEnabled}
                        </button>
                        <button class="btn-toggle-state btn-warning" data-bot-id="${bot.reboot_id}" data-action="force_reboot">
                            FORCE
                        </button>
                    </div>
                    <div class="bot-control-details">
                        Failures: ${bot.consecutive_failures} | Next Reboot: ${bot.next_reboot}
                    </div>
                </div>
            `;
        });
        
        grid.innerHTML = gridHtml;
    }

    function updateWatermelonGrid(botStatuses) {
        const grid = document.getElementById('global-watermelon-grid');
        if (!grid || !botStatuses) return;

        let gridHtml = '';
        botStatuses.main_bots.forEach(bot => {
            const watermelonEnabled = bot.watermelon_enabled ? 'ON' : 'OFF';
            const watermelonClass = bot.watermelon_enabled ? 'btn-rise' : 'btn-rest';
            
            gridHtml += `
                <div class="bot-status-item">
                    <span>${bot.name}</span>
                    <button class="btn-toggle-state ${watermelonClass}" data-bot-id="${bot.reboot_id}" data-action="toggle_watermelon">
                        ${watermelonEnabled}
                    </button>
                </div>
            `;
        });
        
        grid.innerHTML = gridHtml;
    }

    function updateClanDropThresholds(botStatuses, clanDropStatus) {
        const container = document.getElementById('clan-drop-thresholds-container');
        if (!container || !botStatuses) return;

        let html = '';
        botStatuses.main_bots.forEach(bot => {
            const threshold = clanDropStatus?.heart_thresholds?.[bot.reboot_id] || 50;
            html += `
                <div class="grab-section">
                    <h3>${bot.name}</h3>
                    <div class="input-group">
                        <input type="number" class="clan-drop-threshold" data-node="${bot.reboot_id}" value="${threshold}" min="0">
                    </div>
                </div>
            `;
        });
        
        container.innerHTML = html;
    }

    function createServerPanel(server) {
        return `
            <div class="panel server-panel" data-server-id="${server.id}">
                <button class="btn-delete-server" title="Delete Server"><i class="fas fa-times"></i></button>
                <h2><i class="fas fa-server"></i> ${server.name}</h2>
                <div class="server-sub-panel">
                    <h3><i class="fas fa-cogs"></i> Channel Config</h3>
                    <div class="input-group">
                        <label>Main Channel ID</label>
                        <input type="text" class="channel-input" data-field="main_channel_id" value="${server.main_channel_id || ''}">
                    </div>
                    <div class="input-group">
                        <label>KTB Channel ID</label>
                        <input type="text" class="channel-input" data-field="ktb_channel_id" value="${server.ktb_channel_id || ''}">
                    </div>
                    <div class="input-group">
                        <label>Spam Channel ID</label>
                        <input type="text" class="channel-input" data-field="spam_channel_id" value="${server.spam_channel_id || ''}">
                    </div>
                </div>
                <div class="server-sub-panel">
                    <h3><i class="fas fa-crosshairs"></i> Soul Harvest (Card Grab)</h3>
                    <div id="grab-settings-${server.id}">
                        </div>
                </div>
                <div class="server-sub-panel">
                    <h3><i class="fas fa-paper-plane"></i> Auto Broadcast</h3>
                    <div class="input-group">
                        <label>Message</label>
                        <textarea class="spam-message" rows="2">${server.spam_message || ''}</textarea>
                    </div>
                    <div class="input-group">
                        <label>Delay (s)</label>
                        <input type="number" class="spam-delay" value="${server.spam_delay || 10}">
                        <span class="timer-display spam-timer">--:--:--</span>
                    </div>
                    <button type="button" class="btn broadcast-toggle">
                        ${server.spam_enabled ? 'DISABLE' : 'ENABLE'}
                    </button>
                </div>
            </div>
        `;
    }

    function updateServers(servers, botStatuses) {
        const container = document.getElementById('servers-container');
        if (!container) return;

        container.innerHTML = servers.map(server => createServerPanel(server)).join('');
        
        // Update grab settings for each server
        servers.forEach(server => {
            updateServerGrabSettings(server, botStatuses);
        });
    }

    function updateServerGrabSettings(server, botStatuses) {
        const container = document.getElementById(`grab-settings-${server.id}`);
        if (!container || !botStatuses) return;

        let html = '';
        botStatuses.main_bots.forEach(bot => {
            const botNum = bot.reboot_id.split('_')[1];
            const threshold = server[`heart_threshold_${botNum}`] || 50;
            const enabled = server[`auto_grab_enabled_${botNum}`] || false;
            
            html += `
                <div class="grab-section">
                    <h3>${bot.name}</h3>
                    <div class="input-group">
                        <input type="number" class="harvest-threshold" data-node="${botNum}" value="${threshold}" min="0">
                        <button type="button" class="btn harvest-toggle" data-node="${botNum}">
                            ${enabled ? 'DISABLE' : 'ENABLE'}
                        </button>
                    </div>
                </div>
            `;
        });
        
        container.innerHTML = html;
    }

    async function fetchStatus() {
        try {
            const response = await fetch('/status');
            const data = await response.json();

            // Update uptime
            const serverUptimeSeconds = (Date.now() / 1000) - data.server_start_time;
            updateElement(document.getElementById('uptime-timer'), { 
                textContent: formatTime(serverUptimeSeconds) 
            });

            // Update grab logs
            updateGrabLogs(data.grab_success_logs || []);

            // Update clan drop status
            if (data.auto_clan_drop_status) {
                updateElement(document.getElementById('clan-drop-timer'), { 
                    textContent: formatTime(data.auto_clan_drop_status.countdown) 
                });
                updateElement(document.getElementById('clan-drop-toggle-btn'), { 
                    textContent: data.auto_clan_drop_status.enabled ? 'DISABLE' : 'ENABLE' 
                });
                updateElement(document.getElementById('clan-drop-channel-id'), { 
                    value: data.auto_clan_drop_status.channel_id || '' 
                });
                updateElement(document.getElementById('clan-drop-ktb-channel-id'), { 
                    value: data.auto_clan_drop_status.ktb_channel_id || '' 
                });
                
                // Update clan drop thresholds
                updateClanDropThresholds(data.bot_statuses, data.auto_clan_drop_status);
            }

            // Update bot controls
            updateBotControlGrid(data.bot_statuses);
            updateWatermelonGrid(data.bot_statuses);
            
            // Update servers
            updateServers(data.servers || [], data.bot_statuses);
            
        } catch (error) {
            console.error('Error fetching status:', error);
        }
    }

    // Event listeners
    document.addEventListener('click', async function(e) {
        const target = e.target;
        
        // Bot control buttons
        if (target.matches('.btn-toggle-state[data-action]')) {
            const botId = target.dataset.botId;
            const action = target.dataset.action;
            
            if (action === 'toggle_active') {
                await postData('/api/toggle_bot_active', { bot_id: botId });
            } else if (action === 'toggle_reboot') {
                await postData('/api/toggle_reboot', { bot_id: botId });
            } else if (action === 'force_reboot') {
                if (confirm(`Force reboot ${botId}?`)) {
                    await postData('/api/force_reboot', { bot_id: botId });
                }
            } else if (action === 'toggle_watermelon') {
                await postData('/api/toggle_watermelon', { bot_id: botId });
            }
        }
        
        // Clan drop toggle
        if (target.matches('#clan-drop-toggle-btn')) {
            await postData('/api/toggle_clan_drop');
        }
        
        // Clan drop save
        if (target.matches('#clan-drop-save-btn')) {
            const channelId = document.getElementById('clan-drop-channel-id').value;
            const ktbChannelId = document.getElementById('clan-drop-ktb-channel-id').value;
            const thresholds = {};
            
            document.querySelectorAll('.clan-drop-threshold').forEach(input => {
                thresholds[input.dataset.node] = parseInt(input.value) || 50;
            });
            
            await postData('/api/save_clan_drop_settings', {
                channel_id: channelId,
                ktb_channel_id: ktbChannelId,
                heart_thresholds: thresholds
            });
        }
        
        // Add server
        if (target.matches('#add-server-btn, #add-server-btn *')) {
            const serverName = prompt('Enter server name:');
            if (serverName) {
                await postData('/api/add_server', { name: serverName });
            }
        }
        
        // Delete server
        if (target.matches('.btn-delete-server, .btn-delete-server *')) {
            const panel = target.closest('.server-panel');
            const serverId = panel.dataset.serverId;
            if (confirm('Delete this server?')) {
                await postData('/api/delete_server', { server_id: serverId });
            }
        }
        
        // Harvest toggle
        if (target.matches('.harvest-toggle')) {
            const panel = target.closest('.server-panel');
            const serverId = panel.dataset.serverId;
            const botNode = target.dataset.node;
            await postData('/api/toggle_harvest', { 
                server_id: serverId, 
                bot_num: parseInt(botNode) 
            });
        }
        
        // Broadcast toggle
        if (target.matches('.broadcast-toggle')) {
            const panel = target.closest('.server-panel');
            const serverId = panel.dataset.serverId;
            await postData('/api/toggle_broadcast', { server_id: serverId });
        }
    });
    
    // Input change handlers (using event delegation for dynamically added elements)
    document.addEventListener('change', async function(e) {
        const target = e.target;
        
        // Helper function for debouncing might be useful here in a real app,
        // but for now, this is fine.
        
        const panel = target.closest('.server-panel');
        if (!panel) return; // Ignore inputs outside server panels
        
        const serverId = panel.dataset.serverId;
        let payload = { server_id: serverId };

        if (target.matches('.channel-input')) {
            payload.field = target.dataset.field;
            payload.value = target.value;
            await postData('/api/update_server_field', payload);
        } else if (target.matches('.harvest-threshold')) {
            payload.bot_num = parseInt(target.dataset.node);
            payload.threshold = parseInt(target.value) || 50;
            await postData('/api/update_harvest_threshold', payload);
        } else if (target.matches('.spam-message')) {
            payload.field = 'spam_message';
            payload.value = target.value;
            await postData('/api/update_server_field', payload);
        } else if (target.matches('.spam-delay')) {
            payload.field = 'spam_delay';
            payload.value = parseInt(target.value) || 10;
            await postData('/api/update_server_field', payload);
        }
    });


    // Initialize status fetching
    fetchStatus();
    setInterval(fetchStatus, 5000); // Update every 5 seconds
});
</script>
</body>
</html>
"""

# --- FLASK ROUTES & API ENDPOINTS ---

@app.route('/')
def dashboard():
    """Render main dashboard. The new JS will handle dynamic content."""
    # The template is now mostly client-side rendered, so we don't need to pass much.
    # The JS will call /status to get all the dynamic data.
    return render_template_string(HTML_TEMPLATE)

@app.route('/status')
def status():
    """API endpoint trả về status realtime của toàn bộ hệ thống"""
    try:
        # Bot statuses
        main_bots = []
        sub_accounts = []
        
        # Main bots
        for i in range(1, len(main_tokens) + 1):
            bot_id = f'main_{i}'
            bot_instance = bot_manager.get_bot(bot_id)
            health_stats = bot_states["health_stats"].get(bot_id, {})
            reboot_settings = bot_states["reboot_settings"].get(bot_id, {})
            
            # Calculate next reboot time
            next_reboot_time = reboot_settings.get('next_reboot_time', 0)
            now = time.time()
            next_reboot_str = "Ready" if now >= next_reboot_time else formatTime(next_reboot_time - now)
            
            main_bots.append({
                'name': get_bot_name(bot_id),
                'reboot_id': bot_id,
                'is_active': bot_states["active"].get(bot_id, False),
                'consecutive_failures': health_stats.get('consecutive_failures', 0),
                'watermelon_enabled': bot_states["watermelon_grab"].get(bot_id, False),
                'reboot_enabled': reboot_settings.get('enabled', True),
                'next_reboot': next_reboot_str,
                'is_connected': check_bot_health(bot_instance, bot_id) if bot_instance else False
            })
        
        # Sub accounts
        for i in range(1, len(tokens) + 1):
            bot_id = f'sub_{i}'
            bot_instance = bot_manager.get_bot(bot_id)
            health_stats = bot_states["health_stats"].get(bot_id, {})
            reboot_settings = bot_states["reboot_settings"].get(bot_id, {}) # Note: Reboot logic primarily targets main bots for now
            
            next_reboot_time = reboot_settings.get('next_reboot_time', 0)
            now = time.time()
            next_reboot_str = "N/A" # Sub-bots don't have auto-reboot loop by default in this script
            
            sub_accounts.append({
                'name': get_bot_name(bot_id),
                'reboot_id': bot_id,
                'is_active': bot_states["active"].get(bot_id, False),
                'consecutive_failures': health_stats.get('consecutive_failures', 0),
                'reboot_enabled': False, # No reboot for sub-accounts in this logic
                'next_reboot': next_reboot_str,
                'is_connected': check_bot_health(bot_instance, bot_id) if bot_instance else False
            })
        
        # Clan drop status
        clan_drop_settings = bot_states["auto_clan_drop"]
        next_cycle_time = clan_drop_settings.get("last_cycle_start_time", 0) + clan_drop_settings.get("cycle_interval", 1800)
        clan_drop_countdown = max(0, next_cycle_time - time.time())
        
        clan_drop_status = {
            'enabled': clan_drop_settings.get('enabled', False),
            'countdown': clan_drop_countdown,
            'channel_id': clan_drop_settings.get('channel_id', ''),
            'ktb_channel_id': clan_drop_settings.get('ktb_channel_id', ''),
            'heart_thresholds': clan_drop_settings.get('heart_thresholds', {})
        }
        
        # Grab success logs
        grab_logs = bot_manager.get_grab_logs()
        
        return jsonify({
            'server_start_time': server_start_time,
            'bot_statuses': {
                'main_bots': main_bots,
                'sub_accounts': sub_accounts
            },
            'auto_clan_drop_status': clan_drop_status,
            'servers': servers,
            'grab_success_logs': grab_logs
        })
        
    except Exception as e:
        print(f"[Flask] ❌ Error in status endpoint: {e}", flush=True)
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

def formatTime(seconds):
    """Helper function to format time for frontend"""
    if seconds <= 0:
        return "00:00:00"
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"

# --- API ENDPOINTS FOR BOT CONTROL ---

@app.route('/api/toggle_bot_active', methods=['POST'])
def toggle_bot_active():
    try:
        data = request.get_json()
        bot_id = data.get('bot_id')
        
        if not bot_id:
            return jsonify({'status': 'error', 'message': 'Bot ID required'})
        
        current_state = bot_states["active"].get(bot_id, False)
        bot_states["active"][bot_id] = not current_state
        
        bot_name = get_bot_name(bot_id)
        new_state = "RISEN" if not current_state else "RESTING"
        
        return jsonify({
            'status': 'success', 
            'message': f'{bot_name} is now {new_state}',
            'reload': False
        })
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'Error toggling bot: {e}'})

@app.route('/api/toggle_reboot', methods=['POST'])
def toggle_reboot():
    try:
        data = request.get_json()
        bot_id = data.get('bot_id')
        
        if not bot_id:
            return jsonify({'status': 'error', 'message': 'Bot ID required'})
        
        reboot_settings = bot_states["reboot_settings"].setdefault(bot_id, {
            'enabled': True, 
            'delay': 3600, 
            'next_reboot_time': time.time() + 3600
        })
        
        current_state = reboot_settings.get('enabled', True)
        reboot_settings['enabled'] = not current_state
        
        bot_name = get_bot_name(bot_id)
        new_state = "ENABLED" if not current_state else "DISABLED"
        
        return jsonify({
            'status': 'success', 
            'message': f'Auto-reboot for {bot_name} is now {new_state}',
            'reload': False
        })
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'Error toggling reboot: {e}'})

@app.route('/api/force_reboot', methods=['POST'])
def force_reboot():
    try:
        data = request.get_json()
        bot_id = data.get('bot_id')
        
        if not bot_id:
            return jsonify({'status': 'error', 'message': 'Bot ID required'})
        
        bot_name = get_bot_name(bot_id)
        
        # Schedule immediate reboot
        bot_states["reboot_settings"].setdefault(bot_id, {})['next_reboot_time'] = time.time() - 1
        
        return jsonify({
            'status': 'success', 
            'message': f'Force reboot scheduled for {bot_name}',
            'reload': False
        })
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'Error forcing reboot: {e}'})

@app.route('/api/toggle_watermelon', methods=['POST'])
def toggle_watermelon():
    try:
        data = request.get_json()
        bot_id = data.get('bot_id')
        
        if not bot_id:
            return jsonify({'status': 'error', 'message': 'Bot ID required'})
        
        current_state = bot_states["watermelon_grab"].get(bot_id, False)
        bot_states["watermelon_grab"][bot_id] = not current_state
        
        bot_name = get_bot_name(bot_id)
        new_state = "ENABLED" if not current_state else "DISABLED"
        
        return jsonify({
            'status': 'success', 
            'message': f'Watermelon grab for {bot_name} is now {new_state}',
            'reload': False
        })
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'Error toggling watermelon: {e}'})

# --- API ENDPOINTS FOR CLAN DROP ---

@app.route('/api/toggle_clan_drop', methods=['POST'])
def toggle_clan_drop():
    try:
        current_state = bot_states["auto_clan_drop"].get('enabled', False)
        bot_states["auto_clan_drop"]['enabled'] = not current_state
        
        new_state = "ENABLED" if not current_state else "DISABLED"
        
        return jsonify({
            'status': 'success', 
            'message': f'Clan Auto Drop is now {new_state}',
            'reload': False
        })
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'Error toggling clan drop: {e}'})

@app.route('/api/save_clan_drop_settings', methods=['POST'])
def save_clan_drop_settings():
    try:
        data = request.get_json()
        
        clan_settings = bot_states["auto_clan_drop"]
        clan_settings['channel_id'] = data.get('channel_id', '').strip()
        clan_settings['ktb_channel_id'] = data.get('ktb_channel_id', '').strip()
        clan_settings['heart_thresholds'] = data.get('heart_thresholds', {})
        
        return jsonify({
            'status': 'success', 
            'message': 'Clan Drop settings saved successfully',
            'reload': False
        })
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'Error saving clan drop settings: {e}'})

# --- API ENDPOINTS FOR SERVER MANAGEMENT ---

@app.route('/api/add_server', methods=['POST'])
def add_server():
    try:
        data = request.get_json()
        server_name = data.get('name', '').strip()
        
        if not server_name:
            return jsonify({'status': 'error', 'message': 'Server name required'})
        
        new_server = {
            'id': str(uuid.uuid4()),
            'name': server_name,
            'main_channel_id': '',
            'ktb_channel_id': '',
            'spam_channel_id': '',
            'spam_message': '',
            'spam_delay': 10,
            'spam_enabled': False
        }
        
        # Add grab settings for each main bot
        for i in range(1, len(main_tokens) + 1):
            new_server[f'auto_grab_enabled_{i}'] = False
            new_server[f'heart_threshold_{i}'] = 50
        
        servers.append(new_server)
        
        return jsonify({
            'status': 'success', 
            'message': f'Server "{server_name}" added successfully',
            'reload': True # Reload to render new server panel correctly
        })
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'Error adding server: {e}'})

@app.route('/api/delete_server', methods=['POST'])
def delete_server():
    try:
        data = request.get_json()
        server_id = data.get('server_id')
        
        if not server_id:
            return jsonify({'status': 'error', 'message': 'Server ID required'})
        
        global servers
        server_name = next((s.get('name') for s in servers if s.get('id') == server_id), 'Unknown')
        servers = [s for s in servers if s.get('id') != server_id]
        
        return jsonify({
            'status': 'success', 
            'message': f'Server "{server_name}" deleted successfully',
            'reload': True # Reload to remove the panel
        })
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'Error deleting server: {e}'})

@app.route('/api/update_server_field', methods=['POST'])
def update_server_field():
    try:
        data = request.get_json()
        server_id = data.get('server_id')
        field = data.get('field')
        value = data.get('value')
        
        if not server_id or not field:
            return jsonify({'status': 'error', 'message': 'Server ID and field required'})
        
        server = next((s for s in servers if s.get('id') == server_id), None)
        if not server:
            return jsonify({'status': 'error', 'message': 'Server not found'})
        
        # Convert to correct type if necessary
        if field in ['spam_delay']:
             server[field] = int(value)
        else:
            server[field] = value

        return jsonify({
            'status': 'success', 
            'message': f'Updated {field}',
            'reload': False
        })
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'Error updating server field: {e}'})

@app.route('/api/toggle_harvest', methods=['POST'])
def toggle_harvest():
    try:
        data = request.get_json()
        server_id = data.get('server_id')
        bot_num = data.get('bot_num')
        
        if not server_id or bot_num is None:
            return jsonify({'status': 'error', 'message': 'Server ID and bot number required'})
        
        server = next((s for s in servers if s.get('id') == server_id), None)
        if not server:
            return jsonify({'status': 'error', 'message': 'Server not found'})
        
        field = f'auto_grab_enabled_{bot_num}'
        current_state = server.get(field, False)
        server[field] = not current_state
        
        bot_name = get_bot_name(f'main_{bot_num}')
        new_state = "ENABLED" if not current_state else "DISABLED"
        
        return jsonify({
            'status': 'success', 
            'message': f'Harvest for {bot_name} is now {new_state}',
            'reload': False
        })
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'Error toggling harvest: {e}'})

@app.route('/api/update_harvest_threshold', methods=['POST'])
def update_harvest_threshold():
    try:
        data = request.get_json()
        server_id = data.get('server_id')
        bot_num = data.get('bot_num')
        threshold = data.get('threshold', 50)
        
        if not server_id or bot_num is None:
            return jsonify({'status': 'error', 'message': 'Server ID and bot number required'})
        
        server = next((s for s in servers if s.get('id') == server_id), None)
        if not server:
            return jsonify({'status': 'error', 'message': 'Server not found'})
        
        field = f'heart_threshold_{bot_num}'
        server[field] = max(0, int(threshold))
        
        return jsonify({
            'status': 'success', 
            'message': f'Threshold updated to {threshold}',
            'reload': False
        })
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'Error updating threshold: {e}'})

@app.route('/api/toggle_broadcast', methods=['POST'])
def toggle_broadcast():
    try:
        data = request.get_json()
        server_id = data.get('server_id')
        
        if not server_id:
            return jsonify({'status': 'error', 'message': 'Server ID required'})
        
        server = next((s for s in servers if s.get('id') == server_id), None)
        if not server:
            return jsonify({'status': 'error', 'message': 'Server not found'})
        
        current_state = server.get('spam_enabled', False)
        server['spam_enabled'] = not current_state
        
        new_state = "ENABLED" if not current_state else "DISABLED"
        
        return jsonify({
            'status': 'success', 
            'message': f'Broadcast for {server.get("name", "server")} is now {new_state}',
            'reload': False
        })
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'Error toggling broadcast: {e}'})

@app.route('/api/save_settings', methods=['POST'])
def save_settings_api():
    try:
        save_settings()
        return jsonify({'status': 'success', 'message': 'Settings saved'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'Error saving settings: {e}'})

# --- KHỞI ĐỘNG HỆ THỐNG ---
def initialize_bots():
    """Initialize all bots and start background processes"""
    print("[System] 🚀 Initializing Shadow Network...", flush=True)
    
    # Load settings trước
    load_settings()
    
    # Initialize main bots
    for i, token in enumerate(main_tokens, 1):
        if token.strip():
            try:
                bot = create_bot(token.strip(), i, is_main=True)
                if bot:
                    bot_id = f'main_{i}'
                    bot_manager.add_bot(bot_id, bot)
                    
                    # Initialize states
                    bot_states["active"].setdefault(bot_id, False)
                    bot_states["watermelon_grab"].setdefault(bot_id, False)
                    bot_states["reboot_settings"].setdefault(bot_id, {
                        'enabled': True,
                        'delay': 3600,
                        'next_reboot_time': time.time() + 3600,
                        'failure_count': 0
                    })
            except Exception as e:
                print(f"[System] ❌ Failed to initialize main bot {i}: {e}", flush=True)
    
    # Initialize sub bots
    for i, token in enumerate(tokens, 1):
        if token.strip():
            try:
                bot = create_bot(token.strip(), i, is_main=False)
                if bot:
                    bot_id = f'sub_{i}'
                    bot_manager.add_bot(bot_id, bot)
                    
                    # Initialize states
                    bot_states["active"].setdefault(bot_id, False)
                    bot_states["reboot_settings"].setdefault(bot_id, {
                        'enabled': False, # Disabled for sub bots by default
                        'delay': 3600,
                        'next_reboot_time': time.time() + 3600,
                        'failure_count': 0
                    })
            except Exception as e:
                print(f"[System] ❌ Failed to initialize sub bot {i}: {e}", flush=True)
    
    # Start background threads
    threads = [
        threading.Thread(target=auto_reboot_loop, daemon=True),
        threading.Thread(target=auto_clan_drop_loop, daemon=True),
        threading.Thread(target=spam_loop_manager, daemon=True),
        threading.Thread(target=periodic_task, args=(300, save_settings, "Auto Save"), daemon=True),
        threading.Thread(target=periodic_task, args=(60, health_monitoring_check, "Health Monitor"), daemon=True)
    ]
    
    for thread in threads:
        thread.start()
    
    print("[System] ✅ Shadow Network initialized successfully!", flush=True)
    print(f"[System] 📊 Main bots: {len([b for b in bot_manager.get_main_bots_info()])} | Sub accounts: {len([b for b in bot_manager.get_sub_bots_info()])}", flush=True)

if __name__ == "__main__":
    try:
        initialize_bots()
        
        # Start Flask app
        port = int(os.getenv("PORT", 10000))
        print(f"[Flask] 🌐 Starting web interface on port {port}...", flush=True)
        app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
        
    except KeyboardInterrupt:
        print("\n[System] 🛑 Shutting down Shadow Network...", flush=True)
        stop_events["reboot"].set()
        stop_events["clan_drop"].set()
        
        # Cleanup all bots
        for bot_id, bot in bot_manager.get_all_bots():
            try:
                bot_manager.remove_bot(bot_id)
            except Exception as e:
                print(f"[System] ⚠️ Error during cleanup of {bot_id}: {e}", flush=True)
        
        save_settings()
        print("[System] 💤 Shadow Network terminated.", flush=True)
        
    except Exception as e:
        print(f"[System] ❌ Critical error: {e}", flush=True)
        traceback.print_exc()
