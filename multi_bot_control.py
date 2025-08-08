# PHIÊN BẢN CẢI TIẾN - HỖ TRỢ N TÀI KHOẢN CHÍNH - SPAM SONG SONG - TÍCH HỢP DROP CLAN - REBOOT AN TOÀN
import discum
import threading
import time
import os
import re
import requests
import json
import random
import traceback
from flask import Flask, request, render_template_string, jsonify
from dotenv import load_dotenv
import uuid
from datetime import datetime, timedelta

load_dotenv()

# --- CẤU HÌNH ---
main_tokens = os.getenv("MAIN_TOKENS").split(",") if os.getenv("MAIN_TOKENS") else []
tokens = os.getenv("TOKENS").split(",") if os.getenv("TOKENS") else []
karuta_id = "646937666251915264"
karibbit_id = "1311684840462225440"
BOT_NAMES = [
    "ALPHA", "xsyx", "sofa", "dont", "ayaya",
    "owo", "astra", "singo", "dia pox", "clam",
    "rambo", "domixi", "dogi", "sicula", "mo turn", "jan taru", "kio sama"
]

# --- BIẾN TRẠNG THÁI ---
bots, acc_names = [], [
    "Shadow-01", "Ghost-02", "Phantom-03", "Wraith-04", "Specter-05",
    "Banshee-06", "Revenant-07", "Spirit-08", "Shade-09", "Apparition-10",
    "Poltergeist-11", "Demon-12", "Fiend-13", "Ghoul-14", "Vampire-15",
    "Zombie-16", "Skeleton-17", "Lich-18"
]
main_bots = []
servers = []
watermelon_grab_states = {}
bot_active_states = {}

# --- Cải tiến: Cấu trúc reboot settings với safety features ---
bot_reboot_settings = {}

# --- Cài đặt cho tính năng tự động drop clan ---
auto_clan_drop_settings = {
    "enabled": False,
    "channel_id": "",
    "ktb_channel_id": "",
    "last_cycle_start_time": 0,
    "cycle_interval": 1800,
    "bot_delay": 140,
    "heart_thresholds": {}
}

# Các biến điều khiển luồng
auto_reboot_stop_event = threading.Event()
auto_clan_drop_stop_event = threading.Event()
spam_thread, auto_reboot_thread, auto_clan_drop_thread = None, None, None
bots_lock = threading.Lock()
server_start_time = time.time()

# --- CẢI TIẾN: Health monitoring ---
bot_health_stats = {}

# --- HÀM LƯU VÀ TẢI CÀI ĐẶT ---
def save_settings():
    """Lưu cài đặt với error handling tốt hơn"""
    api_key = os.getenv("JSONBIN_API_KEY")
    bin_id = os.getenv("JSONBIN_BIN_ID")
    if not api_key or not bin_id:
        #print("[Settings] Missing JSONBin credentials, saving locally instead", flush=True)
        return save_settings_locally()

    settings = {
        'servers': servers,
        'bot_reboot_settings': bot_reboot_settings,
        'bot_active_states': bot_active_states,
        'watermelon_grab_states': watermelon_grab_states,
        'auto_clan_drop_settings': auto_clan_drop_settings,
        'bot_health_stats': bot_health_stats,
        'last_save_time': time.time()
    }
    headers = {'Content-Type': 'application/json', 'X-Master-Key': api_key}
    url = f"https://api.jsonbin.io/v3/b/{bin_id}"

    try:
        req = requests.put(url, json=settings, headers=headers, timeout=15)
        if req.status_code == 200:
            print("[Settings] ✅ Đã lưu cài đặt lên JSONBin.io thành công.", flush=True)
        else:
            print(f"[Settings] ❌ Lỗi khi lưu cài đặt: {req.status_code} - {req.text}", flush=True)
            save_settings_locally()
    except Exception as e:
        print(f"[Settings] ❌ Exception khi lưu cài đặt: {e}", flush=True)
        save_settings_locally()

def save_settings_locally():
    """Backup save to local file"""
    try:
        settings = {
            'servers': servers,
            'bot_reboot_settings': bot_reboot_settings,
            'bot_active_states': bot_active_states,
            'watermelon_grab_states': watermelon_grab_states,
            'auto_clan_drop_settings': auto_clan_drop_settings,
            'last_save_time': time.time()
        }
        with open('backup_settings.json', 'w') as f:
            json.dump(settings, f, indent=2)
        print("[Settings] ✅ Đã lưu backup cài đặt locally", flush=True)
    except Exception as e:
        print(f"[Settings] ❌ Lỗi khi lưu backup: {e}", flush=True)

