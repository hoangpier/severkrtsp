# PHIÊN BẢN CHUYỂN ĐỔI HOÀN CHỈNH SANG DISCORD.PY-SELF - ĐÃ SỬA LỖI & TỐI ƯU HÓA
import discord, asyncio, threading, time, os, re, requests, json, random, traceback, uuid
from flask import Flask, request, render_template_string, jsonify
from dotenv import load_dotenv
from datetime import datetime, timedelta

load_dotenv()

# --- CẤU HÌNH (Không đổi) ---
main_tokens = os.getenv("MAIN_TOKENS", "").split(",")
tokens = os.getenv("TOKENS", "").split(",")
karuta_id, karibbit_id = "646937666251915264", "1311684840462225440"
BOT_NAMES = ["xsyx", "sofa", "dont", "ayaya", "owo", "astra", "singo", "dia pox", "clam", "rambo", "domixi", "dogi", "sicula", "mo turn", "jan taru", "kio sama"]
acc_names = [f"Bot-{i:02d}" for i in range(1, 21)]

# --- BIẾN TRẠNG THÁI & KHÓA (Không đổi) ---
servers = []
bot_states = {
    "reboot_settings": {}, "active": {}, "watermelon_grab": {}, "health_stats": {},
    "auto_clan_drop": {"enabled": False, "channel_id": "", "ktb_channel_id": "", "last_cycle_start_time": 0, "cycle_interval": 1800, "bot_delay": 140, "heart_thresholds": {}, "max_heart_thresholds": {}}
}
stop_events = {"reboot": threading.Event(), "clan_drop": threading.Event()}
server_start_time = time.time()

# --- QUẢN LÍ BOT THREAD-SAFE (Cập nhật cho Async) ---
class ThreadSafeBotManager:
    def __init__(self):
        self._bots = {}
        self._rebooting = set()
        self._lock = threading.RLock()

    def add_bot(self, bot_id, bot_data):
        with self._lock:
            self._bots[bot_id] = bot_data
            print(f"[Bot Manager] ✅ Added bot {bot_id}", flush=True)

    # SỬA LỖI: Ngắt kết nối an toàn để tránh lỗi "Task was destroyed"
    def remove_bot(self, bot_id):
        with self._lock:
            bot_data = self._bots.pop(bot_id, None)
            if bot_data and bot_data.get('instance'):
                bot = bot_data['instance']
                loop = bot_data['loop']
                if loop.is_running():
                    future = asyncio.run_coroutine_threadsafe(bot.close(), loop)
                    try:
                        future.result(timeout=10)
                        print(f"[Bot Manager] ✅ Gracefully closed bot {bot_id}", flush=True)
                    except Exception as e:
                        print(f"[Bot Manager] ⚠️ Error waiting for bot {bot_id} to close: {e}", flush=True)
                print(f"[Bot Manager] 🗑️ Removed and requested cleanup for bot {bot_id}", flush=True)
            return bot_data

    def get_bot_data(self, bot_id):
        with self._lock:
            return self._bots.get(bot_id)

    def get_all_bots_data(self):
        with self._lock:
            return list(self._bots.items())

    def get_main_bots_info(self):
        with self._lock:
            return [(bot_id, data) for bot_id, data in self._bots.items() if bot_id.startswith('main_')]
            
    def get_sub_bots_info(self):
        with self._lock:
            return [(bot_id, data) for bot_id, data in self._bots.items() if bot_id.startswith('sub_')]

    def is_rebooting(self, bot_id):
        with self._lock:
            return bot_id in self._rebooting

    def start_reboot(self, bot_id):
        with self._lock:
            if self.is_rebooting(bot_id): return False
            self._rebooting.add(bot_id)
            return True

    def end_reboot(self, bot_id):
        with self._lock:
            self._rebooting.discard(bot_id)

bot_manager = ThreadSafeBotManager()

