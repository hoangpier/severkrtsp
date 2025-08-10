# PHIÊN BẢN NÂNG CẤP TOÀN DIỆN - V5.1 - DETAILED WEB LOGS
import discum, threading, time, os, re, requests, json, random, traceback, uuid
from flask import Flask, request, render_template_string, jsonify
from dotenv import load_dotenv
from datetime import datetime
from collections import defaultdict, deque

load_dotenv()

# --- CẤU HÌNH ---
main_tokens = os.getenv("MAIN_TOKENS", "").split(",")
tokens = os.getenv("TOKENS", "").split(",")
karuta_id, karibbit_id = "646937666251915264", "1311684840462225440"
BOT_NAMES = ["ALPHA", "xsyx", "sofa", "dont", "ayaya", "owo", "astra", "singo", "dia pox", "clam", "rambo", "domixi", "dogi", "sicula", "mo turn", "jan taru", "kio sama"]
acc_names = [f"Bot-{i:02d}" for i in range(1, 21)]

# --- BIẾN TRẠNG THÁI & KHÓA ---
servers = []
bot_user_ids = {}
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
        self.stats = defaultdict(lambda: {'successful_grabs': 0, 'failed_attempts': 0, 'highest_heart_grabbed': 0, 'cards_by_condition': defaultdict(int), 'total_hearts_grabbed': 0})
        self.lock = threading.RLock()

    def parse_card_info(self, message_content):
        content_lower = message_content.lower()
        condition_map = {
            'poor': ['poor', 'tệ', 'badly damaged', 'damaged'],
            'good': ['good', 'tốt', 'decent'],
            'excellent': ['excellent', 'tuyệt vời', 'xuất sắc', 'great'],
            'mint': ['mint', 'hoàn hảo', 'perfect', 'pristine']
        }
        condition = 'unknown'
        for cond, patterns in condition_map.items():
            if any(pattern in content_lower for pattern in patterns):
                condition = cond
                break
        
        hearts = 0
        hearts_patterns = [
            r'(\d+)\s*♡', r'(\d+)\s*hearts?', r'♡\s*(\d+)', 
            r'paid\s+(\d+)', r'trả\s+(\d+)', r'(\d+)\s*tim'
        ]
        for pattern in hearts_patterns:
            hearts_match = re.search(pattern, message_content, re.IGNORECASE)
            if hearts_match:
                hearts = int(hearts_match.group(1))
                break
        
        card_name = "Unknown Card"
        name_patterns = [
            r'took the\s+([^.!]+?)(?:\s+card|\s+and\s+paid|\.|!)',
            r'lấy thẻ\s+([^.!]+?)(?:\s+card|\s+và\s+trả|\.|!)',
            r'fought off.*?and took the\s+([^.!]+?)(?:\s+card|\s+and\s+paid|\.|!)'
        ]
        for pattern in name_patterns:
            name_match = re.search(pattern, content_lower, re.IGNORECASE)
            if name_match:
                card_name = name_match.group(1).strip().title()
                card_name = re.sub(r'\s+(card|thẻ)\s*$', '', card_name, flags=re.IGNORECASE)
                break
        
        return card_name, condition, hearts

    def log_event(self, bot_name, event_type, **kwargs):
        with self.lock:
            timestamp = datetime.now().strftime("%H:%M:%S")
            log_entry = {'timestamp': timestamp, 'bot_name': bot_name, 'type': event_type, **kwargs}
            self.logs.appendleft(log_entry)
            
            stats = self.stats[bot_name]
            
            if event_type == 'card_success':
                message_content = kwargs.get('message', '')
                card_name, condition, hearts = self.parse_card_info(message_content)
                
                stats['successful_grabs'] += 1
                stats['cards_by_condition'][condition] += 1
                stats['total_hearts_grabbed'] += hearts
                if hearts > stats['highest_heart_grabbed']:
                    stats['highest_heart_grabbed'] = hearts
                
                print(f"[GRAB SUCCESS] 🎉 {bot_name} GRABBED CARD!", flush=True)
                print(f"               🃏 Card Name: {card_name}", flush=True)
                print(f"               💎 Condition: {condition.upper()}", flush=True)
                print(f"               ♡♡♡ HEARTS: {hearts} ♡♡♡", flush=True)
                print(f"               💰 Total Hearts: {stats['total_hearts_grabbed']} | 🏆 Highest Heart: {stats['highest_heart_grabbed']}", flush=True)
                print("-" * 60, flush=True)
                
                log_entry.update({'card_name': card_name, 'condition': condition, 'hearts': hearts})
                
            elif event_type == 'failed':
                stats['failed_attempts'] += 1
                reason = kwargs.get('reason', 'Unknown')
                print(f"[GRAB FAILED] ❌ {bot_name}: {reason}", flush=True)
            
            elif event_type == 'attempt':
                print(f"[GRAB ATTEMPT] 🎯 {bot_name} attempting grab (Threshold: {kwargs.get('threshold', 0)}♡)...", flush=True)

    def get_logs_for_web(self, limit=50):
        with self.lock: return list(self.logs)[:limit]

    def get_stats_for_web(self):
        with self.lock:
            total_grabs = sum(s['successful_grabs'] for s in self.stats.values())
            total_fails = sum(s['failed_attempts'] for s in self.stats.values())
            summary = {
                'total_cards_grabbed': total_grabs,
                'total_failed_attempts': total_fails,
                'highest_heart_grabbed': max((s['highest_heart_grabbed'] for s in self.stats.values()), default=0),
                'success_rate': round((total_grabs * 100) / (total_grabs + total_fails), 1) if (total_grabs + total_fails) > 0 else 0
            }
            return {'bot_stats': dict(self.stats), 'summary': summary}

card_logger = CardGrabLogger()

