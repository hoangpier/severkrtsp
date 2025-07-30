# PHIÊN BẢN HOÀN CHỈNH - HỖ TRỢ N TÀI KHOẢN CHÍNH - SPAM SONG SONG - TÍCH HỢP DROP CLAN - SOLISFAIR ASSISTANT
import discum
import threading
import time
import os
import re
import requests
import json
from flask import Flask, request, render_template_string, jsonify
from dotenv import load_dotenv
import uuid

load_dotenv()

# --- CẤU HÌNH ---
main_tokens = os.getenv("MAIN_TOKENS").split(",") if os.getenv("MAIN_TOKENS") else []
tokens = os.getenv("TOKENS").split(",") if os.getenv("TOKENS") else []
karuta_id = "646937666251915264"
karibbit_id = "1311684840462225440"
BOT_NAMES = [ # Tên để hiển thị trên giao diện, bạn có thể thêm nếu cần
    "ALPHA", "BETA", "GAMMA", "DELTA", "EPSILON",
    "ZETA", "ETA", "THETA", "IOTA", "KAPPA",
    "LAMBDA", "MU"
]

# --- BIẾN TRẠNG THÁI ---
bots, acc_names = [], [
    "Blacklist", "Khanh bang", "Dersale", "Venus", "WhyK", "Tan",
    "Ylang", "Nina", "Nathan", "Ofer", "White", "the Wicker", "Leader", "Tess", "Wyatt", "Daisy", "CantStop", "Token",
]
main_bots = []
servers = []
watermelon_grab_states = {} # Cài đặt nhặt dưa hấu toàn cục

# --- CHỨC NĂNG MỚI: Cài đặt cho tính năng tự động drop clan ---
auto_clan_drop_settings = {
    "enabled": False,
    "channel_id": "",
    "ktb_channel_id": "",
    "last_cycle_start_time": 0,
    "cycle_interval": 1800, # 30 phút
    "bot_delay": 70, # 70 giây
    "heart_thresholds": {}
}

# --- CHỨC NĂNG SOLISFAIR: Cài đặt cho Trợ lý Pha chế ---
solisfair_settings = {
    "enabled": False, # Chỉ dùng để lưu trạng thái bật/tắt trên UI
    "is_running": False, # Trạng thái chạy/dừng của bot giải đố
    "channel_id": "",   # Kênh để chạy lệnh k!event
    "bot_id": "main_1", # Bot sẽ thực hiện hành động
    "status_message": "Sẵn sàng." # Tin nhắn trạng thái cho giao diện
}

# Cài đặt toàn cục
auto_reboot_enabled = False
auto_reboot_delay = 3600
last_reboot_cycle_time = 0

# Các biến điều khiển luồng
auto_reboot_stop_event = threading.Event()
auto_clan_drop_stop_event = threading.Event()
solisfair_stop_event = threading.Event() # Event để dừng luồng Solisfair
spam_thread, auto_reboot_thread, auto_clan_drop_thread, solisfair_thread = None, None, None, None
bots_lock = threading.Lock()
server_start_time = time.time()
bot_active_states = {}

# --- HÀM LƯU VÀ TẢI CÀI ĐẶT ---
def save_settings():
    api_key = os.getenv("JSONBIN_API_KEY")
    bin_id = os.getenv("JSONBIN_BIN_ID")
    if not api_key or not bin_id: return
    settings = {
        'servers': servers,
        'auto_reboot_enabled': auto_reboot_enabled,
        'auto_reboot_delay': auto_reboot_delay,
        'bot_active_states': bot_active_states,
        'last_reboot_cycle_time': last_reboot_cycle_time,
        'watermelon_grab_states': watermelon_grab_states,
        'auto_clan_drop_settings': auto_clan_drop_settings,
        'solisfair_settings': solisfair_settings
    }
    headers = {'Content-Type': 'application/json', 'X-Master-Key': api_key}
    url = f"https://api.jsonbin.io/v3/b/{bin_id}"
    try:
        req = requests.put(url, json=settings, headers=headers, timeout=10)
        if req.status_code == 200: print("[Settings] Đã lưu cài đặt lên JSONBin.io thành công.", flush=True)
        else: print(f"[Settings] Lỗi khi lưu cài đặt: {req.status_code} - {req.text}", flush=True)
    except Exception as e: print(f"[Settings] Exception khi lưu cài đặt: {e}", flush=True)

def load_settings():
    global servers, auto_reboot_enabled, auto_reboot_delay, bot_active_states, last_reboot_cycle_time, watermelon_grab_states, auto_clan_drop_settings, solisfair_settings
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
                servers.extend(settings.get('servers', []))
                auto_reboot_enabled = settings.get('auto_reboot_enabled', False)
                auto_reboot_delay = settings.get('auto_reboot_delay', 3600)
                bot_active_states = settings.get('bot_active_states', {})
                last_reboot_cycle_time = settings.get('last_reboot_cycle_time', 0)
                watermelon_grab_states = settings.get('watermelon_grab_states', {})
                
                loaded_clan_settings = settings.get('auto_clan_drop_settings', {})
                if loaded_clan_settings:
                    if 'heart_thresholds' not in loaded_clan_settings:
                        loaded_clan_settings['heart_thresholds'] = {}
                    auto_clan_drop_settings.update(loaded_clan_settings)
                
                loaded_solisfair_settings = settings.get('solisfair_settings', {})
                if loaded_solisfair_settings:
                    solisfair_settings.update(loaded_solisfair_settings)
                    solisfair_settings['is_running'] = False

                print("[Settings] Đã tải cài đặt từ JSONBin.io.", flush=True)
            else:
                print("[Settings] JSONBin rỗng, bắt đầu với cài đặt mặc định và lưu lại.", flush=True)
                save_settings()
        else: print(f"[Settings] Lỗi khi tải cài đặt: {req.status_code} - {req.text}", flush=True)
    except Exception as e: print(f"[Settings] Exception khi tải cài đặt: {e}", flush=True)

# --- CÁC HÀM LOGIC BOT ---

def find_button_id_by_emoji_or_label(components, emoji_name=None, label=None):
    if not components: return None
    for row in components:
        for button in row.get('components', []):
            if emoji_name:
                button_emoji = button.get('emoji', {})
                if button_emoji and button_emoji.get('name') == emoji_name:
                    return button.get('custom_id')
            if label:
                button_label = button.get('label', '')
                if button_label and button_label.lower() == label.lower():
                    return button.get('custom_id')
    return None

# --- HÀM PHỤ TRỢ BẤM NÚT (PHIÊN BẢN AN TOÀN) ---
def click_karuta_button(bot, channel_id, guild_id, message_id, message_flags, custom_id):
    """Bấm nút bằng cách gửi request trực tiếp để tương thích với mọi phiên bản discum."""
    url = "https://discord.com/api/v9/interactions"
    payload = {
        "type": 3,
        "application_id": karuta_id,
        "channel_id": channel_id,
        "guild_id": guild_id,
        "message_id": message_id,
        "message_flags": message_flags,
        "data": { "component_type": 2, "custom_id": custom_id },
        "session_id": bot.gateway.session_id,
        "nonce": str(int(time.time() * 1000))
    }
    try:
        # bot.s là đối tượng session của thư viện requests đã được xác thực
        result = bot.s.post(url, json=payload)
        result.raise_for_status()
    except Exception as e:
        print(f"[Click Error] Lỗi khi gửi yêu cầu bấm nút: {e}", flush=True)

