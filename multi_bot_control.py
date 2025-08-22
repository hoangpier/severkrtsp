
# DISCORD.PY-SELF VERSION - MULTI BOT CONTROL
import discord, threading, time, os, re, requests, json, random, traceback, uuid, asyncio
from flask import Flask, request, render_template_string, jsonify
from dotenv import load_dotenv
from datetime import datetime, timedelta

load_dotenv()

# --- CẤU HÌNH ---
main_tokens = [t.strip() for t in os.getenv("MAIN_TOKENS", "").split(",") if t.strip()]
sub_tokens = [t.strip() for t in os.getenv("TOKENS", "").split(",") if t.strip()]
karuta_id, karibbit_id = 646937666251915264, 1311684840462225440
BOT_NAMES = ["xsyx", "sofa", "dont", "ayaya", "owo", "astra", "singo", "dia pox", "clam", "rambo", "domixi", "dogi", "sicula", "mo turn", "jan taru", "kio sama"]
acc_names = [f"Bot-{i:02d}" for i in range(1, 21)]

# --- BIẾN TRẠNG THÁI ---
servers, bot_states = [], {
    "reboot_settings": {}, "active": {}, "watermelon_grab": {}, "health_stats": {},
    "auto_clan_drop": {"enabled": False, "channel_id": "", "ktb_channel_id": "", "last_cycle_start_time": 0, 
                      "cycle_interval": 1800, "bot_delay": 140, "heart_thresholds": {}, "max_heart_thresholds": {}}
}
stop_events = {"reboot": threading.Event(), "clan_drop": threading.Event()}
server_start_time = time.time()

# --- QUẢN LÝ BOT ---
class ThreadSafeBotManager:
    def __init__(self):
        self._bots, self._rebooting, self._lock = {}, set(), threading.RLock()

    def add_bot(self, bot_id, bot_instance):
        with self._lock:
            self._bots[bot_id] = bot_instance
            print(f"[Bot Manager] ✅ Added bot {bot_id}", flush=True)

    def remove_bot(self, bot_id):
        with self._lock:
            bot = self._bots.pop(bot_id, None)
            if bot and not bot.is_closed():
                asyncio.create_task(bot.close())
                print(f"[Bot Manager] 🗑️ Removed bot {bot_id}", flush=True)

    def get_bot(self, bot_id): 
        with self._lock: return self._bots.get(bot_id)
    
    def get_all_bots(self):
        with self._lock: return list(self._bots.items())
    
    def get_main_bots_info(self):
        with self._lock: return [(bid, bot) for bid, bot in self._bots.items() if bid.startswith('main_')]
    
    def get_sub_bots_info(self):
        with self._lock: return [(bid, bot) for bid, bot in self._bots.items() if bid.startswith('sub_')]
    
    def is_rebooting(self, bot_id):
        with self._lock: return bot_id in self._rebooting
    
    def start_reboot(self, bot_id):
        with self._lock:
            if bot_id in self._rebooting: return False
            self._rebooting.add(bot_id)
            return True
    
    def end_reboot(self, bot_id):
        with self._lock: self._rebooting.discard(bot_id)

bot_manager = ThreadSafeBotManager()

# --- LƯU & TẢI CÀI ĐẶT ---
def save_settings():
    api_key, bin_id = os.getenv("JSONBIN_API_KEY"), os.getenv("JSONBIN_BIN_ID")
    settings_data = {'servers': servers, 'bot_states': bot_states, 'last_save_time': time.time()}
    
    if api_key and bin_id:
        try:
            resp = requests.put(f"https://api.jsonbin.io/v3/b/{bin_id}", 
                              json=settings_data, headers={'Content-Type': 'application/json', 'X-Master-Key': api_key}, timeout=15)
            if resp.status_code == 200: 
                print("[Settings] ✅ Đã lưu cài đặt lên JSONBin.io.", flush=True)
                return
        except: pass
    
    try:
        with open('backup_settings.json', 'w') as f: json.dump(settings_data, f, indent=2)
        print("[Settings] ✅ Đã lưu backup locally.", flush=True)
    except Exception as e: print(f"[Settings] ❌ Lỗi backup: {e}", flush=True)

