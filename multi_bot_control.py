# PHIÊN BẢN CẢI TIẾN - HỖ TRỢ N TÀI KHOẢN CHÍNH - SPAM SONG SONG - TÍCH HỢP DROP CLAN - REBOOT AN TOÀN - SỬA LỖI NHẶT DƯA
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
acc_names = [f"Bot-{i:02d}" for i in range(1, 21)] # Tên bot phụ tự động

# --- BIẾN TRẠNG THÁI & KHÓA ---
bots, main_bots, servers = [], [], []
bot_states = {
    "reboot_settings": {}, "active": {}, "watermelon_grab": {}, "health_stats": {},
    "auto_clan_drop": {"enabled": False, "channel_id": "", "ktb_channel_id": "", "last_cycle_start_time": 0, "cycle_interval": 1800, "bot_delay": 140, "heart_thresholds": {}}
}
stop_events = {"reboot": threading.Event(), "clan_drop": threading.Event()}
bots_lock = threading.Lock()
server_start_time = time.time()

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
            return BOT_NAMES[b_index - 1] if b_index -1 < len(BOT_NAMES) else f"MAIN_{b_index}"
        return acc_names[b_index] if b_index < len(acc_names) else f"SUB_{b_index+1}"
    except:
        return bot_id_str.upper()

# --- LOGIC GRAB CARD (TÁI SỬ DỤNG) ---
def _find_and_select_card(bot, channel_id, last_drop_msg_id, heart_threshold, bot_num, ktb_channel_id):
    """Hàm chung để tìm và chọn card dựa trên số heart."""
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
                        
                        print(f"[CARD GRAB | Bot {bot_num}] Chọn dòng {max_index+1} với {max_num}♡ -> {emoji} sau {delay}s", flush=True)
                        
                        def grab_action():
                            try:
                                bot.addReaction(channel_id, last_drop_msg_id, emoji)
                                time.sleep(1.2)
                                if ktb_channel_id: bot.sendMessage(ktb_channel_id, "kt b")
                                print(f"[CARD GRAB | Bot {bot_num}] ✅ Đã grab và gửi kt b", flush=True)
                            except Exception as e:
                                print(f"[CARD GRAB | Bot {bot_num}] ❌ Lỗi grab: {e}", flush=True)

                        threading.Timer(delay, grab_action).start()
                        return True # Thoát khỏi hàm
            return False # Không tìm thấy
        except Exception as e:
            print(f"[CARD GRAB | Bot {bot_num}] ❌ Lỗi đọc messages: {e}", flush=True)
    return False

# --- LOGIC BOT (CẬP NHẬT) ---
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
        # --- Chạy song song cả hai logic ---

        # 1. Luồng nhặt thẻ (Card Grab Logic)
        if auto_grab_enabled and target_server.get('ktb_channel_id'):
            threshold = target_server.get(f'heart_threshold_{bot_num}', 50)
            # Chạy việc tìm thẻ trong một luồng riêng để không chặn việc nhặt dưa
            threading.Thread(target=_find_and_select_card, args=(bot, channel_id, last_drop_msg_id, threshold, bot_num, target_server.get('ktb_channel_id')), daemon=True).start()

        # 2. Luồng nhặt dưa hấu (Watermelon Grab Logic) - Áp dụng phương pháp của tool cũ
        if watermelon_grab_enabled:
            
            def check_for_watermelon_patiently():
                print(f"[WATERMELON | Bot {bot_num}] 🍉 Bắt đầu canh dưa (chờ 5 giây)...", flush=True)
                # Chờ 5 giây cho các bot khác phản ứng
                time.sleep(5) 
                
                try:
                    # Lấy lại thông tin tin nhắn MỚI NHẤT sau khi chờ
                    target_message = bot.getMessage(channel_id, last_drop_msg_id).json()[0]
                    reactions = target_message.get('reactions', [])
                    
                    for reaction in reactions:
                        emoji_name = reaction.get('emoji', {}).get('name', '')
                        if '🍉' in emoji_name or 'watermelon' in emoji_name.lower() or 'dua' in emoji_name.lower():
                            print(f"[WATERMELON | Bot {bot_num}] 🎯 PHÁT HIỆN DỰA HẤU!", flush=True)
                            try:
                                # Thử nhặt
                                bot.addReaction(channel_id, last_drop_msg_id, "🍉")
                                print(f"[WATERMELON | Bot {bot_num}] ✅ NHẶT DỰA THÀNH CÔNG!", flush=True)
                                return # Nhặt xong thì kết thúc
                            except Exception as e:
                                print(f"[WATERMELON | Bot {bot_num}] ❌ Lỗi react khi đã thấy dưa: {e}", flush=True)
                            return
                            
                    # Nếu chạy hết vòng lặp mà không thấy, tức là không có dưa
                    print(f"[WATERMELON | Bot {bot_num}] 😞 Không tìm thấy dưa hấu sau khi chờ.", flush=True)

                except Exception as e:
                    print(f"[WATERMELON | Bot {bot_num}] ❌ Lỗi khi lấy tin nhắn để check dưa: {e}", flush=True)

            # Chạy luồng canh dưa
            threading.Thread(target=check_for_watermelon_patiently, daemon=True).start()

    threading.Thread(target=grab_logic_thread, daemon=True).start()

