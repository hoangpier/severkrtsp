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
bot_reboot_settings = {}  # Sẽ được init với failure tracking

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
bot_health_stats = {}  # Track bot performance metrics
bot_connection_health = {}
last_activity_time = {}
connection_check_interval = 30  # Check mỗi 30 giây

# --- HÀM LƯU VÀ TẢI CÀI ĐẶT ---
def save_settings():
    """Lưu cài đặt với error handling tốt hơn"""
    api_key = os.getenv("JSONBIN_API_KEY")
    bin_id = os.getenv("JSONBIN_BIN_ID")
    if not api_key or not bin_id:
        print("[Settings] Missing JSONBin credentials, saving locally instead", flush=True)
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
            save_settings_locally()  # Fallback to local save
    except Exception as e:
        print(f"[Settings] ❌ Exception khi lưu cài đặt: {e}", flush=True)
        save_settings_locally()  # Fallback to local save

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
    global servers, bot_reboot_settings, bot_active_states, watermelon_grab_states, auto_clan_drop_settings, bot_health_stats

    api_key = os.getenv("JSONBIN_API_KEY")
    bin_id = os.getenv("JSONBIN_BIN_ID")

    # Try JSONBin first
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

    # Fallback to local file
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

    # Initialize with defaults
    print("[Settings] 🔧 Khởi tạo với cài đặt mặc định.", flush=True)
    initialize_default_settings()

def load_settings_from_dict(settings):
    """Helper function to load settings from dictionary"""
    global servers, bot_reboot_settings, bot_active_states, watermelon_grab_states, auto_clan_drop_settings, bot_health_stats
    try:
        servers.extend(settings.get('servers', []))
        bot_reboot_settings.update(settings.get('bot_reboot_settings', {}))
        bot_active_states.update(settings.get('bot_active_states', {}))
        watermelon_grab_states.update(settings.get('watermelon_grab_states', {}))

        loaded_clan_settings = settings.get('auto_clan_drop_settings', {})
        if loaded_clan_settings:
            if 'heart_thresholds' not in loaded_clan_settings:
                loaded_clan_settings['heart_thresholds'] = {}
            auto_clan_drop_settings.update(loaded_clan_settings)

        bot_health_stats.update(settings.get('bot_health_stats', {}))
        return True
    except Exception as e:
        print(f"[Settings] ❌ Lỗi khi parse settings: {e}", flush=True)
        return False

def initialize_default_settings():
    """Initialize default settings"""
    # Sẽ được gọi sau khi khởi tạo bots
    pass

# --- CONNECTION HEALTH CHECK & AUTO RECOVERY SYSTEM ---
def check_bot_health(bot, bot_id):
    """Kiểm tra sức khỏe bot với connection validation chi tiết (Enhanced & Fixed)"""
    try:
        if not bot:
            # Ghi nhận lỗi cho bot không tồn tại
            if bot_id not in bot_health_stats:
                bot_health_stats[bot_id] = {'consecutive_failures': 0}
            bot_health_stats[bot_id]['consecutive_failures'] += 1
            print(f"[Health Check] 🔴 Bot {bot_id} is None", flush=True)
            return False

        start_time = time.time()

        # Test 1: Gateway connection check
        gateway_connected = False
        gateway_error = None

        try:
            if hasattr(bot, 'gateway') and bot.gateway:
                if hasattr(bot.gateway, 'connected'):
                    gateway_connected = bool(bot.gateway.connected)
                elif hasattr(bot.gateway, 'session_id'):
                    gateway_connected = bot.gateway.session_id is not None
            else:
                gateway_error = "No gateway attribute"

        except Exception as e:
            gateway_connected = False
            gateway_error = f"Gateway check failed: {e}"

        # Test 2: Try a simple API call to test actual connectivity (FIXED)
        api_working = False
        api_error = None

        try:
            # SỬA LỖI: Dùng bot.getGuilds(limit=1) thay vì bot.getMe()
            # Đây là một lệnh API nhẹ và ổn định để kiểm tra token và kết nối.
            response = bot.getGuilds(limit=1)
            # Nếu lệnh thành công, nó sẽ trả về một list.
            if isinstance(response.json(), list):
                api_working = True
            else:
                api_error = f"API test failed: Unexpected response type {type(response.json())}"
        except Exception as e:
            api_error = f"API test failed: {e}"

        # Test 3: Check last activity time
        activity_healthy = True
        now = time.time()
        last_activity = last_activity_time.get(bot_id, now)
        time_since_activity = now - last_activity

        if time_since_activity > 300:  # 5 minutes without activity
            activity_healthy = False

        # Overall health assessment
        is_healthy = gateway_connected and api_working and activity_healthy
        response_time = time.time() - start_time

        # Update health stats
        if bot_id not in bot_health_stats:
            bot_health_stats[bot_id] = {'consecutive_failures': 0}
        stats = bot_health_stats[bot_id]
        stats['last_health_check'] = time.time()

        if is_healthy:
            stats['consecutive_failures'] = 0
            return True
        else:
            stats['consecutive_failures'] += 1
            # Detailed error logging
            error_details = []
            if not gateway_connected:
                error_details.append(f"Gateway: {gateway_error or 'disconnected'}")
            if not api_working:
                error_details.append(f"API: {api_error or 'failed'}")
            if not activity_healthy:
                error_details.append(f"Activity: {time_since_activity:.0f}s ago")
            
            print(f"[Health Check] ❌ Bot {bot_id} unhealthy - {'; '.join(error_details)}", flush=True)
            return False

    except Exception as e:
        print(f"[Health Check] ❌ Bot {bot_id} health check exception: {e}", flush=True)
        if bot_id not in bot_health_stats:
            bot_health_stats[bot_id] = {'consecutive_failures': 0}
        bot_health_stats[bot_id]['consecutive_failures'] += 1
        return False
    except Exception as e:
        print(f"[Health Check] ❌ Bot {bot_id} health check exception: {e}", flush=True)

        # Update failure stats
        if bot_id not in bot_health_stats:
            bot_health_stats[bot_id] = {'consecutive_failures': 0}
        bot_health_stats[bot_id]['consecutive_failures'] = bot_health_stats[bot_id].get('consecutive_failures', 0) + 1

        if bot_id not in bot_connection_health:
            bot_connection_health[bot_id] = {'consecutive_failures': 0}
        bot_connection_health[bot_id]['consecutive_failures'] += 1

        return False