def load_settings():
    """Tải cài đặt với fallback options"""
    api_key = os.getenv("JSONBIN_API_KEY")
    bin_id = os.getenv("JSONBIN_BIN_ID")

    if api_key and bin_id:
        headers = {'X-Master-Key': api_key}
        url = f"https://api.jsonbin.io/v3/b/{bin_id}/latest"
        try:
            req = requests.get(url, headers=headers, timeout=15)
            if req.status_code == 200:
                settings = req.json().get("record", {})
                if settings and load_settings_from_dict(settings):
                    print("[Settings] ✅ Đã tải cài đặt từ JSONBin.io.", flush=True)
                    return
        except Exception as e:
            print(f"[Settings] ⚠️ Lỗi khi tải từ JSONBin: {e}", flush=True)

    try:
        with open('backup_settings.json', 'r') as f:
            settings = json.load(f)
            if load_settings_from_dict(settings):
                print("[Settings] ✅ Đã tải cài đặt từ backup file.", flush=True)
                return
    except FileNotFoundError:
        print("[Settings] ⚠️ Không tìm thấy backup file.", flush=True)
    except Exception as e:
        print(f"[Settings] ⚠️ Lỗi khi tải backup: {e}", flush=True)

    print("[Settings] 🔧 Khởi tạo với cài đặt mặc định.", flush=True)

def load_settings_from_dict(settings):
    """Helper function to load settings from dictionary"""
    global servers, bot_reboot_settings, bot_active_states, watermelon_grab_states, auto_clan_drop_settings, bot_health_stats
    try:
        servers.clear()
        servers.extend(settings.get('servers', []))
        bot_reboot_settings.update(settings.get('bot_reboot_settings', {}))
        bot_active_states.update(settings.get('bot_active_states', {}))
        watermelon_grab_states.update(settings.get('watermelon_grab_states', {}))

        loaded_clan_settings = settings.get('auto_clan_drop_settings', {})
        if loaded_clan_settings:
            auto_clan_drop_settings.update(loaded_clan_settings)
        if 'heart_thresholds' not in auto_clan_drop_settings:
            auto_clan_drop_settings['heart_thresholds'] = {}

        bot_health_stats.update(settings.get('bot_health_stats', {}))
        return True
    except Exception as e:
        print(f"[Settings] ❌ Lỗi khi parse settings: {e}", flush=True)
        return False

# --- CẢI TIẾN: SAFE REBOOT FUNCTIONS ---
def safe_reboot_bot(bot_id):
    """Reboot bot một cách an toàn với proper error handling"""
    try:
        print(f"[Safe Reboot] 🔄 Bắt đầu reboot bot {bot_id}...", flush=True)
        if not isinstance(bot_id, str) or '_' not in bot_id or not bot_id.startswith('main_'):
            raise ValueError(f"Invalid bot_id format: {bot_id}")

        bot_index = int(bot_id.split('_')[1]) - 1
        if not (0 <= bot_index < len(main_tokens)):
            raise ValueError(f"Bot index out of range: {bot_index}")

        token = main_tokens[bot_index].strip()
        if not token: raise ValueError(f"Empty token for bot {bot_id}")

        bot_name = BOT_NAMES[bot_index] if bot_index < len(BOT_NAMES) else f"MAIN_{bot_index+1}"

        current_bot = main_bots[bot_index] if bot_index < len(main_bots) else None
        if current_bot and not should_reboot_bot(current_bot, bot_id):
            settings = bot_reboot_settings.get(bot_id, {})
            settings['next_reboot_time'] = time.time() + settings.get('delay', 3600)
            print(f"[Safe Reboot] ✅ Bot {bot_name} khỏe mạnh, hoãn reboot", flush=True)
            return True

        start_time = time.time()
        if bot_index < len(main_bots) and main_bots[bot_index]:
            try:
                print(f"[Safe Reboot] 📴 Đóng connection cũ cho {bot_name}...", flush=True)
                main_bots[bot_index].gateway.close()
                main_bots[bot_index] = None
            except Exception as e:
                print(f"[Safe Reboot] ⚠️ Lỗi khi đóng connection: {e}", flush=True)

        time.sleep(random.uniform(20, 40))

        settings = bot_reboot_settings.get(bot_id, {})
        failure_count = settings.get('failure_count', 0)
        if failure_count > 0:
            extra_delay = min(failure_count * 30, 300)
            print(f"[Safe Reboot] ⏳ Delay thêm {extra_delay}s do {failure_count} lần thất bại", flush=True)
            time.sleep(extra_delay)

        print(f"[Safe Reboot] 🔌 Tạo connection mới cho {bot_name}...", flush=True)
        new_bot = create_bot(token, bot_identifier=(bot_index + 1), is_main=True)

        if not new_bot:
            raise Exception("Failed to create new bot instance")

        with bots_lock:
            while len(main_bots) <= bot_index: main_bots.append(None)
            main_bots[bot_index] = new_bot

        settings['next_reboot_time'] = time.time() + settings.get('delay', 3600)
        settings['failure_count'] = 0
        settings['last_reboot_time'] = time.time()
        
        if bot_id in bot_health_stats:
            bot_health_stats[bot_id]['consecutive_failures'] = 0

        duration = time.time() - start_time
        print(f"[Safe Reboot] ✅ Reboot thành công {bot_name} trong {duration:.1f}s", flush=True)
        return True
    except Exception as e:
        print(f"[Safe Reboot] ❌ Reboot thất bại cho {bot_id}: {e}\n{traceback.format_exc()}", flush=True)
        handle_reboot_failure(bot_id)
        return False