# --- CẦU NỐI ĐỒNG BỘ -> BẤT ĐỒNG BỘ ---
def send_message_from_sync(bot_id, channel_id, content):
    bot_data = bot_manager.get_bot_data(bot_id)
    if not bot_data or not bot_data.get('instance'): return
    
    bot = bot_data['instance']
    loop = bot_data['loop']

    async def _send():
        try:
            channel = bot.get_channel(int(channel_id))
            if channel:
                await channel.send(content)
        except Exception as e:
            print(f"[Async Send] ❌ Lỗi khi gửi tin nhắn từ {bot_id}: {e}", flush=True)

    if loop.is_running():
        future = asyncio.run_coroutine_threadsafe(_send(), loop)
        try:
            future.result(timeout=10)
        except Exception as e:
            print(f"[Async Send] ❌ Lỗi khi chờ kết quả gửi tin: {e}", flush=True)

# --- LƯU & TẢI CÀI ĐẶT (Không đổi) ---
def save_settings():
    # ... (Giữ nguyên)
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
    # ... (Giữ nguyên)
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

# --- HÀM TRỢ GIÚP (Không đổi) ---
def get_bot_name(bot_id_str):
    try:
        parts = bot_id_str.split('_')
        b_type, b_index = parts[0], int(parts[1])
        if b_type == 'main':
            return BOT_NAMES[b_index - 1] if 0 < b_index <= len(BOT_NAMES) else f"MAIN_{b_index}"
        return acc_names[b_index] if b_index < len(acc_names) else f"SUB_{b_index+1}"
    except (IndexError, ValueError):
        return bot_id_str.upper()

# --- LOGIC GRAB CARD (CHUYỂN ĐỔI SANG ASYNC) ---
async def _find_and_select_card(bot, channel_id, last_drop_msg_id, heart_threshold, bot_num, ktb_channel_id, max_heart_threshold=99999):
    try:
        channel = bot.get_channel(int(channel_id))
        if not channel: return False
    except ValueError:
        return False
        
    for _ in range(7):
        await asyncio.sleep(0.5)
        try:
            async for msg_item in channel.history(limit=5):
                if msg_item.author.id == int(karibbit_id) and msg_item.id > int(last_drop_msg_id):
                    if not msg_item.embeds: continue
                    desc = msg_item.embeds[0].description
                    if not desc or '♡' not in desc: continue

                    lines = desc.split('\n')[:3]
                    heart_numbers = [int(re.search(r'♡(\d+)', line).group(1)) if re.search(r'♡(\d+)', line) else 0 for line in lines]
                    if not any(heart_numbers): break
                    
                    valid_cards = [(idx, hearts) for idx, hearts in enumerate(heart_numbers) if heart_threshold <= hearts <= max_heart_threshold]
                    if not valid_cards: continue
                    
                    max_index, max_num = max(valid_cards, key=lambda x: x[1])
                    
                    delays = {1: [0.35, 1.35, 2.05], 2: [0.7, 1.8, 2.4], 3: [0.7, 1.8, 2.4], 4: [0.8, 1.9, 2.5]}
                    bot_delays = delays.get(bot_num, [0.9, 2.0, 2.6])
                    emoji = ["1️⃣", "2️⃣", "3️⃣"][max_index]
                    delay = bot_delays[max_index]
                    
                    print(f"[CARD GRAB | Bot {bot_num}] Chọn dòng {max_index+1} với {max_num}♡ (range: {heart_threshold}-{max_heart_threshold}) -> {emoji} sau {delay}s", flush=True)

                    async def grab_action():
                        try:
                            drop_message = await channel.fetch_message(int(last_drop_msg_id))
                            await drop_message.add_reaction(emoji)
                            await asyncio.sleep(1.2)
                            if ktb_channel_id:
                                ktb_channel_obj = bot.get_channel(int(ktb_channel_id))
                                if ktb_channel_obj: await ktb_channel_obj.send("kt b")
                            print(f"[CARD GRAB | Bot {bot_num}] ✅ Đã grab và gửi kt b", flush=True)
                        except Exception as e:
                            print(f"[CARD GRAB | Bot {bot_num}] ❌ Lỗi grab: {e}", flush=True)
                    
                    # Thay thế threading.Timer bằng logic async
                    await asyncio.sleep(delay)
                    asyncio.create_task(grab_action())
                    return True
            return False
        except Exception as e:
            print(f"[CARD GRAB | Bot {bot_num}] ❌ Lỗi đọc messages: {e}", flush=True)
    return False