# --- HÀM LOGIC SOLISFAIR (ĐÃ SỬA LỖI HOÀN CHỈNH) ---
def run_solisfair_solver(stop_event):
    global solisfair_settings
    
    def update_status(message):
        print(f"[Solisflair] {message}", flush=True)
        solisfair_settings["status_message"] = message

    update_status("Bắt đầu khởi động...")
    solisfair_settings["is_running"] = True
    
    bot = None
    channel_id = None
    message_id = None
    guild_id = None
    try:
        with bots_lock:
            bot_id_str = solisfair_settings.get("bot_id", "main_1")
            if not bot_active_states.get(bot_id_str, False):
                raise ValueError(f"Bot {bot_id_str.upper()} đang OFFLINE. Hãy bật trong System Status.")
            target_bot_index = int(bot_id_str.split('_')[1]) - 1
            if not (0 <= target_bot_index < len(main_bots)):
                raise ValueError("Bot ID không hợp lệ.")
            bot = main_bots[target_bot_index]
            bot_name = BOT_NAMES[target_bot_index]

        channel_id = solisfair_settings["channel_id"]
        if not channel_id:
            raise ValueError("Chưa cài đặt Channel ID.")

        # Lấy Guild ID từ kênh
        try:
            channel_data = bot.getChannel(channel_id).json()
            guild_id = channel_data.get('guild_id')
            if not guild_id:
                raise ValueError("Kênh này không thuộc một server (có thể là DM).")
        except Exception as e:
            raise ValueError(f"Không thể lấy thông tin kênh: {e}")

        update_status(f"Bot {bot_name} đang chuẩn bị...")
        bot.sendMessage(channel_id, "k!event")
        time.sleep(3) 

        messages = bot.getMessages(channel_id, num=10).json()
        event_message = next((m for m in messages if m.get('author', {}).get('id') == karuta_id and "Takumi's Solisfair Stand" in m.get('embeds', [{}])[0].get('title', '')), None)
        
        if not event_message:
            raise ValueError("Không tìm thấy tin nhắn k!event. Hãy thử lại.")
        
        message_id = event_message['id']
        update_status("Đã tìm thấy tin nhắn sự kiện.")

        # VÒNG LẶP GIẢI ĐỐ CHÍNH
        for i in range(100): 
            if stop_event.is_set():
                update_status("Đã nhận lệnh dừng."); break
            
            update_status(f"Bắt đầu vòng lặp thứ {i+1}...")
            time.sleep(1.5)

            raw_msg_data = bot.getMessage(channel_id, message_id).json()
            msg_data = raw_msg_data[0] if isinstance(raw_msg_data, list) and raw_msg_data else raw_msg_data if isinstance(raw_msg_data, dict) else None
            if not msg_data:
                update_status(f"Dữ liệu tin nhắn không hợp lệ: {raw_msg_data}"); break
            
            message_flags = msg_data.get('flags', 0)
            components = msg_data.get('components', [])
            embeds = msg_data.get('embeds', [])
            if not embeds: update_status("Tin nhắn không có embed. Dừng lại."); break
            embed_desc = embeds[0].get('description', '')

            if "You don't have any fruit pieces" in embed_desc:
                update_status("Đã hết mảnh trái cây để đặt."); break
            if "Move the piece around the board" not in embed_desc:
                update_status("Không ở trong màn hình đặt mảnh. Dừng lại."); break

            update_status("Đang thực hiện nước đi mặc định...")
            
            update_status("Đang tìm nút Chọn (tích xanh dương)...")
            select_button_id = find_button_id_by_emoji_or_label(components, emoji_name='☑️') or find_button_id_by_emoji_or_label(components, emoji_name='✔️')
            if not select_button_id:
                update_status("Lỗi: Không tìm thấy nút Chọn (Tích xanh dương)."); break
            
            update_status("Đã tìm thấy nút Chọn. Đang nhấn...")
            click_karuta_button(bot, channel_id, guild_id, message_id, message_flags, select_button_id)
            time.sleep(1.5)

            update_status("Đang tìm nút Xác nhận (tích xanh lá)...")
            raw_msg_data = bot.getMessage(channel_id, message_id).json()
            msg_data = raw_msg_data[0] if isinstance(raw_msg_data, list) and raw_msg_data else raw_msg_data if isinstance(raw_msg_data, dict) else None
            if not msg_data:
                update_status(f"Dữ liệu tin nhắn không hợp lệ sau khi nhấn chọn: {raw_msg_data}"); break

            message_flags = msg_data.get('flags', 0)
            components = msg_data.get('components', [])
            confirm_button_id = find_button_id_by_emoji_or_label(components, emoji_name='✅')
            
            if not confirm_button_id:
                update_status("Lỗi: Không tìm thấy nút Xác Nhận (Tích xanh lá)."); break

            update_status("Đã tìm thấy nút Xác nhận. Đang nhấn...")
            click_karuta_button(bot, channel_id, guild_id, message_id, message_flags, confirm_button_id)
            update_status("Đã xác nhận. Chờ Karuta xử lý...")
            time.sleep(4)

        update_status("Hoàn thành chu trình.")

    except Exception as e:
        update_status(f"Lỗi nghiêm trọng: {e}")
    finally:
        if bot and channel_id and message_id and guild_id:
            try:
                raw_msg_data = bot.getMessage(channel_id, message_id).json()
                msg_data = raw_msg_data[0] if isinstance(raw_msg_data, list) and raw_msg_data else raw_msg_data if isinstance(raw_msg_data, dict) else {}
                
                message_flags = msg_data.get('flags', 0)
                components = msg_data.get('components', [])
                back_button_id = find_button_id_by_emoji_or_label(components, label='Back')
                if back_button_id:
                    click_karuta_button(bot, channel_id, guild_id, message_id, message_flags, back_button_id)
                    update_status("Đã nhấn Back để kết thúc.")
            except Exception as e:
                update_status(f"Không thể nhấn Back: {e}")

        solisfair_settings["is_running"] = False
        save_settings()

