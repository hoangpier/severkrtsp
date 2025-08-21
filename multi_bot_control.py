# PHIÊN BẢN NÂNG CẤP TOÀN DIỆN - TÍCH HỢP BOT MANAGER & SPAM CONTROL THEO NHÓM
import discum, threading, time, os, re, requests, json, random, traceback, uuid
from flask import Flask, request, render_template_string, jsonify
from dotenv import load_dotenv
from datetime import datetime, timedelta

load_dotenv()

# --- CẤU HÌNH ---
main_tokens = os.getenv("MAIN_TOKENS", "").split(",")
tokens = os.getenv("TOKENS", "").split(",")
karuta_id, karibbit_id = "646937666251915264", "1311684840462225440"
BOT_NAMES = ["xsyx", "sofa", "dont", "ayaya", "owo", "astra", "singo", "dia pox", "clam", "rambo", "domixi", "dogi", "sicula", "mo turn", "jan taru", "kio sama"]
acc_names = [f"Bot-{i:02d}" for i in range(1, 21)]

# --- BIẾN TRẠNG THÁI & KHÓA ---
servers = []
bot_states = {
    "reboot_settings": {}, "active": {}, "watermelon_grab": {}, "health_stats": {},
    "auto_clan_drop": {"enabled": False, "channel_id": "", "ktb_channel_id": "", "last_cycle_start_time": 0, "cycle_interval": 1800, "bot_delay": 140, "heart_thresholds": {}, "max_heart_thresholds": {}},
    "spam_groups": [] # <-- DATA MỚI ĐƯỢC THÊM
}
stop_events = {"reboot": threading.Event(), "clan_drop": threading.Event()}
server_start_time = time.time()
bots_lock = threading.Lock() # <-- Thêm lock để quản lý spam task an toàn

# --- QUẢN LÝ BOT THREAD-SAFE (IMPROVED) ---
class ThreadSafeBotManager:
    def __init__(self):
        self._bots = {}
        self._rebooting = set()
        self._lock = threading.RLock()

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
        with open('backup_settings.json', 'w', encoding='utf8') as f:
            json.dump(settings_data, f, indent=2, ensure_ascii=False)
        print("[Settings] ✅ Đã lưu backup cài đặt locally.", flush=True)
    except Exception as e:
        print(f"[Settings] ❌ Lỗi khi lưu backup local: {e}", flush=True)

def load_settings():
    global servers, bot_states
    api_key, bin_id = os.getenv("JSONBIN_API_KEY"), os.getenv("JSONBIN_BIN_ID")

    def load_from_dict(settings):
        try:
            # Sửa lỗi servers bị trùng lặp khi load
            loaded_servers = settings.get('servers', [])
            if not servers:
                servers.extend(loaded_servers)
            
            # Cập nhật bot_states một cách an toàn
            loaded_bot_states = settings.get('bot_states', {})
            for key, value in loaded_bot_states.items():
                if key in bot_states and isinstance(bot_states[key], dict) and isinstance(value, dict):
                    bot_states[key].update(value)
                else: # Ghi đè nếu key không tồn tại hoặc không phải là dict
                    bot_states[key] = value

            # Đảm bảo spam_groups là một list
            if 'spam_groups' not in bot_states or not isinstance(bot_states['spam_groups'], list):
                 bot_states['spam_groups'] = []

            return True
        except Exception as e:
            print(f"[Settings] ❌ Lỗi parse settings: {e}", flush=True)
            return False

    if api_key and bin_id:
        try:
            headers = {'X-Master-Key': api_key, 'X-Bin-Meta': 'false'}
            url = f"https://api.jsonbin.io/v3/b/{bin_id}/latest"
            req = requests.get(url, headers=headers, timeout=15)
            if req.status_code == 200 and load_from_dict(req.json()):
                print("[Settings] ✅ Đã tải cài đặt từ JSONBin.io.", flush=True)
                return
        except Exception as e:
            print(f"[Settings] ⚠️ Lỗi tải từ JSONBin: {e}", flush=True)

    try:
        with open('backup_settings.json', 'r', encoding='utf8') as f:
            if load_from_dict(json.load(f)):
                print("[Settings] ✅ Đã tải cài đặt từ backup file.", flush=True)
                return
    except FileNotFoundError:
        print("[Settings] ⚠️ Không tìm thấy backup file, dùng cài đặt mặc định.", flush=True)
    except Exception as e:
        print(f"[Settings] ⚠️ Lỗi tải backup: {e}", flush=True)

# --- LOGIC SPAM MỚI (TỪ FARM-CONTROL) ---
spam_tasks_running = set()
def farm_style_spam_loop():
    print("[Farm Spam] 🚀 Khởi động hệ thống spam theo nhóm.", flush=True)
    
    def run_spam_cycle(task_id, channel_id, message, bots_to_use_ids):
        global spam_tasks_running
        try:
            bots_to_use = [bot_manager.get_bot(bot_id) for bot_id in bots_to_use_ids if bot_manager.get_bot(bot_id)]
            for bot in bots_to_use:
                try:
                    bot.sendMessage(channel_id, message)
                    time.sleep(1.5) # Delay giữa các bot trong cùng 1 farm
                except Exception:
                    pass
        finally:
            with bots_lock:
                if task_id in spam_tasks_running:
                    spam_tasks_running.remove(task_id)

    while True:
        try:
            now = time.time()
            
            for server in servers:
                server_id = server.get('id')
                if not server_id: continue

                last_spam_time = server.get('last_spam_time', 0)
                spam_delay = int(server.get('spam_delay', 30)) # Sử dụng delay của từng server

                is_task_running = False
                with bots_lock:
                    is_task_running = server_id in spam_tasks_running

                if (now - last_spam_time) >= spam_delay and not is_task_running:
                    group_id = server.get('group_id')
                    if not group_id: continue

                    group = next((g for g in bot_states['spam_groups'] if g.get('id') == group_id), None)
                    if not group or not group.get('spam_enabled'):
                        continue

                    selected_bot_ids = group.get('selected_bots', [])
                    
                    # Lọc các bot đang active
                    active_bots_to_use_ids = [
                        bot_id for bot_id in selected_bot_ids 
                        if bot_states["active"].get(bot_id, False)
                    ]
                    
                    if not active_bots_to_use_ids: continue

                    with bots_lock:
                        spam_tasks_running.add(server_id)

                    server['last_spam_time'] = now
                    
                    print(f"[SPAM DISPATCHER] Cấp luồng cho server '{server['name']}' trong nhóm '{group['name']}'.", flush=True)
                    threading.Thread(
                        target=run_spam_cycle, 
                        args=(server_id, server['spam_channel_id'], server['spam_message'], active_bots_to_use_ids)
                    ).start()
            
            time.sleep(1)
        except Exception as e:
            print(f"[SPAM ERROR] Lỗi trong vòng lặp spam: {e}", flush=True)
            traceback.print_exc()
            time.sleep(5)