def update_last_activity(bot_id):
    """Update last activity time for bot"""
    last_activity_time[bot_id] = time.time()

def emergency_bot_recovery(bot_id, bot_num):
    """Emergency recovery cho bot khi detect connection issues"""
    try:
        print(f"[EMERGENCY RECOVERY | {bot_id}] 🚨 Starting emergency recovery procedure", flush=True)

        # Check if auto-reboot is enabled for this bot
        reboot_settings = bot_reboot_settings.get(bot_id, {})

        if reboot_settings.get('enabled', False):
            print(f"[EMERGENCY RECOVERY | {bot_id}] 🔄 Auto-reboot enabled, triggering immediate reboot", flush=True)

            # Trigger immediate reboot by setting next_reboot_time to now
            reboot_settings['next_reboot_time'] = time.time()
            reboot_settings['emergency_triggered'] = True

        else:
            print(f"[EMERGENCY RECOVERY | {bot_id}] ⚠️ Auto-reboot disabled, attempting soft recovery", flush=True)

            # Try soft recovery methods
            try:
                bot = main_bots[bot_num - 1] if bot_num <= len(main_bots) else None
                if bot and hasattr(bot, 'gateway'):
                    # Try to reconnect gateway
                    print(f"[EMERGENCY RECOVERY | {bot_id}] 🔌 Attempting gateway reconnection", flush=True)
                    # Note: This might need specific implementation based on discum version

            except Exception as soft_recovery_error:
                print(f"[EMERGENCY RECOVERY | {bot_id}] ❌ Soft recovery failed: {soft_recovery_error}", flush=True)

                # As last resort, suggest enabling auto-reboot
                print(f"[EMERGENCY RECOVERY | {bot_id}] 💡 Recommend enabling auto-reboot for this bot", flush=True)

    except Exception as e:
        print(f"[EMERGENCY RECOVERY | {bot_id}] ❌ Recovery procedure failed: {e}", flush=True)

# --- CẢI TIẾN: SAFE REBOOT FUNCTIONS - BẢN SỬA LỖI ---
def safe_reboot_bot(bot_id):
    """Reboot bot một cách an toàn với proper error handling - Fixed version"""
    try:
        print(f"[Safe Reboot] 🔄 Bắt đầu reboot bot {bot_id}...", flush=True)

        # Parse bot info với validation tốt hơn
        if not isinstance(bot_id, str) or '_' not in bot_id:
            raise ValueError(f"Invalid bot_id format: {bot_id}")

        parts = bot_id.split('_')
        if len(parts) != 2 or parts[0] != 'main':
            raise ValueError(f"Invalid bot_id format: {bot_id}")

        try:
            bot_index = int(parts[1]) - 1
        except ValueError:
            raise ValueError(f"Invalid bot index in bot_id: {bot_id}")

        if bot_index < 0 or bot_index >= len(main_tokens):
            raise ValueError(f"Bot index out of range: {bot_index} (available: 0-{len(main_tokens)-1})")

        token = main_tokens[bot_index].strip()
        if not token:
            raise ValueError(f"Empty token for bot {bot_id}")

        bot_name = BOT_NAMES[bot_index] if bot_index < len(BOT_NAMES) else f"MAIN_{bot_index+1}"

        # Health check first - với try-catch riêng
        try:
            current_bot = main_bots[bot_index] if bot_index < len(main_bots) and main_bots[bot_index] else None
            if current_bot and not should_reboot_bot(current_bot, bot_id):
                # Bot is healthy, postpone reboot
                settings = bot_reboot_settings.get(bot_id, {})
                settings['next_reboot_time'] = time.time() + settings.get('delay', 3600)
                print(f"[Safe Reboot] ✅ Bot {bot_name} khỏe mạnh, hoãn reboot", flush=True)
                return True
        except Exception as health_error:
            print(f"[Safe Reboot] ⚠️ Health check failed: {health_error}, continuing with reboot", flush=True)

        start_time = time.time()

        # Step 1: Graceful shutdown với timeout
        if bot_index < len(main_bots) and main_bots[bot_index]:
            try:
                print(f"[Safe Reboot] 📴 Đóng connection cũ cho {bot_name}...", flush=True)
                current_bot = main_bots[bot_index]
                if hasattr(current_bot, 'gateway') and current_bot.gateway:
                    current_bot.gateway.close()
                # Set to None immediately để tránh race condition
                main_bots[bot_index] = None
            except Exception as e:
                print(f"[Safe Reboot] ⚠️ Lỗi khi đóng connection: {e}", flush=True)

        # Step 2: Extended wait với random factor để tránh detection
        base_wait = random.uniform(20, 40)
        print(f"[Safe Reboot] ⏳ Chờ {base_wait:.1f}s để cleanup...", flush=True)
        time.sleep(base_wait)

        # Step 3: Additional safety delay based on failure history
        settings = bot_reboot_settings.get(bot_id, {})
        failure_count = settings.get('failure_count', 0)
        if failure_count > 0:
            extra_delay = min(failure_count * 30, 300)
            print(f"[Safe Reboot] ⏳ Delay thêm {extra_delay}s do {failure_count} lần thất bại trước đó", flush=True)
            time.sleep(extra_delay)

        # Step 4: Create new bot instance với proper error handling
        print(f"[Safe Reboot] 🔌 Tạo connection mới cho {bot_name}...", flush=True)
        new_bot = None
        max_retries = 3

        for attempt in range(max_retries):
            try:
                new_bot = create_bot(token, bot_identifier=(bot_index + 1), is_main=True)
                if new_bot:
                    # Test connection briefly
                    time.sleep(3)  # Wait for connection to establish
                    break
                else:
                    print(f"[Safe Reboot] ⚠️ Attempt {attempt + 1}/{max_retries} failed for {bot_name}", flush=True)
                    if attempt < max_retries - 1:
                        time.sleep(10)  # Wait between retries
            except Exception as create_error:
                print(f"[Safe Reboot] ❌ Create attempt {attempt + 1} error: {create_error}", flush=True)
                if attempt < max_retries - 1:
                    time.sleep(10)

        if not new_bot:
            raise Exception(f"Failed to create new bot instance after {max_retries} attempts")

        # Step 5: Replace old bot với proper locking
        with bots_lock:
            # Ensure main_bots list is long enough
            while len(main_bots) <= bot_index:
                main_bots.append(None)
            main_bots[bot_index] = new_bot

        # Step 6: Update settings với proper error handling
        if bot_id not in bot_reboot_settings:
            bot_reboot_settings[bot_id] = {}

        settings = bot_reboot_settings[bot_id]
        settings['next_reboot_time'] = time.time() + settings.get('delay', 3600)
        settings['failure_count'] = 0  # Reset failure counter
        settings['last_reboot_time'] = time.time()

        # Reset health stats
        if bot_id in bot_health_stats:
            bot_health_stats[bot_id]['consecutive_failures'] = 0
            bot_health_stats[bot_id]['last_health_check'] = time.time()

        duration = time.time() - start_time
        print(f"[Safe Reboot] ✅ Reboot thành công {bot_name} trong {duration:.1f}s", flush=True)

        return True

    except Exception as e:
        print(f"[Safe Reboot] ❌ Reboot thất bại cho {bot_id}: {e}", flush=True)
        print(f"[Safe Reboot] 📊 Traceback: {traceback.format_exc()}", flush=True)

        # Handle failure với error handling
        try:
            handle_reboot_failure(bot_id)
        except Exception as handle_error:
            print(f"[Safe Reboot] ❌ Error in handle_reboot_failure: {handle_error}", flush=True)

        return False