def handle_clan_drop(bot, msg, bot_num):
    if not (auto_clan_drop_settings.get("enabled") and auto_clan_drop_settings.get("ktb_channel_id")):
        return
    channel_id = msg.get("channel_id")
    if channel_id != auto_clan_drop_settings.get("channel_id"):
        return

    last_drop_msg_id = msg["id"]
    
    def grab_handler():
        card_picked = False
        ktb_channel_id = auto_clan_drop_settings["ktb_channel_id"]
        
        for _ in range(6):
            time.sleep(0.5)
            try:
                messages = bot.getMessages(channel_id, num=5).json()
                for msg_item in messages:
                    if msg_item.get("author", {}).get("id") == karibbit_id and int(msg_item["id"]) > int(last_drop_msg_id):
                        if "embeds" in msg_item and len(msg_item["embeds"]) > 0:
                            desc = msg_item["embeds"][0].get("description", "")
                            if '♡' not in desc: continue
                            lines = desc.split('\n')
                            heart_numbers = [int(match.group(1)) if (match := re.search(r'♡(\d+)', line)) else 0 for line in lines[:3]]
                            if not any(heart_numbers): break 
                            max_num = max(heart_numbers)
                            bot_id_str = f'main_{bot_num}'
                            heart_threshold = auto_clan_drop_settings.get("heart_thresholds", {}).get(bot_id_str, 50)
                            
                            if max_num >= heart_threshold:
                                max_index = heart_numbers.index(max_num)
                                delays = { 1: [0.4, 1.4, 2.1], 2: [0.7, 1.8, 2.4], 3: [0.7, 1.8, 2.4], 4: [0.8, 1.9, 2.5] }
                                bot_delays = delays.get(bot_num, [0.9, 2.0, 2.6])
                                emojis = ["1️⃣", "2️⃣", "3️⃣"]
                                emoji = emojis[max_index]
                                delay = bot_delays[max_index]
                                log_message = f"[CLAN DROP | Bot {bot_num}] Chọn dòng {max_index+1} với {max_num} tim -> Emoji {emoji} sau {delay}s"
                                print(log_message, flush=True)
                                def grab_action():
                                    bot.addReaction(channel_id, last_drop_msg_id, emoji)
                                    time.sleep(1)
                                    bot.sendMessage(ktb_channel_id, "kt b")
                                threading.Timer(delay, grab_action).start()
                                card_picked = True
                        if card_picked: break
                if card_picked: break
            except Exception as e:
                print(f"Lỗi khi đọc Karibbit (Clan Drop - Bot {bot_num}): {e}", flush=True)
            if card_picked: break
    
    threading.Thread(target=grab_handler).start()

def handle_grab(bot, msg, bot_num):
    channel_id = msg.get("channel_id")
    target_server = next((s for s in servers if s.get('main_channel_id') == channel_id), None)
    if not target_server: return

    auto_grab_enabled = target_server.get(f'auto_grab_enabled_{bot_num}', False)
    heart_threshold = target_server.get(f'heart_threshold_{bot_num}', 50)
    ktb_channel_id = target_server.get('ktb_channel_id')
    watermelon_grab_enabled = watermelon_grab_states.get(f'main_{bot_num}', False)

    if not auto_grab_enabled and not watermelon_grab_enabled:
        return

    last_drop_msg_id = msg["id"]
    
    def grab_handler():
        card_picked = False
        if auto_grab_enabled and ktb_channel_id:
            for _ in range(6):
                time.sleep(0.5)
                try:
                    messages = bot.getMessages(channel_id, num=5).json()
                    for msg_item in messages:
                        if msg_item.get("author", {}).get("id") == karibbit_id and int(msg_item["id"]) > int(last_drop_msg_id):
                            if "embeds" in msg_item and len(msg_item["embeds"]) > 0:
                                desc = msg_item["embeds"][0].get("description", "")
                                if '♡' not in desc: continue
                                lines = desc.split('\n')
                                heart_numbers = [int(match.group(1)) if (match := re.search(r'♡(\d+)', line)) else 0 for line in lines[:3]]
                                if not any(heart_numbers): break 
                                max_num = max(heart_numbers)
                                if max_num >= heart_threshold:
                                    max_index = heart_numbers.index(max_num)
                                    delays = { 1: [0.4, 1.4, 2.1], 2: [0.7, 1.8, 2.4], 3: [0.7, 1.8, 2.4], 4: [0.8, 1.9, 2.5] }
                                    bot_delays = delays.get(bot_num, [0.9, 2.0, 2.6])
                                    emojis = ["1️⃣", "2️⃣", "3️⃣"]
                                    emoji = emojis[max_index]
                                    delay = bot_delays[max_index]
                                    log_message = f"[{target_server['name']} | Bot {bot_num}] Chọn dòng {max_index+1} với {max_num} tim -> Emoji {emoji} sau {delay}s"
                                    print(log_message, flush=True)
                                    def grab_action():
                                        bot.addReaction(channel_id, last_drop_msg_id, emoji)
                                        time.sleep(1)
                                        bot.sendMessage(ktb_channel_id, "kt b")
                                    threading.Timer(delay, grab_action).start()
                                    card_picked = True
                            if card_picked: break
                    if card_picked: break
                except Exception as e:
                    print(f"Lỗi khi đọc Karibbit (Bot {bot_num} @ {target_server['name']}): {e}", flush=True)
                if card_picked: break

        if watermelon_grab_enabled:
            try:
                time.sleep(0.25)
                full_msg_obj = bot.getMessage(channel_id, last_drop_msg_id).json()
                if isinstance(full_msg_obj, list) and len(full_msg_obj) > 0:
                    full_msg_obj = full_msg_obj[0]
                if 'reactions' in full_msg_obj:
                    for reaction in full_msg_obj['reactions']:
                        if reaction['emoji']['name'] == '🍉':
                            bot.addReaction(channel_id, last_drop_msg_id, "🍉")
                            break 
            except Exception as e:
                print(f"Lỗi khi kiểm tra sự kiện dưa hấu (Bot {bot_num}): {e}", flush=True)

    threading.Thread(target=grab_handler).start()

def create_bot(token, bot_identifier, is_main=False):
    bot = discum.Client(token=token, log=False)
    
    @bot.gateway.command
    def on_ready(resp):
        if resp.event.ready:
            user = resp.raw.get("user", {})
            if isinstance(user, dict) and (user_id := user.get("id")):
                bot_name = BOT_NAMES[bot_identifier-1] if is_main and bot_identifier-1 < len(BOT_NAMES) else acc_names[bot_identifier] if not is_main and bot_identifier < len(acc_names) else f"Bot {bot_identifier}"
                print(f"Đã đăng nhập: {user_id} ({bot_name})", flush=True)

    if is_main:
        @bot.gateway.command
        def on_message(resp):
            if resp.event.message:
                msg = resp.parsed.auto()
                if msg.get("author", {}).get("id") == karuta_id and "dropping" in msg.get("content", "").lower():
                    if msg.get("mentions"):
                        handle_clan_drop(bot, msg, bot_identifier)
                    else:
                        handle_grab(bot, msg, bot_identifier)
            
    threading.Thread(target=bot.gateway.run, daemon=True).start()
    return bot

def run_clan_drop_cycle():
    global auto_clan_drop_settings
    print("[Clan Drop] Bắt đầu chu kỳ drop clan.", flush=True)
    
    settings = auto_clan_drop_settings.copy()
    channel_id = settings.get("channel_id")

    with bots_lock:
        active_main_bots = [
            (bot, i + 1) for i, bot in enumerate(main_bots) 
            if bot and bot_active_states.get(f'main_{i+1}', False)
        ]
    
    if not active_main_bots:
        print("[Clan Drop] Không có bot chính nào hoạt động để thực hiện drop.", flush=True)
        return
    
    for bot, bot_num in active_main_bots:
        if auto_clan_drop_stop_event.is_set(): break
        try:
            bot_name = BOT_NAMES[bot_num-1] if bot_num-1 < len(BOT_NAMES) else f"MAIN_{bot_num}"
            print(f"[Clan Drop] Bot {bot_name} đang gửi 'kd'...", flush=True)
            bot.sendMessage(channel_id, "kd")
            time.sleep(settings.get("bot_delay", 70))
        except Exception as e:
            print(f"[Clan Drop] Lỗi khi gửi 'kd' từ bot {bot_num}: {e}", flush=True)
    
    auto_clan_drop_settings["last_cycle_start_time"] = time.time()
    save_settings()