# ... (Các hàm khác của multi_bot_control.py giữ nguyên: get_bot_name, _find_and_select_card, handle_clan_drop, handle_grab, ...)
# --- HÀM TRỢ GIÚP CHUNG ---
def get_bot_name(bot_id_str):
    try:
        parts = bot_id_str.split('_')
        b_type, b_index = parts[0], int(parts[1])
        if b_type == 'main':
            # Main bot ID bắt đầu từ 1
            return BOT_NAMES[b_index - 1] if 0 < b_index <= len(BOT_NAMES) else f"MAIN_{b_index}"
        # Sub bot ID bắt đầu từ 0
        return acc_names[b_index] if b_index < len(acc_names) else f"SUB_{b_index+1}"
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

# --- LOGIC GRAB CARD (UPDATED) ---
def _find_and_select_card(bot, channel_id, last_drop_msg_id, heart_threshold, bot_num, ktb_channel_id, max_heart_threshold=99999):
    """Hàm chung để tìm và chọn card dựa trên khoảng số heart."""
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
                    
                    valid_cards = []
                    for idx, hearts in enumerate(heart_numbers):
                        if heart_threshold <= hearts <= max_heart_threshold:
                            valid_cards.append((idx, hearts))
                    
                    if not valid_cards: continue
                    
                    max_index, max_num = max(valid_cards, key=lambda x: x[1])

                    delays = {1: [0.35, 1.35, 2.05], 2: [0.7, 1.8, 2.4], 3: [0.7, 1.8, 2.4], 4: [0.8, 1.9, 2.5]}
                    bot_delays = delays.get(bot_num, [0.9, 2.0, 2.6])
                    emoji = ["1️⃣", "2️⃣", "3️⃣"][max_index]
                    delay = bot_delays[max_index]
                    
                    print(f"[CARD GRAB | Bot {bot_num}] Chọn dòng {max_index+1} với {max_num}♡ (range: {heart_threshold}-{max_heart_threshold}) -> {emoji} sau {delay}s", flush=True)
                    
                    def grab_action():
                        try:
                            bot.addReaction(channel_id, last_drop_msg_id, emoji)
                            time.sleep(1.2)
                            if ktb_channel_id: bot.sendMessage(ktb_channel_id, "kt b")
                            print(f"[CARD GRAB | Bot {bot_num}] ✅ Đã grab và gửi kt b", flush=True)
                        except Exception as e:
                            print(f"[CARD GRAB | Bot {bot_num}] ❌ Lỗi grab: {e}", flush=True)

                    threading.Timer(delay, grab_action).start()
                    return True
            return False
        except Exception as e:
            print(f"[CARD GRAB | Bot {bot_num}] ❌ Lỗi đọc messages: {e}", flush=True)
    return False

# --- LOGIC BOT (UPDATED) ---
def handle_clan_drop(bot, msg, bot_num):
    clan_settings = bot_states["auto_clan_drop"]
    if not (clan_settings.get("enabled") and msg.get("channel_id") == clan_settings.get("channel_id")):
        return
    bot_id_str = f'main_{bot_num}'
    threshold = clan_settings.get("heart_thresholds", {}).get(bot_id_str, 50)
    max_threshold = clan_settings.get("max_heart_thresholds", {}).get(bot_id_str, 99999)
    threading.Thread(target=_find_and_select_card, args=(bot, clan_settings["channel_id"], msg["id"], threshold, bot_num, clan_settings["ktb_channel_id"], max_threshold), daemon=True).start()

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
            max_threshold = target_server.get(f'max_heart_threshold_{bot_num}', 99999)
            threading.Thread(target=_find_and_select_card, args=(bot, channel_id, last_drop_msg_id, threshold, bot_num, target_server.get('ktb_channel_id'), max_threshold), daemon=True).start()

        if watermelon_grab_enabled:
            def check_for_watermelon_patiently():
                time.sleep(5) 
                try:
                    target_message = bot.getMessage(channel_id, last_drop_msg_id).json()[0]
                    reactions = target_message.get('reactions', [])
                    for reaction in reactions:
                        emoji_name = reaction.get('emoji', {}).get('name', '')
                        if '🍉' in emoji_name or 'watermelon' in emoji_name.lower():
                            bot.addReaction(channel_id, last_drop_msg_id, "🍉")
                            return
                except Exception:
                    pass
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
            
        return is_connected
    except Exception:
        bot_states["health_stats"].setdefault(bot_id, {})['consecutive_failures'] = \
            bot_states["health_stats"][bot_id].get('consecutive_failures', 0) + 1
        return False

def handle_reboot_failure(bot_id):
    settings = bot_states["reboot_settings"].setdefault(bot_id, {'delay': 3600, 'enabled': True})
    failure_count = settings.get('failure_count', 0) + 1
    settings['failure_count'] = failure_count
    
    backoff_multiplier = min(2 ** failure_count, 8)
    base_delay = settings.get('delay', 3600)
    next_try_delay = max(600, base_delay / backoff_multiplier) * backoff_multiplier
    settings['next_reboot_time'] = time.time() + next_try_delay
    
    if failure_count >= 5:
        settings['enabled'] = False