def handle_reboot_failure(bot_id):
    """Xử lý khi reboot thất bại - Fixed version"""
    try:
        # Ensure bot_reboot_settings has the bot_id
        if bot_id not in bot_reboot_settings:
            bot_reboot_settings[bot_id] = {
                'enabled': True,
                'delay': 3600,
                'failure_count': 0,
                'next_reboot_time': 0
            }

        settings = bot_reboot_settings[bot_id]
        failure_count = settings.get('failure_count', 0) + 1
        settings['failure_count'] = failure_count

        # Exponential backoff với cap
        base_delay = max(settings.get('delay', 3600), 300)  # Minimum 5 minutes
        backoff_multiplier = min(2 ** failure_count, 8)  # Max 8x delay
        backoff_delay = base_delay * backoff_multiplier

        settings['next_reboot_time'] = time.time() + backoff_delay

        print(f"[Safe Reboot] 🔴 Failure #{failure_count} cho {bot_id}", flush=True)
        print(f"[Safe Reboot] ⏰ Next attempt trong {backoff_delay}s (backoff x{backoff_multiplier})", flush=True)

        # Disable after too many failures
        if failure_count >= 5:
            settings['enabled'] = False
            print(f"[Safe Reboot] ❌ Tắt auto-reboot cho {bot_id} sau {failure_count} lần thất bại", flush=True)

    except Exception as e:
        print(f"[Safe Reboot] ❌ Lỗi trong handle_reboot_failure: {e}", flush=True)

def should_reboot_bot(bot, bot_id):
    """Quyết định có nên reboot bot không - Fixed version"""
    try:
        # Kiểm tra bot có tồn tại không
        if not bot:
            print(f"[Health Check] 🔴 Bot {bot_id} không tồn tại, cần reboot", flush=True)
            return True

        # Check if bot is healthy với proper error handling
        try:
            is_healthy = check_bot_health(bot, bot_id)
        except Exception as health_error:
            print(f"[Health Check] ❌ Health check error cho {bot_id}: {health_error}", flush=True)
            return True  # Assume unhealthy if check fails

        if is_healthy:
            return False

        # Check failure threshold
        stats = bot_health_stats.get(bot_id, {})
        consecutive_failures = stats.get('consecutive_failures', 0)

        if consecutive_failures >= 3:
            print(f"[Health Check] 🔴 Bot {bot_id} có {consecutive_failures} lần kiểm tra thất bại liên tiếp, cần reboot", flush=True)
            return True

        print(f"[Health Check] 🟡 Bot {bot_id} có vấn đề nhỏ ({consecutive_failures} failures), chờ thêm", flush=True)
        return False

    except Exception as e:
        print(f"[Health Check] ❌ Lỗi khi kiểm tra bot {bot_id}: {e}", flush=True)
        # When in doubt, assume reboot is needed
        return True

def auto_reboot_loop():
    """Vòng lặp reboot cải tiến với safety features - Fixed version"""
    global main_bots, auto_reboot_stop_event
    print("[Safe Reboot] 🚀 Khởi động luồng tự động reboot cải tiến", flush=True)

    last_reboot_time = 0
    loop_iteration = 0

    while not auto_reboot_stop_event.is_set():
        try:
            loop_iteration += 1
            now = time.time()

            # Rate limiting: Chỉ cho phép reboot mỗi 5 phút
            if now - last_reboot_time < 300:
                auto_reboot_stop_event.wait(timeout=30)
                continue

            # Find bots that need rebooting với error handling
            bots_to_reboot = []
            try:
                for bot_id, settings in list(bot_reboot_settings.items()):
                    if (settings.get('enabled', False) and
                        now >= settings.get('next_reboot_time', 0)):
                        bots_to_reboot.append(bot_id)
            except Exception as find_error:
                print(f"[Safe Reboot] ⚠️ Error finding bots to reboot: {find_error}", flush=True)
                auto_reboot_stop_event.wait(timeout=60)
                continue

            if not bots_to_reboot:
                # Print status every 10 iterations (roughly every 10 minutes)
                if loop_iteration % 10 == 0:
                    enabled_bots = sum(1 for s in bot_reboot_settings.values() if s.get('enabled'))
                    if enabled_bots > 0:
                        print(f"[Safe Reboot] 📊 Loop #{loop_iteration}: {enabled_bots} bots enabled, none need reboot", flush=True)
                auto_reboot_stop_event.wait(timeout=60)
                continue

            # QUAN TRỌNG: Chỉ reboot 1 bot tại một thời điểm
            bot_to_reboot = bots_to_reboot[0]

            print(f"[Safe Reboot] 🎯 Loop #{loop_iteration}: Chọn reboot bot: {bot_to_reboot}", flush=True)

            # Perform safe reboot với full error isolation
            reboot_success = False
            try:
                reboot_success = safe_reboot_bot(bot_to_reboot)
            except Exception as reboot_error:
                print(f"[Safe Reboot] ❌ Critical reboot error: {reboot_error}", flush=True)
                try:
                    handle_reboot_failure(bot_to_reboot)
                except Exception as handle_error:
                    print(f"[Safe Reboot] ❌ Handle failure error: {handle_error}", flush=True)

            if reboot_success:
                last_reboot_time = now

                # Mandatory wait between reboots
                wait_time = random.uniform(300, 600)  # 5-10 phút
                print(f"[Safe Reboot] ⏳ Chờ {wait_time:.0f}s trước reboot tiếp theo", flush=True)
                auto_reboot_stop_event.wait(timeout=wait_time)
            else:
                # Shorter wait on failure
                print(f"[Safe Reboot] ⚠️ Reboot failed, waiting 2 minutes before retry", flush=True)
                auto_reboot_stop_event.wait(timeout=120)

        except Exception as e:
            print(f"[Safe Reboot] ❌ CRITICAL ERROR in auto_reboot_loop: {e}", flush=True)
            print(f"[Safe Reboot] 📊 Traceback: {traceback.format_exc()}", flush=True)
            # Longer wait on critical error
            auto_reboot_stop_event.wait(timeout=300)

    print("[Safe Reboot] 🛑 Luồng tự động reboot đã dừng", flush=True)