# --- LOGIC BOT (CHUYỂN ĐỔI SANG ASYNC) ---
async def handle_clan_drop(bot, msg, bot_num):
    clan_settings = bot_states["auto_clan_drop"]
    if not (clan_settings.get("enabled") and msg.channel.id == int(clan_settings.get("channel_id", 0))):
        return
    bot_id_str = f'main_{bot_num}'
    threshold = clan_settings.get("heart_thresholds", {}).get(bot_id_str, 50)
    max_threshold = clan_settings.get("max_heart_thresholds", {}).get(bot_id_str, 99999)
    asyncio.create_task(_find_and_select_card(bot, clan_settings["channel_id"], msg.id, threshold, bot_num, clan_settings["ktb_channel_id"], max_threshold))

async def handle_grab(bot, msg, bot_num):
    channel_id = msg.channel.id
    target_server = next((s for s in servers if s.get('main_channel_id') == str(channel_id)), None)
    if not target_server: return

    bot_id_str = f'main_{bot_num}'
    auto_grab_enabled = target_server.get(f'auto_grab_enabled_{bot_num}', False)
    watermelon_grab_enabled = bot_states["watermelon_grab"].get(bot_id_str, False)

    if not auto_grab_enabled and not watermelon_grab_enabled: return
    
    if auto_grab_enabled and target_server.get('ktb_channel_id'):
        threshold = target_server.get(f'heart_threshold_{bot_num}', 50)
        max_threshold = target_server.get(f'max_heart_threshold_{bot_num}', 99999)
        asyncio.create_task(_find_and_select_card(bot, str(channel_id), msg.id, threshold, bot_num, target_server.get('ktb_channel_id'), max_threshold))

    if watermelon_grab_enabled:
        async def check_for_watermelon_patiently():
            print(f"[WATERMELON | Bot {bot_num}] 🍉 Bắt đầu canh dưa (chờ 5 giây)...", flush=True)
            await asyncio.sleep(5) 
            try:
                target_message = await msg.channel.fetch_message(msg.id)
                for reaction in target_message.reactions:
                    emoji_name = str(reaction.emoji).lower()
                    if '🍉' in emoji_name or 'watermelon' in emoji_name or 'dua' in emoji_name:
                        print(f"[WATERMELON | Bot {bot_num}] 🎯 PHÁT HIỆN DƯA HẤU!", flush=True)
                        try:
                            await target_message.add_reaction("🍉")
                            print(f"[WATERMELON | Bot {bot_num}] ✅ NHẶT DƯA THÀNH CÔNG!", flush=True)
                        except Exception as e:
                            print(f"[WATERMELON | Bot {bot_num}] ❌ Lỗi react khi đã thấy dưa: {e}", flush=True)
                        return
                print(f"[WATERMELON | Bot {bot_num}] 😞 Không tìm thấy dưa hấu sau khi chờ.", flush=True)
            except Exception as e:
                print(f"[WATERMELON | Bot {bot_num}] ❌ Lỗi khi lấy tin nhắn để check dưa: {e}", flush=True)
        asyncio.create_task(check_for_watermelon_patiently())