def load_settings():
    global servers, bot_states
    api_key, bin_id = os.getenv("JSONBIN_API_KEY"), os.getenv("JSONBIN_BIN_ID")
    
    def load_from_dict(settings):
        try:
            servers.extend(settings.get('servers', []))
            for key, value in settings.get('bot_states', {}).items():
                if key in bot_states and isinstance(value, dict): bot_states[key].update(value)
            return True
        except: return False

    if api_key and bin_id:
        try:
            resp = requests.get(f"https://api.jsonbin.io/v3/b/{bin_id}/latest", 
                              headers={'X-Master-Key': api_key}, timeout=15)
            if resp.status_code == 200 and load_from_dict(resp.json().get("record", {})):
                print("[Settings] ✅ Đã tải từ JSONBin.io.", flush=True)
                return
        except: pass
    
    try:
        with open('backup_settings.json', 'r') as f:
            if load_from_dict(json.load(f)): print("[Settings] ✅ Đã tải từ backup.", flush=True)
    except: print("[Settings] ⚠️ Dùng cài đặt mặc định.", flush=True)

# --- HÀM TRỢ GIÚP ---
def get_bot_name(bot_id_str):
    try:
        parts = bot_id_str.split('_')
        b_type, b_index = parts[0], int(parts[1])
        if b_type == 'main': return BOT_NAMES[b_index - 1] if 0 < b_index <= len(BOT_NAMES) else f"MAIN_{b_index}"
        return acc_names[b_index] if b_index < len(acc_names) else f"SUB_{b_index+1}"
    except: return bot_id_str.upper()

# --- LOGIC GRAB CARD ---
async def find_and_select_card(bot, channel_id, last_drop_msg_id, heart_threshold, bot_num, ktb_channel_id, max_heart_threshold=99999):
    """Hàm tìm và chọn card dựa trên khoảng số heart."""
    for _ in range(7):
        await asyncio.sleep(0.5)
        try:
            channel = bot.get_channel(int(channel_id))
            if not channel: continue
            
            async for message in channel.history(limit=5):
                if message.author.id == karibbit_id and int(message.id) > int(last_drop_msg_id):
                    if not message.embeds or '♡' not in message.embeds[0].description: continue
                    
                    lines = message.embeds[0].description.split('\n')[:3]
                    heart_numbers = [int(re.search(r'♡(\d+)', line).group(1)) if re.search(r'♡(\d+)', line) else 0 for line in lines]
                    if not any(heart_numbers): break
                    
                    valid_cards = [(idx, hearts) for idx, hearts in enumerate(heart_numbers) if heart_threshold <= hearts <= max_heart_threshold]
                    if not valid_cards: continue
                    
                    max_index, max_num = max(valid_cards, key=lambda x: x[1])
                    delays = {1: [0.35, 1.35, 2.05], 2: [0.7, 1.8, 2.4], 3: [0.7, 1.8, 2.4], 4: [0.8, 1.9, 2.5]}
                    bot_delays = delays.get(bot_num, [0.9, 2.0, 2.6])
                    emoji = ["1️⃣", "2️⃣", "3️⃣"][max_index]
                    delay = bot_delays[max_index]
                    
                    print(f"[CARD GRAB | Bot {bot_num}] Chọn dòng {max_index+1} với {max_num}♡ -> {emoji} sau {delay}s", flush=True)
                    
                    async def grab_action():
                        try:
                            await message.add_reaction(emoji)
                            await asyncio.sleep(1.2)
                            if ktb_channel_id:
                                ktb_channel = bot.get_channel(int(ktb_channel_id))
                                if ktb_channel: await ktb_channel.send("kt b")
                        except Exception as e: print(f"[CARD GRAB] ❌ Lỗi grab: {e}", flush=True)
                    
                    asyncio.create_task(asyncio.sleep(delay).then(grab_action))
                    return True
            return False
        except Exception as e: print(f"[CARD GRAB] ❌ Lỗi: {e}", flush=True)
    return False