# --- CÁC HÀM LOGIC BOT (CẬP NHẬT) ---
def handle_clan_drop(bot, msg, bot_num):
    """Cải tiến hàm handle_clan_drop tương tự"""
    update_last_activity(f"main_{bot_num}")
    if not (auto_clan_drop_settings.get("enabled") and auto_clan_drop_settings.get("ktb_channel_id")):
        return

    channel_id = msg.get("channel_id")
    if channel_id != auto_clan_drop_settings.get("channel_id"):
        return

    last_drop_msg_id = msg["id"]

    def grab_handler():
        card_picked = False
        ktb_channel_id = auto_clan_drop_settings["ktb_channel_id"]

        for attempt in range(8):  # Tăng số attempts
            time.sleep(0.5)
            try:
                messages = bot.getMessages(channel_id, num=5).json()
                update_last_activity(f"main_{bot_num}")
                if not isinstance(messages, list):
                    continue

                for msg_item in messages:
                    author_id = msg_item.get("author", {}).get("id")
                    msg_id = msg_item.get("id")

                    if author_id == karibbit_id and msg_id and int(msg_id) > int(last_drop_msg_id):
                        embeds = msg_item.get("embeds", [])
                        if not embeds:
                            continue

                        desc = embeds[0].get("description", "")
                        if '♡' not in desc:
                            continue

                        lines = desc.split('\n')
                        if len(lines) < 3:
                            continue

                        heart_numbers = []
                        for line in lines[:3]:
                            match = re.search(r'♡(\d+)', line)
                            heart_numbers.append(int(match.group(1)) if match else 0)

                        if not any(heart_numbers):
                            break

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

                            print(f"[CLAN DROP | Bot {bot_num}] Chọn dòng {max_index+1} với {max_num}♡ -> {emoji} sau {delay}s", flush=True)

                            def grab_action():
                                try:
                                    bot.addReaction(channel_id, last_drop_msg_id, emoji)
                                    update_last_activity(f"main_{bot_num}")
                                    time.sleep(1.2)
                                    bot.sendMessage(ktb_channel_id, "kt b")
                                    update_last_activity(f"main_{bot_num}")
                                    print(f"[CLAN DROP | Bot {bot_num}] ✅ Đã grab và gửi kt b", flush=True)
                                except Exception as e:
                                    print(f"[CLAN DROP | Bot {bot_num}] ❌ Lỗi grab: {e}", flush=True)

                            threading.Timer(delay, grab_action).start()
                            card_picked = True
                            break

                if card_picked:
                    break

            except Exception as e:
                print(f"[CLAN DROP | Bot {bot_num}] ❌ Lỗi (attempt {attempt+1}): {e}", flush=True)
                continue

            if card_picked:
                break

    threading.Thread(target=grab_handler, daemon=True).start()