def handle_reboot_failure(bot_id):
    """Xử lý khi reboot thất bại"""
    try:
        if bot_id not in bot_reboot_settings:
            bot_reboot_settings[bot_id] = {'enabled': True, 'delay': 3600, 'failure_count': 0, 'next_reboot_time': 0}
        
        settings = bot_reboot_settings[bot_id]
        failure_count = settings.get('failure_count', 0) + 1
        settings['failure_count'] = failure_count

        base_delay = max(settings.get('delay', 3600), 300)
        backoff_multiplier = min(2 ** failure_count, 8)
        backoff_delay = base_delay * backoff_multiplier
        settings['next_reboot_time'] = time.time() + backoff_delay

        print(f"[Safe Reboot] 🔴 Failure #{failure_count} cho {bot_id}. Next attempt in {backoff_delay}s", flush=True)

        if failure_count >= 5:
            settings['enabled'] = False
            print(f"[Safe Reboot] ❌ Tắt auto-reboot cho {bot_id} sau {failure_count} lần thất bại", flush=True)
    except Exception as e:
        print(f"[Safe Reboot] ❌ Lỗi trong handle_reboot_failure: {e}", flush=True)

def should_reboot_bot(bot, bot_id):
    """Quyết định có nên reboot bot không"""
    if not bot:
        print(f"[Health Check] 🔴 Bot {bot_id} không tồn tại, cần reboot", flush=True)
        return True
    try:
        is_healthy = check_bot_health(bot, bot_id)
        if is_healthy:
            return False
        
        stats = bot_health_stats.get(bot_id, {})
        consecutive_failures = stats.get('consecutive_failures', 0)
        if consecutive_failures >= 3:
            print(f"[Health Check] 🔴 Bot {bot_id} có {consecutive_failures} lần check lỗi, cần reboot", flush=True)
            return True
        return False
    except Exception as e:
        print(f"[Health Check] ❌ Lỗi khi kiểm tra bot {bot_id}: {e}", flush=True)
        return True

def check_bot_health(bot, bot_id):
    """Kiểm tra sức khỏe của bot"""
    try:
        if not bot or not hasattr(bot, 'gateway') or not bot.gateway.connected:
            is_connected = False
        else:
            is_connected = True

        if bot_id not in bot_health_stats:
            bot_health_stats[bot_id] = {'consecutive_failures': 0}
        
        stats = bot_health_stats[bot_id]
        if is_connected:
            stats['consecutive_failures'] = 0
            return True
        else:
            stats['consecutive_failures'] = stats.get('consecutive_failures', 0) + 1
            print(f"[Health Check] ⚠️ Bot {bot_id} gateway not connected ({stats['consecutive_failures']} failures)", flush=True)
            return False
    except Exception as e:
        print(f"[Health Check] ❌ Bot {bot_id} health check failed: {e}", flush=True)
        if bot_id in bot_health_stats:
            bot_health_stats[bot_id]['consecutive_failures'] = bot_health_stats[bot_id].get('consecutive_failures', 0) + 1
        return False

def auto_reboot_loop():
    """Vòng lặp reboot cải tiến"""
    print("[Safe Reboot] 🚀 Khởi động luồng tự động reboot", flush=True)
    last_reboot_time = 0
    while not auto_reboot_stop_event.is_set():
        try:
            now = time.time()
            if now - last_reboot_time < 300: # Rate limit: 5 phút
                auto_reboot_stop_event.wait(timeout=30)
                continue

            bots_to_reboot = [bot_id for bot_id, s in bot_reboot_settings.items() if s.get('enabled') and now >= s.get('next_reboot_time', 0)]
            
            if not bots_to_reboot:
                auto_reboot_stop_event.wait(timeout=60)
                continue

            bot_to_reboot = bots_to_reboot[0]
            print(f"[Safe Reboot] 🎯 Chọn reboot bot: {bot_to_reboot}", flush=True)
            if safe_reboot_bot(bot_to_reboot):
                last_reboot_time = now
                wait_time = random.uniform(300, 600) # 5-10 phút
                print(f"[Safe Reboot] ⏳ Chờ {wait_time:.0f}s trước reboot tiếp theo", flush=True)
                auto_reboot_stop_event.wait(timeout=wait_time)
            else:
                auto_reboot_stop_event.wait(timeout=120)

        except Exception as e:
            print(f"[Safe Reboot] ❌ CRITICAL ERROR in auto_reboot_loop: {e}\n{traceback.format_exc()}", flush=True)
            auto_reboot_stop_event.wait(timeout=300)

# --- CÁC HÀM LOGIC BOT (ĐÃ SỬA LỖI) ---