# --- HỆ THỐNG REBOOT & HEALTH CHECK (REVISED) ---
def check_bot_health(bot, bot_id):
    stats = bot_states["health_stats"].setdefault(bot_id, {'consecutive_failures': 0})
    
    # Kiểm tra bot có tồn tại không
    if not bot:
        stats['consecutive_failures'] += 1
        print(f"[Health Check] ❌ Bot {bot_id} is None", flush=True)
        return False
    
    try:
        # Kiểm tra gateway có tồn tại không
        if not hasattr(bot, 'gateway') or not bot.gateway:
            stats['consecutive_failures'] += 1
            print(f"[Health Check] ❌ Bot {bot_id} gateway is None", flush=True)
            return False
        
        # Kiểm tra trạng thái kết nối
        is_connected = hasattr(bot.gateway, 'connected') and bot.gateway.connected
        
        if is_connected:
            stats['consecutive_failures'] = 0
            # print(f"[Health Check] ✅ Bot {bot_id} healthy", flush=True) # Optional: can be too spammy
        else:
            stats['consecutive_failures'] += 1
            print(f"[Health Check] ⚠️ Bot {bot_id} gateway not connected (failures: {stats['consecutive_failures']})", flush=True)
        
        return is_connected
        
    except Exception as e:
        stats['consecutive_failures'] += 1
        print(f"[Health Check] ❌ Error checking bot {bot_id}: {e}", flush=True)
        return False

def safe_reboot_bot(bot_id):
    print(f"[Safe Reboot] 🔄 Bắt đầu reboot bot {bot_id}...", flush=True)
    
    try:
        # Parse bot ID
        parts = bot_id.split('_')
        if len(parts) != 2 or parts[0] != 'main':
            raise ValueError(f"Invalid bot_id format: {bot_id}")
        
        bot_index = int(parts[1]) - 1
        if bot_index < 0 or bot_index >= len(main_tokens):
            raise ValueError(f"Bot index out of range: {bot_index}")
            
        token = main_tokens[bot_index].strip()
        if not token:
            raise ValueError(f"Empty token for bot {bot_id}")
            
        bot_name = get_bot_name(bot_id)
        
        # Kiểm tra bot hiện tại có cần reboot không
        current_bot = main_bots[bot_index] if bot_index < len(main_bots) else None
        if current_bot and check_bot_health(current_bot, bot_id):
            print(f"[Safe Reboot] ✅ Bot {bot_name} khỏe mạnh, hoãn reboot", flush=True)
            # Reset failure count nếu bot khỏe mạnh
            bot_states["reboot_settings"][bot_id]['failure_count'] = 0
            return True

        # Cleanup bot cũ
        print(f"[Safe Reboot] 🧹 Cleaning up old bot {bot_name}...", flush=True)
        if current_bot:
            try:
                if hasattr(current_bot, 'gateway') and current_bot.gateway:
                    current_bot.gateway.close()
                print(f"[Safe Reboot] ✅ Old gateway closed for {bot_name}", flush=True)
            except Exception as e:
                print(f"[Safe Reboot] ⚠️ Error closing old gateway for {bot_name}: {e}", flush=True)
        
        # Set bot về None trước khi tạo mới
        with bots_lock:
            main_bots[bot_index] = None

        # Tính toán thời gian chờ với backoff
        settings = bot_states["reboot_settings"].get(bot_id, {})
        failure_count = settings.get('failure_count', 0)
        base_wait = 20
        backoff_wait = min(failure_count * 10, 60)  # Tối đa 60s backoff
        wait_time = random.uniform(base_wait, base_wait + 20) + backoff_wait
        
        print(f"[Safe Reboot] ⏳ Chờ {wait_time:.1f}s trước khi tạo bot mới...", flush=True)
        time.sleep(wait_time)

        # Tạo bot mới
        print(f"[Safe Reboot] 🛠️ Creating new bot instance for {bot_name}...", flush=True)
        new_bot = create_bot(token, bot_identifier=(bot_index + 1), is_main=True)
        
        if not new_bot:
            raise Exception("create_bot returned None")

        # Đợi bot khởi tạo xong
        time.sleep(3)
        
        # Kiểm tra bot mới có hoạt động không
        if not check_bot_health(new_bot, bot_id):
            print(f"[Safe Reboot] ⚠️ New bot {bot_name} health check failed, will be handled by next health cycle", flush=True)
            # Vẫn keep bot mới và để health check tự xử lý
        
        # Cập nhật bot mới vào danh sách
        with bots_lock:
            main_bots[bot_index] = new_bot
        
        # Cập nhật settings thành công
        current_time = time.time()
        settings.update({
            'next_reboot_time': current_time + settings.get('delay', 3600),
            'failure_count': 0,
            'last_reboot_time': current_time
        })
        bot_states["health_stats"][bot_id]['consecutive_failures'] = 0
        
        print(f"[Safe Reboot] ✅ Reboot thành công {bot_name}", flush=True)
        return True
        
    except Exception as e:
        print(f"[Safe Reboot] ❌ Reboot thất bại cho {bot_id}: {e}", flush=True)
        print(f"[Safe Reboot] 📊 Traceback: {traceback.format_exc()}", flush=True)
        handle_reboot_failure(bot_id)
        return False