def handle_grab(bot, msg, bot_num):
    """Enhanced grab handler với connection check trước khi grab"""
    bot_id = f"main_{bot_num}"

    # Update activity immediately
    update_last_activity(bot_id)

    channel_id = msg.get("channel_id")
    target_server = next((s for s in servers if s.get('main_channel_id') == channel_id), None)
    if not target_server:
        return

    auto_grab_enabled = target_server.get(f'auto_grab_enabled_{bot_num}', False)
    heart_threshold = target_server.get(f'heart_threshold_{bot_num}', 50)
    ktb_channel_id = target_server.get('ktb_channel_id')
    watermelon_grab_enabled = watermelon_grab_states.get(bot_id, False)

    if not auto_grab_enabled and not watermelon_grab_enabled:
        return

    # CRITICAL: Check bot health before attempting grab
    if not check_bot_health(bot, bot_id):
        print(f"[GRAB FAILED | Bot {bot_num}] ❌ Bot unhealthy, skipping grab attempt", flush=True)
        # Trigger immediate health recovery
        threading.Thread(target=emergency_bot_recovery, args=(bot_id, bot_num), daemon=True).start()
        return

    last_drop_msg_id = msg["id"]

    def grab_handler():
        try:
            # === CARD GRAB LOGIC ===
            card_picked = False
            if auto_grab_enabled and ktb_channel_id:
                for attempt in range(6):
                    time.sleep(0.5)
                    try:
                        messages = bot.getMessages(channel_id, num=5).json()
                        update_last_activity(bot_id)
                        if not isinstance(messages, list):
                            continue

                        for msg_item in messages:
                            author_id = msg_item.get("author", {}).get("id")
                            msg_id = msg_item.get("id")

                            if author_id == karibbit_id and msg_id and int(msg_id) > int(last_drop_msg_id):
                                embeds = msg_item.get("embeds", [])
                                if not embeds: continue
                                desc = embeds[0].get("description", "")
                                if '♡' not in desc: continue
                                lines = desc.split('\n')
                                if len(lines) < 3: continue
                                heart_numbers = [int(match.group(1)) if (match := re.search(r'♡(\d+)', line)) else 0 for line in lines[:3]]
                                if not any(heart_numbers): break
                                max_num = max(heart_numbers)
                                if max_num >= heart_threshold:
                                    max_index = heart_numbers.index(max_num)
                                    delays = {1: [0.4, 1.4, 2.1], 2: [0.7, 1.8, 2.4], 3: [0.7, 1.8, 2.4], 4: [0.8, 1.9, 2.5]}
                                    bot_delays = delays.get(bot_num, [0.9, 2.0, 2.6])
                                    emojis = ["1️⃣", "2️⃣", "3️⃣"]
                                    emoji = emojis[max_index]
                                    delay = bot_delays[max_index]
                                    print(f"[CARD GRAB | Bot {bot_num}] Chọn dòng {max_index+1} với {max_num}♡ -> {emoji} sau {delay}s", flush=True)
                                    def grab_action():
                                        try:
                                            bot.addReaction(channel_id, last_drop_msg_id, emoji)
                                            update_last_activity(bot_id)
                                            time.sleep(1.2)
                                            bot.sendMessage(ktb_channel_id, "kt b")
                                            update_last_activity(bot_id)
                                            print(f"[CARD GRAB | Bot {bot_num}] ✅ Đã grab và gửi kt b", flush=True)
                                        except Exception as e:
                                            print(f"[CARD GRAB | Bot {bot_num}] ❌ Lỗi grab: {e}", flush=True)
                                    threading.Timer(delay, grab_action).start()
                                    card_picked = True
                                    break
                            if card_picked: break
                        if card_picked: break
                    except Exception as e:
                        print(f"[CARD GRAB | Bot {bot_num}] ❌ Lỗi đọc messages (attempt {attempt+1}): {e}", flush=True)
                        continue
                    if card_picked: break

            # === ENHANCED WATERMELON GRAB LOGIC ===
            if watermelon_grab_enabled:
                watermelon_found = False
                check_start_time = time.time()
                max_check_duration = 15
                check_interval = 0.3
                attempt_count = 0

                while time.time() - check_start_time < max_check_duration and not watermelon_found:
                    attempt_count += 1

                    # Health check mỗi ~3 giây
                    if attempt_count > 1 and attempt_count % 10 == 0:
                        if not check_bot_health(bot, bot_id):
                            print(f"[WATERMELON | Bot {bot_num}] 💔 Bot became unhealthy during hunt, aborting", flush=True)
                            break
                    try:
                        recent_messages = bot.getMessages(channel_id, num=3).json()
                        update_last_activity(bot_id)
                        if not isinstance(recent_messages, list):
                            time.sleep(check_interval)
                            continue

                        target_message = next((m for m in recent_messages if m.get("id") == last_drop_msg_id), None)

                        if not target_message:
                            time.sleep(check_interval)
                            continue

                        reactions = target_message.get('reactions', [])
                        if not reactions:
                            time.sleep(check_interval)
                            continue

                        watermelon_reaction_found = False
                        for reaction in reactions:
                            emoji_data = reaction.get('emoji', {})
                            emoji_name = emoji_data.get('name', '')
                            is_watermelon = (emoji_name == '🍉' or 'watermelon' in emoji_name.lower() or 'dua' in emoji_name.lower() or emoji_name == '\U0001f349')
                            if is_watermelon:
                                print(f"[WATERMELON | Bot {bot_num}] 🎯 WATERMELON DETECTED! (attempt {attempt_count})", flush=True)
                                watermelon_reaction_found = True
                                break
                        
                        if watermelon_reaction_found:
                            if not check_bot_health(bot, bot_id):
                                print(f"[WATERMELON | Bot {bot_num}] ❌ Bot unhealthy right before reaction!", flush=True)
                                break
                            
                            reaction_success = False
                            for react_attempt in range(5):
                                try:
                                    bot.addReaction(channel_id, last_drop_msg_id, "🍉")
                                    print(f"[WATERMELON | Bot {bot_num}] ✅ WATERMELON GRABBED! (attempt {react_attempt + 1})", flush=True)
                                    reaction_success = True
                                    watermelon_found = True
                                    update_last_activity(bot_id)
                                    break
                                except Exception as react_error:
                                    print(f"[WATERMELON | Bot {bot_num}] ❌ React attempt {react_attempt + 1} failed: {react_error}", flush=True)
                                    if react_attempt < 4: time.sleep(0.1)
                            
                            if not reaction_success:
                                print(f"[WATERMELON | Bot {bot_num}] 💔 All reaction attempts failed", flush=True)
                            break
                        else:
                            time.sleep(check_interval)
                    except Exception as e:
                        if "connection" in str(e).lower() or "timeout" in str(e).lower():
                            print(f"[WATERMELON | Bot {bot_num}] 🚨 Connection error detected, triggering recovery", flush=True)
                            threading.Thread(target=emergency_bot_recovery, args=(bot_id, bot_num), daemon=True).start()
                            break
                        time.sleep(check_interval)

        except Exception as e:
            print(f"[GRAB HANDLER | Bot {bot_num}] ❌ Critical error: {e}", flush=True)
            print(f"[GRAB HANDLER | Bot {bot_num}] 📊 Traceback: {traceback.format_exc()}", flush=True)

    threading.Thread(target=grab_handler, daemon=True).start()

def create_bot(token, bot_identifier, is_main=False):
    """Tạo bot với error handling tốt hơn"""
    try:
        print(f"[Bot Creation] 🔌 Đang tạo bot {bot_identifier} ({'main' if is_main else 'sub'})...", flush=True)

        bot = discum.Client(token=token, log=False)

        @bot.gateway.command
        def on_ready(resp):
            if resp.event.ready:
                user = resp.raw.get("user", {})
                if isinstance(user, dict) and (user_id := user.get("id")):
                    bot_name = BOT_NAMES[bot_identifier-1] if is_main and bot_identifier-1 < len(BOT_NAMES) else acc_names[bot_identifier] if not is_main and bot_identifier < len(acc_names) else f"Bot {bot_identifier}"
                    print(f"[Bot Creation] ✅ Đã đăng nhập: {user_id} ({bot_name})", flush=True)

                    # Initialize health stats
                    if is_main:
                        bot_id = f"main_{bot_identifier}"
                        update_last_activity(bot_id)
                        if bot_id not in bot_health_stats:
                            bot_health_stats[bot_id] = {
                                'last_health_check': time.time(),
                                'consecutive_failures': 0,
                                'total_checks': 0,
                                'created_time': time.time()
                            }

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

        # Wait a moment to ensure connection is established
        time.sleep(2)

        return bot

    except Exception as e:
        print(f"[Bot Creation] ❌ Lỗi tạo bot {bot_identifier}: {e}", flush=True)
        print(f"[Bot Creation] 📊 Traceback: {traceback.format_exc()}", flush=True)
        return None