# --- QUẢN LÝ BOT ---
class ThreadSafeBotManager:
    def __init__(self):
        self._bots, self._rebooting, self._lock = {}, set(), threading.RLock()
    def add_bot(self, bot_id, bot_instance):
        with self._lock: self._bots[bot_id] = bot_instance; print(f"[Bot Manager] ✅ Added {bot_id}", flush=True)
    def remove_bot(self, bot_id):
        with self._lock:
            if bot := self._bots.pop(bot_id, None):
                try:
                    if hasattr(bot, 'gateway') and hasattr(bot.gateway, 'close'): bot.gateway.close()
                except Exception as e: print(f"[Bot Manager] ⚠️ Error closing gateway for {bot_id}: {e}", flush=True)
                print(f"[Bot Manager] 🗑️ Removed {bot_id}", flush=True)
    def get_bot(self, bot_id):
        with self._lock: return self._bots.get(bot_id)
    def get_all_bots(self, active_only=False):
        with self._lock:
            bots = self._bots.items()
            return [(bid, b) for bid, b in bots if bot_states["active"].get(bid)] if active_only else list(bots)
    def get_main_bots_info(self):
        with self._lock: return [(bid, b) for bid, b in self._bots.items() if bid.startswith('main_')]
    def get_sub_bots_info(self):
        with self._lock: return [(bid, b) for bid, b in self._bots.items() if bid.startswith('sub_')]
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
    try:
        if api_key and bin_id:
            headers = {'Content-Type': 'application/json', 'X-Master-Key': api_key}
            req = requests.put(f"https://api.jsonbin.io/v3/b/{bin_id}", json=settings_data, headers=headers, timeout=10)
            if req.status_code == 200: return print("[Settings] ✅ Saved to JSONBin.io.", flush=True)
        with open('backup_settings.json', 'w') as f: json.dump(settings_data, f, indent=2)
        print("[Settings] ✅ Saved settings locally.", flush=True)
    except Exception as e: print(f"[Settings] ❌ Save failed: {e}", flush=True)

def load_settings():
    global servers, bot_states
    api_key, bin_id = os.getenv("JSONBIN_API_KEY"), os.getenv("JSONBIN_BIN_ID")
    settings = None
    try:
        if api_key and bin_id:
            headers = {'X-Master-Key': api_key}
            req = requests.get(f"https://api.jsonbin.io/v3/b/{bin_id}/latest", headers=headers, timeout=10)
            if req.status_code == 200: settings = req.json().get("record", {})
    except Exception as e: print(f"[Settings] ⚠️ JSONBin load failed: {e}", flush=True)

    if not settings:
        try:
            with open('backup_settings.json', 'r') as f: settings = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e: print(f"[Settings] ⚠️ Backup load failed: {e}", flush=True)
    
    if settings:
        servers.extend(settings.get('servers', []))
        for key, value in settings.get('bot_states', {}).items():
            if key in bot_states and isinstance(value, dict): bot_states[key].update(value)
        print("[Settings] ✅ Settings loaded.", flush=True)
    else: print("[Settings] ⚠️ Using default settings.", flush=True)

# --- HÀM TRỢ GIÚP & LOGIC BOT ---
def get_bot_name(bot_id_str):
    try:
        b_type, b_index = bot_id_str.split('_')
        b_index = int(b_index)
        if b_type == 'main': return BOT_NAMES[b_index - 1] if 0 < b_index <= len(BOT_NAMES) else f"MAIN_{b_index}"
        return acc_names[b_index] if b_index < len(acc_names) else f"SUB_{b_index+1}"
    except (IndexError, ValueError): return bot_id_str.upper()

def _find_and_select_card(bot, channel_id, last_drop_msg_id, heart_threshold, bot_num, ktb_channel_id):
    bot_name = get_bot_name(f'main_{bot_num}')
    card_logger.log_event(bot_name, 'attempt', threshold=heart_threshold, channel_id=channel_id)
    
    for attempt in range(7):
        time.sleep(0.5)
        try:
            messages = bot.getMessages(channel_id, num=5).json()
            if not isinstance(messages, list): continue
            
            for msg_item in messages:
                if (msg_item.get("author", {}).get("id") == karibbit_id and 
                    int(msg_item.get("id", 0)) > int(last_drop_msg_id)):
                    
                    embeds = msg_item.get("embeds", [])
                    if not embeds or '♡' not in (desc := embeds[0].get("description", "")):
                        continue
                    
                    lines, heart_numbers = desc.split('\n')[:3], []
                    for line in lines:
                        match = re.search(r'♡(\d+)', line)
                        heart_numbers.append(int(match.group(1)) if match else 0)
                    
                    if not any(heart_numbers):
                        card_logger.log_event(bot_name, 'failed', reason='No hearts found in embed')
                        break

                    max_hearts = max(heart_numbers)
                    if max_hearts >= heart_threshold:
                        max_index = heart_numbers.index(max_hearts)
                        delays = {1: [0.4, 1.4, 2.1], 2: [0.7, 1.8, 2.4], 3: [0.7, 1.8, 2.4], 4: [0.8, 1.9, 2.5]}
                        bot_delays = delays.get(bot_num, [0.9, 2.0, 2.6])
                        
                        emoji = ["1️⃣", "2️⃣", "3️⃣"][max_index]
                        delay = bot_delays[max_index]
                        
                        def grab_action():
                            try:
                                print(f"[{bot_name}] 🎯 Reacting {emoji} for {max_hearts}♡ card...", flush=True)
                                bot.addReaction(channel_id, last_drop_msg_id, emoji)
                                time.sleep(1.2)
                                if ktb_channel_id:
                                    bot.sendMessage(ktb_channel_id, "kt b")
                            except Exception as e:
                                card_logger.log_event(bot_name, 'failed', reason=f'Reaction error: {str(e)}')
                        
                        threading.Timer(delay, grab_action).start()
                        return
                    else:
                        card_logger.log_event(bot_name, 'failed', reason=f'Hearts too low ({max_hearts} < {heart_threshold})')
                        return
                        
        except Exception as e:
            print(f"[CARD FIND] ❌ Error finding card (attempt {attempt+1}): {e}", flush=True)
    
    card_logger.log_event(bot_name, 'failed', reason='No suitable cards found after 7 attempts')

def handle_card_drop(bot, msg, bot_num):
    channel_id = msg.get("channel_id")
    bot_id_str = f'main_{bot_num}'
    
    clan_settings = bot_states["auto_clan_drop"]
    if clan_settings.get("enabled") and channel_id == clan_settings.get("channel_id"):
        threshold = clan_settings.get("heart_thresholds", {}).get(bot_id_str, 50)
        return threading.Thread(target=_find_and_select_card, args=(bot, channel_id, msg["id"], threshold, bot_num, clan_settings["ktb_channel_id"]), daemon=True).start()

    if not (target_server := next((s for s in servers if s.get('main_channel_id') == channel_id), None)): return

    if target_server.get(f'auto_grab_enabled_{bot_num}', False):
        threshold = target_server.get(f'heart_threshold_{bot_num}', 50)
        threading.Thread(target=_find_and_select_card, args=(bot, channel_id, msg["id"], threshold, bot_num, target_server.get('ktb_channel_id')), daemon=True).start()

    if bot_states["watermelon_grab"].get(bot_id_str, False):
        def check_watermelon():
            time.sleep(5)
            try:
                target_msg = bot.getMessage(channel_id, msg["id"]).json()[0]
                if any('🍉' in r.get('emoji', {}).get('name', '') for r in target_msg.get('reactions', [])):
                    bot.addReaction(channel_id, msg["id"], "🍉")
            except Exception:
                pass
        threading.Thread(target=check_watermelon, daemon=True).start()