def handle_reboot_failure(bot_id):
    settings = bot_states["reboot_settings"].setdefault(bot_id, {
        'delay': 3600, 
        'enabled': True, 
        'failure_count': 0,
        'next_reboot_time': 0
    })
    
    failure_count = settings.get('failure_count', 0) + 1
    settings['failure_count'] = failure_count
    
    # Exponential backoff với cap
    base_delay = max(settings.get('delay', 3600), 300)  # Tối thiểu 5 phút
    backoff_multiplier = min(2 ** (failure_count - 1), 8)  # Tối đa x8
    backoff_delay = base_delay * backoff_multiplier
    
    # Cap tối đa 2 giờ
    backoff_delay = min(backoff_delay, 7200)
    
    settings['next_reboot_time'] = time.time() + backoff_delay
    
    print(f"[Safe Reboot] 🔴 Failure #{failure_count} cho {bot_id}. Thử lại sau {backoff_delay//60}m {backoff_delay%60:.0f}s.", flush=True)
    
    # Disable sau 5 lần thất bại liên tiếp
    if failure_count >= 5:
        settings['enabled'] = False
        print(f"[Safe Reboot] ❌ Tắt auto-reboot cho {bot_id} sau 5 lần thất bại.", flush=True)

# --- VÒNG LẶP NỀN (REVISED) ---
def auto_reboot_loop():
    print("[Safe Reboot] 🚀 Khởi động luồng tự động reboot.", flush=True)
    last_reboot_time = 0
    
    while not stop_events["reboot"].is_set():
        try:
            now = time.time()
            
            # Rate limiting: tối thiểu 5 phút giữa các lần reboot
            if now - last_reboot_time < 300:
                stop_events["reboot"].wait(30)
                continue

            bot_to_reboot = None
            earliest_time = float('inf')
            
            # Tìm bot cần reboot sớm nhất
            for bot_id, settings in list(bot_states["reboot_settings"].items()):
                if not settings.get('enabled', False):
                    continue
                    
                next_reboot_time = settings.get('next_reboot_time', 0)
                if now >= next_reboot_time and next_reboot_time < earliest_time:
                    bot_to_reboot = bot_id
                    earliest_time = next_reboot_time
            
            if bot_to_reboot:
                print(f"[Safe Reboot] 🎯 Chọn reboot bot: {bot_to_reboot}", flush=True)
                
                if safe_reboot_bot(bot_to_reboot):
                    last_reboot_time = now
                    # Chờ random từ 5-10 phút trước reboot tiếp theo
                    wait_time = random.uniform(300, 600)
                    print(f"[Safe Reboot] ⏳ Chờ {wait_time//60:.0f}m {wait_time%60:.0f}s trước reboot tiếp theo.", flush=True)
                    stop_events["reboot"].wait(wait_time)
                else:
                    # Nếu reboot thất bại, chờ 2 phút rồi thử bot khác
                    print(f"[Safe Reboot] ⚠️ Reboot failed, waiting 2m before next attempt", flush=True)
                    stop_events["reboot"].wait(120)
            else:
                # Không có bot nào cần reboot, chờ 1 phút
                stop_events["reboot"].wait(60)
                
        except Exception as e:
            print(f"[Safe Reboot] ❌ Error in auto_reboot_loop: {e}", flush=True)
            print(f"[Safe Reboot] 📊 Traceback: {traceback.format_exc()}", flush=True)
            stop_events["reboot"].wait(60)
    
    print("[Safe Reboot] 🛑 Luồng tự động reboot đã dừng.", flush=True)

def run_clan_drop_cycle():
    print("[Clan Drop] 🚀 Bắt đầu chu kỳ drop clan.", flush=True)
    settings = bot_states["auto_clan_drop"]
    channel_id = settings.get("channel_id")
    
    with bots_lock:
        active_bots = [(bot, i + 1) for i, bot in enumerate(main_bots) if bot and bot_states["active"].get(f'main_{i+1}', False)]

    if not active_bots:
        print("[Clan Drop] ⚠️ Không có bot chính nào hoạt động.", flush=True)
        return

    for bot, bot_num in active_bots:
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
            with bots_lock:
                bots_to_spam = [b for i, b in enumerate(main_bots) if b and bot_states["active"].get(f'main_{i+1}')] + \
                               [b for i, b in enumerate(bots) if b and bot_states["active"].get(f'sub_{i}')]
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
            # Dọn dẹp thread cũ
            for server_id in list(active_threads.keys()):
                if server_id not in current_ids:
                    print(f"[Spam] 🛑 Dừng luồng cho server đã xóa: {server_id}", flush=True)
                    active_threads.pop(server_id)[1].set()
            # Quản lý thread mới/hiện tại
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
    with bots_lock:
        all_bots = [(f"main_{i+1}", bot) for i, bot in enumerate(main_bots) if bot is not None] + \
                   [(f"sub_{i}", bot) for i, bot in enumerate(bots) if bot is not None]
    
    # Check bots that are supposed to be active but the object is missing
    all_bot_ids = {bot_id for bot_id, bot in all_bots}
    for bot_id in bot_states["health_stats"]:
         if bot_id not in all_bot_ids:
             check_bot_health(None, bot_id)

    # Check existing bot objects
    for bot_id, bot in all_bots:
        check_bot_health(bot, bot_id)