# --- CÁC VÒNG LẶP NỀN (Cải tiến) ---
def continuous_connection_monitor():
    """Background thread để monitor connection 24/7"""
    print("[CONNECTION MONITOR] 🔍 Starting continuous connection monitoring", flush=True)

    while True:
        try:
            with bots_lock:
                # Check all main bots
                for i, bot in enumerate(main_bots):
                    if bot:
                        bot_id = f"main_{i+1}"
                        if bot_active_states.get(bot_id, False):
                            check_bot_health(bot, bot_id)

                            # Trigger recovery if unhealthy for too long
                            health_record = bot_connection_health.get(bot_id, {})
                            consecutive_failures = health_record.get('consecutive_failures', 0)

                            if consecutive_failures >= 3:  # 3 failed checks = ~1.5 minutes
                                print(f"[CONNECTION MONITOR] 🚨 Bot {bot_id} has {consecutive_failures} consecutive failures", flush=True)
                                threading.Thread(target=emergency_bot_recovery, args=(bot_id, i+1), daemon=True).start()

            # Sleep between checks
            time.sleep(connection_check_interval)

        except Exception as e:
            print(f"[CONNECTION MONITOR] ❌ Monitor error: {e}", flush=True)
            time.sleep(60)  # Longer sleep on error

def run_clan_drop_cycle():
    """Clan drop cycle với better error handling"""
    print("[Clan Drop] 🚀 Bắt đầu chu kỳ drop clan.", flush=True)
    settings = auto_clan_drop_settings.copy()
    channel_id = settings.get("channel_id")

    with bots_lock:
        active_main_bots = [(bot, i + 1) for i, bot in enumerate(main_bots)
                           if bot and bot_active_states.get(f'main_{i+1}', False)]

    if not active_main_bots:
        print("[Clan Drop] ⚠️ Không có bot chính nào hoạt động để thực hiện drop.", flush=True)
        return

    for bot, bot_num in active_main_bots:
        if auto_clan_drop_stop_event.is_set():
            break

        try:
            bot_name = BOT_NAMES[bot_num-1] if bot_num-1 < len(BOT_NAMES) else f"MAIN_{bot_num}"
            print(f"[Clan Drop] 📤 Bot {bot_name} đang gửi 'kd'...", flush=True)

            bot.sendMessage(channel_id, "kd")
            update_last_activity(f"main_{bot_num}")

            # Random delay để tránh pattern detection
            base_delay = settings.get("bot_delay", 140)
            random_delay = random.uniform(base_delay * 0.8, base_delay * 1.2)
            time.sleep(random_delay)

        except Exception as e:
            print(f"[Clan Drop] ❌ Lỗi khi gửi 'kd' từ bot {bot_num}: {e}", flush=True)

    auto_clan_drop_settings["last_cycle_start_time"] = time.time()
    save_settings()

def auto_clan_drop_loop():
    """Clan drop loop với improved timing"""
    while not auto_clan_drop_stop_event.is_set():
        try:
            if auto_clan_drop_stop_event.wait(timeout=60):
                break

            settings = auto_clan_drop_settings
            is_enabled = settings.get("enabled")
            channel_id = settings.get("channel_id")
            interval = settings.get("cycle_interval", 1800)
            last_run = settings.get("last_cycle_start_time", 0)

            if is_enabled and channel_id and (time.time() - last_run) >= interval:
                run_clan_drop_cycle()

        except Exception as e:
            print(f"[Clan Drop] ❌ ERROR in auto_clan_drop_loop: {e}", flush=True)
            time.sleep(60)

    print("[Clan Drop] 🛑 Luồng tự động drop clan đã dừng.", flush=True)

def spam_loop():
    """Spam loop với better management"""
    active_server_threads = {}

    while True:
        try:
            current_server_ids = {s['id'] for s in servers}

            # Clean up threads for deleted servers
            for server_id in list(active_server_threads.keys()):
                if server_id not in current_server_ids:
                    print(f"[Spam Control] 🛑 Dừng luồng spam cho server đã bị xóa: {server_id}", flush=True)
                    _, stop_event = active_server_threads.pop(server_id)
                    stop_event.set()

            # Start/stop threads based on server settings
            for server in servers:
                server_id = server.get('id')
                spam_is_on = (server.get('spam_enabled') and
                             server.get('spam_message') and
                             server.get('spam_channel_id'))

                if spam_is_on and server_id not in active_server_threads:
                    print(f"[Spam Control] 🚀 Bắt đầu luồng spam cho server: {server.get('name')}", flush=True)
                    stop_event = threading.Event()
                    thread = threading.Thread(target=spam_for_server, args=(server, stop_event), daemon=True)
                    thread.start()
                    active_server_threads[server_id] = (thread, stop_event)

                elif not spam_is_on and server_id in active_server_threads:
                    print(f"[Spam Control] 🛑 Dừng luồng spam cho server: {server.get('name')}", flush=True)
                    _, stop_event = active_server_threads.pop(server_id)
                    stop_event.set()

            time.sleep(5)

        except Exception as e:
            print(f"[Spam Control] ❌ ERROR in spam_loop_manager: {e}", flush=True)
            time.sleep(5)