def safe_reboot_bot(bot_id):
    if not bot_manager.start_reboot(bot_id):
        return False

    try:
        match = re.match(r"main_(\d+)", bot_id)
        if not match: raise ValueError("Định dạng bot_id không hợp lệ.")
        
        bot_index = int(match.group(1)) - 1
        if not (0 <= bot_index < len(main_tokens)): raise IndexError("Bot index ngoài phạm vi.")

        token = main_tokens[bot_index].strip()
        bot_manager.remove_bot(bot_id)

        settings = bot_states["reboot_settings"].get(bot_id, {})
        failure_count = settings.get('failure_count', 0)
        wait_time = random.uniform(20, 40) + min(failure_count * 30, 300)
        time.sleep(wait_time)

        new_bot = create_bot(token, bot_identifier=(bot_index + 1), is_main=True)
        if not new_bot: raise Exception("Không thể tạo instance bot mới.")

        bot_manager.add_bot(bot_id, new_bot)
        
        settings.update({ 'next_reboot_time': time.time() + settings.get('delay', 3600), 'failure_count': 0, 'last_reboot_time': time.time() })
        bot_states["health_stats"][bot_id]['consecutive_failures'] = 0
        return True
    except Exception:
        handle_reboot_failure(bot_id)
        return False
    finally:
        bot_manager.end_reboot(bot_id)

# --- VÒNG LẶP NỀN (IMPROVED) ---
def auto_reboot_loop():
    last_global_reboot_time = 0
    consecutive_system_failures = 0
    
    while not stop_events["reboot"].is_set():
        try:
            now = time.time()
            min_global_interval = 600
            if now - last_global_reboot_time < min_global_interval:
                stop_events["reboot"].wait(60)
                continue

            bot_to_reboot = None
            highest_priority_score = -1
            reboot_settings_copy = dict(bot_states["reboot_settings"].items())
            
            for bot_id, settings in reboot_settings_copy.items():
                if not settings.get('enabled', False) or bot_manager.is_rebooting(bot_id): continue
                next_reboot_time = settings.get('next_reboot_time', 0)
                if now < next_reboot_time: continue
                    
                health_stats = bot_states["health_stats"].get(bot_id, {})
                failure_count = health_stats.get('consecutive_failures', 0)
                time_overdue = now - next_reboot_time
                priority_score = (failure_count * 1000) + time_overdue
                
                if priority_score > highest_priority_score:
                    highest_priority_score = priority_score
                    bot_to_reboot = bot_id
            
            if bot_to_reboot:
                if safe_reboot_bot(bot_to_reboot):
                    last_global_reboot_time = now
                    consecutive_system_failures = 0
                    wait_time = random.uniform(300, 600)
                    stop_events["reboot"].wait(wait_time)
                else:
                    consecutive_system_failures += 1
                    backoff_time = min(120 * (2 ** consecutive_system_failures), 1800)
                    stop_events["reboot"].wait(backoff_time)
            else:
                stop_events["reboot"].wait(60)
        except Exception:
            stop_events["reboot"].wait(120)

def run_clan_drop_cycle():
    settings = bot_states["auto_clan_drop"]
    channel_id = settings.get("channel_id")
    
    active_main_bots = [ (bot, int(bot_id.split('_')[1])) for bot_id, bot in bot_manager.get_main_bots_info() if bot and bot_states["active"].get(bot_id, False) ]
    if not active_main_bots: return

    for bot, bot_num in active_main_bots:
        if stop_events["clan_drop"].is_set(): break
        try:
            bot.sendMessage(channel_id, "kd")
            time.sleep(random.uniform(settings["bot_delay"] * 0.8, settings["bot_deloy"] * 1.2))
        except Exception: pass
    
    settings["last_cycle_start_time"] = time.time()
    save_settings()

def auto_clan_drop_loop():
    while not stop_events["clan_drop"].is_set():
        settings = bot_states["auto_clan_drop"]
        if (settings.get("enabled") and settings.get("channel_id") and (time.time() - settings.get("last_cycle_start_time", 0)) >= settings.get("cycle_interval", 1800)):
            run_clan_drop_cycle()
        stop_events["clan_drop"].wait(60)

def periodic_task(interval, task_func, task_name):
    while True:
        time.sleep(interval)
        try:
            task_func()
        except Exception: pass

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
                    bot_states["health_stats"].setdefault(bot_id_str, {})
                    bot_states["health_stats"][bot_id_str].update({'created_time': time.time(), 'consecutive_failures': 0})
            except Exception: pass
        
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
                            safe_message_handler_wrapper(handler, bot, msg, bot_identifier)
                except Exception: pass

        def start_gateway():
            try:
                bot.gateway.run(auto_reconnect=True)
            except Exception: pass
        
        threading.Thread(target=start_gateway, daemon=True).start()
        
        connection_timeout = 20
        start_time = time.time()
        while time.time() - start_time < connection_timeout:
            if hasattr(bot.gateway, 'connected') and bot.gateway.connected: return bot
            time.sleep(0.5)
        
        bot.gateway.close()
        return None
    except Exception:
        return None