# --- KHỞI TẠO BOT (REVISED) ---
def create_bot(token, bot_identifier, is_main=False):
    bot_id_str = f"main_{bot_identifier}" if is_main else f"sub_{bot_identifier}"
    bot_name = get_bot_name(bot_id_str)
    
    try:
        print(f"[Bot] 🔨 Creating bot instance for {bot_name}...", flush=True)
        
        if not token or not token.strip():
            raise ValueError(f"Empty or invalid token for {bot_name}")
        
        bot = discum.Client(token=token.strip(), log=False)
        
        # Track connection status
        connection_ready = {'ready': False, 'error': None}
        
        @bot.gateway.command
        def on_ready(resp):
            try:
                if resp.event.ready:
                    user = resp.raw.get("user", {})
                    user_id = user.get('id', 'Unknown')
                    username = user.get('username', 'Unknown')
                    print(f"[Bot] ✅ Bot connected: {user_id} ({username}) - {bot_name}", flush=True)
                    
                    # Initialize health stats
                    bot_states["health_stats"].setdefault(bot_id_str, {}).update({
                        'created_time': time.time(),
                        'consecutive_failures': 0,
                        'user_id': user_id,
                        'username': username
                    })
                    
                    connection_ready['ready'] = True
            except Exception as e:
                print(f"[Bot] ❌ Error in on_ready for {bot_name}: {e}", flush=True)
                connection_ready['error'] = str(e)
        
        @bot.gateway.command 
        def on_error(resp):
            if resp.event.error:
                error_msg = resp.parsed.auto()
                print(f"[Bot] ⚠️ Gateway error for {bot_name}: {error_msg}", flush=True)
                connection_ready['error'] = str(error_msg)
        
        # Setup message handler for main bots
        if is_main:
            @bot.gateway.command
            def on_message(resp):
                try:
                    if resp.event.message:
                        msg = resp.parsed.auto()
                        author_id = msg.get("author", {}).get("id")
                        content = msg.get("content", "").lower()
                        
                        if author_id == karuta_id and "dropping" in content:
                            # Determine handler based on mentions
                            handler = handle_clan_drop if msg.get("mentions") else handle_grab
                            threading.Thread(
                                target=handler, 
                                args=(bot, msg, bot_identifier),
                                daemon=True
                            ).start()
                            
                except Exception as e:
                    print(f"[Bot] ❌ Error in message handler for {bot_name}: {e}", flush=True)

        # Start gateway in thread
        print(f"[Bot] 🚀 Starting gateway for {bot_name}...", flush=True)
        gateway_thread = threading.Thread(target=bot.gateway.run, daemon=True)
        gateway_thread.start()
        
        # Wait for connection with timeout
        timeout_seconds = 30
        start_time = time.time()
        
        while time.time() - start_time < timeout_seconds:
            if connection_ready['ready']:
                print(f"[Bot] ✅ Bot {bot_name} successfully initialized", flush=True)
                return bot
            elif connection_ready['error']:
                raise Exception(f"Gateway error: {connection_ready['error']}")
            time.sleep(0.5)
        
        # Timeout reached
        print(f"[Bot] ⚠️ Bot {bot_name} initialization timeout, but keeping instance for health checks", flush=True)
        return bot  # Return bot even if not fully ready, let health check handle it
        
    except Exception as e:
        print(f"[Bot] ❌ Failed to create bot {bot_name}: {e}", flush=True)
        print(f"[Bot] 📊 Traceback: {traceback.format_exc()}", flush=True)
        return None