def handle_karuta_response(msg):
    content = msg.get("content", "")
    content_lower = content.lower()

    if not any(keyword in content_lower for keyword in ["took the", "fought off", "lấy thẻ"]):
        return

    for bot_id, user_id in list(bot_user_ids.items()):
        if not user_id: continue

        if user_id in content:
            winner_part = ""
            if "fought off" in content_lower: winner_part = content.split("fought off")[0]
            elif "took the" in content_lower: winner_part = content.split(" took the")[0]
            elif "lấy thẻ" in content_lower: winner_part = content.split("lấy thẻ")[0]

            if user_id in winner_part:
                bot_name = get_bot_name(bot_id)
                card_logger.log_event(bot_name, 'card_success', message=content)
                return

# --- HỆ THỐNG REBOOT & HEALTH CHECK ---
def check_bot_health(bot_instance, bot_id):
    stats = bot_states["health_stats"].setdefault(bot_id, {'consecutive_failures': 0})
    is_connected = bot_instance and hasattr(bot_instance.gateway, 'connected') and bot_instance.gateway.connected
    stats['consecutive_failures'] = 0 if is_connected else stats.get('consecutive_failures', 0) + 1
    if not is_connected: print(f"[Health] ⚠️ {bot_id} disconnected. Failures: {stats['consecutive_failures']}", flush=True)

def safe_reboot_bot(bot_id):
    if not bot_manager.start_reboot(bot_id):
        print(f"[Reboot] ⚠️ {bot_id} already rebooting.", flush=True); return False
    
    print(f"[Reboot] 🔄 Starting reboot for {bot_id}...", flush=True)
    try:
        bot_index = int(bot_id.split('_')[1]) - 1
        token = main_tokens[bot_index].strip()
        bot_manager.remove_bot(bot_id)

        settings = bot_states["reboot_settings"].get(bot_id, {})
        wait_time = random.uniform(20, 40) + min(settings.get('failure_count', 0) * 30, 300)
        print(f"[Reboot] ⏳ Waiting {wait_time:.1f}s to avoid rate limit...", flush=True)
        time.sleep(wait_time)

        if not (new_bot := create_bot(token, bot_identifier=(bot_index + 1), is_main=True)):
            raise Exception("Failed to create new bot instance.")

        bot_manager.add_bot(bot_id, new_bot)
        settings.update({'next_reboot_time': time.time() + settings.get('delay', 3600), 'failure_count': 0, 'last_reboot_time': time.time()})
        bot_states["health_stats"][bot_id]['consecutive_failures'] = 0
        print(f"[Reboot] ✅ Reboot successful for {bot_id}", flush=True)
        return True
    except Exception as e:
        print(f"[Reboot] ❌ Reboot failed for {bot_id}: {e}", flush=True)
        settings = bot_states["reboot_settings"].setdefault(bot_id, {})
        failure_count = settings.get('failure_count', 0) + 1
        backoff = min(2 ** failure_count, 8)
        next_try = max(600, settings.get('delay', 3600) / backoff) * backoff
        settings.update({'failure_count': failure_count, 'next_reboot_time': time.time() + next_try})
        if failure_count >= 5: settings['enabled'] = False; print(f"[Reboot] ❌ Auto-reboot disabled for {bot_id}", flush=True)
        return False
    finally:
        bot_manager.end_reboot(bot_id)

# --- VÒNG LẶP NỀN ---
def auto_reboot_loop():
    print("[Reboot] 🚀 Auto-reboot loop started.", flush=True)
    while not stop_events["reboot"].is_set():
        now = time.time()
        bot_to_reboot = None
        highest_priority = -1
        
        for bot_id, settings in bot_states["reboot_settings"].items():
            if not settings.get('enabled') or bot_manager.is_rebooting(bot_id) or now < settings.get('next_reboot_time', 0): continue
            failures = bot_states["health_stats"].get(bot_id, {}).get('consecutive_failures', 0)
            priority = (failures * 1000) + (now - settings.get('next_reboot_time', 0))
            if priority > highest_priority:
                highest_priority, bot_to_reboot = priority, bot_id

        if bot_to_reboot:
            if safe_reboot_bot(bot_to_reboot):
                stop_events["reboot"].wait(random.uniform(300, 600))
            else:
                stop_events["reboot"].wait(120)
        else:
            stop_events["reboot"].wait(60)

def auto_clan_drop_loop():
    while not stop_events["clan_drop"].is_set():
        settings = bot_states["auto_clan_drop"]
        if settings.get("enabled") and settings.get("channel_id") and (time.time() - settings.get("last_cycle_start_time", 0)) >= settings.get("cycle_interval", 1800):
            print("[Clan Drop] 🚀 Starting clan drop cycle.", flush=True)
            active_bots = [(bot, int(bid.split('_')[1])) for bid, bot in bot_manager.get_main_bots_info() if bot and bot_states["active"].get(bid)]
            if not active_bots: print("[Clan Drop] ⚠️ No active main bots.", flush=True)
            
            for bot, bot_num in active_bots:
                if stop_events["clan_drop"].is_set(): break
                try:
                    bot.sendMessage(settings["channel_id"], "kd")
                    time.sleep(random.uniform(settings["bot_delay"] * 0.8, settings["bot_delay"] * 1.2))
                except Exception as e: print(f"[Clan Drop] ❌ Error sending 'kd' from bot {bot_num}: {e}", flush=True)
            
            settings["last_cycle_start_time"] = time.time()
            save_settings()
        stop_events["clan_drop"].wait(60)

def spam_loop_manager():
    active_threads = {}
    while True:
        try:
            current_ids = {s['id'] for s in servers}
            for server_id in list(active_threads.keys()):
                if server_id not in current_ids:
                    print(f"[Spam] 🛑 Stopping spam for deleted server: {server_id}", flush=True)
                    active_threads.pop(server_id)[1].set()
            
            for server in servers:
                server_id = server.get('id')
                spam_on = server.get('spam_enabled') and server.get('spam_message') and server.get('spam_channel_id')
                if spam_on and server_id not in active_threads:
                    print(f"[Spam] 🚀 Starting spam for: {server.get('name')}", flush=True)
                    stop_event = threading.Event()
                    thread = threading.Thread(target=lambda s=server, se=stop_event: spam_for_server(s, se), daemon=True)
                    thread.start()
                    active_threads[server_id] = (thread, stop_event)
                elif not spam_on and server_id in active_threads:
                    print(f"[Spam] 🛑 Stopping spam for: {server.get('name')}", flush=True)
                    active_threads.pop(server_id)[1].set()
            time.sleep(5)
        except Exception as e: print(f"[Spam] ❌ ERROR in spam_loop_manager: {e}", flush=True); time.sleep(5)