# --- LOGIC BOT ---
def handle_grab_sync(bot, message, bot_num):
    """Wrapper đồng bộ cho async grab logic"""
    def run_async_grab():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            # Clan drop logic
            clan_settings = bot_states["auto_clan_drop"]
            if clan_settings.get("enabled") and message.channel.id == int(clan_settings.get("channel_id", 0)):
                bot_id_str = f'main_{bot_num}'
                threshold = clan_settings.get("heart_thresholds", {}).get(bot_id_str, 50)
                max_threshold = clan_settings.get("max_heart_thresholds", {}).get(bot_id_str, 99999)
                loop.run_until_complete(find_and_select_card(bot, str(message.channel.id), str(message.id), 
                                                           threshold, bot_num, clan_settings["ktb_channel_id"], max_threshold))
                return

            # Regular grab logic
            target_server = next((s for s in servers if s.get('main_channel_id') == str(message.channel.id)), None)
            if not target_server: return

            bot_id_str = f'main_{bot_num}'
            auto_grab_enabled = target_server.get(f'auto_grab_enabled_{bot_num}', False)
            watermelon_grab_enabled = bot_states["watermelon_grab"].get(bot_id_str, False)

            if auto_grab_enabled:
                threshold = target_server.get(f'heart_threshold_{bot_num}', 50)
                max_threshold = target_server.get(f'max_heart_threshold_{bot_num}', 99999)
                loop.run_until_complete(find_and_select_card(bot, str(message.channel.id), str(message.id), 
                                                           threshold, bot_num, target_server.get('ktb_channel_id'), max_threshold))

            if watermelon_grab_enabled:
                async def check_watermelon():
                    await asyncio.sleep(5)
                    try:
                        msg = await message.channel.fetch_message(message.id)
                        for reaction in msg.reactions:
                            if '🍉' in str(reaction.emoji) or 'watermelon' in str(reaction.emoji).lower():
                                await msg.add_reaction("🍉")
                                print(f"[WATERMELON | Bot {bot_num}] ✅ NHẶT DƯA THÀNH CÔNG!", flush=True)
                                return
                    except Exception as e: print(f"[WATERMELON] ❌ Lỗi: {e}", flush=True)
                
                loop.run_until_complete(check_watermelon())
        finally:
            loop.close()
    
    threading.Thread(target=run_async_grab, daemon=True).start()

# --- HỆ THỐNG REBOOT ---
def check_bot_health(bot_instance, bot_id):
    try:
        stats = bot_states["health_stats"].setdefault(bot_id, {'consecutive_failures': 0, 'last_check': time.time()})
        is_connected = bot_instance and not bot_instance.is_closed()
        if is_connected: stats['consecutive_failures'] = 0
        else: stats['consecutive_failures'] += 1
        return is_connected
    except: 
        bot_states["health_stats"].setdefault(bot_id, {})['consecutive_failures'] = \
            bot_states["health_stats"][bot_id].get('consecutive_failures', 0) + 1
        return False

def handle_reboot_failure(bot_id):
    settings = bot_states["reboot_settings"].setdefault(bot_id, {'delay': 3600, 'enabled': True, 'failure_count': 0})
    failure_count = settings['failure_count'] + 1
    settings['failure_count'] = failure_count
    backoff_multiplier = min(2 ** failure_count, 8)
    next_try_delay = max(600, settings.get('delay', 3600) * backoff_multiplier)
    settings['next_reboot_time'] = time.time() + next_try_delay
    print(f"[Safe Reboot] 🔴 Failure #{failure_count} for {bot_id}. Next try: {next_try_delay/60:.1f}min", flush=True)
    if failure_count >= 5: settings['enabled'] = False