# --- FLASK APP ---
app = Flask(__name__)
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Shadow Network Control - Enhanced</title>
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
        .status-panel, .global-settings-panel, .clan-drop-panel { grid-column: 1 / -1; }
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
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1 class="title">Shadow Network Control</h1>
            <div class="subtitle">Enhanced Safe Reboot System</div>
        </div>
        <div id="msg-status-container" class="msg-status"> <span id="msg-status-text"></span></div>
        <div class="main-grid">
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
                         <div>⏱️ Min Reboot Interval: 5 minutes | Max Failures: 5 attempts</div>
                         <div>🎯 Reboot Strategy: One-at-a-time with 20-40s cleanup delay + backoff</div>
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
                            <button type="button" id="clan-drop-toggle-btn" class="btn btn-small">{{ 'DISABLE' if auto_clan_drop.enabled else 'ENABLE' }}</button>
                        </div>
                    </div>
                </div>
                <div class="server-sub-panel">
                    <h3><i class="fas fa-cogs"></i> Configuration</h3>
                    <div class="input-group"><label>Drop Channel ID</label><input type="text" id="clan-drop-channel-id" value="{{ auto_clan_drop.channel_id or '' }}"></div>
                    <div class="input-group"><label>KTB Channel ID</label><input type="text" id="clan-drop-ktb-channel-id" value="{{ auto_clan_drop.ktb_channel_id or '' }}"></div>
                </div>
                <div class="server-sub-panel">
                    <h3><i class="fas fa-crosshairs"></i> Soul Harvest (Clan Drop)</h3>
                    {% for bot in main_bots_info %}
                    <div class="grab-section">
                        <h3>{{ bot.name }}</h3>
                        <div class="input-group">
                            <input type="number" class="clan-drop-threshold" data-node="main_{{ bot.id }}" value="{{ auto_clan_drop.heart_thresholds[('main_' + bot.id|string)]|default(50) }}" min="0">
                        </div>
                    </div>
                    {% endfor %}
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

            {% for server in servers %}
            <div class="panel server-panel" data-server-id="{{ server.id }}">
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
                    {% for bot in main_bots_info %}
                    <div class="grab-section">
                        <h3>{{ bot.name }}</h3>
                        <div class="input-group">
                            <input type="number" class="harvest-threshold" data-node="{{ bot.id }}" value="{{ server['heart_threshold_' + bot.id|string] or 50 }}" min="0">
                            <button type="button" class="btn harvest-toggle" data-node="{{ bot.id }}">
                                {{ 'DISABLE' if server['auto_grab_enabled_' + bot.id|string] else 'ENABLE' }}
                            </button>
                        </div>
                    </div>
                    {% endfor %}
                </div>
                <div class="server-sub-panel">
                    <h3><i class="fas fa-paper-plane"></i> Auto Broadcast</h3>
                    <div class="input-group"><label>Message</label><textarea class="spam-message" rows="2">{{ server.spam_message or '' }}</textarea></div>
                    <div class="input-group">
                         <label>Delay (s)</label>
                         <input type="number" class="spam-delay" value="{{ server.spam_delay or 10 }}">
                         <span class="timer-display spam-timer">--:--:--</span>
                    </div>
                    <button type="button" class="btn broadcast-toggle">{{ 'DISABLE' if server.spam_enabled else 'ENABLE' }}</button>
                </div>
            </div>
            {% endfor %}

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
                const response = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) });
                const result = await response.json();
                showStatusMessage(result.message, result.status !== 'success' ? 'error' : 'success');
                if (result.status === 'success' && url !== '/api/save_settings') {
                    fetch('/api/save_settings', { method: 'POST' });
                    if (result.reload) { setTimeout(() => window.location.reload(), 500); }
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

        async function fetchStatus() {
            try {
                const response = await fetch('/status');
                const data = await response.json();

                const serverUptimeSeconds = (Date.now() / 1000) - data.server_start_time;
                updateElement(document.getElementById('uptime-timer'), { textContent: formatTime(serverUptimeSeconds) });

                if (data.auto_clan_drop_status) {
                    updateElement(document.getElementById('clan-drop-timer'), { textContent: formatTime(data.auto_clan_drop_status.countdown) });
                    updateElement(document.getElementById('clan-drop-toggle-btn'), { textContent: data.auto_clan_drop_status.enabled ? 'DISABLE' : 'ENABLE' });
                }

                const botControlGrid = document.getElementById('bot-control-grid');
                const allBots = [...data.bot_statuses.main_bots, ...data.bot_statuses.sub_accounts];

                allBots.forEach(bot => {
                    const botId = bot.reboot_id;
                    let itemContainer = document.getElementById(`bot-container-${botId}`);

                    if (!itemContainer) {
                        itemContainer = document.createElement('div');
                        itemContainer.id = `bot-container-${botId}`;
                        itemContainer.className = 'status-row';
                        itemContainer.style.cssText = 'flex-direction: column; align-items: stretch; padding: 10px;';

                        let healthClass = 'health-good';
                        if (bot.health_status === 'warning') healthClass = 'health-warning';
                        else if (bot.health_status === 'bad') healthClass = 'health-bad';

                        let controlHtml = `
                            <div style="display: flex; justify-content: space-between; align-items: center; width: 100%;">
                               <span style="font-weight: bold; ${bot.type === 'main' ? 'color: #FF4500;' : ''}">${bot.name}<span class="health-indicator ${healthClass}"></span></span>
                               <button type="button" id="toggle-state-${botId}" data-target="${botId}" class="btn-toggle-state ${bot.is_active ? 'btn-rise' : 'btn-rest'}">
                                   ${bot.is_active ? 'ONLINE' : 'OFFLINE'}
                               </button>
                            </div>`;

                        if (bot.type === 'main') {
                            const r_settings = data.bot_reboot_settings[botId] || { delay: 3600, enabled: false, failure_count: 0 };
                            const statusClass = r_settings.failure_count > 0 ? 'btn-warning' : (r_settings.enabled ? 'btn-rise' : 'btn-rest');
                            const statusText = r_settings.failure_count > 0 ? `FAIL(${r_settings.failure_count})` : (r_settings.enabled ? 'AUTO' : 'MANUAL');

                            controlHtml += `
                            <div class="input-group" style="margin-top: 10px; margin-bottom: 0;">
                                 <input type="number" class="bot-reboot-delay" value="${r_settings.delay}" data-bot-id="${botId}" style="width: 80px; text-align: right; flex-grow: 0;">
                                 <span id="timer-${botId}" class="timer-display bot-reboot-timer" style="padding: 0 10px;">--:--:--</span>
                                 <button type="button" id="toggle-reboot-${botId}" class="btn btn-small bot-reboot-toggle ${statusClass}" data-bot-id="${botId}">
                                     ${statusText}
                                 </button>
                                 <button type="button" class="btn btn-small bot-force-reboot" data-bot-id="${botId}" title="Force immediate reboot" style="background-color: var(--warning-orange); color: #000; flex-grow: 0; padding: 5px 8px; border-color: var(--warning-orange);">
                                    <i class="fas fa-sync-alt"></i>
                                 </button>
                            </div>`;
                        }
                        itemContainer.innerHTML = controlHtml;
                        botControlGrid.appendChild(itemContainer);
                    }
                    else {
                        const stateButton = document.getElementById(`toggle-state-${botId}`);
                        if (stateButton) {
                            stateButton.textContent = bot.is_active ? 'ONLINE' : 'OFFLINE';
                            stateButton.className = `btn-toggle-state ${bot.is_active ? 'btn-rise' : 'btn-rest'}`;
                        }

                        const healthIndicator = itemContainer.querySelector('.health-indicator');
                        if (healthIndicator) {
                            let healthClass = 'health-good';
                            if (bot.health_status === 'warning') healthClass = 'health-warning';
                            else if (bot.health_status === 'bad') healthClass = 'health-bad';
                            healthIndicator.className = `health-indicator ${healthClass}`;
                        }

                        if (bot.type === 'main') {
                            const r_settings = data.bot_reboot_settings[botId];
                            if (r_settings) {
                                const timerDisplay = document.getElementById(`timer-${botId}`);
                                const rebootButton = document.getElementById(`toggle-reboot-${botId}`);
                                if (timerDisplay) timerDisplay.textContent = formatTime(r_settings.countdown);
                                if (rebootButton) {
                                    const statusClass = r_settings.failure_count > 0 ? 'btn btn-small bot-reboot-toggle btn-warning' :
                                                       (r_settings.enabled ? 'btn btn-small bot-reboot-toggle btn-rise' : 'btn btn-small bot-reboot-toggle btn-rest');
                                    const statusText = r_settings.failure_count > 0 ? `FAIL(${r_settings.failure_count})` :
                                                      (r_settings.enabled ? 'AUTO' : 'MANUAL');
                                    rebootButton.className = statusClass;
                                    rebootButton.textContent = statusText;
                                }
                            }
                        }
                    }
                });

                const wmGrid = document.getElementById('global-watermelon-grid');
                wmGrid.innerHTML = '';
                if (data.watermelon_grab_states && data.bot_statuses) {
                    data.bot_statuses.main_bots.forEach(bot => {
                        const botNodeId = bot.reboot_id;
                        const isEnabled = data.watermelon_grab_states[botNodeId];
                        const item = document.createElement('div');
                        item.className = 'bot-status-item';
                        item.innerHTML = `<span>${bot.name}</span>
                            <button type="button" class="btn btn-small watermelon-toggle" data-node="${botNodeId}">
                                <i class="fas fa-seedling"></i>&nbsp;${isEnabled ? 'DISABLE' : 'ENABLE'}
                            </button>`;
                        wmGrid.appendChild(item);
                    });
                }

                data.servers.forEach(serverData => {
                    const serverPanel = document.querySelector(`.server-panel[data-server-id="${serverData.id}"]`);
                    if (!serverPanel) return;
                    serverPanel.querySelectorAll('.harvest-toggle').forEach(btn => {
                        const node = btn.dataset.node;
                        updateElement(btn, { textContent: serverData[`auto_grab_enabled_${node}`] ? 'DISABLE' : 'ENABLE' });
                    });
                    const spamToggleBtn = serverPanel.querySelector('.broadcast-toggle');
                    updateElement(spamToggleBtn, { textContent: serverData.spam_enabled ? 'DISABLE' : 'ENABLE' });
                    const spamTimer = serverPanel.querySelector('.spam-timer');
                    updateElement(spamTimer, { textContent: formatTime(serverData.spam_countdown)});
                });

            } catch (error) { console.error('Error fetching status:', error); }
        }

        setInterval(fetchStatus, 1000);

        document.querySelector('.container').addEventListener('click', e => {
            const button = e.target.closest('button');
            if (!button) return;
            const serverPanel = button.closest('.server-panel');
            const serverId = serverPanel ? serverPanel.dataset.serverId : null;

            const actions = {
                'bot-reboot-toggle': () => postData('/api/bot_reboot_toggle', { bot_id: button.dataset.botId, delay: document.querySelector(`.bot-reboot-delay[data-bot-id="${button.dataset.botId}"]`).value }),
                'bot-force-reboot': () => confirm(`Are you sure you want to force reboot bot ${button.dataset.botId}? This resets failure counts.`) && postData('/api/force_reboot_bot', { bot_id: button.dataset.botId }),
                'btn-toggle-state': () => postData('/api/toggle_bot_state', { target: button.dataset.target }),
                'clan-drop-toggle-btn': () => postData('/api/clan_drop_toggle'),
                'clan-drop-save-btn': () => {
                    const thresholds = {};
                    document.querySelectorAll('.clan-drop-threshold').forEach(i => { thresholds[i.dataset.node] = parseInt(i.value, 10); });
                    postData('/api/clan_drop_update', { channel_id: document.getElementById('clan-drop-channel-id').value, ktb_channel_id: document.getElementById('clan-drop-ktb-channel-id').value, heart_thresholds: thresholds });
                },
                'watermelon-toggle': () => postData('/api/watermelon_toggle', { node: button.dataset.node }),
                'harvest-toggle': () => serverId && postData('/api/harvest_toggle', { server_id: serverId, node: button.dataset.node, threshold: serverPanel.querySelector(`.harvest-threshold[data-node="${button.dataset.node}"]`).value }),
                'broadcast-toggle': () => serverId && postData('/api/broadcast_toggle', { server_id: serverId, message: serverPanel.querySelector('.spam-message').value, delay: serverPanel.querySelector('.spam-delay').value }),
                'btn-delete-server': () => serverId && confirm('Are you sure?') && postData('/api/delete_server', { server_id: serverId })
            };

            for (const cls in actions) {
                if (button.classList.contains(cls) || button.id === cls) {
                    actions[cls]();
                    return;
                }
            }
        });

        document.querySelector('.main-grid').addEventListener('change', e => {
            const target = e.target;
            const serverPanel = target.closest('.server-panel');
            if (serverPanel && target.classList.contains('channel-input')) {
                const payload = { server_id: serverPanel.dataset.serverId };
                payload[target.dataset.field] = target.value;
                postData('/api/update_server_channels', payload);
            }
        });

        document.getElementById('add-server-btn').addEventListener('click', () => {
            const name = prompt("Enter a name for the new server:", "New Server");
            if (name) { postData('/api/add_server', { name: name }); }
        });
    });