def spam_for_server(server_config, stop_event):
    while not stop_event.is_set():
        bots_to_spam = [bot for _, bot in bot_manager.get_all_bots(active_only=True)]
        delay = server_config.get('spam_delay', 10)
        for bot in bots_to_spam:
            if stop_event.is_set(): break
            try:
                bot.sendMessage(server_config['spam_channel_id'], server_config['spam_message'])
                time.sleep(random.uniform(1.5, 2.5))
            except Exception as e: print(f"[Spam] ❌ Error sending from bot to {server_config.get('name')}: {e}", flush=True)
        stop_event.wait(random.uniform(delay * 0.9, delay * 1.1))

def periodic_task(interval, task_func, task_name):
    print(f"[{task_name}] 🚀 Starting periodic task.", flush=True)
    while True: time.sleep(interval); task_func()

# --- KHỞI TẠO BOT ---
def create_bot(token, bot_identifier, is_main=False):
    try:
        bot = discum.Client(token=token, log=False)
        bot_id_str = f"main_{bot_identifier}" if is_main else f"sub_{bot_identifier}"
        
        @bot.gateway.command
        def on_ready(resp):
            if resp.event.ready:
                user = resp.raw.get("user", {})
                user_id = user.get('id')
                print(f"[Bot] ✅ Logged in: {user_id} ({get_bot_name(bot_id_str)})", flush=True)
                bot_states["health_stats"].setdefault(bot_id_str, {})['consecutive_failures'] = 0
                if user_id:
                    bot_user_ids[bot_id_str] = user_id
        
        if is_main:
            @bot.gateway.command
            def on_message(resp):
                if not resp.event.message: return
                msg = resp.parsed.auto()
                author_id = msg.get("author", {}).get("id")
                
                try:
                    if author_id == karuta_id:
                        if "dropping" in msg.get("content", "").lower():
                             threading.Thread(target=handle_card_drop, args=(bot, msg, bot_identifier), daemon=True).start()
                        else:
                             handle_karuta_response(msg)
                except Exception as e:
                    print(f"[Bot] ❌ Error in on_message for {bot_id_str}: {e}\n{traceback.format_exc()}", flush=True)

        threading.Thread(target=lambda: bot.gateway.run(auto_reconnect=True), daemon=True).start()
        
        start_time = time.time()
        while time.time() - start_time < 20:
            if hasattr(bot.gateway, 'connected') and bot.gateway.connected: return bot
            time.sleep(0.5)
        
        print(f"[Bot] ⚠️ Gateway timeout for {bot_id_str}.", flush=True)
        bot.gateway.close()
        return None
    except Exception as e:
        print(f"[Bot] ❌ Critical error creating bot {bot_identifier}: {e}", flush=True)
        return None