def safe_reboot_bot(bot_id):
    if not bot_manager.start_reboot(bot_id): return False
    print(f"[Safe Reboot] 🔄 Reboot {bot_id}...", flush=True)
    try:
        match = re.match(r"main_(\d+)", bot_id)
        if not match: raise ValueError("Invalid bot_id format")
        
        bot_index = int(match.group(1)) - 1
        if not (0 <= bot_index < len(main_tokens)): raise IndexError("Bot index out of range")

        token = main_tokens[bot_index]
        bot_manager.remove_bot(bot_id)
        time.sleep(random.uniform(20, 40))

        new_bot = create_bot(token, bot_index + 1, is_main=True)
        if not new_bot: raise Exception("Failed to create new bot")

        bot_manager.add_bot(bot_id, new_bot)
        settings = bot_states["reboot_settings"][bot_id]
        settings.update({'next_reboot_time': time.time() + settings.get('delay', 3600), 
                        'failure_count': 0, 'last_reboot_time': time.time()})
        bot_states["health_stats"][bot_id]['consecutive_failures'] = 0
        print(f"[Safe Reboot] ✅ Reboot success {get_bot_name(bot_id)}", flush=True)
        return True
    except Exception as e:
        print(f"[Safe Reboot] ❌ Reboot failed {bot_id}: {e}", flush=True)
        handle_reboot_failure(bot_id)
        return False
    finally:
        bot_manager.end_reboot(bot_id)

# --- VÒNG LẶP NỀN ---
def auto_reboot_loop():
    print("[Safe Reboot] 🚀 Auto reboot loop started", flush=True)
    last_global_reboot_time = 0
    
    while not stop_events["reboot"].is_set():
        try:
            now = time.time()
            if now - last_global_reboot_time < 600: # 10 min cooldown
                stop_events["reboot"].wait(60)
                continue

            bot_to_reboot, highest_priority = None, -1
            for bot_id, settings in bot_states["reboot_settings"].items():
                if not settings.get('enabled') or bot_manager.is_rebooting(bot_id) or now < settings.get('next_reboot_time', 0): continue
                
                health_stats = bot_states["health_stats"].get(bot_id, {})
                priority = health_stats.get('consecutive_failures', 0) * 1000 + (now - settings.get('next_reboot_time', 0))
                if priority > highest_priority: highest_priority, bot_to_reboot = priority, bot_id
            
            if bot_to_reboot and safe_reboot_bot(bot_to_reboot):
                last_global_reboot_time = now
                stop_events["reboot"].wait(random.uniform(300, 600))
            else:
                stop_events["reboot"].wait(60)
        except Exception as e:
            print(f"[Safe Reboot] ❌ Error: {e}", flush=True)
            stop_events["reboot"].wait(120)

def run_clan_drop_cycle():
    print("[Clan Drop] 🚀 Starting cycle", flush=True)
    settings = bot_states["auto_clan_drop"]
    channel_id = settings.get("channel_id")
    active_main_bots = [(bot, int(bot_id.split('_')[1])) for bot_id, bot in bot_manager.get_main_bots_info() 
                       if bot and bot_states["active"].get(bot_id)]

    for bot, bot_num in active_main_bots:
        if stop_events["clan_drop"].is_set(): break
        try:
            async def send_kd():
                channel = bot.get_channel(int(channel_id))
                if channel: await channel.send("kd")
            
            asyncio.run_coroutine_threadsafe(send_kd(), bot.loop)
            time.sleep(random.uniform(settings["bot_delay"] * 0.8, settings["bot_delay"] * 1.2))
        except Exception as e: print(f"[Clan Drop] ❌ Error: {e}", flush=True)
    
    settings["last_cycle_start_time"] = time.time()