</script>
</body>
</html>
"""

# --- FLASK ROUTES ---
@app.route("/")
def index():
    main_bots_info = [{"id": i + 1, "name": get_bot_name(f"main_{i+1}")} for i in range(len(main_tokens))]
    # Sort servers by name for consistent ordering
    sorted_servers = sorted(servers, key=lambda s: s.get('name', ''))
    return render_template_string(HTML_TEMPLATE, servers=sorted_servers, main_bots_info=main_bots_info, auto_clan_drop=bot_states["auto_clan_drop"])

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
    for i in range(len(main_tokens)):
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
    server, node = find_server(data.get('server_id')), data.get('node')
    if not server or not node: return jsonify({'status': 'error', 'message': 'Yêu cầu không hợp lệ.'}), 400
    grab_key, threshold_key = f'auto_grab_enabled_{node}', f'heart_threshold_{node}'
    server[grab_key] = not server.get(grab_key, False)
    server[threshold_key] = int(data.get('threshold', 50))
    status_msg = 'ENABLED' if server[grab_key] else 'DISABLED'
    return jsonify({'status': 'success', 'message': f"🎯 Card Grab cho {get_bot_name(f'main_{node}')} đã {status_msg}."})

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
    settings = bot_states["reboot_settings"].get(bot_id)
    if not settings: return jsonify({'status': 'error', 'message': '❌ Invalid Bot ID.'}), 400
    settings.update({'enabled': not settings.get('enabled', False), 'delay': delay, 'failure_count': 0})
    if settings['enabled']:
        settings['next_reboot_time'] = time.time() + delay
        msg = f"🔄 Safe Auto-Reboot ENABLED cho {get_bot_name(bot_id)} (mỗi {delay}s)"
    else:
        msg = f"🛑 Auto-Reboot DISABLED cho {get_bot_name(bot_id)}"
    return jsonify({'status': 'success', 'message': msg})

@app.route("/api/force_reboot_bot", methods=['POST'])
def api_force_reboot_bot():
    """API endpoint để force reboot một bot cụ thể"""
    bot_id = request.json.get('bot_id')
    if not bot_id or not bot_id.startswith('main_'):
        return jsonify({'status': 'error', 'message': 'Invalid bot ID'}), 400
    
    # Reset failure count trước khi force reboot
    if bot_id in bot_states["reboot_settings"]:
        bot_states["reboot_settings"][bot_id]['failure_count'] = 0
    
    # Chạy reboot trong background thread
    def force_reboot():
        success = safe_reboot_bot(bot_id)
        if success:
            print(f"[Force Reboot] ✅ Successfully force rebooted {bot_id}", flush=True)
        else:
            print(f"[Force Reboot] ❌ Failed to force reboot {bot_id}", flush=True)
    
    threading.Thread(target=force_reboot, daemon=True).start()
    
    return jsonify({
        'status': 'success', 
        'message': f'🔄 Force reboot initiated for {get_bot_name(bot_id)}'
    })

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
    save_settings()
    return jsonify({'status': 'success', 'message': '💾 Settings saved.'})

@app.route("/status")
def status_endpoint():
    now = time.time()
    def get_bot_status_list(bot_list, type_prefix):
        status_list = []
        # Handle main bots based on tokens, not just active instances
        if type_prefix == "main":
            num_bots = len(main_tokens)
        else:
            num_bots = len(tokens)
            
        for i in range(num_bots):
            bot_id = f"{type_prefix}_{i if type_prefix == 'sub' else i+1}"
            bot_instance = None
            if type_prefix == 'main' and i < len(main_bots):
                bot_instance = main_bots[i]
            elif type_prefix == 'sub' and i < len(bots):
                bot_instance = bots[i]
            
            failures = bot_states["health_stats"].get(bot_id, {}).get('consecutive_failures', 0)
            health_status = 'bad' if failures >= 3 else 'warning' if failures > 0 else 'good'
            
            status_list.append({
                "name": get_bot_name(bot_id),
                "status": bot_instance is not None,
                "reboot_id": bot_id,
                "is_active": bot_states["active"].get(bot_id, False),
                "type": type_prefix,
                "health_status": health_status
            })
        return status_list

    with bots_lock:
        bot_statuses = {
            "main_bots": get_bot_status_list(main_bots, "main"),
            "sub_accounts": get_bot_status_list(bots, "sub")
        }
    
    clan_settings = bot_states["auto_clan_drop"]
    clan_drop_status = {
        "enabled": clan_settings.get("enabled", False),
        "countdown": (clan_settings.get("last_cycle_start_time", 0) + clan_settings.get("cycle_interval", 1800) - now) if clan_settings.get("enabled") else 0
    }
    
    # Calculate countdown for reboot settings
    reboot_settings_with_countdown = {}
    for bot_id, settings in bot_states["reboot_settings"].items():
        new_settings = settings.copy()
        new_settings['countdown'] = max(0, settings.get('next_reboot_time', 0) - now) if settings.get('enabled') else 0
        reboot_settings_with_countdown[bot_id] = new_settings

    return jsonify({
        'bot_reboot_settings': reboot_settings_with_countdown,
        'bot_statuses': bot_statuses,
        'server_start_time': server_start_time,
        'servers': servers,
        'watermelon_grab_states': bot_states["watermelon_grab"],
        'auto_clan_drop_status': clan_drop_status
    })

# --- MAIN EXECUTION ---
if __name__ == "__main__":
    print("🚀 Shadow Network Control - Enhanced Version Starting...", flush=True)
    load_settings()

    print("🔌 Initializing bots...", flush=True)
    # Initialize main_bots list with None placeholders
    main_bots = [None] * len(main_tokens)
    with bots_lock:
        for i, token in enumerate(t for t in main_tokens if t.strip()):
            bot_num = i + 1
            bot = create_bot(token.strip(), bot_identifier=bot_num, is_main=True)
            if i < len(main_bots):
                main_bots[i] = bot

            bot_id = f"main_{bot_num}"
            bot_states["active"].setdefault(bot_id, True)
            bot_states["watermelon_grab"].setdefault(bot_id, False)
            bot_states["auto_clan_drop"]["heart_thresholds"].setdefault(bot_id, 50)
            bot_states["reboot_settings"].setdefault(bot_id, {'enabled': False, 'delay': 3600, 'next_reboot_time': 0, 'failure_count': 0})
            bot_states["health_stats"].setdefault(bot_id, {'consecutive_failures': 0})

        for i, token in enumerate(t for t in tokens if t.strip()):
            bots.append(create_bot(token.strip(), bot_identifier=i, is_main=False))
            bot_id = f'sub_{i}'
            bot_states["active"].setdefault(bot_id, True)
            bot_states["health_stats"].setdefault(bot_id, {'consecutive_failures': 0})

    print("🔧 Starting background threads...", flush=True)
    threading.Thread(target=periodic_task, args=(1800, save_settings, "Save"), daemon=True).start()
    threading.Thread(target=periodic_task, args=(60, health_monitoring_check, "Health"), daemon=True).start()
    threading.Thread(target=spam_loop_manager, daemon=True).start()
    
    auto_reboot_thread = threading.Thread(target=auto_reboot_loop, daemon=True)
    auto_reboot_thread.start()
    
    auto_clan_drop_thread = threading.Thread(target=auto_clan_drop_loop, daemon=True)
    auto_clan_drop_thread.start()
    
    port = int(os.environ.get("PORT", 10000))
    print(f"🌐 Web Server running at http://0.0.0.0:{port}", flush=True)
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