def spam_for_server(server_config, stop_event):
    """Spam cho server cụ thể với error handling"""
    server_name = server_config.get('name')
    channel_id = server_config.get('spam_channel_id')
    message = server_config.get('spam_message')

    while not stop_event.is_set():
        try:
            with bots_lock:
                active_main_bots = [bot for i, bot in enumerate(main_bots)
                                  if bot and bot_active_states.get(f'main_{i+1}', False)]
                active_sub_bots = [bot for i, bot in enumerate(bots)
                                 if bot and bot_active_states.get(f'sub_{i}', False)]
                bots_to_spam = active_main_bots + active_sub_bots

            delay = server_config.get('spam_delay', 10)

            for bot_idx, bot in enumerate(bots_to_spam):
                if stop_event.is_set():
                    break
                try:
                    bot_id_str = ""
                    # Find bot_id to update activity
                    if bot in main_bots:
                        idx = main_bots.index(bot)
                        bot_id_str = f"main_{idx+1}"
                    
                    bot.sendMessage(channel_id, message)
                    if bot_id_str:
                        update_last_activity(bot_id_str)
                        
                    time.sleep(random.uniform(1.5, 2.5))  # Random delay giữa bots
                except Exception as e:
                    print(f"[Spam] ❌ Lỗi gửi spam từ bot tới server {server_name}: {e}", flush=True)

            if not stop_event.is_set():
                # Add some randomization to spam timing
                random_delay = random.uniform(delay * 0.9, delay * 1.1)
                stop_event.wait(timeout=random_delay)

        except Exception as e:
            print(f"[Spam] ❌ ERROR in spam_for_server {server_name}: {e}", flush=True)
            stop_event.wait(timeout=10)

def periodic_save_loop():
    """Periodic save với better timing"""
    while True:
        time.sleep(1800)  # Save every 30 minutes
        try:
            print("[Settings] 💾 Bắt đầu lưu định kỳ...", flush=True)
            save_settings()
        except Exception as e:
            print(f"[Settings] ❌ Lỗi trong periodic save: {e}", flush=True)

# --- FLASK APP ---
app = Flask(__name__)

# --- IMPROVED HTML TEMPLATE ---
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

# --- FLASK ROUTES (Enhanced) ---
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
    if 'heart_thresholds' in data:
        for key, value in data['heart_thresholds'].items():
            if isinstance(value, int):
                auto_clan_drop_settings.setdefault('heart_thresholds', {})[key] = value
    return jsonify({'status': 'success', 'message': '💾 Clan Drop settings updated successfully.'})

@app.route("/api/add_server", methods=['POST'])
def api_add_server():
    data = request.get_json()
    name = data.get('name')
    if not name: return jsonify({'status': 'error', 'message': 'Server name is required.'}), 400
    new_server = {"id": f"server_{uuid.uuid4().hex}", "name": name, "main_channel_id": "", "ktb_channel_id": "", "spam_channel_id": "", "spam_enabled": False, "spam_message": "", "spam_delay": 10, "last_spam_time": 0}
    for i in range(len(main_tokens)):
        bot_num = i + 1
        new_server[f'auto_grab_enabled_{bot_num}'] = False
        new_server[f'heart_threshold_{bot_num}'] = 50
    servers.append(new_server)
    return jsonify({'status': 'success', 'message': f'✅ Server "{name}" added successfully.', 'reload': True})

@app.route("/api/delete_server", methods=['POST'])
def api_delete_server():
    global servers
    server_id = request.get_json().get('server_id')
    server_to_delete = next((s for s in servers if s.get('id') == server_id), None)
    if server_to_delete:
        servers = [s for s in servers if s.get('id') != server_id]
        return jsonify({'status': 'success', 'message': f'🗑️ Server "{server_to_delete.get("name")}" deleted successfully.', 'reload': True})
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
    return jsonify({'status': 'success', 'message': f'🔧 {", ".join(updated_fields)} updated for {server["name"]}.'})

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
    try:
        bot_name = BOT_NAMES[int(node)-1]
    except (ValueError, IndexError):
        bot_name = f"MAIN_{node}"
    status_icon = "🎯" if server[grab_key] else "🛑"
    msg = f"{status_icon} Card Grab for {bot_name} was {'ENABLED' if server[grab_key] else 'DISABLED'} on server {server['name']}."
    return jsonify({'status': 'success', 'message': msg})

@app.route("/api/watermelon_toggle", methods=['POST'])
def api_watermelon_toggle():
    data = request.get_json()
    node = data.get('node')
    if not node or node not in watermelon_grab_states:
        return jsonify({'status': 'error', 'message': 'Invalid bot node.'}), 404
    watermelon_grab_states[node] = not watermelon_grab_states.get(node, False)
    try:
        bot_name_index = int(node.split('_')[1]) - 1
        bot_name = BOT_NAMES[bot_name_index] if bot_name_index < len(BOT_NAMES) else f"MAIN_{node}"
    except (IndexError, ValueError):
        bot_name = node.upper()
    status_icon = "🍉" if watermelon_grab_states[node] else "🛑"
    msg = f"{status_icon} Global Watermelon Grab was {'ENABLED' if watermelon_grab_states[node] else 'DISABLED'} for {bot_name}."
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
        return jsonify({'status': 'error', 'message': f'❌ Spam message/channel required for {server["name"]}.'})
    status_icon = "📢" if server['spam_enabled'] else "🛑"
    msg = f"{status_icon} Auto Broadcast {'ENABLED' if server['spam_enabled'] else 'DISABLED'} for {server['name']}."
    return jsonify({'status': 'success', 'message': msg})

@app.route("/api/bot_reboot_toggle", methods=['POST'])
def api_bot_reboot_toggle():
    global auto_reboot_thread
    data = request.get_json()
    bot_id = data.get('bot_id')
    delay = int(data.get("delay", 3600))

    if not bot_id or bot_id not in bot_reboot_settings:
        return jsonify({'status': 'error', 'message': '❌ Invalid Bot ID.'}), 400

    settings = bot_reboot_settings[bot_id]
    settings['enabled'] = not settings.get('enabled', False)
    settings['delay'] = delay
    settings['failure_count'] = 0  # Reset failure count when toggling

    try:
        bot_name_index = int(bot_id.split('_')[1]) - 1
        bot_name = BOT_NAMES[bot_name_index] if bot_name_index < len(BOT_NAMES) else bot_id
    except (IndexError, ValueError):
        bot_name = bot_id

    if settings['enabled']:
        settings['next_reboot_time'] = time.time() + delay
        if auto_reboot_thread is None or not auto_reboot_thread.is_alive():
            print("[Enhanced Reboot] 🚀 Kích hoạt luồng Safe Reboot System", flush=True)
            auto_reboot_stop_event.clear()
            auto_reboot_thread = threading.Thread(target=auto_reboot_loop, daemon=True)
            auto_reboot_thread.start()
        msg = f"🔄 Safe Auto-Reboot ENABLED for {bot_name} (every {delay}s with health checks)"
    else:
        settings['next_reboot_time'] = 0
        msg = f"🛑 Auto-Reboot DISABLED for {bot_name}"

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
    return jsonify({'status': 'success', 'message': '💾 Settings saved successfully.'})