def auto_clan_drop_loop():
    while not stop_events["clan_drop"].is_set():
        settings = bot_states["auto_clan_drop"]
        if (settings.get("enabled") and settings.get("channel_id") and 
            (time.time() - settings.get("last_cycle_start_time", 0)) >= settings.get("cycle_interval", 1800)):
            run_clan_drop_cycle()
        stop_events["clan_drop"].wait(60)

# --- HỆ THỐNG SPAM 4 LUỒNG ---
def enhanced_spam_loop():
    print("[Enhanced Spam] 🚀 Starting 4-thread spam system...", flush=True)
    server_pair_index, delay_between_pairs, delay_within_pair, max_threads = 0, 1.5, 1.3, 4
    
    while True:
        try:
            active_spam_servers = [s for s in servers if s.get('spam_enabled') and s.get('spam_channel_id') and s.get('spam_message')]
            active_bots = [(bot_id, bot) for bot_id, bot in bot_manager.get_all_bots() if bot_states["active"].get(bot_id)]
            
            if not active_spam_servers or not active_bots:
                time.sleep(5)
                continue
            
            current_server_pair = active_spam_servers[server_pair_index * 2:(server_pair_index * 2) + 2]
            if not current_server_pair:
                server_pair_index = 0
                continue
            
            bots_per_group = max(1, len(active_bots) // max_threads)
            bot_groups = [active_bots[i:i + bots_per_group] for i in range(0, len(active_bots), bots_per_group)]
            
            def group_spam_action(bots_in_group, servers_pair):
                try:
                    # Spam server đầu tiên
                    if servers_pair:
                        server1 = servers_pair[0]
                        for bot_id, bot_instance in bots_in_group:
                            try:
                                async def send_spam1():
                                    channel = bot_instance.get_channel(int(server1['spam_channel_id']))
                                    if channel: await channel.send(server1['spam_message'])
                                asyncio.run_coroutine_threadsafe(send_spam1(), bot_instance.loop)
                                time.sleep(0.1)
                            except: pass

                    # Spam server thứ hai sau delay
                    if len(servers_pair) > 1:
                        time.sleep(delay_within_pair)
                        server2 = servers_pair[1]
                        for bot_id, bot_instance in bots_in_group:
                            try:
                                async def send_spam2():
                                    channel = bot_instance.get_channel(int(server2['spam_channel_id']))
                                    if channel: await channel.send(server2['spam_message'])
                                asyncio.run_coroutine_threadsafe(send_spam2(), bot_instance.loop)
                                time.sleep(0.02)
                            except: pass
                except Exception as e: print(f"[Enhanced Spam] ❌ Error: {e}", flush=True)
            
            spam_threads = []
            for bot_group in bot_groups:
                thread = threading.Thread(target=group_spam_action, args=(bot_group, current_server_pair), daemon=True)
                spam_threads.append(thread)
                thread.start()
            
            for thread in spam_threads: thread.join(timeout=10)
            server_pair_index += 1
            time.sleep(delay_between_pairs)
            
        except Exception as e:
            print(f"[Enhanced Spam] ❌ Error: {e}", flush=True)
            time.sleep(10)

def periodic_task(interval, task_func, task_name):
    while True:
        time.sleep(interval)
        try: task_func()
        except Exception as e: print(f"[{task_name}] ❌ Error: {e}", flush=True)

def health_monitoring_check():
    for bot_id, bot in bot_manager.get_all_bots(): check_bot_health(bot, bot_id)

# --- KHỞI TẠO BOT ---
def create_bot(token, bot_identifier, is_main=False):
    try:
        bot_id_str = f"main_{bot_identifier}" if is_main else f"sub_{bot_identifier}"
        
        class SelfBot(discord.Client):
            def __init__(self, **options):
                super().__init__(**options)
                self.bot_id_str = bot_id_str
                self.bot_num = bot_identifier

            async def on_ready(self):
                print(f"[Bot] ✅ Login: {self.user.id} ({get_bot_name(self.bot_id_str)}) - {self.user.name}", flush=True)
                bot_states["health_stats"].setdefault(self.bot_id_str, {'created_time': time.time(), 'consecutive_failures': 0})

            async def on_message(self, message):
                if not is_main or message.author.id != karuta_id or "dropping" not in message.content.lower(): return
                try: handle_grab_sync(self, message, self.bot_num)
                except Exception as e: print(f"[Bot] ❌ Message handler error: {e}", flush=True)

        bot = SelfBot()
        
        def run_bot():
            try: bot.run(token, bot=False)
            except Exception as e: print(f"[Bot] ❌ Run error for {bot_id_str}: {e}", flush=True)
        
        threading.Thread(target=run_bot, daemon=True).start()
        time.sleep(3)  # Wait for connection
        return bot if not bot.is_closed() else None

    except Exception as e:
        print(f"[Bot] ❌ Create error {bot_identifier}: {e}", flush=True)
        return None


# --- FLASK APP & GIAO DIỆN (HTML không đổi, các route được giữ nguyên) ---
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
        .heart-input { flex-grow: 0 !important; width: 100px; text-align: center; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1 class="title">Shadow Network Control</h1>
            <div class="subtitle">discord.py-self Edition - FIXED VERSION</div>
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
                         <div>⏱️ Min Reboot Interval: 10 minutes | Max Failures: 5 attempts</div>
                         <div>🎯 Reboot Strategy: Priority-based, one-at-a-time with cleanup delay</div>
                         <div>🐛 BUG FIXES: ✅ Watermelon Grab | ✅ Spam System Timing</div>
                     </div>
                     <div id="bot-control-grid" class="bot-status-grid" style="grid-template-columns: repeat(auto-fit, minmax(380px, 1fr));"></div>
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
                            <input type="number" class="clan-drop-threshold heart-input" data-node="main_{{ bot.id }}" value="{{ auto_clan_drop.heart_thresholds[('main_' + bot.id|string)]|default(50) }}" min="0" max="99999" placeholder="Min ♡">
                            <input type="number" class="clan-drop-max-threshold heart-input" data-node="main_{{ bot.id }}" value="{{ auto_clan_drop.max_heart_thresholds[('main_' + bot.id|string)]|default(99999) }}" min="0" max="99999" placeholder="Max ♡">
                        </div>
                    </div>
                    {% endfor %}
                </div>
                <button type="button" id="clan-drop-save-btn" class="btn" style="margin-top: 20px;">Save Clan Drop Settings</button>
            </div>
            <div class="panel global-settings-panel">
                <h2><i class="fas fa-globe"></i> Global Event Settings</h2>
                <div class="server-sub-panel">
                    <h3><i class="fas fa-seedling"></i> Watermelon Grab (All Servers) - 🍉 FIXED!</h3>
                    <div id="global-watermelon-grid" class="bot-status-grid" style="grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));"></div>
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
                             <input type="number" class="harvest-threshold heart-input" data-node="{{ bot.id }}" value="{{ server['heart_threshold_' + bot.id|string] or 50 }}" min="0" placeholder="Min ♡">
                            <input type="number" class="harvest-max-threshold heart-input" data-node="{{ bot.id }}" value="{{ server['max_heart_threshold_' + bot.id|string]|default(99999) }}" min="0" placeholder="Max ♡">
                            <button type="button" class="btn harvest-toggle" data-node="{{ bot.id }}">
                                {{ 'DISABLE' if server['auto_grab_enabled_' + bot.id|string] else 'ENABLE' }}
                            </button>
                        </div>
                    </div>
                    {% endfor %}
                </div>
                <div class="server-sub-panel">
                    <h3><i class="fas fa-paper-plane"></i> Auto Broadcast - ⚡ FIXED!</h3>
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
            <div class="panel add-server-btn" id="add-server-btn"> <i class="fas fa-plus"></i></div>
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
                const updatedBotIds = new Set();
                allBots.forEach(bot => {
                    const botId = bot.reboot_id;
                    updatedBotIds.add(`bot-container-${botId}`);
                    let itemContainer = document.getElementById(`bot-container-${botId}`);
                    if (!itemContainer) {
                        itemContainer = document.createElement('div');
                        itemContainer.id = `bot-container-${botId}`;
                        itemContainer.className = 'status-row';
                        itemContainer.style.cssText = 'flex-direction: column; align-items: stretch; padding: 10px;';
                        botControlGrid.appendChild(itemContainer);
                    }
                    let healthClass = 'health-good';
                    if (bot.health_status === 'warning') healthClass = 'health-warning';
                    else if (bot.health_status === 'bad') healthClass = 'health-bad';
                    let rebootingIndicator = bot.is_rebooting ? ' <i class="fas fa-sync-alt fa-spin"></i>' : '';
                    let controlHtml = `
                        <div style="display: flex; justify-content: space-between; align-items: center; width: 100%;">
                           <span style="font-weight: bold; ${bot.type === 'main' ? 'color: #FF4500;' : ''}">${bot.name}<span class="health-indicator ${healthClass}"></span>${rebootingIndicator}</span>
                           <button type="button" id="toggle-state-${botId}" data-target="${botId}" class="btn-toggle-state ${bot.is_active ? 'btn-rise' : 'btn-rest'}">
                               ${bot.is_active ? 'ONLINE' : 'OFFLINE'}
                           </button>
                        </div>`;
                    if (bot.type === 'main') {
                        const r_settings = data.bot_reboot_settings[botId] || { delay: 3600, enabled: false, failure_count: 0 };
                        const statusClass = r_settings.failure_count > 0 ? 'btn-warning' : (r_settings.enabled ? 'btn-rise' : 'btn-rest');
                        const statusText = r_settings.failure_count > 0 ? `FAIL(${r_settings.failure_count})` : (r_settings.enabled ? 'AUTO' : 'MANUAL');
                        const countdownText = formatTime(r_settings.countdown);
                        controlHtml += `
                        <div class="input-group" style="margin-top: 10px; margin-bottom: 0;">
                             <input type="number" class="bot-reboot-delay" value="${r_settings.delay}" data-bot-id="${botId}" style="width: 80px; text-align: right; flex-grow: 0;">
                             <span id="timer-${botId}" class="timer-display bot-reboot-timer" style="padding: 0 10px;">${countdownText}</span>
                             <button type="button" id="toggle-reboot-${botId}" class="btn btn-small bot-reboot-toggle ${statusClass}" data-bot-id="${botId}">
                                 ${statusText}
                             </button>
                        </div>`;
                    }
                    itemContainer.innerHTML = controlHtml;
                });
                Array.from(botControlGrid.children).forEach(child => {
                    if (!updatedBotIds.has(child.id)) child.remove();
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
                'btn-toggle-state': () => postData('/api/toggle_bot_state', { target: button.dataset.target }),
                'clan-drop-toggle-btn': () => postData('/api/clan_drop_toggle'),
                'clan-drop-save-btn': () => {
                    const thresholds = {}, maxThresholds = {};
                    document.querySelectorAll('.clan-drop-threshold').forEach(i => { thresholds[i.dataset.node] = parseInt(i.value, 10); });
                    document.querySelectorAll('.clan-drop-max-threshold').forEach(i => { maxThresholds[i.dataset.node] = parseInt(i.value, 10); });
                    postData('/api/clan_drop_update', { channel_id: document.getElementById('clan-drop-channel-id').value, ktb_channel_id: document.getElementById('clan-drop-ktb-channel-id').value, heart_thresholds: thresholds, max_heart_thresholds: maxThresholds });
                },
                'watermelon-toggle': () => postData('/api/watermelon_toggle', { node: button.dataset.node }),
                'harvest-toggle': () => serverId && postData('/api/harvest_toggle', { server_id: serverId, node: button.dataset.node, threshold: serverPanel.querySelector(`.harvest-threshold[data-node="${button.dataset.node}"]`).value, max_threshold: serverPanel.querySelector(`.harvest-max-threshold[data-node="${button.dataset.node}"]`).value }),
                'broadcast-toggle': () => serverId && postData('/api/broadcast_toggle', { server_id: serverId, message: serverPanel.querySelector('.spam-message').value, delay: serverPanel.querySelector('.spam-delay').value }),
                'btn-delete-server': () => serverId && confirm('Are you sure?') && postData('/api/delete_server', { server_id: serverId })
            };
            for (const cls in actions) { if (button.classList.contains(cls) || button.id === cls) { actions[cls](); return; } }
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
@app.route("/")
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route("/status")
def status_endpoint():
    now = time.time()
    def get_bot_status_list(bot_info_list, type_prefix):
        return [{"name": get_bot_name(bot_id), "status": bot is not None and not bot.is_closed(), 
                "reboot_id": bot_id, "is_active": bot_states["active"].get(bot_id, False), 
                "type": type_prefix, "health_status": "good", "is_rebooting": bot_manager.is_rebooting(bot_id)}
               for bot_id, bot in bot_info_list]

    return jsonify({
        'bot_reboot_settings': bot_states["reboot_settings"],
        'bot_statuses': {"main_bots": get_bot_status_list(bot_manager.get_main_bots_info(), "main"),
                        "sub_accounts": get_bot_status_list(bot_manager.get_sub_bots_info(), "sub")},
        'server_start_time': server_start_time, 'servers': servers,
        'watermelon_grab_states': bot_states["watermelon_grab"],
        'auto_clan_drop_status': {"enabled": bot_states["auto_clan_drop"].get("enabled", False), "countdown": 0}
    })

# --- MAIN EXECUTION ---
if __name__ == "__main__":
    print("🚀 Shadow Network Control - Discord.py-self Starting...", flush=True)
    load_settings()

    # Khởi tạo bot chính
    for i, token in enumerate(main_tokens):
        bot_num = i + 1
        bot_id = f"main_{bot_num}"
        bot = create_bot(token, bot_identifier=bot_num, is_main=True)
        if bot: bot_manager.add_bot(bot_id, bot)
        
        for key in ["active", "watermelon_grab"]: bot_states[key].setdefault(bot_id, key == "active")
        bot_states["auto_clan_drop"]["heart_thresholds"].setdefault(bot_id, 50)
        bot_states["auto_clan_drop"].setdefault("max_heart_thresholds", {}).setdefault(bot_id, 99999)
        bot_states["reboot_settings"].setdefault(bot_id, {'enabled': False, 'delay': 3600, 'next_reboot_time': 0, 'failure_count': 0})
        bot_states["health_stats"].setdefault(bot_id, {'consecutive_failures': 0})

    # Khởi tạo bot phụ
    for i, token in enumerate(sub_tokens):
        bot_id = f"sub_{i}"
        bot = create_bot(token, bot_identifier=i, is_main=False)
        if bot: bot_manager.add_bot(bot_id, bot)
        bot_states["active"].setdefault(bot_id, True)
        bot_states["health_stats"].setdefault(bot_id, {'consecutive_failures': 0})

    # Khởi động background threads
    for args in [(1800, save_settings, "Save"), (300, health_monitoring_check, "Health")]:
        threading.Thread(target=periodic_task, args=args, daemon=True).start()
    
    # Khởi động spam system (4 luồng)
    threading.Thread(target=enhanced_spam_loop, daemon=True).start()
    
    # Khởi động auto reboot và clan drop
    threading.Thread(target=auto_reboot_loop, daemon=True).start()
    threading.Thread(target=auto_clan_drop_loop, daemon=True).start()
    
    port = int(os.environ.get("PORT", 10000))
    print(f"🌐 Web Server running at http://0.0.0.0:{port}", flush=True)
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