# --- FLASK APP & GIAO DIỆN (UPDATED) ---
app = Flask(__name__)
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Shadow Network Control - Group Spam Integrated</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <link href="https://fonts.googleapis.com/css2?family=Creepster&family=Orbitron:wght@400;700;900&family=Courier+Prime:wght@400;700&family=Nosifer&display=swap" rel="stylesheet">
    <style>
        :root { --primary-bg: #0a0a0a; --secondary-bg: #1a1a1a; --panel-bg: #111111; --border-color: #333333; --blood-red: #8b0000; --dark-red: #550000; --bone-white: #f8f8ff; --necro-green: #228b22; --text-primary: #f0f0f0; --text-secondary: #cccccc; --warning-orange: #ff8c00; --success-green: #32cd32; --purple: #9932CC;}
        body { font-family: 'Courier Prime', monospace; background: var(--primary-bg); color: var(--text-primary); margin: 0; padding: 0;}
        .container { max-width: 1800px; margin: 0 auto; padding: 20px; }
        .header { text-align: center; margin-bottom: 30px; padding: 20px; border-bottom: 2px solid var(--blood-red); position: relative; }
        .title { font-family: 'Nosifer', cursive; font-size: 3rem; color: var(--blood-red); }
        .subtitle { font-family: 'Orbitron', sans-serif; font-size: 1rem; color: var(--necro-green); margin-top: 10px; }
        .main-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(500px, 1fr)); gap: 20px; }
        .panel { background: var(--panel-bg); border: 1px solid var(--border-color); border-radius: 10px; padding: 25px; position: relative;}
        .panel h2, .panel h3 { font-family: 'Orbitron', cursive; font-size: 1.4rem; margin-bottom: 20px; text-transform: uppercase; border-bottom: 2px solid; padding-bottom: 10px; color: var(--bone-white); }
        .panel h2 i, .panel h3 i { margin-right: 10px; }
        .btn { background: var(--secondary-bg); border: 1px solid var(--border-color); color: var(--text-primary); padding: 10px 15px; border-radius: 4px; cursor: pointer; font-family: 'Orbitron', monospace; font-weight: 700; text-transform: uppercase; width: 100%; transition: all 0.3s ease; }
        .btn:hover { background: var(--dark-red); border-color: var(--blood-red); }
        .btn-small { padding: 5px 10px; font-size: 0.9em;}
        .input-group { display: flex; align-items: stretch; gap: 10px; margin-bottom: 15px; }
        .input-group label { background: #000; border: 1px solid var(--border-color); border-right: 0; padding: 10px 15px; border-radius: 4px 0 0 4px; display:flex; align-items:center; min-width: 120px;}
        .input-group input, .input-group textarea, .input-group select { flex-grow: 1; background: #000; border: 1px solid var(--border-color); color: var(--text-primary); padding: 10px 15px; border-radius: 0 4px 4px 0; font-family: 'Courier Prime', monospace; }
        .grab-section { display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; padding: 15px; background: rgba(0,0,0,0.2); border-radius: 8px;}
        .grab-section h3 { margin: 0; display: flex; align-items: center; gap: 10px; width: 80px; flex-shrink: 0; }
        .grab-section .input-group { margin-bottom: 0; flex-grow: 1; margin-left: 20px;}
        .msg-status { text-align: center; color: var(--necro-green); padding: 12px; border: 1px dashed var(--border-color); border-radius: 4px; margin-bottom: 20px; display: none; }
        .status-panel, .global-settings-panel, .clan-drop-panel, .group-management-panel { grid-column: 1 / -1; }
        .status-row { display: flex; justify-content: space-between; align-items: center; padding: 12px; background: rgba(0,0,0,0.4); border-radius: 8px; }
        .timer-display { font-size: 1.2em; font-weight: 700; }
        .bot-status-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 8px; }
        .bot-status-item { display: flex; justify-content: space-between; align-items: center; padding: 5px 8px; background: rgba(0,0,0,0.3); border-radius: 4px; }
        .btn-toggle-state { padding: 3px 5px; font-size: 0.9em; border-radius: 4px; cursor: pointer; text-transform: uppercase; background: transparent; font-weight: 700; border: none; }
        .btn-rise { color: var(--success-green); } .btn-rest { color: var(--dark-red); } .btn-warning { color: var(--warning-orange); }
        .add-btn { display: flex; align-items: center; justify-content: center; min-height: 200px; border: 2px dashed var(--border-color); cursor: pointer; transition: all 0.3s ease; flex-direction: column; }
        .add-btn:hover { background: var(--secondary-bg); border-color: var(--blood-red); }
        .add-btn i { font-size: 3rem; color: var(--text-secondary); margin-bottom: 10px; }
        .btn-delete { position: absolute; top: 15px; right: 15px; background: var(--dark-red); border: 1px solid var(--blood-red); color: var(--bone-white); width: 30px; height: 30px; border-radius: 50%; display: flex; align-items: center; justify-content: center;}
        .server-sub-panel, .group-sub-panel { border-top: 1px solid var(--border-color); margin-top: 20px; padding-top: 20px;}
        .health-indicator { display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-left: 5px; }
        .health-good { background-color: var(--success-green); } .health-warning { background-color: var(--warning-orange); } .health-bad { background-color: var(--blood-red); }
        .heart-input { flex-grow: 0 !important; width: 100px; text-align: center; }
        .group-panel { border-left: 5px solid var(--purple); }
        .bot-selector { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 5px; margin-top: 10px; max-height: 150px; overflow-y: auto; background: #000; padding: 10px; border-radius: 4px;}
        .bot-selector-item label { display: flex; align-items: center; width: 100%; font-size: 0.9em; cursor: pointer; }
        .bot-selector-item input { margin-right: 10px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1 class="title">Shadow Network Control</h1>
            <div class="subtitle">Group Spam & Enhanced Safe Reboot System</div>
        </div>
        <div id="msg-status-container" class="msg-status"> <span id="msg-status-text"></span></div>

        <div class="panel status-panel">
             <h2><i class="fas fa-heartbeat"></i> System Status & Enhanced Reboot Control</h2>
             <div id="bot-control-grid" class="bot-status-grid" style="grid-template-columns: repeat(auto-fit, minmax(380px, 1fr));"></div>
        </div>
        
        <div class="panel group-management-panel">
            <h2><i class="fas fa-layer-group"></i> Group Spam Management</h2>
            <div id="group-grid" class="main-grid">
                {% for group in spam_groups %}
                <div class="panel group-panel" data-group-id="{{ group.id }}">
                    <button class="btn-delete delete-group-btn"><i class="fas fa-times"></i></button>
                    <h3>{{ group.name }}</h3>
                    <div class="input-group">
                        <label>Spam Control</label>
                        <button class="btn group-spam-toggle">{{ 'DISABLE' if group.spam_enabled else 'ENABLE' }}</button>
                    </div>
                    <div class="group-sub-panel">
                        <h4>Select Bots for this Group:</h4>
                        <div class="bot-selector">
                            {% for bot in all_bots_info %}
                            <div class="bot-selector-item"><label><input type="checkbox" class="bot-checkbox" value="{{ bot.reboot_id }}" {% if bot.reboot_id in group.get('selected_bots', []) %}checked{% endif %}> {{ bot.name }}</label></div>
                            {% endfor %}
                        </div>
                    </div>
                </div>
                {% endfor %}
                <div id="add-group-btn" class="panel add-btn">
                    <i class="fas fa-plus"></i><span>Add New Group</span>
                </div>
            </div>
        </div>

        <div class="main-grid">
            <div class="panel clan-drop-panel">
                <h2><i class="fas fa-users"></i> Clan Auto Drop</h2>
                <div class="server-sub-panel">
                    <div class="input-group"><label>Drop Channel ID</label><input type="text" id="clan-drop-channel-id" value="{{ auto_clan_drop.channel_id or '' }}"></div>
                    <div class="input-group"><label>KTB Channel ID</label><input type="text" id="clan-drop-ktb-channel-id" value="{{ auto_clan_drop.ktb_channel_id or '' }}"></div>
                    {% for bot in main_bots_info %}
                    <div class="grab-section"><h3>{{ bot.name }}</h3><div class="input-group"><input type="number" class="clan-drop-threshold heart-input" data-node="main_{{ bot.id }}" value="{{ auto_clan_drop.heart_thresholds[('main_' + bot.id|string)]|default(50) }}" placeholder="Min ♡"><input type="number" class="clan-drop-max-threshold heart-input" data-node="main_{{ bot.id }}" value="{{ auto_clan_drop.max_heart_thresholds[('main_' + bot.id|string)]|default(99999) }}" placeholder="Max ♡"></div></div>
                    {% endfor %}
                    <button type="button" id="clan-drop-save-btn" class="btn">Save Clan Settings</button>
                    <button type="button" id="clan-drop-toggle-btn" class="btn" style="margin-top:10px;">{{ 'DISABLE' if auto_clan_drop.enabled else 'ENABLE' }}</button>
                </div>
            </div>
             <div class="panel global-settings-panel">
                <h2><i class="fas fa-globe"></i> Global Event Settings</h2>
                <div class="server-sub-panel">
                    <h3><i class="fas fa-seedling"></i> Watermelon Grab</h3>
                    <div id="global-watermelon-grid" class="bot-status-grid" style="grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));"></div>
                </div>
            </div>
        </div>
        
        <h2 style="font-family: 'Orbitron'; color: var(--bone-white); margin-top: 40px;"><i class="fas fa-server"></i> Server Management</h2>
        <div class="main-grid">
            {% for server in servers %}
            <div class="panel server-panel" data-server-id="{{ server.id }}">
                <button class="btn-delete delete-server-btn" title="Delete Server"><i class="fas fa-times"></i></button>
                <h3><i class="fas fa-server"></i> {{ server.name }}</h3>
                <div class="server-sub-panel">
                    <h4><i class="fas fa-cogs"></i> Channel & Group Config</h4>
                    <div class="input-group">
                        <label>Assign to Group</label>
                        <select class="server-group-select">
                            <option value="">-- No Group --</option>
                            {% for group in spam_groups %}<option value="{{ group.id }}" {{ 'selected' if server.group_id == group.id else '' }}>{{ group.name }}</option>{% endfor %}
                        </select>
                    </div>
                    <div class="input-group"><label>Main (Grab)</label><input type="text" class="channel-input" data-field="main_channel_id" value="{{ server.main_channel_id or '' }}"></div>
                    <div class="input-group"><label>KTB Channel</label><input type="text" class="channel-input" data-field="ktb_channel_id" value="{{ server.ktb_channel_id or '' }}"></div>
                    <div class="input-group"><label>Spam Channel</label><input type="text" class="channel-input" data-field="spam_channel_id" value="{{ server.spam_channel_id or '' }}"></div>
                </div>
                <div class="server-sub-panel">
                    <h4><i class="fas fa-paper-plane"></i> Auto Broadcast (thuộc Group)</h4>
                    <div class="input-group"><label>Message</label><textarea class="spam-message channel-input" data-field="spam_message" rows="2">{{ server.spam_message or '' }}</textarea></div>
                    <div class="input-group"><label>Delay (s)</label><input type="number" class="spam-delay channel-input" data-field="spam_delay" value="{{ server.spam_delay or 30 }}"></div>
                    <p style="font-size: 0.8em; color: var(--text-secondary);">Lưu ý: Việc BẬT/TẮT spam được quản lý ở cấp độ NHÓM. Delay và Message là của riêng server này.</p>
                </div>
                <div class="server-sub-panel">
                    <h4><i class="fas fa-crosshairs"></i> Soul Harvest (Card Grab)</h4>
                    {% for bot in main_bots_info %}
                    <div class="grab-section">
                        <h3>{{ bot.name }}</h3>
                        <div class="input-group">
                             <input type="number" class="harvest-threshold heart-input" data-node="{{ bot.id }}" value="{{ server['heart_threshold_' + bot.id|string] or 50 }}" placeholder="Min ♡">
                            <input type="number" class="harvest-max-threshold heart-input" data-node="{{ bot.id }}" value="{{ server['max_heart_threshold_' + bot.id|string]|default(99999) }}" placeholder="Max ♡">
                            <button type="button" class="btn harvest-toggle" data-node="{{ bot.id }}">
                                {{ 'DISABLE' if server['auto_grab_enabled_' + bot.id|string] else 'ENABLE' }}
                            </button>
                        </div>
                    </div>
                    {% endfor %}
                </div>
            </div>
            {% endfor %}
            <div class="panel add-btn" id="add-server-btn">
                <i class="fas fa-plus"></i><span>Add New Server</span>
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
            msgStatusContainer.className = `msg-status ${type === 'error' ? 'error' : ''}`;
            msgStatusContainer.style.display = 'block';
            setTimeout(() => { msgStatusContainer.style.display = 'none'; }, 4000);
        }

        async function postData(url = '', data = {}) {
            try {
                const response = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) });
                const result = await response.json();
                showStatusMessage(result.message, result.status);
                if (result.reload) { setTimeout(() => window.location.reload(), 500); }
                if (result.status === 'success' && url !== '/api/save_settings') {
                    fetch('/api/save_settings', { method: 'POST' });
                }
                setTimeout(fetchStatus, 500);
                return result;
            } catch (error) { showStatusMessage('Server communication error.', 'error'); }
        }
        
        async function fetchStatus() {
             try {
                const response = await fetch('/status');
                const data = await response.json();
                
                const botControlGrid = document.getElementById('bot-control-grid');
                botControlGrid.innerHTML = '';
                const allBots = [...data.bot_statuses.main_bots, ...data.bot_statuses.sub_accounts];

                allBots.forEach(bot => {
                    const botId = bot.reboot_id;
                    let itemContainer = document.createElement('div');
                    itemContainer.className = 'status-row';
                    itemContainer.style.cssText = 'flex-direction: column; align-items: stretch; padding: 10px;';
                    
                    let healthClass = 'health-good';
                    if (bot.health_status === 'warning') healthClass = 'health-warning';
                    else if (bot.health_status === 'bad') healthClass = 'health-bad';
                    let rebootingIndicator = bot.is_rebooting ? ' <i class="fas fa-sync-alt fa-spin"></i>' : '';

                    let controlHtml = `<div style="display: flex; justify-content: space-between; align-items: center; width: 100%;"><span style="font-weight: bold; ${bot.type === 'main' ? 'color: #FF4500;' : ''}">${bot.name}<span class="health-indicator ${healthClass}"></span>${rebootingIndicator}</span><button type="button" data-target="${botId}" class="btn-toggle-state ${bot.is_active ? 'btn-rise' : 'btn-rest'}">${bot.is_active ? 'ONLINE' : 'OFFLINE'}</button></div>`;

                    if (bot.type === 'main') {
                        const r_settings = data.bot_reboot_settings[botId] || {};
                        const statusClass = r_settings.failure_count > 0 ? 'btn-warning' : (r_settings.enabled ? 'btn-rise' : 'btn-rest');
                        const statusText = r_settings.failure_count > 0 ? `FAIL(${r_settings.failure_count})` : (r_settings.enabled ? 'AUTO' : 'MANUAL');
                        controlHtml += `<div class="input-group" style="margin-top: 10px; margin-bottom: 0;"><input type="number" class="bot-reboot-delay" value="${r_settings.delay}" data-bot-id="${botId}" style="width: 80px; text-align: right; flex-grow: 0;"><button type="button" class="btn btn-small bot-reboot-toggle ${statusClass}" data-bot-id="${botId}">${statusText}</button></div>`;
                    }
                    itemContainer.innerHTML = controlHtml;
                    botControlGrid.appendChild(itemContainer);
                });

                const wmGrid = document.getElementById('global-watermelon-grid');
                wmGrid.innerHTML = '';
                data.bot_statuses.main_bots.forEach(bot => {
                    const botNodeId = bot.reboot_id;
                    const isEnabled = data.watermelon_grab_states[botNodeId];
                    const item = document.createElement('div');
                    item.className = 'bot-status-item';
                    item.innerHTML = `<span>${bot.name}</span><button type="button" class="btn btn-small watermelon-toggle" data-node="${botNodeId}"><i class="fas fa-seedling"></i>&nbsp;${isEnabled ? 'DISABLE' : 'ENABLE'}</button>`;
                    wmGrid.appendChild(item);
                });
            } catch (error) { console.error('Error fetching status:', error); }
        }
        setInterval(fetchStatus, 5000);
        fetchStatus();

        // Main Click Handler
        document.body.addEventListener('click', e => {
            const button = e.target.closest('button');
            if (!button) return;

            // Global buttons
            if (button.matches('.btn-toggle-state')) { postData('/api/toggle_bot_state', { target: button.dataset.target }); return; }
            if (button.matches('.bot-reboot-toggle')) { postData('/api/bot_reboot_toggle', { bot_id: button.dataset.botId, delay: document.querySelector(`.bot-reboot-delay[data-bot-id="${button.dataset.botId}"]`).value }); return; }
            if (button.matches('#clan-drop-toggle-btn')) { postData('/api/clan_drop_toggle'); return; }
            if (button.matches('#clan-drop-save-btn')) {
                const thresholds = {}, maxThresholds = {};
                document.querySelectorAll('.clan-drop-threshold').forEach(i => { thresholds[i.dataset.node] = parseInt(i.value, 10); });
                document.querySelectorAll('.clan-drop-max-threshold').forEach(i => { maxThresholds[i.dataset.node] = parseInt(i.value, 10); });
                postData('/api/clan_drop_update', { channel_id: document.getElementById('clan-drop-channel-id').value, ktb_channel_id: document.getElementById('clan-drop-ktb-channel-id').value, heart_thresholds: thresholds, max_heart_thresholds: maxThresholds });
                return;
            }
            if (button.matches('.watermelon-toggle')) { postData('/api/watermelon_toggle', { node: button.dataset.node }); return; }
            if (button.matches('#add-server-btn')) { const name = prompt("Enter a name for the new server:"); if (name) postData('/api/add_server', { name }); return; }
            if (button.matches('#add-group-btn')) { const name = prompt("Nhập tên nhóm mới:"); if (name) postData('/api/group/add', { name }); return; }
            
            // Server Panel Buttons
            const serverPanel = button.closest('.server-panel');
            if (serverPanel) {
                const serverId = serverPanel.dataset.serverId;
                if (button.matches('.delete-server-btn')) { if (confirm('Are you sure?')) postData('/api/delete_server', { server_id: serverId }); }
                if (button.matches('.harvest-toggle')) { postData('/api/harvest_toggle', { server_id: serverId, node: button.dataset.node, threshold: serverPanel.querySelector(`.harvest-threshold[data-node="${button.dataset.node}"]`).value, max_threshold: serverPanel.querySelector(`.harvest-max-threshold[data-node="${button.dataset.node}"]`).value }); }
                return;
            }

            // Group Panel Buttons
            const groupPanel = button.closest('.group-panel');
            if (groupPanel) {
                const groupId = groupPanel.dataset.groupId;
                if (button.matches('.delete-group-btn')) { if (confirm('Xóa nhóm này? Các server trong nhóm sẽ bị mất nhóm.')) postData('/api/group/delete', { group_id: groupId }); }
                if (button.matches('.group-spam-toggle')) { postData('/api/group/spam_toggle', { group_id: groupId }).then(() => location.reload()); }
                return;
            }
        });

        // Main Change Handler
        document.body.addEventListener('change', e => {
            const target = e.target;
            
            const serverPanel = target.closest('.server-panel');
            if (serverPanel) {
                const serverId = serverPanel.dataset.serverId;
                let payload = { server_id: serverId };
                if (target.matches('.channel-input')) {
                     payload[target.dataset.field] = target.value;
                } else if (target.matches('.server-group-select')) {
                     payload['group_id'] = target.value;
                }
                postData('/api/update_server', payload);
                return;
            }

            const groupPanel = target.closest('.group-panel');
            if (groupPanel && target.matches('.bot-checkbox')) {
                const groupId = groupPanel.dataset.groupId;
                const selected_bots = Array.from(groupPanel.querySelectorAll('.bot-checkbox:checked')).map(cb => cb.value);
                postData('/api/group/update', { group_id: groupId, selected_bots });
                return;
            }
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
    
    all_bots_info = []
    main_bots = [{"name": get_bot_name(bid), "reboot_id": bid} for bid, _ in bot_manager.get_main_bots_info()]
    sub_bots = [{"name": get_bot_name(bid), "reboot_id": bid} for bid, _ in bot_manager.get_sub_bots_info()]
    all_bots_info.extend(sorted(main_bots, key=lambda x: int(x['reboot_id'].split('_')[1])))
    all_bots_info.extend(sorted(sub_bots, key=lambda x: int(x['reboot_id'].split('_')[1])))
    
    if "max_heart_thresholds" not in bot_states["auto_clan_drop"]:
        bot_states["auto_clan_drop"]["max_heart_thresholds"] = {}

    return render_template_string(HTML_TEMPLATE, 
        servers=sorted(servers, key=lambda s: s.get('name', '')), 
        main_bots_info=main_bots_info, 
        auto_clan_drop=bot_states["auto_clan_drop"],
        spam_groups=bot_states["spam_groups"],
        all_bots_info=all_bots_info
    )

# --- GROUP API (NEW) ---
@app.route("/api/group/add", methods=['POST'])
def api_group_add():
    name = request.json.get('name')
    if not name: return jsonify({'status': 'error', 'message': 'Tên nhóm là bắt buộc.'}), 400
    new_group = {
        "id": f"group_{uuid.uuid4().hex}", "name": name, "spam_enabled": False, "selected_bots": []
    }
    bot_states["spam_groups"].append(new_group)
    return jsonify({'status': 'success', 'message': f'Nhóm "{name}" đã được thêm.', 'reload': True})

@app.route("/api/group/delete", methods=['POST'])
def api_group_delete():
    group_id = request.json.get('group_id')
    bot_states["spam_groups"] = [g for g in bot_states["spam_groups"] if g.get('id') != group_id]
    for server in servers:
        if server.get('group_id') == group_id:
            server['group_id'] = None
    return jsonify({'status': 'success', 'message': 'Nhóm đã được xóa.', 'reload': True})

@app.route("/api/group/spam_toggle", methods=['POST'])
def api_group_spam_toggle():
    group_id = request.json.get('group_id')
    group = next((g for g in bot_states["spam_groups"] if g.get('id') == group_id), None)
    if not group: return jsonify({'status': 'error', 'message': 'Không tìm thấy nhóm.'}), 404
    group['spam_enabled'] = not group.get('spam_enabled', False)
    if group['spam_enabled']:
        for server in servers:
            if server.get('group_id') == group_id:
                server['last_spam_time'] = time.time()
    state = "BẬT" if group['spam_enabled'] else "TẮT"
    return jsonify({'status': 'success', 'message': f"Spam nhóm đã {state}."})

@app.route("/api/group/update", methods=['POST'])
def api_group_update():
    data = request.json
    group_id = data.get('group_id')
    group = next((g for g in bot_states["spam_groups"] if g.get('id') == group_id), None)
    if not group: return jsonify({'status': 'error', 'message': 'Không tìm thấy nhóm.'}), 404
    if 'selected_bots' in data: group['selected_bots'] = data['selected_bots']
    return jsonify({'status': 'success', 'message': f'Đã cập nhật bot cho nhóm {group["name"]}.'})

# --- SERVER & OTHER API (UPDATED and EXISTING) ---
def find_server(server_id):
    return next((s for s in servers if s.get('id') == server_id), None)

@app.route("/api/add_server", methods=['POST'])
def api_add_server():
    name = request.json.get('name')
    if not name: return jsonify({'status': 'error', 'message': 'Tên server là bắt buộc.'}), 400
    new_server = {"id": f"server_{uuid.uuid4().hex}", "name": name, "spam_delay": 30, "group_id": None}
    main_bots_count = len([t for t in main_tokens if t.strip()])
    for i in range(main_bots_count):
        new_server[f'auto_grab_enabled_{i+1}'] = False
        new_server[f'heart_threshold_{i+1}'] = 50
        new_server[f'max_heart_threshold_{i+1}'] = 99999
    servers.append(new_server)
    return jsonify({'status': 'success', 'message': f'✅ Server "{name}" đã được thêm.', 'reload': True})

@app.route("/api/delete_server", methods=['POST'])
def api_delete_server():
    server_id = request.json.get('server_id')
    servers[:] = [s for s in servers if s.get('id') != server_id]
    return jsonify({'status': 'success', 'message': f'🗑️ Server đã được xóa.', 'reload': True})
    
@app.route("/api/update_server", methods=['POST'])
def api_update_server():
    data = request.json
    server = find_server(data.get('server_id'))
    if not server: return jsonify({'status': 'error', 'message': 'Không tìm thấy server.'}), 404
    
    allowed_fields = ['main_channel_id', 'ktb_channel_id', 'spam_channel_id', 'spam_message', 'spam_delay', 'group_id']
    for field in allowed_fields:
        if field in data:
            value = data[field]
            # Chuyển đổi kiểu dữ liệu nếu cần
            if field == 'spam_delay' and value is not None:
                try: value = int(value)
                except (ValueError, TypeError): value = 30 # Mặc định
            server[field] = value

    return jsonify({'status': 'success', 'message': f'🔧 Kênh đã được cập nhật cho {server["name"]}.'})

@app.route("/api/harvest_toggle", methods=['POST'])
def api_harvest_toggle():
    data = request.json
    server, node_str = find_server(data.get('server_id')), data.get('node')
    if not server or not node_str: return jsonify({'status': 'error', 'message': 'Yêu cầu không hợp lệ.'}), 400
    node = str(node_str)
    server[f'auto_grab_enabled_{node}'] = not server.get(f'auto_grab_enabled_{node}', False)
    server[f'heart_threshold_{node}'] = int(data.get('threshold', 50))
    server[f'max_heart_threshold_{node}'] = int(data.get('max_threshold', 99999))
    status_msg = 'ENABLED' if server[f'auto_grab_enabled_{node}'] else 'DISABLED'
    return jsonify({'status': 'success', 'message': f"🎯 Card Grab cho {get_bot_name(f'main_{node}')} đã {status_msg}."})

@app.route("/api/clan_drop_toggle", methods=['POST'])
def api_clan_drop_toggle():
    settings = bot_states["auto_clan_drop"]
    settings['enabled'] = not settings.get('enabled', False)
    if settings['enabled']:
        if not settings.get('channel_id'):
            settings['enabled'] = False
            return jsonify({'status': 'error', 'message': 'Clan Drop Channel ID phải được cài đặt.'})
        threading.Thread(target=run_clan_drop_cycle).start()
        msg = "✅ Clan Auto Drop ENABLED."
    else:
        msg = "🛑 Clan Auto Drop DISABLED."
    return jsonify({'status': 'success', 'message': msg})

@app.route("/api/clan_drop_update", methods=['POST'])
def api_clan_drop_update():
    data = request.get_json()
    thresholds = bot_states["auto_clan_drop"].setdefault('heart_thresholds', {})
    max_thresholds = bot_states["auto_clan_drop"].setdefault('max_heart_thresholds', {})
    for key, value in data.get('heart_thresholds', {}).items():
        if isinstance(value, int): thresholds[key] = value
    for key, value in data.get('max_heart_thresholds', {}).items():
        if isinstance(value, int): max_thresholds[key] = value
    bot_states["auto_clan_drop"].update({ 'channel_id': data.get('channel_id', '').strip(), 'ktb_channel_id': data.get('ktb_channel_id', '').strip()})
    return jsonify({'status': 'success', 'message': '💾 Clan Drop settings updated.'})

@app.route("/api/watermelon_toggle", methods=['POST'])
def api_watermelon_toggle():
    node = request.json.get('node')
    bot_states["watermelon_grab"][node] = not bot_states["watermelon_grab"].get(node, False)
    status_msg = 'ENABLED' if bot_states["watermelon_grab"][node] else 'DISABLED'
    return jsonify({'status': 'success', 'message': f"🍉 Global Watermelon Grab đã {status_msg} cho {get_bot_name(node)}."})

@app.route("/api/bot_reboot_toggle", methods=['POST'])
def api_bot_reboot_toggle():
    data = request.json
    bot_id, delay = data.get('bot_id'), int(data.get("delay", 3600))
    settings = bot_states["reboot_settings"].get(bot_id)
    settings.update({'enabled': not settings.get('enabled', False), 'delay': delay, 'failure_count': 0})
    if settings['enabled']: settings['next_reboot_time'] = time.time() + delay
    msg = f"🔄 Auto-Reboot {'ENABLED' if settings['enabled'] else 'DISABLED'} cho {get_bot_name(bot_id)}"
    return jsonify({'status': 'success', 'message': msg})

@app.route("/api/toggle_bot_state", methods=['POST'])
def api_toggle_bot_state():
    target = request.json.get('target')
    bot_states["active"][target] = not bot_states["active"][target]
    state_text = "🟢 ONLINE" if bot_states["active"][target] else "🔴 OFFLINE"
    return jsonify({'status': 'success', 'message': f"Bot {get_bot_name(target)} đã được set thành {state_text}"})

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
            status_list.append({ "name": get_bot_name(bot_id), "reboot_id": bot_id, "is_active": bot_states["active"].get(bot_id, False), "type": type_prefix, "health_status": health_status, "is_rebooting": bot_manager.is_rebooting(bot_id)})
        return sorted(status_list, key=lambda x: int(x['reboot_id'].split('_')[1]))

    bot_statuses = { "main_bots": get_bot_status_list(bot_manager.get_main_bots_info(), "main"), "sub_accounts": get_bot_status_list(bot_manager.get_sub_bots_info(), "sub")}
    reboot_settings_copy = bot_states["reboot_settings"].copy()
    for bot_id, settings in reboot_settings_copy.items():
        settings['countdown'] = max(0, settings.get('next_reboot_time', 0) - now) if settings.get('enabled') else 0

    return jsonify({ 'bot_reboot_settings': reboot_settings_copy, 'bot_statuses': bot_statuses, 'watermelon_grab_states': bot_states["watermelon_grab"] })

# --- MAIN EXECUTION (UPDATED) ---
if __name__ == "__main__":
    print("🚀 Shadow Network Control - V4 Group Spam Integrated Starting...", flush=True)
    load_settings()

    print("🔌 Initializing bots using Bot Manager...", flush=True)
    
    for i, token in enumerate(t for t in main_tokens if t.strip()):
        bot_num = i + 1; bot_id = f"main_{bot_num}"
        bot = create_bot(token.strip(), bot_identifier=bot_num, is_main=True)
        if bot: bot_manager.add_bot(bot_id, bot)
        bot_states["active"].setdefault(bot_id, True)
        bot_states["watermelon_grab"].setdefault(bot_id, False)
        bot_states["auto_clan_drop"]["heart_thresholds"].setdefault(bot_id, 50)
        bot_states["auto_clan_drop"].setdefault("max_heart_thresholds", {}).setdefault(bot_id, 99999)
        bot_states["reboot_settings"].setdefault(bot_id, {'enabled': False, 'delay': 3600, 'next_reboot_time': 0, 'failure_count': 0})
        bot_states["health_stats"].setdefault(bot_id, {'consecutive_failures': 0})

    for i, token in enumerate(t for t in tokens if t.strip()):
        bot_id = f"sub_{i}"
        bot = create_bot(token.strip(), bot_identifier=i, is_main=False)
        if bot: bot_manager.add_bot(bot_id, bot)
        bot_states["active"].setdefault(bot_id, True)
        bot_states["health_stats"].setdefault(bot_id, {'consecutive_failures': 0})

    print("🔧 Starting background threads...", flush=True)
    threading.Thread(target=periodic_task, args=(300, save_settings, "Save"), daemon=True).start()
    threading.Thread(target=periodic_task, args=(120, health_monitoring_check, "Health"), daemon=True).start()
    
    # <-- KHỞI ĐỘNG HỆ THỐNG SPAM MỚI -->
    threading.Thread(target=farm_style_spam_loop, daemon=True).start()
    
    threading.Thread(target=auto_reboot_loop, daemon=True).start()
    threading.Thread(target=auto_clan_drop_loop, daemon=True).start()
    
    port = int(os.environ.get("PORT", 10000))
    print(f"🌐 Web Server running at http://0.0.0.0:{port}", flush=True)
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