def create_bot(token, bot_identifier, is_main=False):
    """Tạo bot với trình xử lý sự kiện an toàn, đã sửa lỗi AttributeError"""
    try:
        print(f"[Bot Creation] 🔌 Đang tạo bot {bot_identifier} ({'main' if is_main else 'sub'})...", flush=True)
        bot = discum.Client(token=token, log=False)

        @bot.gateway.command
        def on_ready(resp):
            if hasattr(resp.event, 'ready') and resp.event.ready:
                user = resp.raw.get("user", {})
                if isinstance(user, dict) and (user_id := user.get("id")):
                    bot_name = BOT_NAMES[bot_identifier-1] if is_main and bot_identifier-1 < len(BOT_NAMES) else f"Bot {bot_identifier}"
                    print(f"[Bot Creation] ✅ Đã đăng nhập: {user_id} ({bot_name})", flush=True)
                    if is_main:
                        bot_id = f"main_{bot_identifier}"
                        if bot_id not in bot_health_stats:
                            bot_health_stats[bot_id] = {'consecutive_failures': 0}

        if is_main:
            @bot.gateway.command
            def on_gateway_event(resp):
                # Xử lý tin nhắn mới
                if hasattr(resp.event, 'message'):
                    msg = resp.parsed.auto()
                    author_object = msg.get("author")
                    
                    # >>>>> DÒNG SỬA LỖI NẰM Ở ĐÂY <<<<<<<
                    if isinstance(author_object, dict):
                        author_id = author_object.get("id")
                        content = msg.get("content", "").lower()
                        
                        if author_id == karuta_id and "dropping" in content:
                            if msg.get("mentions"):
                                handle_clan_drop(bot, msg, bot_identifier)
                            else:
                                handle_grab(bot, msg, bot_identifier)
                        
                        elif author_id == karibbit_id and any(k in content for k in ["drop", "grab", "pick"]):
                            handle_grab(bot, msg, bot_identifier)

                # Xử lý reaction mới
                if hasattr(resp.event, 'message_reaction_add'):
                    reaction_data = resp.parsed.auto()
                    emoji = reaction_data.get("emoji", {})
                    emoji_name = emoji.get("name", "")
                    
                    if any(p in emoji_name.lower() for p in ['🍉', 'watermelon', 'dua']):
                        print(f"[WATERMELON REACTION | Bot {bot_identifier}] 🍉 Detected: {emoji_name}", flush=True)
                        if watermelon_grab_states.get(f'main_{bot_identifier}', False):
                            channel_id = reaction_data.get("channel_id")
                            message_id = reaction_data.get("message_id")
                            threading.Thread(target=lambda: quick_watermelon_grab(bot, channel_id, message_id, bot_identifier), daemon=True).start()

        threading.Thread(target=bot.gateway.run, daemon=True).start()
        time.sleep(2)
        return bot
    except Exception as e:
        print(f"[Bot Creation] ❌ Lỗi tạo bot {bot_identifier}: {e}\n{traceback.format_exc()}", flush=True)
        return None

def quick_watermelon_grab(bot, channel_id, message_id, bot_num):
    """Quick watermelon grab khi detect được reaction"""
    try:
        print(f"[QUICK WATERMELON | Bot {bot_num}] 🚀 Attempting quick grab...", flush=True)
        for emoji in ['🍉', '\U0001f349']:
            try:
                bot.addReaction(channel_id, message_id, emoji)
                print(f"[QUICK WATERMELON | Bot {bot_num}] ✅ Success!", flush=True)
                return True
            except: continue
        return False
    except: return False

def handle_clan_drop(bot, msg, bot_num):
    """Xử lý clan drop"""
    if not (auto_clan_drop_settings.get("enabled") and auto_clan_drop_settings.get("ktb_channel_id")): return
    if msg.get("channel_id") != auto_clan_drop_settings.get("channel_id"): return
    
    last_drop_msg_id = msg["id"]
    ktb_channel_id = auto_clan_drop_settings["ktb_channel_id"]
    channel_id = msg.get("channel_id")
    
    def grab_handler():
        for _ in range(8):
            time.sleep(0.5)
            try:
                messages = bot.getMessages(channel_id, num=5).json()
                if not isinstance(messages, list): continue
                for msg_item in messages:
                    if msg_item.get("author", {}).get("id") == karibbit_id and int(msg_item.get("id")) > int(last_drop_msg_id):
                        embeds = msg_item.get("embeds", [])
                        if not embeds or '♡' not in embeds[0].get("description", ""): continue
                        
                        lines = embeds[0]['description'].split('\n')[:3]
                        heart_numbers = [int(m.group(1)) if (m := re.search(r'♡(\d+)', l)) else 0 for l in lines]
                        if not any(heart_numbers): break

                        max_num = max(heart_numbers)
                        threshold = auto_clan_drop_settings.get("heart_thresholds", {}).get(f'main_{bot_num}', 50)
                        
                        if max_num >= threshold:
                            max_index = heart_numbers.index(max_num)
                            delays = {1:[0.4,1.4,2.1], 2:[0.7,1.8,2.4], 3:[0.7,1.8,2.4], 4:[0.8,1.9,2.5]}
                            delay = delays.get(bot_num, [0.9,2.0,2.6])[max_index]
                            emoji = ["1️⃣", "2️⃣", "3️⃣"][max_index]

                            print(f"[CLAN DROP | Bot {bot_num}] Chọn {max_num}♡ -> {emoji} sau {delay}s", flush=True)
                            
                            def grab_action():
                                try:
                                    bot.addReaction(channel_id, last_drop_msg_id, emoji)
                                    time.sleep(1.2)
                                    bot.sendMessage(ktb_channel_id, "kt b")
                                except Exception as e: print(f"[CLAN DROP | Bot {bot_num}] ❌ Lỗi grab: {e}", flush=True)
                            
                            threading.Timer(delay, grab_action).start()
                            return
            except: continue
    threading.Thread(target=grab_handler, daemon=True).start()