def auto_clan_drop_loop():
    while not auto_clan_drop_stop_event.is_set():
        try:
            if auto_clan_drop_stop_event.wait(timeout=60): break
            
            settings = auto_clan_drop_settings
            is_enabled = settings.get("enabled")
            channel_id = settings.get("channel_id")
            interval = settings.get("cycle_interval", 1800)
            last_run = settings.get("last_cycle_start_time", 0)
            
            if is_enabled and channel_id and (time.time() - last_run) >= interval:
                run_clan_drop_cycle()

        except Exception as e:
            print(f"[ERROR in auto_clan_drop_loop] {e}", flush=True)
            time.sleep(60)
    print("[Clan Drop] Luồng tự động drop clan đã dừng.", flush=True)

def auto_reboot_loop():
    global last_reboot_cycle_time, main_bots
    while not auto_reboot_stop_event.is_set():
        try:
            if auto_reboot_stop_event.wait(timeout=60): break
            if auto_reboot_enabled and (time.time() - last_reboot_cycle_time) >= auto_reboot_delay:
                print("[Reboot] Hết thời gian chờ, tiến hành reboot các tài khoản chính.", flush=True)
                with bots_lock:
                    new_main_bots = []
                    for i, bot in enumerate(main_bots):
                        if i < len(main_tokens):
                            bot.gateway.close()
                            time.sleep(2)
                            bot_name = BOT_NAMES[i] if i < len(BOT_NAMES) else f"MAIN_{i+1}"
                            new_bot = create_bot(main_tokens[i], bot_identifier=(i+1), is_main=True)
                            new_main_bots.append(new_bot)
                            print(f"Đã reboot bot {bot_name}", flush=True)
                            time.sleep(5)
                    main_bots = new_main_bots
                last_reboot_cycle_time = time.time()
                save_settings()
        except Exception as e:
            print(f"[ERROR in auto_reboot_loop] {e}", flush=True)
            time.sleep(60)
    print("[Reboot] Luồng tự động reboot đã dừng.", flush=True)

def spam_loop():
    active_server_threads = {}
    while True:
        try:
            current_server_ids = {s['id'] for s in servers}
            
            for server_id in list(active_server_threads.keys()):
                if server_id not in current_server_ids:
                    print(f"[Spam Control] Dừng luồng spam cho server đã bị xóa: {server_id}", flush=True)
                    _, stop_event = active_server_threads.pop(server_id)
                    stop_event.set()

            for server in servers:
                server_id = server.get('id')
                spam_is_on = server.get('spam_enabled') and server.get('spam_message') and server.get('spam_channel_id')
                
                if spam_is_on and server_id not in active_server_threads:
                    print(f"[Spam Control] Bắt đầu luồng spam cho server: {server.get('name')}", flush=True)
                    stop_event = threading.Event()
                    thread = threading.Thread(target=spam_for_server, args=(server, stop_event), daemon=True)
                    thread.start()
                    active_server_threads[server_id] = (thread, stop_event)
                elif not spam_is_on and server_id in active_server_threads:
                    print(f"[Spam Control] Dừng luồng spam cho server: {server.get('name')}", flush=True)
                    _, stop_event = active_server_threads.pop(server_id)
                    stop_event.set()

            time.sleep(5)
        except Exception as e:
            print(f"[ERROR in spam_loop_manager] {e}", flush=True)
            time.sleep(5)

def spam_for_server(server_config, stop_event):
    server_name = server_config.get('name')
    channel_id = server_config.get('spam_channel_id')
    message = server_config.get('spam_message')
    while not stop_event.is_set():
        try:
            with bots_lock:
                active_main_bots = [bot for i, bot in enumerate(main_bots) if bot and bot_active_states.get(f'main_{i+1}', False)]
                active_sub_bots = [bot for i, bot in enumerate(bots) if bot and bot_active_states.get(f'sub_{i}', False)]
                bots_to_spam = active_main_bots + active_sub_bots
            
            delay = server_config.get('spam_delay', 10)
            
            for bot in bots_to_spam:
                if stop_event.is_set(): break
                try:
                    bot.sendMessage(channel_id, message)
                    time.sleep(2) 
                except Exception as e:
                    print(f"Lỗi gửi spam từ bot tới server {server_name}: {e}", flush=True)
            
            if not stop_event.is_set():
                stop_event.wait(timeout=delay)
        except Exception as e:
            print(f"[ERROR in spam_for_server {server_name}] {e}", flush=True)
            stop_event.wait(timeout=10)

def periodic_save_loop():
    while True:
        time.sleep(36000)
        print("[Settings] Bắt đầu lưu định kỳ (10 giờ)...", flush=True)
        save_settings()
        
app = Flask(__name__)