# --- FLASK APP & GIAO DIỆN ---
app = Flask(__name__)
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Shadow Network Control - Enhanced</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700&family=Courier+Prime&family=Nosifer&display=swap" rel="stylesheet">
    <style>
        :root { --primary-bg: #0a0a0a; --secondary-bg: #1a1a1a; --panel-bg: #111111; --border-color: #333333; --blood-red: #8b0000; --dark-red: #550000; --bone-white: #f8f8ff; --necro-green: #228b22; --text-primary: #f0f0f0; --text-secondary: #cccccc; --warning-orange: #ff8c00; --success-green: #32cd32; --mint-cyan: #00ffff;}
        body { font-family: 'Courier Prime', monospace; background: var(--primary-bg); color: var(--text-primary); margin: 0; padding: 15px;}
        .container { max-width: 1800px; margin: 0 auto; }
        .header { text-align: center; margin-bottom: 20px; padding: 15px; border-bottom: 2px solid var(--blood-red); }
        .title { font-family: 'Nosifer', cursive; font-size: 2.5rem; color: var(--blood-red); }
        .main-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(480px, 1fr)); gap: 15px; }
        .panel { background: var(--panel-bg); border: 1px solid var(--border-color); border-radius: 8px; padding: 20px; }
        .panel h2 { font-family: 'Orbitron', cursive; font-size: 1.3rem; margin: 0 0 15px 0; padding-bottom: 10px; border-bottom: 2px solid; color: var(--bone-white); }
        .btn { background: var(--secondary-bg); border: 1px solid var(--border-color); color: var(--text-primary); padding: 8px 12px; border-radius: 4px; cursor: pointer; font-family: 'Orbitron'; text-transform: uppercase; transition: all 0.3s ease; }
        .btn:hover { background: var(--dark-red); border-color: var(--blood-red); }
        .btn-small { padding: 4px 8px; font-size: 0.85em; }
        .input-group { display: flex; gap: 10px; margin-bottom: 12px; }
        .input-group label { background: #000; border: 1px solid var(--border-color); border-right: 0; padding: 8px 12px; border-radius: 4px 0 0 4px; min-width: 120px; text-align: center; display:flex; align-items:center; justify-content:center; }
        .input-group input, .input-group textarea { flex-grow: 1; background: #000; border: 1px solid var(--border-color); color: var(--text-primary); padding: 8px 12px; border-radius: 0 4px 4px 0; }
        .grab-section { display: flex; align-items: center; margin-bottom: 10px; padding: 10px; background: rgba(0,0,0,0.2); border-radius: 6px; }
        .grab-section h3 { margin: 0; width: 80px; }
        .msg-status { text-align: center; color: var(--necro-green); padding: 10px; border: 1px dashed var(--border-color); border-radius: 4px; margin-bottom: 15px; display: none; }
        .status-panel, .global-settings-panel, .clan-drop-panel { grid-column: 1 / -1; }
        .flex-row { display: flex; justify-content: space-between; align-items: center; padding: 10px; background: rgba(0,0,0,0.4); border-radius: 6px; }
        .timer-display { font-size: 1.1em; font-weight: bold; }
        .bot-status-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(350px, 1fr)); gap: 8px; }
        .btn-toggle-state { padding: 3px 5px; font-size: 0.9em; background: transparent; font-weight: bold; border: none; cursor: pointer;}
        .btn-rise { color: var(--success-green); } .btn-rest { color: var(--dark-red); } .btn-warning { color: var(--warning-orange); }
        .add-server-btn { display: flex; align-items: center; justify-content: center; min-height: 150px; border: 2px dashed var(--border-color); cursor: pointer; }
        .server-sub-panel { border-top: 1px solid var(--border-color); margin-top: 15px; padding-top: 15px; }
        .health-indicator { display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-left: 5px; }
        .health-good { background: var(--success-green); } .health-warning { background: var(--warning-orange); } .health-bad { background: var(--blood-red); }
        .log-list { max-height: 500px; overflow-y: auto; border: 1px solid var(--border-color); border-radius: 6px; padding: 5px; }
        .log-entry { padding: 8px; border-bottom: 1px solid #222; display: flex; gap: 10px; align-items: flex-start; font-size: 0.9em; }
        .log-timestamp { color: #888; white-space: nowrap; }
        .log-bot-name { font-weight: bold; min-width: 80px; color: var(--mint-cyan); white-space: nowrap;}
        .card-condition { padding: 2px 6px; border-radius: 3px; font-size: 0.8rem; text-transform: uppercase; color: black; }
        .condition-poor { background: #ff4444; } .condition-good { background: #ffaa00; } .condition-excellent { background: #44ff44; } .condition-mint { background: #00ffff; } .condition-unknown { background: #888888; color: white; }
        .stat-card { background: rgba(0,0,0,0.3); padding: 10px; border-radius: 6px; text-align: center; border: 1px solid var(--border-color); }
        .stat-number { font-size: 1.5rem; font-weight: bold; color: var(--success-green); }
        .log-details { font-family: 'Courier New', monospace; line-height: 1.6; white-space: pre-wrap; }
        .log-details div { padding-left: 5px; }
        .log-details .hearts-display { font-weight: bold; color: var(--mint-cyan); font-size: 1.1em; }
    </style>
</head>
<body>
<div class="container">
    <div class="header"><h1 class="title">Shadow Network Control</h1></div>
    <div id="msg-status-container" class="msg-status"></div>
    <div class="main-grid">
        <div class="panel status-panel">
            <h2><i class="fas fa-heartbeat"></i> System & Bot Status</h2>
            <div class="flex-row" style="margin-bottom:15px;"><span><i class="fas fa-server"></i> Uptime: <span id="uptime-timer">--:--:--</span></span><span><i class="fas fa-shield-alt"></i> Reboot: <span id="reboot-status">ACTIVE</span></span></div>
            <div id="bot-control-grid" class="bot-status-grid"></div>
        </div>

        <div class="panel">
            <h2><i class="fas fa-chart-bar"></i> Card Grab Stats</h2>
            <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; margin-bottom: 10px;">
                <div class="stat-card"><span class="stat-number" id="total-cards">0</span><span>Total Grabs</span></div>
                <div class="stat-card"><span class="stat-number" id="success-rate">0%</span><span>Success Rate</span></div>
                <div class="stat-card"><span class="stat-number" id="highest-heart">0♡</span><span>Max Hearts</span></div>
                <div class="stat-card"><span class="stat-number" id="total-failures">0</span><span>Fails</span></div>
            </div>
            <div id="bot-stats-container"></div>
        </div>

        <div class="panel">
             <h2><i class="fas fa-list"></i> Card Grab Log</h2>
             <div class="log-list" id="log-container"><div class="no-logs">Waiting for activity...</div></div>
        </div>

        <div class="panel clan-drop-panel">
            <h2><i class="fas fa-users"></i> Clan Auto Drop</h2>
            <div class="flex-row"><span>Next Cycle: <span id="clan-drop-timer" class="timer-display">--:--:--</span></span><button id="clan-drop-toggle-btn" class="btn btn-small">ENABLE</button></div>
            <div class="server-sub-panel">
                <div class="input-group"><label>Drop Ch. ID</label><input id="clan-drop-channel-id" value="{{ auto_clan_drop.channel_id or '' }}"></div>
                <div class="input-group"><label>KTB Ch. ID</label><input id="clan-drop-ktb-channel-id" value="{{ auto_clan_drop.ktb_channel_id or '' }}"></div>
                {% for bot in main_bots_info %}<div class="grab-section"><h3>{{ bot.name }}</h3><div class="input-group"><input type="number" class="clan-drop-threshold" data-node="main_{{ bot.id }}" value="{{ auto_clan_drop.heart_thresholds[('main_' + bot.id|string)]|default(50) }}"></div></div>{% endfor %}
                <button id="clan-drop-save-btn" class="btn" style="width:100%;">Save Clan Settings</button>
            </div>
        </div>

        <div class="panel global-settings-panel">
            <h2><i class="fas fa-globe"></i> Global Settings</h2>
            <div class="server-sub-panel">
                <h3><i class="fas fa-seedling"></i> Watermelon Grab</h3>
                <div id="global-watermelon-grid" class="bot-status-grid" style="grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));"></div>
            </div>
        </div>

        {% for server in servers %}
        <div class="panel server-panel" data-server-id="{{ server.id }}">
            <h2><i class="fas fa-server"></i> {{ server.name }} <button class="btn-delete-server" style="float:right;background:var(--dark-red);border-radius:50%;">&times;</button></h2>
            <div class="server-sub-panel">
                <div class="input-group"><label>Main Ch. ID</label><input class="channel-input" data-field="main_channel_id" value="{{ server.main_channel_id or '' }}"></div>
                <div class="input-group"><label>KTB Ch. ID</label><input class="channel-input" data-field="ktb_channel_id" value="{{ server.ktb_channel_id or '' }}"></div>
                <div class="input-group"><label>Spam Ch. ID</label><input class="channel-input" data-field="spam_channel_id" value="{{ server.spam_channel_id or '' }}"></div>
            </div>
            <div class="server-sub-panel"><h3><i class="fas fa-crosshairs"></i> Card Grab</h3>
                {% for bot in main_bots_info %}<div class="grab-section"><h3>{{ bot.name }}</h3><div class="input-group"><input type="number" class="harvest-threshold" data-node="{{ bot.id }}" value="{{ server['heart_threshold_' + bot.id|string] or 50 }}"><button class="btn harvest-toggle" data-node="{{ bot.id }}">{{ 'DISABLE' if server['auto_grab_enabled_' + bot.id|string] else 'ENABLE' }}</button></div></div>{% endfor %}
            </div>
            <div class="server-sub-panel"><h3><i class="fas fa-paper-plane"></i> Auto Broadcast</h3>
                <div class="input-group"><label>Message</label><textarea class="spam-message" rows="1">{{ server.spam_message or '' }}</textarea></div>
                <div class="input-group"><label>Delay (s)</label><input type="number" class="spam-delay" value="{{ server.spam_delay or 10 }}"><button class="btn broadcast-toggle" style="width:100%;">{{ 'DISABLE' if server.spam_enabled else 'ENABLE' }}</button></div>
            </div>
        </div>
        {% endfor %}
        <div class="panel add-server-btn" id="add-server-btn"><i class="fas fa-plus" style="font-size:2rem;"></i></div>
    </div>
</div>
<script>
document.addEventListener('DOMContentLoaded', function () {
    const msgContainer = document.getElementById('msg-status-container');
    const showMsg = (message, type = 'success') => {
        if (!message) return;
        msgContainer.textContent = message;
        msgContainer.className = `msg-status ${type}`;
        msgContainer.style.display = 'block';
        setTimeout(() => { msgContainer.style.display = 'none'; }, 4000);
    };

    async function post(url, data) {
        try {
            const response = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) });
            const result = await response.json();
            showMsg(result.message, result.status);
            if (result.status === 'success') {
                fetch('/api/save_settings', { method: 'POST' });
                if (result.reload) setTimeout(() => window.location.reload(), 500);
            }
            return result;
        } catch (error) { showMsg('Server communication error.', 'error'); }
    }

    const formatTime = (s) => isNaN(s) || s < 0 ? "--:--:--" : new Date(s * 1000).toISOString().slice(11, 19);
    
    function updateUI(data) {
        document.getElementById('uptime-timer').textContent = formatTime((Date.now() / 1000) - data.server_start_time);
        
        const botGrid = document.getElementById('bot-control-grid');
        botGrid.innerHTML = '';
        const allBots = [...data.bot_statuses.main_bots, ...data.bot_statuses.sub_accounts];
        allBots.forEach(bot => {
            const r_settings = data.bot_reboot_settings[bot.reboot_id] || {};
            const healthClass = `health-${bot.health_status}`;
            const rebootingIcon = bot.is_rebooting ? ' <i class="fas fa-sync-alt fa-spin"></i>' : '';
            let mainBotHtml = '';
            if (bot.type === 'main') {
                const statusClass = r_settings.failure_count > 0 ? 'btn-warning' : (r_settings.enabled ? 'btn-rise' : 'btn-rest');
                const statusText = r_settings.failure_count > 0 ? `FAIL(${r_settings.failure_count})` : (r_settings.enabled ? 'AUTO' : 'MANUAL');
                mainBotHtml = `<input type="number" class="bot-reboot-delay" value="${r_settings.delay || 3600}" data-bot-id="${bot.reboot_id}" style="width:70px;text-align:right;">
                               <span class="timer-display">${formatTime(r_settings.countdown)}</span>
                               <button class="btn btn-small bot-reboot-toggle ${statusClass}" data-bot-id="${bot.reboot_id}">${statusText}</button>`;
            }
            botGrid.innerHTML += `<div class="flex-row" style="gap:10px;">
                <span style="font-weight:bold;">${bot.name}<span class="health-indicator ${healthClass}"></span>${rebootingIcon}</span>
                <div style="display:flex; align-items:center; gap: 8px;">
                    ${mainBotHtml}
                    <button class="btn-toggle-state ${bot.is_active ? 'btn-rise' : 'btn-rest'}" data-target="${bot.reboot_id}">${bot.is_active ? 'ON' : 'OFF'}</button>
                </div>
            </div>`;
        });
        
        const wmGrid = document.getElementById('global-watermelon-grid');
        wmGrid.innerHTML = '';
        data.bot_statuses.main_bots.forEach(bot => {
            const isEnabled = data.watermelon_grab_states[bot.reboot_id];
            wmGrid.innerHTML += `<div class="flex-row"><span>${bot.name}</span><button class="btn btn-small watermelon-toggle" data-node="${bot.reboot_id}">${isEnabled ? 'DISABLE' : 'ENABLE'}</button></div>`;
        });

        data.servers.forEach(server => {
            const panel = document.querySelector(`.server-panel[data-server-id="${server.id}"]`);
            if (!panel) return;
            panel.querySelectorAll('.harvest-toggle').forEach(btn => btn.textContent = server[`auto_grab_enabled_${btn.dataset.node}`] ? 'DISABLE' : 'ENABLE');
            panel.querySelector('.broadcast-toggle').textContent = server.spam_enabled ? 'DISABLE' : 'ENABLE';
        });
        
        if (data.auto_clan_drop_status) {
            document.getElementById('clan-drop-timer').textContent = formatTime(data.auto_clan_drop_status.countdown);
            document.getElementById('clan-drop-toggle-btn').textContent = data.auto_clan_drop_status.enabled ? 'DISABLE' : 'ENABLE';
        }
    }
    
    function updateLogs(data, statsData) {
        const logContainer = document.getElementById('log-container');
        if (!data.logs || data.logs.length === 0) {
            logContainer.innerHTML = '<div class="no-logs">No activity yet.</div>'; 
            return;
        }
        
        let newHtml = '';
        data.logs.forEach(log => {
            let content = '';
            
            if (log.type === 'card_success') {
                const botStats = statsData && statsData.bot_stats ? statsData.bot_stats[log.bot_name] : null;
                
                content = `<div class="log-details">
                    <div>🎉 <b>${log.bot_name}</b> GRABBED CARD!</div>
                    <div><span style="display: inline-block; width: 110px;">🃏 Card Name:</span> ${log.card_name}</div>
                    <div><span style="display: inline-block; width: 110px;">💎 Condition:</span> <span class="card-condition condition-${log.condition}">${log.condition}</span></div>
                    <div class="hearts-display"><span style="display: inline-block; width: 110px;">♡♡♡ HEARTS:</span> ${log.hearts} ♡♡♡</div>`;
                
                if (botStats) {
                    content += `<div><span style="display: inline-block; width: 110px;">💰 Total Hearts:</span> ${botStats.total_hearts_grabbed}</div>
                                <div><span style="display: inline-block; width: 110px;">🏆 Highest Heart:</span> ${botStats.highest_heart_grabbed}</div>`;
                }
                content += `</div>`;
                           
            } else if (log.type === 'failed') {
                content = `<span style="color: #ffaa88;">Failed: ${log.reason}</span>`;
            } else if (log.type === 'attempt') {
                content = `<span style="color: #ffdd44;">Attempting grab (threshold: ${log.threshold}♡)</span>`;
            }
            
            newHtml += `<div class="log-entry ${log.type}">
                <span class="log-timestamp">[${log.timestamp}]</span>
                <div style="flex-grow: 1;">${content}</div>
            </div>`;
        });
        logContainer.innerHTML = newHtml;
    }

    function updateStats(data) {
        const summary = data.summary;
        
        document.getElementById('total-cards').textContent = summary.total_cards_grabbed;
        document.getElementById('success-rate').textContent = `${summary.success_rate}%`;
        document.getElementById('highest-heart').textContent = `${summary.highest_heart_grabbed}♡`;
        document.getElementById('total-failures').textContent = summary.total_failed_attempts;

        const statsContainer = document.getElementById('bot-stats-container');
        statsContainer.innerHTML = '';
        
        for (const [botName, stats] of Object.entries(data.bot_stats)) {
            const avgHearts = stats.successful_grabs > 0 ? 
                Math.round(stats.total_hearts_grabbed / stats.successful_grabs) : 0;
                
            let heartsDisplay = `${stats.total_hearts_grabbed}♡`;
            if (stats.successful_grabs > 0) {
                heartsDisplay += ` (avg: ${avgHearts}♡)`;
            }
            
            let botColor = stats.highest_heart_grabbed >= 100 ? '#ff69b4' : stats.highest_heart_grabbed >= 50 ? '#ffd700' : '#32cd32';
            
            statsContainer.innerHTML += `<div class="flex-row" style="font-size:0.9em; border-left: 3px solid ${botColor}; padding-left: 8px;">
                <strong style="color: ${botColor}; min-width: 80px;">${botName}</strong>
                <span title="Total cards grabbed">📚${stats.successful_grabs}</span>
                <span title="Failed attempts">❌${stats.failed_attempts}</span>
                <span title="Highest hearts grabbed">🏆${stats.highest_heart_grabbed}♡</span>
                <span title="Total hearts earned">${heartsDisplay}</span>
            </div>`;
        }
    }
    
    async function fetchData() {
        try {
            const [statusRes, logsRes, statsRes] = await Promise.all([fetch('/status'), fetch('/api/card_logs'), fetch('/api/card_stats')]);
            const statusData = await statusRes.json();
            const logsData = await logsRes.json();
            const statsData = await statsRes.json();
            
            updateUI(statusData);
            updateLogs(logsData, statsData);
            updateStats(statsData);
        } catch (error) { console.error('Error fetching data:', error); }
    }

    setInterval(fetchData, 2000);
    fetchData();

    document.querySelector('.container').addEventListener('click', e => {
        const btn = e.target.closest('button');
        if (!btn) return;
        const serverPanel = btn.closest('.server-panel');
        const serverId = serverPanel ? serverPanel.dataset.serverId : null;

        const actions = {
            'bot-reboot-toggle': () => post('/api/bot_reboot_toggle', { bot_id: btn.dataset.botId, delay: document.querySelector(`.bot-reboot-delay[data-bot-id="${btn.dataset.botId}"]`).value }),
            'btn-toggle-state': () => post('/api/toggle_bot_state', { target: btn.dataset.target }),
            'clan-drop-toggle-btn': () => post('/api/clan_drop_toggle'),
            'clan-drop-save-btn': () => {
                const thresholds = {};
                document.querySelectorAll('.clan-drop-threshold').forEach(i => thresholds[i.dataset.node] = parseInt(i.value, 10));
                post('/api/clan_drop_update', { channel_id: document.getElementById('clan-drop-channel-id').value, ktb_channel_id: document.getElementById('clan-drop-ktb-channel-id').value, heart_thresholds: thresholds });
            },
            'watermelon-toggle': () => post('/api/watermelon_toggle', { node: btn.dataset.node }),
            'harvest-toggle': () => serverId && post('/api/harvest_toggle', { server_id: serverId, node: btn.dataset.node, threshold: serverPanel.querySelector(`.harvest-threshold[data-node="${btn.dataset.node}"]`).value }),
            'broadcast-toggle': () => serverId && post('/api/broadcast_toggle', { server_id: serverId, message: serverPanel.querySelector('.spam-message').value, delay: serverPanel.querySelector('.spam-delay').value }),
            'btn-delete-server': () => serverId && confirm('Are you sure?') && post('/api/delete_server', { server_id: serverId }),
        };

        for (const cls in actions) {
            if (btn.classList.contains(cls) || btn.id === cls) return actions[cls]();
        }
    });

    document.querySelector('.main-grid').addEventListener('change', e => {
        if (e.target.classList.contains('channel-input')) {
            const serverPanel = e.target.closest('.server-panel');
            const payload = { server_id: serverPanel.dataset.serverId, [e.target.dataset.field]: e.target.value };
            post('/api/update_server_channels', payload);
        }
    });

    document.getElementById('add-server-btn').addEventListener('click', () => {
        const name = prompt("Enter new server name:", "New Server");
        if (name) post('/api/add_server', { name });
    });
});
</script>
</body>
</html>
"""

# --- FLASK ROUTES ---
@app.route("/")
def index():
    main_bots_info = sorted([{"id": int(bid.split('_')[1]), "name": get_bot_name(bid)} for bid, _ in bot_manager.get_main_bots_info()], key=lambda x: x['id'])
    return render_template_string(HTML_TEMPLATE, servers=sorted(servers, key=lambda s: s.get('name', '')), main_bots_info=main_bots_info, auto_clan_drop=bot_states["auto_clan_drop"])

@app.route("/api/clan_drop_toggle", methods=['POST'])
def api_clan_drop_toggle():
    s = bot_states["auto_clan_drop"]
    s['enabled'] = not s.get('enabled', False)
    if s['enabled'] and (not s.get('channel_id') or not s.get('ktb_channel_id')):
        s['enabled'] = False
        return jsonify({'status': 'error', 'message': 'Clan Drop & KTB Channel ID must be set.'})
    return jsonify({'status': 'success', 'message': f"✅ Clan Auto Drop {'ENABLED' if s['enabled'] else 'DISABLED'}."})

@app.route("/api/clan_drop_update", methods=['POST'])
def api_clan_drop_update():
    data = request.get_json()
    bot_states["auto_clan_drop"].update({
        'channel_id': data.get('channel_id', '').strip(),
        'ktb_channel_id': data.get('ktb_channel_id', '').strip(),
        'heart_thresholds': {k: int(v) for k, v in data.get('heart_thresholds', {}).items()}
    })
    return jsonify({'status': 'success', 'message': '💾 Clan Drop settings updated.'})

@app.route("/api/add_server", methods=['POST'])
def api_add_server():
    name = request.json.get('name')
    if not name: return jsonify({'status': 'error', 'message': 'Server name is required.'}), 400
    new_server = {"id": f"server_{uuid.uuid4().hex}", "name": name, "spam_delay": 10}
    for i in range(len([t for t in main_tokens if t.strip()])):
        new_server.update({f'auto_grab_enabled_{i+1}': False, f'heart_threshold_{i+1}': 50})
    servers.append(new_server)
    return jsonify({'status': 'success', 'message': f'✅ Server "{name}" added.', 'reload': True})

@app.route("/api/delete_server", methods=['POST'])
def api_delete_server():
    server_id = request.json.get('server_id')
    servers[:] = [s for s in servers if s.get('id') != server_id]
    return jsonify({'status': 'success', 'message': '🗑️ Server deleted.', 'reload': True})

def find_server(server_id):
    return next((s for s in servers if s.get('id') == server_id), None)

@app.route("/api/update_server_channels", methods=['POST'])
def api_update_server_channels():
    data = request.json
    server = find_server(data.get('server_id'))
    if not server: return jsonify({'status': 'error', 'message': 'Server not found.'}), 404
    server.update(data)
    return jsonify({'status': 'success', 'message': f'🔧 Kênh đã được cập nhật cho {server["name"]}.'})

@app.route("/api/harvest_toggle", methods=['POST'])
def api_harvest_toggle():
    data = request.json
    server, node_str = find_server(data.get('server_id')), data.get('node')
    if not server or not node_str: return jsonify({'status': 'error', 'message': 'Yêu cầu không hợp lệ.'}), 400
    node = str(node_str)
    grab_key, threshold_key = f'auto_grab_enabled_{node}', f'heart_threshold_{node}'
    server[grab_key] = not server.get(grab_key, False)
    server[threshold_key] = int(data.get('threshold', 50))
    status_msg = 'ENABLED' if server[grab_key] else 'DISABLED'
    bot_id = f'main_{node}'
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
    data = request.json
    server = find_server(data.get('server_id'))
    if not server: return jsonify({'status': 'error', 'message': 'Server not found.'}), 404
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
    if not settings: return jsonify({'status': 'error', 'message': 'Invalid Bot ID.'}), 400
    
    settings.update({'enabled': not settings.get('enabled', False), 'delay': delay, 'failure_count': 0})
    if settings['enabled']:
        settings['next_reboot_time'] = time.time() + delay
        msg = f"🔄 Safe Auto-Reboot ENABLED cho {get_bot_name(bot_id)}"
    else:
        msg = f"🛑 Auto-Reboot DISABLED cho {get_bot_name(bot_id)}"
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
            status_list.append({
                "name": get_bot_name(bot_id), 
                "reboot_id": bot_id,
                "is_active": bot_states["active"].get(bot_id, False), 
                "type": type_prefix, 
                "health_status": health_status,
                "is_rebooting": bot_manager.is_rebooting(bot_id)
            })
        return sorted(status_list, key=lambda x: int(x['reboot_id'].split('_')[1]))

    bot_statuses = {
        "main_bots": get_bot_status_list(bot_manager.get_main_bots_info(), "main"),
        "sub_accounts": get_bot_status_list(bot_manager.get_sub_bots_info(), "sub")
    }
    
    clan_settings = bot_states["auto_clan_drop"]
    clan_drop_status = {
        "enabled": clan_settings.get("enabled", False),
        "countdown": (clan_settings.get("last_cycle_start_time", 0) + clan_settings.get("cycle_interval", 1800) - now) if clan_settings.get("enabled") else 0
    }
    
    reboot_settings_copy = bot_states["reboot_settings"].copy()
    for bot_id, settings in reboot_settings_copy.items():
        settings['countdown'] = max(0, settings.get('next_reboot_time', 0) - now) if settings.get('enabled') else 0

    return jsonify({
        'bot_reboot_settings': reboot_settings_copy,
        'bot_statuses': bot_statuses,
        'server_start_time': server_start_time,
        'servers': servers,
        'watermelon_grab_states': bot_states["watermelon_grab"],
        'auto_clan_drop_status': clan_drop_status
    })

@app.route("/api/debug_bots")
def api_debug_bots():
    return jsonify({
        'bot_user_ids': bot_user_ids,
        'active_bots': {k: v for k, v in bot_states["active"].items() if v},
        'registered_bots': list(bot_manager._bots.keys()),
        'recent_logs': card_logger.get_logs_for_web(10)
    })

@app.route("/api/test_card_log", methods=['POST'])
def api_test_card_log():
    data = request.json
    test_message = data.get('message', '<@123456789> took the Test Card!')
    
    fake_msg = {'content': test_message, 'author': {'id': karuta_id}}
    
    handle_karuta_response(fake_msg)
    return jsonify({'status': 'success', 'message': 'Test card log sent'})

# --- MAIN EXECUTION ---
if __name__ == "__main__":
    print("🚀 Shadow Network Control - V5.1 Final Debug Starting...", flush=True)
    load_settings()

    print("🔌 Initializing bots using Bot Manager...", flush=True)
    
    for i, token in enumerate(t for t in main_tokens if t.strip()):
        bot_num = i + 1
        bot_id = f"main_{bot_num}"
        bot = create_bot(token.strip(), bot_identifier=bot_num, is_main=True)
        if bot: bot_manager.add_bot(bot_id, bot)
        
        bot_states["active"].setdefault(bot_id, True)
        bot_states["watermelon_grab"].setdefault(bot_id, False)
        bot_states["auto_clan_drop"]["heart_thresholds"].setdefault(bot_id, 50)
        bot_states["reboot_settings"].setdefault(bot_id, {'enabled': False, 'delay': 3600, 'next_reboot_time': 0, 'failure_count': 0})
        bot_states["health_stats"].setdefault(bot_id, {'consecutive_failures': 0})

    for i, token in enumerate(t for t in tokens if t.strip()):
        bot_id = f"sub_{i}"
        bot = create_bot(token.strip(), bot_identifier=i, is_main=False)
        if bot: bot_manager.add_bot(bot_id, bot)
        bot_states["active"].setdefault(bot_id, True)
        bot_states["health_stats"].setdefault(bot_id, {'consecutive_failures': 0})

    print("🔧 Starting background threads...", flush=True)
    threading.Thread(target=periodic_task, args=(1800, save_settings, "Save"), daemon=True).start()
    threading.Thread(target=periodic_task, args=(300, lambda: [check_bot_health(b, bid) for bid, b in bot_manager.get_all_bots(active_only=True)], "Health"), daemon=True).start()
    threading.Thread(target=spam_loop_manager, daemon=True).start()
    
    auto_reboot_thread = threading.Thread(target=auto_reboot_loop, daemon=True)
    auto_reboot_thread.start()
    
    auto_clan_drop_thread = threading.Thread(target=auto_clan_drop_loop, daemon=True)
    auto_clan_drop_thread.start()
    
    port = int(os.environ.get("PORT", 10000))
    print(f"🌐 Web Server running at http://0.0.0.0:{port}", flush=True)
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