def handle_grab(bot, msg, bot_num):
    """Xử lý card drop và watermelon grab"""
    channel_id = msg.get("channel_id")
    target_server = next((s for s in servers if s.get('main_channel_id') == channel_id), None)
    if not target_server: return

    auto_grab_enabled = target_server.get(f'auto_grab_enabled_{bot_num}', False)
    watermelon_grab_enabled = watermelon_grab_states.get(f'main_{bot_num}', False)
    if not auto_grab_enabled and not watermelon_grab_enabled: return

    last_drop_msg_id = msg["id"]
    
    def grab_handler():
        if auto_grab_enabled:
            card_grab_logic(bot, channel_id, last_drop_msg_id, target_server, bot_num)
        if watermelon_grab_enabled:
            polling_watermelon_grab(bot, channel_id, last_drop_msg_id, bot_num)

    threading.Thread(target=grab_handler, daemon=True).start()

def card_grab_logic(bot, channel_id, last_drop_msg_id, server, bot_num):
    ktb_channel_id = server.get('ktb_channel_id')
    heart_threshold = server.get(f'heart_threshold_{bot_num}', 50)
    
    for _ in range(6):
        time.sleep(0.5)
        try:
            messages = bot.getMessages(channel_id, num=5).json()
            if not isinstance(messages, list): continue
            for msg_item in messages:
                if msg_item.get("author", {}).get("id") == karibbit_id and int(msg_item.get("id")) > int(last_drop_msg_id):
                    embeds = msg_item.get("embeds", [])
                    if not embeds or '♡' not in embeds[0].get("description", ""): continue
                    
                    lines = embeds[0]['description'].split('\n')[:3]
                    heart_numbers = [int(m.group(1)) if (m := re.search(r'♡(\d+)', l)) else 0 for l in lines]
                    if not any(heart_numbers): break

                    max_num = max(heart_numbers)
                    if max_num >= heart_threshold:
                        max_index = heart_numbers.index(max_num)
                        delays = {1:[0.4,1.4,2.1], 2:[0.7,1.8,2.4], 3:[0.7,1.8,2.4], 4:[0.8,1.9,2.5]}
                        delay = delays.get(bot_num, [0.9,2.0,2.6])[max_index]
                        emoji = ["1️⃣", "2️⃣", "3️⃣"][max_index]

                        print(f"[CARD GRAB | Bot {bot_num}] ✅ Found: {max_num}♡ -> {emoji} after {delay}s", flush=True)
                        
                        def grab_action():
                            try:
                                bot.addReaction(channel_id, last_drop_msg_id, emoji)
                                if ktb_channel_id:
                                    time.sleep(1.2)
                                    bot.sendMessage(ktb_channel_id, "kt b")
                            except Exception as e: print(f"[CARD GRAB | Bot {bot_num}] ❌ Grab error: {e}", flush=True)
                        
                        threading.Timer(delay, grab_action).start()
                        return
        except: continue

def polling_watermelon_grab(bot, channel_id, message_id, bot_num):
    """Rà quét tìm dưa hấu"""
    start_time = time.time()
    while time.time() - start_time < 20:
        try:
            msg_data = bot.getMessage(channel_id, message_id).json()
            target_message = msg_data[0] if isinstance(msg_data, list) else msg_data
            
            if target_message and 'reactions' in target_message:
                for reaction in target_message['reactions']:
                    emoji_name = reaction.get('emoji', {}).get('name', '')
                    if any(p in emoji_name.lower() for p in ['🍉', 'watermelon', 'dua']):
                        print(f"[POLLING WATERMELON | Bot {bot_num}] 🎯 FOUND!", flush=True)
                        quick_watermelon_grab(bot, channel_id, message_id, bot_num)
                        return
            time.sleep(0.25)
        except: time.sleep(0.3)

# --- CÁC VÒNG LẶP NỀN ---
def run_clan_drop_cycle():
    """Chạy một chu kỳ clan drop"""
    print("[Clan Drop] 🚀 Bắt đầu chu kỳ drop clan.", flush=True)
    channel_id = auto_clan_drop_settings.get("channel_id")
    with bots_lock:
        active_bots = [(b, i + 1) for i, b in enumerate(main_bots) if b and bot_active_states.get(f'main_{i+1}', False)]
    
    if not active_bots:
        print("[Clan Drop] ⚠️ Không có bot chính nào hoạt động.", flush=True)
        return

    for bot, bot_num in active_bots:
        if auto_clan_drop_stop_event.is_set(): break
        try:
            bot.sendMessage(channel_id, "kd")
            delay = auto_clan_drop_settings.get("bot_delay", 140)
            time.sleep(random.uniform(delay * 0.8, delay * 1.2))
        except Exception as e:
            print(f"[Clan Drop] ❌ Lỗi gửi 'kd' từ bot {bot_num}: {e}", flush=True)
    
    auto_clan_drop_settings["last_cycle_start_time"] = time.time()
    save_settings()