# --- GIAO DIỆN WEB ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Karuta Deep - Shadow Network Control</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <link href="https://fonts.googleapis.com/css2?family=Creepster&family=Orbitron:wght@400;700;900&family=Courier+Prime:wght@400;700&family=Nosifer&display=swap" rel="stylesheet">
    <style>
        :root { --primary-bg: #0a0a0a; --secondary-bg: #1a1a1a; --panel-bg: #111111; --border-color: #333333; --blood-red: #8b0000; --dark-red: #550000; --bone-white: #f8f8ff; --necro-green: #228b22; --text-primary: #f0f0f0; --text-secondary: #cccccc; }
        body { font-family: 'Courier Prime', monospace; background: var(--primary-bg); color: var(--text-primary); margin: 0; padding: 0;}
        .container { max-width: 1600px; margin: 0 auto; padding: 20px; }
        .header { text-align: center; margin-bottom: 30px; padding: 20px; border-bottom: 2px solid var(--blood-red); }
        .title { font-family: 'Nosifer', cursive; font-size: 3rem; color: var(--blood-red); }
        .main-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(500px, 1fr)); gap: 20px; }
        .panel { background: var(--panel-bg); border: 1px solid var(--border-color); border-radius: 10px; padding: 25px; position: relative;}
        .panel h2 { font-family: 'Orbitron', cursive; font-size: 1.4rem; margin-bottom: 20px; text-transform: uppercase; border-bottom: 2px solid; padding-bottom: 10px; color: var(--bone-white); }
        .panel h2 i { margin-right: 10px; }
        .btn { background: var(--secondary-bg); border: 1px solid var(--border-color); color: var(--text-primary); padding: 10px 15px; border-radius: 4px; cursor: pointer; font-family: 'Orbitron', monospace; font-weight: 700; text-transform: uppercase; width: 100%; }
        .btn-small { padding: 5px 10px; font-size: 0.9em;}
        .input-group { display: flex; align-items: stretch; gap: 10px; margin-bottom: 15px; }
        .input-group label { background: #000; border: 1px solid var(--border-color); border-right: 0; padding: 10px 15px; border-radius: 4px 0 0 4px; display:flex; align-items:center; min-width: 120px;}
        .input-group input, .input-group textarea, .input-group select { flex-grow: 1; background: #000; border: 1px solid var(--border-color); color: var(--text-primary); padding: 10px 15px; border-radius: 0 4px 4px 0; font-family: 'Courier Prime', monospace; }
        .grab-section { display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; padding: 15px; background: rgba(0,0,0,0.2); border-radius: 8px;}
        .grab-section h3 { margin: 0; display: flex; align-items: center; gap: 10px; width: 80px; flex-shrink: 0; }
        .grab-section .input-group { margin-bottom: 0; flex-grow: 1; margin-left: 20px;}
        .msg-status { text-align: center; color: var(--necro-green); padding: 12px; border: 1px dashed var(--border-color); border-radius: 4px; margin-bottom: 20px; display: none; }
        .status-panel, .global-settings-panel, .clan-drop-panel { grid-column: 1 / -1; }
        .status-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 15px; }
        .status-row { display: flex; justify-content: space-between; align-items: center; padding: 12px; background: rgba(0,0,0,0.4); border-radius: 8px; }
        .timer-display { font-size: 1.2em; font-weight: 700; }
        .bot-status-container { display: grid; grid-template-columns: 1fr 2fr; gap: 20px; margin-top: 15px; border-top: 1px solid var(--border-color); padding-top: 15px; }
        .bot-status-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 8px; }
        .bot-status-item { display: flex; justify-content: space-between; align-items: center; padding: 5px 8px; background: rgba(0,0,0,0.3); border-radius: 4px; }
        .btn-toggle-state { padding: 3px 5px; font-size: 0.9em; border-radius: 4px; cursor: pointer; text-transform: uppercase; background: transparent; font-weight: 700; border: none; }
        .btn-rise { color: var(--necro-green); } .btn-rest { color: var(--dark-red); }
        .bot-main span:first-child { color: #FF4500; font-weight: 700; }
        .add-server-btn { display: flex; align-items: center; justify-content: center; min-height: 200px; border: 2px dashed var(--border-color); cursor: pointer; transition: all 0.3s ease; }
        .add-server-btn:hover { background: var(--secondary-bg); border-color: var(--blood-red); }
        .add-server-btn i { font-size: 3rem; color: var(--text-secondary); }
        .btn-delete-server { position: absolute; top: 15px; right: 15px; background: var(--dark-red); border: 1px solid var(--blood-red); color: var(--bone-white); width: auto; padding: 5px 10px; border-radius: 50%; }
        .server-sub-panel { border-top: 1px solid var(--border-color); margin-top: 20px; padding-top: 20px;}
        .flex-row { display:flex; gap: 10px; align-items: center;}
    </style>
</head>
<body>
    <div class="container">
        <div class="header"> <h1 class="title">Shadow Network Control</h1> </div>
        <div id="msg-status-container" class="msg-status"> <span id="msg-status-text"></span></div>
        <div class="main-grid">
            <div class="panel status-panel">
                <h2><i class="fas fa-heartbeat"></i> System Status</h2>
                <div class="bot-status-container">
                    <div class="status-grid">
                         <div class="status-row">
                            <span><i class="fas fa-redo"></i> Auto Reboot</span>
                            <div class="flex-row">
                                <input type="number" id="auto-reboot-delay" value="{{ auto_reboot_delay }}" style="width: 80px; text-align: right; padding: 5px;">
                                <span id="reboot-timer" class="timer-display">--:--:--</span>
                                <button type="button" id="auto-reboot-toggle-btn" class="btn btn-small">{{ 'DISABLE' if auto_reboot_enabled else 'ENABLE' }}</button>
                            </div>
                        </div>
                        <div class="status-row">
                            <span><i class="fas fa-server"></i> Uptime</span>
                            <div><span id="uptime-timer" class="timer-display">--:--:--</span></div>
                        </div>
                    </div>
                    <div id="bot-status-list" class="bot-status-grid"></div>
                </div>
            </div>

            <!-- PANEL MỚI CHO SOLISFAIR -->
            <div class="panel">
                <h2><i class="fas fa-cocktail"></i> Trợ Lý Pha Chế Solisfair</h2>
                <div class="server-sub-panel" style="border-top: none; margin-top: 0; padding-top: 0;">
                    <h3><i class="fas fa-robot"></i> Điều Khiển</h3>
                    <div class="input-group">
                        <label>Channel ID</label>
                        <input type="text" id="solisfair-channel-id" value="{{ solisfair_settings.channel_id or '' }}">
                    </div>
                    <div class="input-group">
                        <label>Bot Thực Hiện</label>
                        <select id="solisfair-bot-id">
                            {% for bot in main_bots_info %}
                            <option value="main_{{ bot.id }}" {% if solisfair_settings.bot_id == 'main_' + bot.id|string %}selected{% endif %}>{{ bot.name }}</option>
                            {% endfor %}
                        </select>
                    </div>
                    <button type="button" id="solisfair-save-btn" class="btn btn-small" style="margin-bottom: 15px;">Lưu Cài Đặt</button>
                    <button type="button" id="solisfair-toggle-btn" class="btn">BẮT ĐẦU</button>
                </div>
                 <div class="server-sub-panel">
                    <h3><i class="fas fa-info-circle"></i> Trạng Thái</h3>
                    <div id="solisfair-status" style="padding: 10px; background: rgba(0,0,0,0.3); border-radius: 4px; min-height: 40px; font-family: 'Courier Prime', monospace;">
                        Sẵn sàng.
                    </div>
                </div>
            </div>
            <!-- KẾT THÚC PANEL MỚI -->

            <div class="panel clan-drop-panel">
                <h2><i class="fas fa-users"></i> Clan Auto Drop</h2>
                <div class="status-grid" style="grid-template-columns: 1fr;">
                     <div class="status-row">
                        <span><i class="fas fa-hourglass-half"></i> Next Drop Cycle</span>
                        <div class="flex-row">
                            <span id="clan-drop-timer" class="timer-display">--:--:--</span>
                            <button type="button" id="clan-drop-toggle-btn" class="btn btn-small">{{ 'DISABLE' if auto_clan_drop_settings.enabled else 'ENABLE' }}</button>
                        </div>
                    </div>
                </div>
                <div class="server-sub-panel">
                    <h3><i class="fas fa-cogs"></i> Configuration</h3>
                    <div class="input-group"><label>Drop Channel ID</label><input type="text" id="clan-drop-channel-id" value="{{ auto_clan_drop_settings.channel_id or '' }}"></div>
                    <div class="input-group"><label>KTB Channel ID</label><input type="text" id="clan-drop-ktb-channel-id" value="{{ auto_clan_drop_settings.ktb_channel_id or '' }}"></div>
                </div>
                <div class="server-sub-panel">
                    <h3><i class="fas fa-crosshairs"></i> Soul Harvest (Clan Drop)</h3>
                    {% for bot in main_bots_info %}
                    <div class="grab-section">
                        <h3>{{ bot.name }}</h3>
                        <div class="input-group">
                            <input type="number" class="clan-drop-threshold" data-node="main_{{ bot.id }}" value="{{ auto_clan_drop_settings.heart_thresholds[('main_' + bot.id|string)]|default(50) }}" min="0">
                        </div>
                    </div>
                    {% endfor %}
                </div>
                <button type="button" id="clan-drop-save-btn" class="btn" style="margin-top: 20px;">Save Clan Drop Settings</button>
            </div>

            <div class="panel global-settings-panel">
                <h2><i class="fas fa-globe"></i> Global Event Settings</h2>
                <div class="server-sub-panel">
                    <h3><i class="fas fa-watermelon-slice"></i> Watermelon Grab (All Servers)</h3>
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
        
        function showStatusMessage(message, isError = false) { if (!message) return; msgStatusText.textContent = message; msgStatusContainer.style.color = isError ? 'var(--blood-red)' : 'var(--necro-green)'; msgStatusContainer.style.display = 'block'; setTimeout(() => { msgStatusContainer.style.display = 'none'; }, 4000); }
        async function postData(url = '', data = {}) {
            try {
                const response = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) });
                const result = await response.json();
                showStatusMessage(result.message, result.status !== 'success');
                if (result.status === 'success' && url !== '/api/save_settings') { fetch('/api/save_settings', { method: 'POST' }); if (result.reload) { setTimeout(() => window.location.reload(), 500); } }
                setTimeout(fetchStatus, 500);
                return result;
            } catch (error) { console.error('Error:', error); showStatusMessage('Server communication error.', true); }
        }
        function formatTime(seconds) { if (isNaN(seconds) || seconds < 0) return "--:--:--"; seconds = Math.floor(seconds); const h = Math.floor(seconds / 3600).toString().padStart(2, '0'); const m = Math.floor((seconds % 3600) / 60).toString().padStart(2, '0'); const s = (seconds % 60).toString().padStart(2, '0'); return `${h}:${m}:${s}`; }
        function updateElement(element, { textContent, className, value, innerHTML }) { if (!element) return; if (textContent !== undefined) element.textContent = textContent; if (className !== undefined) element.className = className; if (value !== undefined) element.value = value; if (innerHTML !== undefined) element.innerHTML = innerHTML; }
        
        async function fetchStatus() {
            try {
                const response = await fetch('/status');
                const data = await response.json();
                updateElement(document.getElementById('reboot-timer'), { textContent: formatTime(data.reboot_countdown) });
                updateElement(document.getElementById('auto-reboot-toggle-btn'), { textContent: data.reboot_enabled ? 'DISABLE' : 'ENABLE' });
                const serverUptimeSeconds = (Date.now() / 1000) - data.server_start_time;
                updateElement(document.getElementById('uptime-timer'), { textContent: formatTime(serverUptimeSeconds) });
                
                if (data.auto_clan_drop_status) {
                    updateElement(document.getElementById('clan-drop-timer'), { textContent: formatTime(data.auto_clan_drop_status.countdown) });
                    updateElement(document.getElementById('clan-drop-toggle-btn'), { textContent: data.auto_clan_drop_status.enabled ? 'DISABLE' : 'ENABLE' });
                }

                // --- CẬP NHẬT GIAO DIỆN SOLISFAIR ---
                if (data.solisfair_settings) {
                    const settings = data.solisfair_settings;
                    updateElement(document.getElementById('solisfair-toggle-btn'), { textContent: settings.is_running ? 'DỪNG LẠI' : 'BẮT ĐẦU' });
                    updateElement(document.getElementById('solisfair-status'), { textContent: settings.status_message });
                    const channelInput = document.getElementById('solisfair-channel-id');
                    if (document.activeElement !== channelInput) { updateElement(channelInput, { value: settings.channel_id }); }
                    const botSelect = document.getElementById('solisfair-bot-id');
                    if (document.activeElement !== botSelect) { updateElement(botSelect, { value: settings.bot_id }); }
                }

                const botListContainer = document.getElementById('bot-status-list');
                botListContainer.innerHTML = ''; 
                const allBots = [...data.bot_statuses.main_bots, ...data.bot_statuses.sub_accounts];
                allBots.forEach(bot => {
                    const item = document.createElement('div');
                    item.className = 'bot-status-item';
                    if (bot.type === 'main') item.classList.add('bot-main');
                    const buttonText = bot.is_active ? 'ONLINE' : 'OFFLINE';
                    const buttonClass = bot.is_active ? 'btn-rise' : 'btn-rest';
                    item.innerHTML = `<span>${bot.name}</span><button type="button" data-target="${bot.reboot_id}" class="btn-toggle-state ${buttonClass}">${buttonText}</button>`;
                    botListContainer.appendChild(item);
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
                                <i class="fas fa-watermelon-slice"></i>&nbsp;${isEnabled ? 'DISABLE' : 'ENABLE'}
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

            // --- XỬ LÝ NÚT BẤM SOLISFAIR ---
            if (button.id === 'solisfair-toggle-btn') {
                postData('/api/solisfair_toggle');
                return;
            }
            if (button.id === 'solisfair-save-btn') {
                const channel_id = document.getElementById('solisfair-channel-id').value;
                const bot_id = document.getElementById('solisfair-bot-id').value;
                postData('/api/solisfair_update_settings', { channel_id, bot_id });
                return;
            }

            if (button.id === 'clan-drop-toggle-btn') {
                postData('/api/clan_drop_toggle');
                return;
            }
            if (button.id === 'clan-drop-save-btn') {
                const channel_id = document.getElementById('clan-drop-channel-id').value;
                const ktb_channel_id = document.getElementById('clan-drop-ktb-channel-id').value;
                const thresholds = {};
                document.querySelectorAll('.clan-drop-threshold').forEach(input => {
                    thresholds[input.dataset.node] = parseInt(input.value, 10);
                });
                postData('/api/clan_drop_update', { channel_id, ktb_channel_id, heart_thresholds: thresholds });
                return;
            }

            if (button.classList.contains('watermelon-toggle')) {
                const node = button.dataset.node;
                postData('/api/watermelon_toggle', { node: node });
                return;
            }

            const serverPanel = button.closest('.server-panel');
            if (serverPanel) {
                const serverId = serverPanel.dataset.serverId;
                if (button.classList.contains('harvest-toggle')) { 
                    const node = button.dataset.node; 
                    const thresholdInput = serverPanel.querySelector(`.harvest-threshold[data-node="${node}"]`); 
                    postData('/api/harvest_toggle', { server_id: serverId, node: node, threshold: thresholdInput.value }); 
                } else if (button.classList.contains('broadcast-toggle')) { 
                    const message = serverPanel.querySelector('.spam-message').value; 
                    const delay = serverPanel.querySelector('.spam-delay').value; 
                    postData('/api/broadcast_toggle', { server_id: serverId, message: message, delay: delay }); 
                } else if (button.classList.contains('btn-delete-server')) { 
                    if(confirm('Are you sure? This action cannot be undone.')) { postData('/api/delete_server', { server_id: serverId }); } 
                }
                return;
            }
            
            if (button.id === 'auto-reboot-toggle-btn') {
                postData('/api/reboot_toggle_auto', { delay: document.getElementById('auto-reboot-delay').value });
            } else if (button.matches('#bot-status-list button[data-target]')) {
                postData('/api/toggle_bot_state', { target: button.dataset.target });
            }
        });

        document.querySelector('.main-grid').addEventListener('change', e => {
            const target = e.target;
            const serverPanel = target.closest('.server-panel');
            if (!serverPanel || !target.classList.contains('channel-input')) return;
            const serverId = serverPanel.dataset.serverId;
            const payload = { server_id: serverId };
            payload[target.dataset.field] = target.value;
            postData('/api/update_server_channels', payload);
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
    sorted_servers = sorted(servers, key=lambda s: s.get('name', ''))
    main_bots_info = [
        {"id": i + 1, "name": BOT_NAMES[i] if i < len(BOT_NAMES) else f"MAIN_{i+1}"}
        for i in range(len(main_tokens))
    ]
    return render_template_string(HTML_TEMPLATE, 
        servers=sorted_servers, 
        auto_reboot_enabled=auto_reboot_enabled, 
        auto_reboot_delay=auto_reboot_delay, 
        main_bots_info=main_bots_info,
        auto_clan_drop_settings=auto_clan_drop_settings,
        solisfair_settings=solisfair_settings # <-- THÊM MỚI
    )

# --- API MỚI CHO SOLISFAIR ---
@app.route("/api/solisfair_toggle", methods=['POST'])
def api_solisfair_toggle():
    global solisfair_thread, solisfair_stop_event
    
    if solisfair_settings.get("is_running"):
        solisfair_stop_event.set()
        solisfair_settings["status_message"] = "Đang dừng..."
        msg = "Đã gửi yêu cầu dừng Trợ lý Pha chế."
    else:
        if not solisfair_settings.get('channel_id'):
            return jsonify({'status': 'error', 'message': 'Bạn cần cài đặt Channel ID trước.'})
        solisfair_stop_event.clear()
        solisfair_thread = threading.Thread(target=run_solisfair_solver, args=(solisfair_stop_event,), daemon=True)
        solisfair_thread.start()
        msg = "Trợ lý Pha chế đã được kích hoạt."
        
    return jsonify({'status': 'success', 'message': msg})

@app.route("/api/solisfair_update_settings", methods=['POST'])
def api_solisfair_update_settings():
    data = request.get_json()
    solisfair_settings['channel_id'] = data.get('channel_id', '').strip()
    solisfair_settings['bot_id'] = data.get('bot_id', 'main_1')
    # Không cần lưu ngay, hàm save_settings() sẽ được gọi chung
    return jsonify({'status': 'success', 'message': 'Đã cập nhật cài đặt Solisfair.'})

# --- Các API cũ giữ nguyên ---
@app.route("/api/clan_drop_toggle", methods=['POST'])
def api_clan_drop_toggle():
    global auto_clan_drop_settings, auto_clan_drop_thread
    auto_clan_drop_settings['enabled'] = not auto_clan_drop_settings.get('enabled', False)
    if auto_clan_drop_settings['enabled']:
        if not auto_clan_drop_settings.get('channel_id') or not auto_clan_drop_settings.get('ktb_channel_id'):
            auto_clan_drop_settings['enabled'] = False
            return jsonify({'status': 'error', 'message': 'Clan Drop Channel ID and KTB Channel ID must be set first.'})
        
        threading.Thread(target=run_clan_drop_cycle).start()
        
        if auto_clan_drop_thread is None or not auto_clan_drop_thread.is_alive():
            auto_clan_drop_stop_event.clear()
            auto_clan_drop_thread = threading.Thread(target=auto_clan_drop_loop, daemon=True)
            auto_clan_drop_thread.start()
        msg = "Clan Auto Drop ENABLED & First cycle triggered."
    else:
        auto_clan_drop_stop_event.set()
        auto_clan_drop_thread = None
        msg = "Clan Auto Drop DISABLED."
    return jsonify({'status': 'success', 'message': msg})

@app.route("/api/clan_drop_update", methods=['POST'])
def api_clan_drop_update():
    global auto_clan_drop_settings
    data = request.get_json()
    auto_clan_drop_settings['channel_id'] = data.get('channel_id', '').strip()
    auto_clan_drop_settings['ktb_channel_id'] = data.get('ktb_channel_id', '').strip()
    if 'heart_thresholds' in data:
        for key, value in data['heart_thresholds'].items():
            if isinstance(value, int):
                auto_clan_drop_settings.setdefault('heart_thresholds', {})[key] = value
    return jsonify({'status': 'success', 'message': 'Clan Drop settings updated.'})

@app.route("/api/add_server", methods=['POST'])
def api_add_server():
    data = request.get_json()
    name = data.get('name')
    if not name: return jsonify({'status': 'error', 'message': 'Server name is required.'}), 400
    
    new_server = {
        "id": f"server_{uuid.uuid4().hex}", "name": name,
        "main_channel_id": "", "ktb_channel_id": "", "spam_channel_id": "",
        "spam_enabled": False, "spam_message": "", "spam_delay": 10, "last_spam_time": 0
    }
    for i in range(len(main_tokens)):
        bot_num = i + 1
        new_server[f'auto_grab_enabled_{bot_num}'] = False
        new_server[f'heart_threshold_{bot_num}'] = 50

    servers.append(new_server)
    return jsonify({'status': 'success', 'message': f'Server "{name}" added.', 'reload': True})

@app.route("/api/delete_server", methods=['POST'])
def api_delete_server():
    global servers
    server_id = request.get_json().get('server_id')
    server_to_delete = next((s for s in servers if s.get('id') == server_id), None)
    if server_to_delete:
        servers = [s for s in servers if s.get('id') != server_id]
        return jsonify({'status': 'success', 'message': f'Server "{server_to_delete.get("name")}" deleted.', 'reload': True})
    return jsonify({'status': 'error', 'message': 'Server not found.'}), 404

@app.route("/api/update_server_channels", methods=['POST'])
def api_update_server_channels():
    data = request.get_json()
    server = next((s for s in servers if s.get('id') == data.get('server_id')), None)
    if not server: return jsonify({'status': 'error', 'message': 'Server not found.'}), 404
    updated_fields = []
    for field in ['main_channel_id', 'ktb_channel_id', 'spam_channel_id']:
        if field in data:
            server[field] = data[field]
            updated_fields.append(field.replace('_', ' ').title())
    return jsonify({'status': 'success', 'message': f'{", ".join(updated_fields)} updated for {server["name"]}.'})

@app.route("/api/harvest_toggle", methods=['POST'])
def api_harvest_toggle():
    data = request.get_json()
    server = next((s for s in servers if s.get('id') == data.get('server_id')), None)
    node = data.get('node')
    if not server or not node: return jsonify({'status': 'error', 'message': 'Invalid request.'}), 400
    grab_key = f'auto_grab_enabled_{node}'
    threshold_key = f'heart_threshold_{node}'
    server[grab_key] = not server.get(grab_key, False)
    server[threshold_key] = int(data.get('threshold', 50))
    state = "ENABLED" if server[grab_key] else "DISABLED"
    try:
        bot_name = BOT_NAMES[int(node)-1]
    except (ValueError, IndexError):
        bot_name = f"MAIN_{node}"
    msg = f"Card Grab for {bot_name} was {state} on server {server['name']}."
    return jsonify({'status': 'success', 'message': msg})

@app.route("/api/watermelon_toggle", methods=['POST'])
def api_watermelon_toggle():
    global watermelon_grab_states
    data = request.get_json()
    node = data.get('node')
    if not node or node not in watermelon_grab_states:
        return jsonify({'status': 'error', 'message': 'Invalid bot node.'}), 404
    
    watermelon_grab_states[node] = not watermelon_grab_states.get(node, False)
    
    state = "ENABLED" if watermelon_grab_states[node] else "DISABLED"
    try:
        bot_name_index = int(node.split('_')[1]) - 1
        bot_name = BOT_NAMES[bot_name_index] if bot_name_index < len(BOT_NAMES) else f"MAIN_{node}"
    except (IndexError, ValueError):
        bot_name = node.upper()

    msg = f"Global Watermelon Grab was {state} for Node {bot_name}."
    return jsonify({'status': 'success', 'message': msg})

@app.route("/api/broadcast_toggle", methods=['POST'])
def api_broadcast_toggle():
    data = request.get_json()
    server = next((s for s in servers if s.get('id') == data.get('server_id')), None)
    if not server: return jsonify({'status': 'error', 'message': 'Server not found.'}), 404
    server['spam_message'] = data.get("message", "").strip()
    server['spam_delay'] = int(data.get("delay", 10))
    server['spam_enabled'] = not server.get('spam_enabled', False)
    if server['spam_enabled'] and (not server['spam_message'] or not server['spam_channel_id']):
        server['spam_enabled'] = False
        return jsonify({'status': 'error', 'message': f'Spam message/channel required for {server["name"]}.'})
    msg = f"Spam {'ENABLED' if server['spam_enabled'] else 'DISABLED'} for {server['name']}."
    return jsonify({'status': 'success', 'message': msg})

@app.route("/api/reboot_toggle_auto", methods=['POST'])
def api_reboot_toggle_auto():
    global auto_reboot_enabled, auto_reboot_delay, auto_reboot_thread, auto_reboot_stop_event, last_reboot_cycle_time
    data = request.get_json()
    auto_reboot_enabled = not auto_reboot_enabled
    auto_reboot_delay = int(data.get("delay", 3600))
    if auto_reboot_enabled:
        last_reboot_cycle_time = time.time()
        if auto_reboot_thread is None or not auto_reboot_thread.is_alive():
            auto_reboot_stop_event.clear()
            auto_reboot_thread = threading.Thread(target=auto_reboot_loop, daemon=True)
            auto_reboot_thread.start()
        msg = "Global Auto Reboot ENABLED."
    else:
        if auto_reboot_stop_event: auto_reboot_stop_event.set()
        auto_reboot_thread = None
        msg = "Global Auto Reboot DISABLED."
    return jsonify({'status': 'success', 'message': msg})

@app.route("/api/toggle_bot_state", methods=['POST'])
def api_toggle_bot_state():
    target = request.get_json().get('target')
    if target in bot_active_states:
        bot_active_states[target] = not bot_active_states[target]
        state_text = "AWAKENED" if bot_active_states[target] else "DORMANT"
        return jsonify({'status': 'success', 'message': f"Target {target.upper()} set to {state_text}."})
    return jsonify({'status': 'error', 'message': 'Target not found.'}), 404

@app.route("/api/save_settings", methods=['POST'])
def api_save_settings():
    save_settings()
    return jsonify({'status': 'success', 'message': 'Settings saved.'})

@app.route("/status")
def status():
    now = time.time()
    for server in servers:
        server['spam_countdown'] = 0
        if server.get('spam_enabled'):
            pass
        
    with bots_lock:
        main_bot_statuses = [
            {"name": BOT_NAMES[i] if i < len(BOT_NAMES) else f"MAIN_{i+1}", "status": bot is not None, "reboot_id": f"main_{i+1}", "is_active": bot_active_states.get(f"main_{i+1}", False), "type": "main"} 
            for i, bot in enumerate(main_bots)
        ]
        sub_bot_statuses = [
            {"name": acc_names[i] if i < len(acc_names) else f"Sub {i+1}", "status": bot is not None, "reboot_id": f"sub_{i}", "is_active": bot_active_states.get(f"sub_{i}", False), "type": "sub"}
            for i, bot in enumerate(bots)
        ]

    clan_drop_status = {
        "enabled": auto_clan_drop_settings.get("enabled", False),
        "countdown": (auto_clan_drop_settings.get("last_cycle_start_time", 0) + auto_clan_drop_settings.get("cycle_interval", 1800) - now) if auto_clan_drop_settings.get("enabled", False) else 0
    }

    return jsonify({
        'reboot_enabled': auto_reboot_enabled, 
        'reboot_countdown': (last_reboot_cycle_time + auto_reboot_delay - now) if auto_reboot_enabled else 0,
        'bot_statuses': {"main_bots": main_bot_statuses, "sub_accounts": sub_bot_statuses},
        'server_start_time': server_start_time,
        'servers': servers,
        'watermelon_grab_states': watermelon_grab_states,
        'auto_clan_drop_status': clan_drop_status,
        'solisfair_settings': solisfair_settings # <-- THÊM MỚI
    })

# --- MAIN EXECUTION ---
if __name__ == "__main__":
    load_settings()
    
    print("Đang khởi tạo các bot...", flush=True)
    with bots_lock:
        for i, token in enumerate(main_tokens):
            if token.strip():
                bot_num = i + 1
                bot_id = f"main_{bot_num}"
                main_bots.append(create_bot(token.strip(), bot_identifier=bot_num, is_main=True))
                if bot_id not in bot_active_states: bot_active_states[bot_id] = True
                if bot_id not in watermelon_grab_states: watermelon_grab_states[bot_id] = False
                if bot_id not in auto_clan_drop_settings.get('heart_thresholds', {}):
                    auto_clan_drop_settings.setdefault('heart_thresholds', {})[bot_id] = 50
        
        for i, token in enumerate(tokens):
            if token.strip():
                bot_id = f'sub_{i}'
                bots.append(create_bot(token.strip(), bot_identifier=i, is_main=False))
                if bot_id not in bot_active_states: bot_active_states[bot_id] = True

    print("Đang khởi tạo các luồng nền...", flush=True)
    threading.Thread(target=periodic_save_loop, daemon=True).start()
    spam_thread = threading.Thread(target=spam_loop, daemon=True)
    spam_thread.start()
    
    if auto_reboot_enabled:
        auto_reboot_stop_event.clear()
        auto_reboot_thread = threading.Thread(target=auto_reboot_loop, daemon=True)
        auto_reboot_thread.start()

    if auto_clan_drop_settings.get("enabled"):
        auto_clan_drop_stop_event.clear()
        auto_clan_drop_thread = threading.Thread(target=auto_clan_drop_loop, daemon=True)
        auto_clan_drop_thread.start()
    
    port = int(os.environ.get("PORT", 10000))
    print(f"Khởi động Web Server tại http://0.0.0.0:{port}", flush=True)
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