# --- HỆ THỐNG REBOOT & HEALTH CHECK (Cập nhật cho discord.py-self) ---
def check_bot_health(bot_data, bot_id):
    try:
        stats = bot_states["health_stats"].setdefault(bot_id, {'consecutive_failures': 0, 'last_check': 0})
        stats['last_check'] = time.time()
        
        if not bot_data or not bot_data.get('instance'):
            stats['consecutive_failures'] += 1
            return False

        bot = bot_data['instance']
        is_connected = bot.is_ready()
        
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
        old_bot_data = bot_manager.remove_bot(bot_id)
        if old_bot_data and old_bot_data.get('thread') and old_bot_data['thread'].is_alive():
             old_bot_data['thread'].join(timeout=15)

        settings = bot_states["reboot_settings"].get(bot_id, {})
        failure_count = settings.get('failure_count', 0)
        wait_time = random.uniform(20, 40) + min(failure_count * 30, 300)
        print(f"[Safe Reboot] ⏳ Chờ {wait_time:.1f}s để cleanup...", flush=True)
        time.sleep(wait_time)

        print(f"[Safe Reboot] 🔧 Creating new bot thread for {bot_name}", flush=True)
        new_bot_is_ready = threading.Event()
        new_thread = threading.Thread(target=initialize_and_run_bot, args=(token, bot_id, True, new_bot_is_ready), daemon=True)
        new_thread.start()
        
        ready_in_time = new_bot_is_ready.wait(timeout=60)
        
        if not ready_in_time:
             raise Exception("Bot mới không sẵn sàng trong 60 giây.")

        settings.update({
            'next_reboot_time': time.time() + settings.get('delay', 3600),
            'failure_count': 0, 'last_reboot_time': time.time()
        })
        bot_states["health_stats"].setdefault(bot_id, {})['consecutive_failures'] = 0
        print(f"[Safe Reboot] ✅ Reboot thành công {bot_name}", flush=True)
        return True
    except Exception as e:
        print(f"[Safe Reboot] ❌ Reboot thất bại cho {bot_id}: {e}", flush=True)
        traceback.print_exc()
        handle_reboot_failure(bot_id)
        return False
    finally:
        bot_manager.end_reboot(bot_id)

# --- VÒNG LẶP NỀN (Cập nhật cho async) ---
def auto_reboot_loop():
    # ... (Giữ nguyên logic)
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
    channel_id = settings.get("channel_id")
    if not channel_id: return
    
    active_main_bots_info = [
        (bot_id, int(bot_id.split('_')[1])) 
        for bot_id, data in bot_manager.get_main_bots_info() 
        if data.get('instance') and bot_states["active"].get(bot_id, False)
    ]
    if not active_main_bots_info:
        print("[Clan Drop] ⚠️ Không có bot chính nào hoạt động.", flush=True)
        return

    for bot_id, bot_num in active_main_bots_info:
        if stop_events["clan_drop"].is_set(): break
        try:
            print(f"[Clan Drop] 📤 Bot {get_bot_name(f'main_{bot_num}')} đang gửi 'kd'...", flush=True)
            send_message_from_sync(bot_id, channel_id, "kd")
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