def auto_clan_drop_loop():
    """Vòng lặp tự động clan drop"""
    while not auto_clan_drop_stop_event.is_set():
        try:
            settings = auto_clan_drop_settings
            if settings.get("enabled") and (time.time() - settings.get("last_cycle_start_time", 0)) >= settings.get("cycle_interval", 1800):
                run_clan_drop_cycle()
            auto_clan_drop_stop_event.wait(60)
        except Exception as e:
            print(f"[Clan Drop] ❌ ERROR in auto_clan_drop_loop: {e}", flush=True)
            time.sleep(60)

def spam_loop():
    """Quản lý các luồng spam"""
    active_threads = {}
    while True:
        try:
            current_ids = {s['id'] for s in servers}
            for server_id in list(active_threads.keys()):
                if server_id not in current_ids:
                    print(f"[Spam Control] 🛑 Dừng luồng spam cho server đã xóa: {server_id}", flush=True)
                    active_threads.pop(server_id)[1].set()
            
            for server in servers:
                server_id = server.get('id')
                is_on = server.get('spam_enabled') and server.get('spam_message') and server.get('spam_channel_id')
                if is_on and server_id not in active_threads:
                    print(f"[Spam Control] 🚀 Bắt đầu luồng spam cho server: {server.get('name')}", flush=True)
                    stop_event = threading.Event()
                    thread = threading.Thread(target=spam_for_server, args=(server, stop_event), daemon=True)
                    thread.start()
                    active_threads[server_id] = (thread, stop_event)
                elif not is_on and server_id in active_threads:
                    print(f"[Spam Control] 🛑 Dừng luồng spam cho server: {server.get('name')}", flush=True)
                    active_threads.pop(server_id)[1].set()
            time.sleep(5)
        except Exception as e:
            print(f"[Spam Control] ❌ ERROR in spam_loop_manager: {e}", flush=True)

def spam_for_server(server_config, stop_event):
    """Luồng spam cho một server cụ thể"""
    server_name = server_config.get('name')
    channel_id = server_config.get('spam_channel_id')
    message = server_config.get('spam_message')
    delay = server_config.get('spam_delay', 10)
    
    while not stop_event.is_set():
        try:
            with bots_lock:
                active_bots = [b for i, b in enumerate(main_bots) if b and bot_active_states.get(f'main_{i+1}', False)]
                active_bots.extend([b for i, b in enumerate(bots) if b and bot_active_states.get(f'sub_{i}', False)])
            
            for bot in active_bots:
                if stop_event.is_set(): break
                try: bot.sendMessage(channel_id, message); time.sleep(random.uniform(1.5, 2.5))
                except: pass
            
            server_config[f"last_spam_time_{server_name.replace(' ', '_')}"] = time.time()
            stop_event.wait(random.uniform(delay * 0.9, delay * 1.1))
        except Exception as e:
            print(f"[Spam] ❌ ERROR in spam_for_server {server_name}: {e}", flush=True)
            stop_event.wait(10)

def periodic_save_loop():
    """Lưu cài đặt định kỳ"""
    while True:
        time.sleep(1800)
        save_settings()