@app.route("/status")
def status():
    now = time.time()
    for server in servers:
        server['spam_countdown'] = 0

    with bots_lock:
        main_bot_statuses = []
        for i, bot in enumerate(main_bots):
            bot_id = f"main_{i+1}"
            bot_name = BOT_NAMES[i] if i < len(BOT_NAMES) else f"MAIN_{i+1}"

            # Determine health status
            health_status = 'good'
            health_record = bot_connection_health.get(bot_id, {})
            if health_record:
                failures = health_record.get('consecutive_failures', 0)
                if failures >= 3:
                    health_status = 'bad'
                elif failures > 0:
                    health_status = 'warning'

            main_bot_statuses.append({
                "name": bot_name,
                "status": bot is not None,
                "reboot_id": bot_id,
                "is_active": bot_active_states.get(bot_id, False),
                "type": "main",
                "health_status": health_status
            })

        sub_bot_statuses = []
        for i, bot in enumerate(bots):
            bot_id = f"sub_{i}"
            bot_name = acc_names[i] if i < len(acc_names) else f"Sub {i+1}"

            # Health status for sub-bots (can be simplified if not monitored)
            health_status = 'good'

            sub_bot_statuses.append({
                "name": bot_name,
                "status": bot is not None,
                "reboot_id": bot_id,
                "is_active": bot_active_states.get(bot_id, False),
                "type": "sub",
                "health_status": health_status
            })

    clan_drop_status = {
        "enabled": auto_clan_drop_settings.get("enabled", False),
        "countdown": (auto_clan_drop_settings.get("last_cycle_start_time", 0) +
                     auto_clan_drop_settings.get("cycle_interval", 1800) - now)
                    if auto_clan_drop_settings.get("enabled", False) else 0
    }

    for bot_id, settings in bot_reboot_settings.items():
        if settings.get('enabled'):
            settings['countdown'] = max(0, settings.get('next_reboot_time', 0) - now)
        else:
            settings['countdown'] = 0

    return jsonify({
        'bot_reboot_settings': bot_reboot_settings,
        'bot_statuses': {
            "main_bots": main_bot_statuses,
            "sub_accounts": sub_bot_statuses
        },
        'server_start_time': server_start_time,
        'servers': servers,
        'watermelon_grab_states': watermelon_grab_states,
        'auto_clan_drop_status': clan_drop_status,
        'bot_health_stats': bot_health_stats
    })

# --- MAIN EXECUTION (Enhanced) ---
if __name__ == "__main__":
    print("🚀 Shadow Network Control - Enhanced Version Starting...", flush=True)

    # Load settings first
    load_settings()

    print("🔌 Initializing bots with enhanced safety features...", flush=True)
    with bots_lock:
        # Initialize main bots
        for i, token in enumerate(main_tokens):
            if token.strip():
                bot_num = i + 1
                bot_id = f"main_{bot_num}"

                print(f"[Init] 🤖 Creating main bot {bot_num}...", flush=True)
                bot = create_bot(token.strip(), bot_identifier=bot_num, is_main=True)
                main_bots.append(bot)

                # Initialize states
                if bot_id not in bot_active_states:
                    bot_active_states[bot_id] = True
                if bot_id not in watermelon_grab_states:
                    watermelon_grab_states[bot_id] = False
                if bot_id not in auto_clan_drop_settings.get('heart_thresholds', {}):
                    auto_clan_drop_settings.setdefault('heart_thresholds', {})[bot_id] = 50

                # Initialize enhanced reboot settings
                if bot_id not in bot_reboot_settings:
                    bot_reboot_settings[bot_id] = {
                        'enabled': False,
                        'delay': 3600,  # Default 1 hour
                        'next_reboot_time': 0,
                        'failure_count': 0,
                        'last_reboot_time': 0
                    }

                # Initialize health stats
                if bot_id not in bot_health_stats:
                    bot_health_stats[bot_id] = {
                        'last_health_check': time.time(),
                        'consecutive_failures': 0,
                        'total_checks': 0,
                        'created_time': time.time()
                    }

        # Initialize sub bots
        for i, token in enumerate(tokens):
            if token.strip():
                bot_id = f'sub_{i}'
                print(f"[Init] 🤖 Creating sub bot {i}...", flush=True)
                bot = create_bot(token.strip(), bot_identifier=i, is_main=False)
                bots.append(bot)

                if bot_id not in bot_active_states:
                    bot_active_states[bot_id] = True

    print("🔧 Starting enhanced background threads...", flush=True)

    # Start background threads
    threading.Thread(target=periodic_save_loop, daemon=True).start()
    threading.Thread(target=continuous_connection_monitor, daemon=True).start()

    # Start spam management
    spam_thread = threading.Thread(target=spam_loop, daemon=True)
    spam_thread.start()

    # Start reboot system if any bots have it enabled
    if any(s.get('enabled') for s in bot_reboot_settings.values()):
        print("[Enhanced Reboot] 🔄 Starting Safe Reboot System...", flush=True)
        auto_reboot_stop_event.clear()
        auto_reboot_thread = threading.Thread(target=auto_reboot_loop, daemon=True)
        auto_reboot_thread.start()

    # Start clan drop if enabled
    if auto_clan_drop_settings.get("enabled"):
        print("[Clan Drop] 🚀 Starting Auto Clan Drop...", flush=True)
        auto_clan_drop_stop_event.clear()
        auto_clan_drop_thread = threading.Thread(target=auto_clan_drop_loop, daemon=True)
        auto_clan_drop_thread.start()

    port = int(os.environ.get("PORT", 10000))
    print(f"🌐 Starting Enhanced Web Server at http://0.0.0.0:{port}", flush=True)
    print("✅ Shadow Network Control - Enhanced Version Ready!", flush=True)

    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