# --- HỆ THỐNG SPAM (SỬA LỖI: Đồng bộ hóa luồng spam) ---
def enhanced_spam_loop():
    print("[Enhanced Spam] 🚀 Khởi động hệ thống spam tối ưu (đa luồng)...", flush=True)
    server_pair_index = 0
    delay_between_pairs = 2
    delay_within_pair = 1.5
    max_threads = 4
    
    while True:
        try:
            active_spam_servers = [s for s in servers if s.get('spam_enabled') and s.get('spam_channel_id') and s.get('spam_message')]
            active_bots = [bot_id for bot_id, data in bot_manager.get_all_bots_data() if bot_states["active"].get(bot_id) and data.get('instance')]
            
            if not active_spam_servers or not active_bots:
                time.sleep(5)
                continue
            
            start_index = server_pair_index * 2
            current_server_pair = active_spam_servers[start_index:start_index + 2]
            
            if not current_server_pair:
                server_pair_index = 0
                time.sleep(delay_between_pairs) 
                continue
            
            print(f"[Enhanced Spam] 📤 Spam cặp #{server_pair_index + 1}: {[s.get('name', 'Unknown') for s in current_server_pair]}", flush=True)
            
            bot_groups = []
            bots_per_group = max(1, len(active_bots) // max_threads)
            for i in range(0, len(active_bots), bots_per_group):
                bot_groups.append(active_bots[i:i + bots_per_group])
            
            spam_threads = []
            for group_index, bot_group in enumerate(bot_groups):
                def group_spam_action(bots_in_group=bot_group, servers_pair=current_server_pair, group_id=group_index):
                    try:
                        server1 = servers_pair[0]
                        for bot_id in bots_in_group:
                            send_message_from_sync(bot_id, server1['spam_channel_id'], server1['spam_message'])
                            time.sleep(0.1)

                        if len(servers_pair) > 1:
                            time.sleep(delay_within_pair)
                            server2 = servers_pair[1]
                            for bot_id in bots_in_group:
                                send_message_from_sync(bot_id, server2['spam_channel_id'], server2['spam_message'])
                                time.sleep(0.02)
                    except Exception as e:
                        print(f"[Enhanced Spam] ❌ Lỗi nhóm {group_id}: {e}", flush=True)
                
                thread = threading.Thread(target=group_spam_action, daemon=True)
                spam_threads.append(thread)
                thread.start()
            
            # Đảm bảo các luồng spam hoàn thành trước khi sang chu kỳ mới
            for thread in spam_threads:
                thread.join()
            
            server_pair_index = (server_pair_index + 1) % ( (len(active_spam_servers) + 1) // 2 )
            time.sleep(delay_between_pairs)
            
        except Exception as e:
            print(f"[Enhanced Spam] ❌ Lỗi nghiêm trọng: {e}", flush=True)
            traceback.print_exc()
            time.sleep(10)

def ultra_optimized_spam_loop():
    # ... (Giữ nguyên)
    print("[Ultra Spam] 🚀 Khởi động spam siêu tối ưu - 1 luồng duy nhất...", flush=True)
    server_pair_index = 0
    delay_between_pairs = 1.5
    delay_within_pair = 0.8
    while True:
        try:
            active_spam_servers = [s for s in servers if s.get('spam_enabled') and s.get('spam_channel_id') and s.get('spam_message')]
            active_bots = [bot_id for bot_id, data in bot_manager.get_all_bots_data() if bot_states["active"].get(bot_id) and data.get('instance')]
            
            if not active_spam_servers or not active_bots:
                time.sleep(5); continue
            
            start_index = server_pair_index * 2
            current_server_pair = active_spam_servers[start_index:start_index + 2]
            
            if not current_server_pair:
                server_pair_index = 0
                continue
            
            print(f"[Ultra Spam] 📤 Spam cặp #{server_pair_index + 1}: {[s.get('name', 'Unknown') for s in current_server_pair]}", flush=True)
            
            server1 = current_server_pair[0]
            for bot_id in active_bots:
                send_message_from_sync(bot_id, server1['spam_channel_id'], server1['spam_message'])
                time.sleep(0.01)

            if len(current_server_pair) > 1:
                time.sleep(delay_within_pair)
                server2 = current_server_pair[1]
                for bot_id in active_bots:
                    send_message_from_sync(bot_id, server2['spam_channel_id'], server2['spam_message'])
                    time.sleep(0.01)

            server_pair_index = (server_pair_index + 1) % ( (len(active_spam_servers) + 1) // 2 )
            time.sleep(delay_between_pairs)
            
        except Exception as e:
            print(f"[Ultra Spam] ❌ Lỗi nghiêm trọng: {e}", flush=True)
            traceback.print_exc()
            time.sleep(10)

def start_optimized_spam_system(mode="optimized"):
    # ... (Giữ nguyên)
    print(f"[Spam System] 🔄 Khởi động hệ thống spam ở chế độ '{mode}'...", flush=True)
    if mode == "ultra":
        spam_thread = threading.Thread(target=ultra_optimized_spam_loop, daemon=True)
    else:
        spam_thread = threading.Thread(target=enhanced_spam_loop, daemon=True)
    spam_thread.start()
    print(f"[Spam System] ✅ Hệ thống spam '{mode}' đã khởi động!", flush=True)

def periodic_task(interval, task_func, task_name):
    # ... (Giữ nguyên)
    print(f"[{task_name}] 🚀 Khởi động luồng định kỳ.", flush=True)
    while True:
        time.sleep(interval)
        try: task_func()
        except Exception as e: print(f"[{task_name}] ❌ Lỗi: {e}", flush=True)

def health_monitoring_check():
    all_bots = bot_manager.get_all_bots_data()
    for bot_id, bot_data in all_bots:
        check_bot_health(bot_data, bot_id)

# --- KHỞI TẠO BOT (VIẾT LẠI HOÀN TOÀN CHO discord.py-self) ---
def initialize_and_run_bot(token, bot_id_str, is_main, ready_event=None):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    bot = discord.Client(self_bot=True)
    
    try:
        bot_identifier_str = bot_id_str.split('_')[1]
        # Đối với bot chính, số định danh bắt đầu từ 1, còn bot phụ từ 0
        bot_identifier = int(bot_identifier_str) + 1 if is_main else int(bot_identifier_str)
    except (IndexError, ValueError):
        print(f"[Bot Init] ⚠️ Không thể phân tích ID cho bot: {bot_id_str}. Dùng giá trị mặc định.", flush=True)
        bot_identifier = 99
    
    @bot.event
    async def on_ready():
        try:
            print(f"[Bot] ✅ Đăng nhập: {bot.user.id} ({get_bot_name(bot_id_str)}) - {bot.user.name}", flush=True)
            stats = bot_states["health_stats"].setdefault(bot_id_str, {})
            stats.update({'created_time': time.time(), 'consecutive_failures': 0})
            if ready_event: ready_event.set()
        except Exception as e:
            print(f"[Bot] ❌ Error in on_ready for {bot_id_str}: {e}", flush=True)
    
    if is_main:
        @bot.event
        async def on_message(msg):
            try:
                # SỬA LỖI: Chỉ xử lý tin nhắn drop thẻ thật sự (có embeds)
                if msg.author.id == int(karuta_id) and "dropping" in msg.content.lower() and msg.embeds:
                    is_clan_drop = bool(msg.mentions) 
                    handler = handle_clan_drop if is_clan_drop else handle_grab
                    # Gọi trực tiếp hàm async
                    await handler(bot, msg, bot_identifier)
            except Exception as e:
                print(f"[Bot] ❌ Error in on_message for {bot_id_str}: {e}\n{traceback.format_exc()}", flush=True)
    
    try:
        bot_data = {'instance': bot, 'loop': loop, 'thread': threading.current_thread()}
        bot_manager.add_bot(bot_id_str, bot_data)
        loop.run_until_complete(bot.start(token))
    except (discord.LoginFailure, discord.errors.PrivilegedIntentsRequired):
        print(f"[Bot] ❌ Login thất bại cho {get_bot_name(bot_id_str)}. Token có thể không hợp lệ hoặc thiếu Intents.", flush=True)
        if ready_event: ready_event.set()
        bot_manager.remove_bot(bot_id_str)
    except Exception as e:
        print(f"[Bot] ❌ Lỗi khi chạy bot {bot_id_str}: {e}", flush=True)
        if ready_event: ready_event.set()
        bot_manager.remove_bot(bot_id_str)
    finally:
        if loop.is_running():
            loop.stop()
        loop.close()
        print(f"[Bot] ⏹️ Event loop closed for {bot_id_str}", flush=True)

# --- FLASK APP & GIAO DIỆN (Giữ nguyên) ---
app = Flask(__name__)
# HTML_TEMPLATE và các route giữ nguyên như file multi_bot_control_self.py đã sửa
# ... (Phần này rất dài và không thay đổi, nên được lược bỏ cho ngắn gọn)
# ... (Bạn chỉ cần copy phần Flask từ file đã sửa trước đó)
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
    main_bots_info_list = [(bot_id, data) for bot_id, data in bot_manager.get_main_bots_info()]
    main_bots_info = [{"id": int(bot_id.split('_')[1]), "name": get_bot_name(bot_id)} for bot_id, _ in main_bots_info_list]
    main_bots_info.sort(key=lambda x: x['id'])
    if "max_heart_thresholds" not in bot_states["auto_clan_drop"]:
        bot_states["auto_clan_drop"]["max_heart_thresholds"] = {}
    return render_template_string(HTML_TEMPLATE, servers=sorted(servers, key=lambda s: s.get('name', '')), main_bots_info=main_bots_info, auto_clan_drop=bot_states["auto_clan_drop"])

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
    max_thresholds = bot_states["auto_clan_drop"].setdefault('max_heart_thresholds', {})
    for key, value in data.get('heart_thresholds', {}).items():
        if isinstance(value, int): thresholds[key] = value
    for key, value in data.get('max_heart_thresholds', {}).items():
        if isinstance(value, int): max_thresholds[key] = value
    bot_states["auto_clan_drop"].update({'channel_id': data.get('channel_id', '').strip(), 'ktb_channel_id': data.get('ktb_channel_id', '').strip()})
    return jsonify({'status': 'success', 'message': '💾 Clan Drop settings updated.'})

@app.route("/api/add_server", methods=['POST'])
def api_add_server():
    name = request.json.get('name')
    if not name: return jsonify({'status': 'error', 'message': 'Tên server là bắt buộc.'}), 400
    new_server = {"id": f"server_{uuid.uuid4().hex}", "name": name, "spam_delay": 10}
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

def find_server(server_id): return next((s for s in servers if s.get('id') == server_id), None)

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
    server, node_str = find_server(data.get('server_id')), data.get('node')
    if not server or not node_str: return jsonify({'status': 'error', 'message': 'Yêu cầu không hợp lệ.'}), 400
    node, grab_key, threshold_key, max_threshold_key = str(node_str), f'auto_grab_enabled_{node_str}', f'heart_threshold_{node_str}', f'max_heart_threshold_{node_str}'
    server[grab_key] = not server.get(grab_key, False)
    server[threshold_key] = int(data.get('threshold', 50))
    server[max_threshold_key] = int(data.get('max_threshold', 99999))
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
    if not re.match(r"main_\d+", bot_id): return jsonify({'status': 'error', 'message': '❌ Invalid Bot ID Format.'}), 400
    settings = bot_states["reboot_settings"].get(bot_id)
    if not settings: return jsonify({'status': 'error', 'message': '❌ Invalid Bot ID.'}), 400
    settings.update({'enabled': not settings.get('enabled', False), 'delay': delay, 'failure_count': 0})
    if settings['enabled']:
        settings['next_reboot_time'] = time.time() + delay
        msg = f"🔄 Safe Auto-Reboot ENABLED cho {get_bot_name(bot_id)} (mỗi {delay}s)"
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
def api_save_settings(): save_settings(); return jsonify({'status': 'success', 'message': '💾 Settings saved.'})

@app.route("/status")
def status_endpoint():
    now = time.time()
    def get_bot_status_list(bot_info_list, type_prefix):
        status_list = []
        for bot_id, data in bot_info_list:
            failures = bot_states["health_stats"].get(bot_id, {}).get('consecutive_failures', 0)
            health_status = 'bad' if failures >= 3 else 'warning' if failures > 0 else 'good'
            status_list.append({
                "name": get_bot_name(bot_id), "status": data.get('instance') is not None, "reboot_id": bot_id,
                "is_active": bot_states["active"].get(bot_id, False), "type": type_prefix, "health_status": health_status,
                "is_rebooting": bot_manager.is_rebooting(bot_id)
            })
        return sorted(status_list, key=lambda x: int(x['reboot_id'].split('_')[1]))
    bot_statuses = {
        "main_bots": get_bot_status_list(bot_manager.get_main_bots_info(), "main"),
        "sub_accounts": get_bot_status_list(bot_manager.get_sub_bots_info(), "sub")
    }
    clan_settings = bot_states["auto_clan_drop"]
    clan_drop_status = {"enabled": clan_settings.get("enabled", False), "countdown": (clan_settings.get("last_cycle_start_time", 0) + clan_settings.get("cycle_interval", 1800) - now) if clan_settings.get("enabled") else 0}
    reboot_settings_copy = bot_states["reboot_settings"].copy()
    for bot_id, settings in reboot_settings_copy.items():
        settings['countdown'] = max(0, settings.get('next_reboot_time', 0) - now) if settings.get('enabled') else 0
    for server in servers: server['spam_countdown'] = 0
    return jsonify({'bot_reboot_settings': reboot_settings_copy, 'bot_statuses': bot_statuses, 'server_start_time': server_start_time, 'servers': servers, 'watermelon_grab_states': bot_states["watermelon_grab"], 'auto_clan_drop_status': clan_drop_status})

# --- MAIN EXECUTION (VIẾT LẠI HOÀN TOÀN) ---
if __name__ == "__main__":
    print("🚀 Shadow Network Control - discord.py-self Stable Version Starting...", flush=True)
    load_settings()

    print("🔌 Initializing bots...", flush=True)
    bot_threads = []

    # Khởi tạo bot chính
    for i, token in enumerate(t for t in main_tokens if t.strip()):
        bot_num = i + 1
        bot_id = f"main_{bot_num}"
        thread = threading.Thread(target=initialize_and_run_bot, args=(token.strip(), bot_id, True), daemon=True)
        bot_threads.append(thread)
        bot_states["active"].setdefault(bot_id, True)
        bot_states["watermelon_grab"].setdefault(bot_id, False)
        bot_states["auto_clan_drop"]["heart_thresholds"].setdefault(bot_id, 50)
        bot_states["auto_clan_drop"].setdefault("max_heart_thresholds", {}).setdefault(bot_id, 99999)
        bot_states["reboot_settings"].setdefault(bot_id, {'enabled': False, 'delay': 3600, 'next_reboot_time': 0, 'failure_count': 0})
        bot_states["health_stats"].setdefault(bot_id, {'consecutive_failures': 0})

    # Khởi tạo bot phụ
    for i, token in enumerate(t for t in tokens if t.strip()):
        bot_id = f"sub_{i}"
        thread = threading.Thread(target=initialize_and_run_bot, args=(token.strip(), bot_id, False), daemon=True)
        bot_threads.append(thread)
        bot_states["active"].setdefault(bot_id, True)
        bot_states["health_stats"].setdefault(bot_id, {'consecutive_failures': 0})

    # Khởi động các luồng bot
    for t in bot_threads:
        t.start()
        time.sleep(2) # Rải đều thời gian khởi động để tránh rate limit

    print("🔧 Starting background threads...", flush=True)
    threading.Thread(target=periodic_task, args=(1800, save_settings, "Save"), daemon=True).start()
    threading.Thread(target=periodic_task, args=(300, health_monitoring_check, "Health"), daemon=True).start()
    
    start_optimized_spam_system(mode="optimized") 
    
    threading.Thread(target=auto_reboot_loop, daemon=True).start()
    threading.Thread(target=auto_clan_drop_loop, daemon=True).start()
    
    port = int(os.environ.get("PORT", 10000))
    print(f"🌐 Web Server running at http://0.0.0.0:{port}", flush=True)
    app.run(host=f"0.0.0.0", port=port, debug=False, use_reloader=False)