def health_monitoring_loop():
    """Theo dõi sức khỏe bot"""
    print("[Health Monitor] 🏥 Khởi động health monitoring", flush=True)
    while True:
        try:
            with bots_lock:
                for i, bot in enumerate(main_bots):
                    if bot: check_bot_health(bot, f"main_{i+1}")
            time.sleep(300)
        except: time.sleep(60)

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
                         <div>🎯 Reboot Strategy: One-at-a-time with 20-40s cleanup delay</div>
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

                        // Update health indicator
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
            if (button.classList.contains('bot-reboot-toggle')) {
                const botId = button.dataset.botId;
                const delayInput = document.querySelector(`.bot-reboot-delay[data-bot-id="${botId}"]`);
                postData('/api/bot_reboot_toggle', { bot_id: botId, delay: delayInput.value });
                return;
            }
            if (button.classList.contains('btn-toggle-state')) {
                postData('/api/toggle_bot_state', { target: button.dataset.target });
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
                postData('/api/watermelon_toggle', { node: button.dataset.node });
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
    main_bots_info = [{"id": i + 1, "name": BOT_NAMES[i] if i < len(BOT_NAMES) else f"MAIN_{i+1}"} for i in range(len(main_tokens))]
    return render_template_string(HTML_TEMPLATE, servers=sorted_servers, main_bots_info=main_bots_info, auto_clan_drop_settings=auto_clan_drop_settings)

@app.route("/api/clan_drop_toggle", methods=['POST'])
def api_clan_drop_toggle():
    global auto_clan_drop_thread
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
        msg = "✅ Clan Auto Drop ENABLED & First cycle triggered."
    else:
        auto_clan_drop_stop_event.set()
        auto_clan_drop_thread = None
        msg = "🛑 Clan Auto Drop DISABLED."
    return jsonify({'status': 'success', 'message': msg})

@app.route("/api/clan_drop_update", methods=['POST'])
def api_clan_drop_update():
    data = request.get_json()
    auto_clan_drop_settings['channel_id'] = data.get('channel_id', '').strip()
    auto_clan_drop_settings['ktb_channel_id'] = data.get('ktb_channel_id', '').strip()
    thresholds = data.get('heart_thresholds', {})
    if isinstance(thresholds, dict):
        auto_clan_drop_settings['heart_thresholds'] = {k: int(v) for k, v in thresholds.items()}
    return jsonify({'status': 'success', 'message': '💾 Clan Drop settings updated.'})

@app.route("/api/add_server", methods=['POST'])
def api_add_server():
    data = request.get_json()
    name = data.get('name')
    if not name: return jsonify({'status': 'error', 'message': 'Server name is required.'}), 400
    new_server = {"id": f"server_{uuid.uuid4().hex}", "name": name, "main_channel_id": "", "ktb_channel_id": "", "spam_channel_id": "", "spam_enabled": False, "spam_message": "", "spam_delay": 10}
    for i in range(len(main_tokens)):
        bot_num = i + 1
        new_server[f'auto_grab_enabled_{bot_num}'] = False
        new_server[f'heart_threshold_{bot_num}'] = 50
    servers.append(new_server)
    return jsonify({'status': 'success', 'message': f'✅ Server "{name}" added.', 'reload': True})

@app.route("/api/delete_server", methods=['POST'])
def api_delete_server():
    global servers
    server_id = request.get_json().get('server_id')
    server_to_delete = next((s for s in servers if s.get('id') == server_id), None)
    if server_to_delete:
        servers = [s for s in servers if s.get('id') != server_id]
        return jsonify({'status': 'success', 'message': f'🗑️ Server "{server_to_delete.get("name")}" deleted.', 'reload': True})
    return jsonify({'status': 'error', 'message': 'Server not found.'}), 404

@app.route("/api/update_server_channels", methods=['POST'])
def api_update_server_channels():
    data = request.get_json()
    server = next((s for s in servers if s.get('id') == data.get('server_id')), None)
    if not server: return jsonify({'status': 'error', 'message': 'Server not found.'}), 404
    for field in ['main_channel_id', 'ktb_channel_id', 'spam_channel_id']:
        if field in data: server[field] = data[field]
    return jsonify({'status': 'success', 'message': f'🔧 Channels updated for {server["name"]}.'})

@app.route("/api/harvest_toggle", methods=['POST'])
def api_harvest_toggle():
    data = request.get_json()
    server = next((s for s in servers if s.get('id') == data.get('server_id')), None)
    node = data.get('node')
    if not server or not node: return jsonify({'status': 'error', 'message': 'Invalid request.'}), 400
    grab_key = f'auto_grab_enabled_{node}'
    server[grab_key] = not server.get(grab_key, False)
    server[f'heart_threshold_{node}'] = int(data.get('threshold', 50))
    bot_name = BOT_NAMES[int(node)-1] if int(node)-1 < len(BOT_NAMES) else f"MAIN_{node}"
    status = 'ENABLED' if server[grab_key] else 'DISABLED'
    return jsonify({'status': 'success', 'message': f"🎯 Card Grab for {bot_name} {status} on {server['name']}."})

@app.route("/api/watermelon_toggle", methods=['POST'])
def api_watermelon_toggle():
    data = request.get_json()
    node = data.get('node')
    if not node or node not in watermelon_grab_states: return jsonify({'status': 'error', 'message': 'Invalid bot node.'}), 404
    watermelon_grab_states[node] = not watermelon_grab_states.get(node, False)
    bot_name_index = int(node.split('_')[1]) - 1
    bot_name = BOT_NAMES[bot_name_index] if bot_name_index < len(BOT_NAMES) else node.upper()
    status = 'ENABLED' if watermelon_grab_states[node] else 'DISABLED'
    return jsonify({'status': 'success', 'message': f"🍉 Global Watermelon Grab {status} for {bot_name}."})

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
        return jsonify({'status': 'error', 'message': f'❌ Spam message/channel required for {server["name"]}.'})
    status = 'ENABLED' if server['spam_enabled'] else 'DISABLED'
    return jsonify({'status': 'success', 'message': f"📢 Auto Broadcast {status} for {server['name']}."})

@app.route("/api/bot_reboot_toggle", methods=['POST'])
def api_bot_reboot_toggle():
    global auto_reboot_thread
    data = request.get_json()
    bot_id = data.get('bot_id')
    delay = int(data.get("delay", 3600))
    if not bot_id or bot_id not in bot_reboot_settings: return jsonify({'status': 'error', 'message': 'Invalid Bot ID.'}), 400

    settings = bot_reboot_settings[bot_id]
    settings['enabled'] = not settings.get('enabled', False)
    settings['delay'] = delay
    settings['failure_count'] = 0

    bot_name_index = int(bot_id.split('_')[1]) - 1
    bot_name = BOT_NAMES[bot_name_index] if bot_name_index < len(BOT_NAMES) else bot_id
    
    if settings['enabled']:
        settings['next_reboot_time'] = time.time() + delay
        if auto_reboot_thread is None or not auto_reboot_thread.is_alive():
            auto_reboot_stop_event.clear()
            auto_reboot_thread = threading.Thread(target=auto_reboot_loop, daemon=True)
            auto_reboot_thread.start()
        msg = f"🔄 Safe Auto-Reboot ENABLED for {bot_name} (every {delay}s)."
    else:
        settings['next_reboot_time'] = 0
        msg = f"🛑 Auto-Reboot DISABLED for {bot_name}."
    return jsonify({'status': 'success', 'message': msg})

@app.route("/api/toggle_bot_state", methods=['POST'])
def api_toggle_bot_state():
    target = request.get_json().get('target')
    if target in bot_active_states:
        bot_active_states[target] = not bot_active_states[target]
        state_text = "🟢 ONLINE" if bot_active_states[target] else "🔴 OFFLINE"
        return jsonify({'status': 'success', 'message': f"Bot {target.upper()} set to {state_text}"})
    return jsonify({'status': 'error', 'message': 'Target not found.'}), 404

@app.route("/api/save_settings", methods=['POST'])
def api_save_settings():
    save_settings()
    return jsonify({'status': 'success', 'message': '💾 Settings saved.'})

@app.route("/status")
def status():
    now = time.time()
    servers_copy = json.loads(json.dumps(servers))
    for server in servers_copy:
        last_spam_key = f"last_spam_time_{server.get('name', '').replace(' ', '_')}"
        if server.get('spam_enabled'):
            countdown = (server.get(last_spam_key, 0) + server.get('spam_delay', 10)) - now
            server['spam_countdown'] = max(0, countdown)
        else: server['spam_countdown'] = 0

    with bots_lock:
        main_bot_statuses = []
        for i, bot in enumerate(main_bots):
            bot_id = f"main_{i+1}"
            bot_name = BOT_NAMES[i] if i < len(BOT_NAMES) else f"MAIN_{i+1}"
            health_status = 'good'
            if bot_id in bot_health_stats:
                failures = bot_health_stats[bot_id].get('consecutive_failures', 0)
                if failures >= 3: health_status = 'bad'
                elif failures > 0: health_status = 'warning'
            main_bot_statuses.append({"name": bot_name, "reboot_id": bot_id, "is_active": bot_active_states.get(bot_id, False), "type": "main", "health_status": health_status})
        
        sub_bot_statuses = [{"name": acc_names[i] if i < len(acc_names) else f"Sub {i+1}", "reboot_id": f"sub_{i}", "is_active": bot_active_states.get(f"sub_{i}", False), "type": "sub", "health_status": "good"} for i, bot in enumerate(bots)]

    clan_drop_status = {"enabled": auto_clan_drop_settings.get("enabled", False), "countdown": (auto_clan_drop_settings.get("last_cycle_start_time", 0) + auto_clan_drop_settings.get("cycle_interval", 1800) - now) if auto_clan_drop_settings.get("enabled") else 0}
    reboot_settings_with_countdown = {bot_id: {**s, 'countdown': max(0, s.get('next_reboot_time', 0) - now) if s.get('enabled') else 0} for bot_id, s in bot_reboot_settings.items()}

    return jsonify({'bot_reboot_settings': reboot_settings_with_countdown, 'bot_statuses': {"main_bots": main_bot_statuses, "sub_accounts": sub_bot_statuses}, 'server_start_time': server_start_time, 'servers': servers_copy, 'watermelon_grab_states': watermelon_grab_states, 'auto_clan_drop_status': clan_drop_status})

# --- MAIN EXECUTION ---
if __name__ == "__main__":
    print("🚀 Shadow Network Control - Enhanced Version Starting...", flush=True)
    load_settings()
    print("🔌 Initializing bots...", flush=True)
    
    with bots_lock:
        for i, token in enumerate(main_tokens):
            if token.strip():
                bot_num, bot_id = i + 1, f"main_{i+1}"
                main_bots.append(create_bot(token.strip(), bot_identifier=bot_num, is_main=True))
                if bot_id not in bot_active_states: bot_active_states[bot_id] = True
                if bot_id not in watermelon_grab_states: watermelon_grab_states[bot_id] = False
                if bot_id not in auto_clan_drop_settings.get('heart_thresholds', {}): auto_clan_drop_settings.setdefault('heart_thresholds', {})[bot_id] = 50
                if bot_id not in bot_reboot_settings: bot_reboot_settings[bot_id] = {'enabled': False, 'delay': 3600, 'next_reboot_time': 0, 'failure_count': 0, 'last_reboot_time': 0}

        for i, token in enumerate(tokens):
            if token.strip():
                bot_id = f'sub_{i}'
                bots.append(create_bot(token.strip(), bot_identifier=i, is_main=False))
                if bot_id not in bot_active_states: bot_active_states[bot_id] = True

    print("🔧 Starting background threads...", flush=True)
    threading.Thread(target=periodic_save_loop, daemon=True).start()
    threading.Thread(target=health_monitoring_loop, daemon=True).start()
    threading.Thread(target=spam_loop, daemon=True).start()

    if any(s.get('enabled') for s in bot_reboot_settings.values()):
        auto_reboot_stop_event.clear()
        auto_reboot_thread = threading.Thread(target=auto_reboot_loop, daemon=True)
        auto_reboot_thread.start()

    if auto_clan_drop_settings.get("enabled"):
        auto_clan_drop_stop_event.clear()
        auto_clan_drop_thread = threading.Thread(target=auto_clan_drop_loop, daemon=True)
        auto_clan_drop_thread.start()

    port = int(os.environ.get("PORT", 10000))
    print(f"🌐 Starting Web Server at http://0.0.0.0:{port}", flush=True)
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
