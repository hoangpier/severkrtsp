# PHIÊN BẢN CHUYỂN ĐỔI SANG DISCORD.PY-SELF - TÍCH HỢP LẠI SPAM ĐA LUỒNG - ĐÃ SỬA LỖI
import discord, asyncio, threading, time, os, re, requests, json, random, traceback, uuid
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
    "auto_clan_drop": {"enabled": False, "channel_id": "", "ktb_channel_id": "", "last_cycle_start_time": 0, "cycle_interval": 1800, "bot_delay": 140, "heart_thresholds": {}, "max_heart_thresholds": {}}
}
stop_events = {"reboot": threading.Event(), "clan_drop": threading.Event()}
server_start_time = time.time()

# --- QUẢN LÍ BOT THREAD-SAFE (Cải tiến cho Async) ---
class ThreadSafeBotManager:
    def __init__(self):
        self._bots = {}
        self._rebooting = set()
        self._lock = threading.RLock()

    def add_bot(self, bot_id, bot_data):
        with self._lock:
            self._bots[bot_id] = bot_data
            print(f"[Bot Manager] ✅ Added bot {bot_id}", flush=True)

    def remove_bot(self, bot_id):
        with self._lock:
            bot_data = self._bots.pop(bot_id, None)
            if bot_data and bot_data.get('instance'):
                bot = bot_data['instance']
                loop = bot_data['loop']
                if loop.is_running():
                    asyncio.run_coroutine_threadsafe(bot.close(), loop)
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

# --- HÀM GỬI LỆNH ASYNC TỪ LUỒNG ĐỒNG BỘ ---
def send_message_from_sync(bot_id, channel_id, content):
    bot_data = bot_manager.get_bot_data(bot_id)
    if not bot_data: return
    
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
            # Ensure servers have unique IDs
            loaded_servers = settings.get('servers', [])
            for s in loaded_servers:
                if 'id' not in s:
                    s['id'] = str(uuid.uuid4())
            servers.extend(loaded_servers)
            
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

# --- LOGIC GRAB CARD (Chuyển đổi sang async) ---
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
                                ktb_channel = bot.get_channel(int(ktb_channel_id))
                                if ktb_channel: await ktb_channel.send("kt b")
                            print(f"[CARD GRAB | Bot {bot_num}] ✅ Đã grab và gửi kt b", flush=True)
                        except Exception as e:
                            print(f"[CARD GRAB | Bot {bot_num}] ❌ Lỗi grab: {e}", flush=True)

                    await asyncio.sleep(delay)
                    asyncio.create_task(grab_action())
                    return True
            return False
        except Exception as e:
            print(f"[CARD GRAB | Bot {bot_num}] ❌ Lỗi đọc messages: {e}", flush=True)
    return False

# --- LOGIC BOT (Chuyển đổi sang async) ---
async def handle_clan_drop(bot, msg, bot_num):
    clan_settings = bot_states["auto_clan_drop"]
    if not (clan_settings.get("enabled") and msg.channel.id == int(clan_settings.get("channel_id", 0))):
        return
    bot_id_str = f'main_{bot_num}'
    threshold = clan_settings.get("heart_thresholds", {}).get(bot_id_str, 50)
    max_threshold = clan_settings.get("max_heart_thresholds", {}).get(bot_id_str, 99999)
    asyncio.create_task(_find_and_select_card(bot, clan_settings["channel_id"], msg.id, threshold, bot_num, clan_settings["ktb_channel_id"], max_threshold))

# --- START: LOGIC NHẶT DƯA ĐÃ SỬA ---
async def handle_grab(bot, msg, bot_num):
    """
    Xử lý việc nhặt thẻ và dưa hấu từ drop của Karuta.
    Phiên bản này được tối ưu cho discord.py-self với khả năng xử lý lỗi mạnh mẽ.
    """
    try:
        channel_id = msg.channel.id
        # Tìm cấu hình server tương ứng với kênh hiện tại
        target_server = next((s for s in servers if s.get('main_channel_id') == str(channel_id)), None)
        if not target_server:
            return

        bot_id_str = f'main_{bot_num}'
        auto_grab_enabled = target_server.get(f'auto_grab_enabled_{bot_num}', False)
        watermelon_grab_enabled = bot_states.get("watermelon_grab", {}).get(bot_id_str, False)

        # Thoát nếu không có tính năng nào được bật cho bot này
        if not auto_grab_enabled and not watermelon_grab_enabled:
            return

        # --- LOGIC NHẶT THẺ (Bất đồng bộ) ---
        if auto_grab_enabled and target_server.get('ktb_channel_id'):
            threshold = target_server.get(f'heart_threshold_{bot_num}', 50)
            max_threshold = target_server.get(f'max_heart_threshold_{bot_num}', 99999)
            # Tạo một task chạy song song để tìm và chọn thẻ mà không làm block code chính
            asyncio.create_task(_find_and_select_card(
                bot, str(channel_id), msg.id, threshold, bot_num, target_server.get('ktb_channel_id'), max_threshold
            ))

        # --- LOGIC NHẶT DƯA HẤU (Bất đồng bộ với Timeout và Thử lại) ---
        if watermelon_grab_enabled:
            # Tạo một task chạy song song để kiểm tra và nhặt dưa
            asyncio.create_task(check_and_grab_watermelon(msg, bot_num))

    except Exception as e:
        print(f"[HANDLE_GRAB | Bot {bot_num}] ❌ Đã xảy ra lỗi không mong muốn: {e}\n{traceback.format_exc()}", flush=True)


async def check_and_grab_watermelon(msg, bot_num, wait_time=5, total_timeout=10):
    """
    Chờ một khoảng thời gian ngắn, sau đó lấy lại tin nhắn để kiểm tra reaction dưa hấu,
    và tự thêm reaction nếu tìm thấy.
    
    Args:
        msg (discord.Message): Tin nhắn drop ban đầu.
        bot_num (int): Số thứ tự của bot.
        wait_time (int): Thời gian chờ (giây) để reaction xuất hiện.
        total_timeout (int): Tổng thời gian tối đa (giây) cho toàn bộ tác vụ.
    """
    task_start_time = time.time()
    print(f"[WATERMELON | Bot {bot_num}] 🍉 Bắt đầu canh dưa (chờ tối đa {wait_time}s)...", flush=True)

    try:
        # Chờ để các reaction khác xuất hiện
        await asyncio.sleep(wait_time)

        # Lấy lại tin nhắn đã cập nhật với logic thử lại
        target_message = None
        # Vòng lặp thử lại cho đến khi hết thời gian timeout
        while time.time() - task_start_time < total_timeout:
            try:
                target_message = await msg.channel.fetch_message(msg.id)
                break  # Thành công, thoát khỏi vòng lặp thử lại
            except discord.NotFound:
                print(f"[WATERMELON | Bot {bot_num}] ⚠️ Không tìm thấy tin nhắn, có thể đã bị xóa.", flush=True)
                return  # Tin nhắn đã biến mất, không cần thử lại
            except discord.HTTPException as e:
                print(f"[WATERMELON | Bot {bot_num}] ⚠️ Lỗi HTTP khi lấy tin nhắn, đang thử lại... (Status: {e.status})", flush=True)
                await asyncio.sleep(0.5)  # Chờ một chút trước khi thử lại
            except Exception as e:
                print(f"[WATERMELON | Bot {bot_num}] ❌ Lỗi không xác định khi lấy tin nhắn: {e}", flush=True)
                return

        if not target_message:
            print(f"[WATERMELON | Bot {bot_num}] ❌ Không thể lấy tin nhắn sau nhiều lần thử.", flush=True)
            return

        # Kiểm tra tất cả reaction trên tin nhắn
        watermelon_found = False
        for reaction in target_message.reactions:
            try:
                emoji_str = str(reaction.emoji)
                # getattr là cách an toàn để lấy '.name' chỉ có ở custom emoji
                emoji_name = getattr(reaction.emoji, 'name', '').lower()
                
                watermelon_patterns = ['🍉', 'watermelon', 'dua', '🍈']
                
                if any(pattern in emoji_str or pattern in emoji_name for pattern in watermelon_patterns):
                    print(f"[WATERMELON | Bot {bot_num}] 🎯 Phát hiện dưa: {emoji_str}", flush=True)
                    watermelon_found = True
                    
                    # Thử thêm reaction với logic retry
                    for attempt in range(2):
                        try:
                            await target_message.add_reaction("🍉")
                            print(f"[WATERMELON | Bot {bot_num}] ✅ Nhặt dưa thành công!", flush=True)
                            return  # Thoát sau khi nhặt thành công
                        except discord.Forbidden:
                            print(f"[WATERMELON | Bot {bot_num}] ❌ Không có quyền thêm reaction.", flush=True)
                            return  # Không cần thử lại nếu không có quyền
                        except discord.HTTPException as e:
                            print(f"[WATERMELON | Bot {bot_num}] ⚠️ Lỗi khi react (lần {attempt + 1}/2): Status {e.status}", flush=True)
                            await asyncio.sleep(0.5)
                    
                    print(f"[WATERMELON | Bot {bot_num}] ❌ Không thể react sau 2 lần thử.", flush=True)
                    return # Dừng lại sau khi đã thử react nhưng thất bại

            except Exception as e:
                print(f"[WATERMELON | Bot {bot_num}] ⚠️ Lỗi khi xử lý một reaction: {e}", flush=True)
                continue # Bỏ qua reaction lỗi và tiếp tục với cái tiếp theo

        if not watermelon_found:
            print(f"[WATERMELON | Bot {bot_num}] 😞 Không tìm thấy reaction dưa hấu sau khi chờ.", flush=True)

    except asyncio.CancelledError:
        print(f"[WATERMELON | Bot {bot_num}] ⏱️ Tác vụ canh dưa đã bị hủy.", flush=True)
    except Exception as e:
        print(f"[WATERMELON | Bot {bot_num}] ❌ Lỗi không mong muốn trong tác vụ canh dưa: {e}\n{traceback.format_exc()}", flush=True)
# --- END: LOGIC NHẶT DƯA ĐÃ SỬA ---


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
        if old_bot_data and old_bot_data.get('thread'):
             old_bot_data['thread'].join(timeout=15) # Chờ luồng cũ kết thúc

        settings = bot_states["reboot_settings"].get(bot_id, {})
        failure_count = settings.get('failure_count', 0)
        wait_time = random.uniform(20, 40) + min(failure_count * 30, 300)
        
        print(f"[Safe Reboot] ⏳ Chờ {wait_time:.1f}s để cleanup...", flush=True)
        time.sleep(wait_time)

        print(f"[Safe Reboot] 🔧 Creating new bot thread for {bot_name}", flush=True)
        new_bot_is_ready = threading.Event()
        new_thread = threading.Thread(target=initialize_and_run_bot, args=(token, bot_id, True, new_bot_is_ready), daemon=True)
        new_thread.start()

        # Chờ bot mới sẵn sàng với timeout
        ready_in_time = new_bot_is_ready.wait(timeout=60)
        if not ready_in_time:
            raise Exception("Bot mới không sẵn sàng trong 60 giây.")

        # Thêm bot thread mới vào manager sau khi nó đã khởi động
        new_bot_data = bot_manager.get_bot_data(bot_id)
        if not new_bot_data:
            raise Exception("Không tìm thấy dữ liệu bot mới trong manager sau khi khởi động.")
        new_bot_data['thread'] = new_thread
        
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
        bot_manager.end_reboot(bot_id)

# --- VÒNG LẶP NỀN (Cập nhật cho async) ---
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

            bot_to_reboot = None
            highest_priority = -1

            main_bots_info = bot_manager.get_main_bots_info()
            for bot_id, bot_data in main_bots_info:
                settings = bot_states["reboot_settings"].setdefault(bot_id, {'delay': 3600, 'enabled': True})
                if not settings.get('enabled', True): continue

                next_reboot = settings.get('next_reboot_time', 0)
                if now >= next_reboot:
                    priority = (now - next_reboot) + settings.get('failure_count', 0) * 1000
                    if priority > highest_priority:
                        highest_priority = priority
                        bot_to_reboot = bot_id
            
            if bot_to_reboot:
                if safe_reboot_bot(bot_to_reboot):
                    last_global_reboot_time = time.time()
                    consecutive_system_failures = 0
                else:
                    consecutive_system_failures += 1
                    if consecutive_system_failures >= 3:
                        print("[Safe Reboot] 🛑 Dừng hệ thống reboot 10 phút do 3 lần thất bại liên tiếp.", flush=True)
                        stop_events["reboot"].wait(600)
                        consecutive_system_failures = 0
            
            stop_events["reboot"].wait(60)
        except Exception as e:
            print(f"[Safe Reboot] ❌ Lỗi nghiêm trọng trong reboot loop: {e}", flush=True)
            stop_events["reboot"].wait(300)

def health_monitoring_check():
    main_bots_info = bot_manager.get_main_bots_info()
    for bot_id, bot_data in main_bots_info:
        if not check_bot_health(bot_data, bot_id):
            stats = bot_states["health_stats"].get(bot_id, {})
            if stats.get('consecutive_failures', 0) >= 3:
                print(f"[Health Check] 🚨 Bot {bot_id} mất kết nối 3 lần, kích hoạt reboot sớm.", flush=True)
                settings = bot_states["reboot_settings"].setdefault(bot_id, {})
                settings['next_reboot_time'] = time.time() - 1 

def auto_clan_drop_loop():
    print("[Clan Drop] 🚀 Khởi động luồng tự động clan drop.", flush=True)
    while not stop_events["clan_drop"].is_set():
        try:
            clan_settings = bot_states["auto_clan_drop"]
            if not clan_settings.get("enabled", False):
                stop_events["clan_drop"].wait(10)
                continue

            now = time.time()
            last_start = clan_settings.get("last_cycle_start_time", 0)
            interval = clan_settings.get("cycle_interval", 1800)
            
            if now - last_start < interval:
                stop_events["clan_drop"].wait(10)
                continue

            clan_settings["last_cycle_start_time"] = now
            print(f"[Clan Drop] ▶️ Bắt đầu chu kỳ clan drop mới lúc {datetime.now()}", flush=True)
            
            main_bots_info = bot_manager.get_main_bots_info()
            active_main_bots = [bot_id for bot_id, _ in main_bots_info if bot_states.get("active", {}).get(bot_id, True)]
            
            if not active_main_bots:
                print("[Clan Drop] ⚠️ Không có bot chính nào hoạt động để thực hiện clan drop.", flush=True)
                continue

            channel_id = clan_settings.get("channel_id")
            if not channel_id:
                print("[Clan Drop] ⚠️ Channel ID cho clan drop chưa được cài đặt.", flush=True)
                continue

            bot_delay = clan_settings.get("bot_delay", 140)
            
            for i, bot_id in enumerate(active_main_bots):
                if stop_events["clan_drop"].is_set():
                    print("[Clan Drop] ⏹️ Chu kỳ bị dừng sớm.", flush=True)
                    break
                
                print(f"[Clan Drop] -> Bot {get_bot_name(bot_id)} đang drop...", flush=True)
                send_message_from_sync(bot_id, channel_id, "kcd")
                
                if i < len(active_main_bots) - 1:
                    stop_events["clan_drop"].wait(bot_delay)

            print(f"[Clan Drop] ✅ Hoàn thành chu kỳ. Chu kỳ tiếp theo sau {interval/60:.1f} phút.", flush=True)

        except Exception as e:
            print(f"[Clan Drop] ❌ Lỗi nghiêm trọng trong clan drop loop: {e}", flush=True)
            stop_events["clan_drop"].wait(300)

def periodic_task(interval, func, name):
    while True:
        time.sleep(interval)
        try:
            func()
        except Exception as e:
            print(f"Error in periodic task '{name}': {e}", flush=True)

# --- FLASK WEB SERVER ---
app = Flask(__name__)

@app.route('/')
def index():
    return render_template_string("""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Bot Control Panel</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <link rel="preconnect" href="https://fonts.googleapis.com">
        <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
        <style>
            body { font-family: 'Inter', sans-serif; }
            .status-dot { height: 10px; width: 10px; border-radius: 50%; display: inline-block; }
            .bg-green-500 { background-color: #22c55e; }
            .bg-red-500 { background-color: #ef4444; }
            .bg-yellow-500 { background-color: #eab308; }
            .bg-gray-400 { background-color: #9ca3af; }
            .toast {
                position: fixed; top: 20px; right: 20px; background-color: #22c55e; color: white;
                padding: 1rem; border-radius: 0.5rem; z-index: 1000;
                opacity: 0; transition: opacity 0.5s, transform 0.5s;
                transform: translateY(-20px);
            }
            .toast.show { opacity: 1; transform: translateY(0); }
            .toast.error { background-color: #ef4444; }
            .btn {
                padding: 0.5rem 1rem;
                border-radius: 0.375rem;
                font-weight: 500;
                transition: background-color 0.2s;
                cursor: pointer;
            }
            .btn-primary { background-color: #2563eb; color: white; }
            .btn-primary:hover { background-color: #1d4ed8; }
            .btn-secondary { background-color: #4b5563; color: white; }
            .btn-secondary:hover { background-color: #374151; }
            .btn-danger { background-color: #dc2626; color: white; }
            .btn-danger:hover { background-color: #b91c1c; }
            .btn-success { background-color: #16a34a; color: white; }
            .btn-success:hover { background-color: #15803d; }
            .input-field {
                background-color: #374151;
                border: 1px solid #4b5563;
                color: white;
                padding: 0.5rem;
                border-radius: 0.375rem;
            }
        </style>
    </head>
    <body class="bg-gray-900 text-white p-4 md:p-8">
        <div class="max-w-7xl mx-auto">
            <h1 class="text-3xl font-bold mb-6 text-cyan-400">Bot Control Panel</h1>
            <div id="toast" class="toast"></div>
            
            <!-- System Info & Global Actions -->
            <div class="bg-gray-800 p-4 rounded-lg mb-6">
                <h2 class="text-xl font-semibold mb-3 text-cyan-300">System Information</h2>
                <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
                    <div><strong>Status:</strong> <span id="system-status" class="text-green-400">Running</span></div>
                    <div><strong>Uptime:</strong> <span id="uptime">--:--:--</span></div>
                    <div><strong>Total Bots:</strong> <span id="total-bots">0</span></div>
                    <div><strong>Last Save:</strong> <span id="last-save">Never</span></div>
                </div>
                <div class="mt-4 flex gap-2">
                    <button onclick="saveAllSettings()" class="btn btn-primary">Save All Settings</button>
                </div>
            </div>

            <!-- Server Management -->
            <div class="bg-gray-800 p-4 rounded-lg mb-6">
                <h2 class="text-xl font-semibold mb-3 text-cyan-300">Server Management</h2>
                <div id="server-list" class="space-y-4"></div>
                <div class="mt-4">
                    <h3 class="font-semibold mb-2">Add New Server</h3>
                    <div class="flex flex-wrap gap-2 items-center">
                        <input type="text" id="new-server-name" placeholder="Server Name" class="input-field">
                        <input type="text" id="new-main-channel-id" placeholder="Main Channel ID" class="input-field">
                        <input type="text" id="new-ktb-channel-id" placeholder="KTB Channel ID" class="input-field">
                        <button onclick="addServer()" class="btn btn-success">Add Server</button>
                    </div>
                </div>
            </div>

            <!-- Clan Drop Management -->
            <div class="bg-gray-800 p-4 rounded-lg mb-6">
                <h2 class="text-xl font-semibold mb-3 text-cyan-300">Auto Clan Drop</h2>
                <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                        <label class="flex items-center gap-2 cursor-pointer">
                            <input type="checkbox" id="clan-drop-enabled" onchange="updateClanDropSettings()" class="w-4 h-4 text-blue-600 bg-gray-700 border-gray-600 rounded focus:ring-blue-600 ring-offset-gray-800 focus:ring-2">
                            Enable Auto Clan Drop
                        </label>
                        <p class="text-sm text-gray-400 mt-1">Next cycle starts around: <span id="clan-drop-next-cycle">--:--</span></p>
                    </div>
                    <div class="grid grid-cols-1 sm:grid-cols-2 gap-2">
                         <input type="text" id="clan-drop-channel-id" placeholder="Clan Drop Channel ID" class="input-field" onchange="updateClanDropSettings()">
                         <input type="text" id="clan-drop-ktb-channel-id" placeholder="KTB Channel ID" class="input-field" onchange="updateClanDropSettings()">
                         <input type="number" id="clan-drop-cycle-interval" placeholder="Cycle Interval (s)" class="input-field" onchange="updateClanDropSettings()">
                         <input type="number" id="clan-drop-bot-delay" placeholder="Delay Between Bots (s)" class="input-field" onchange="updateClanDropSettings()">
                    </div>
                </div>
                 <div class="mt-4">
                    <h3 class="font-semibold mb-2">Heart Thresholds for Clan Drop</h3>
                    <div id="clan-drop-thresholds" class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-2"></div>
                </div>
            </div>
            
            <!-- Bot Status & Control -->
            <div class="bg-gray-800 p-4 rounded-lg">
                <h2 class="text-xl font-semibold mb-3 text-cyan-300">Bot Control</h2>
                <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
                    <div>
                        <h3 class="font-semibold mb-2 text-cyan-200">Main Bots (<span id="main-bot-count">0</span>)</h3>
                        <div id="main-bot-list" class="space-y-3"></div>
                    </div>
                    <div>
                        <h3 class="font-semibold mb-2 text-cyan-200">Sub Bots (<span id="sub-bot-count">0</span>)</h3>
                        <div id="sub-bot-list" class="space-y-3"></div>
                    </div>
                </div>
            </div>
        </div>
        
        <script>
            // --- START: JAVASCRIPT ĐẦY ĐỦ ---
            let ALL_BOTS_INFO = [];

            function showToast(message, isError = false) {
                const toast = document.getElementById('toast');
                toast.textContent = message;
                toast.className = 'toast show' + (isError ? ' error' : '');
                setTimeout(() => {
                    toast.className = 'toast';
                }, 3000);
            }

            async function postUpdate(payload) {
                try {
                    const response = await fetch('/update', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(payload)
                    });
                    const data = await response.json();
                    if (data.success) {
                        showToast(data.message || 'Action successful!');
                        fetchStatus(); // Refresh data after a successful action
                    } else {
                        showToast(data.message || 'An error occurred.', true);
                    }
                    return data;
                } catch (error) {
                    showToast('Failed to communicate with the server.', true);
                    console.error('Update error:', error);
                }
            }

            function formatUptime(seconds) {
                const d = Math.floor(seconds / (3600*24));
                const h = Math.floor(seconds % (3600*24) / 3600);
                const m = Math.floor(seconds % 3600 / 60);
                const s = Math.floor(seconds % 60);
                return `${d > 0 ? d + 'd ' : ''}${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
            }
            
            function formatTimestamp(ts) {
                if (!ts || ts === 0) return 'Never';
                return new Date(ts * 1000).toLocaleString();
            }

            function renderServers(servers) {
                const list = document.getElementById('server-list');
                if (!servers || servers.length === 0) {
                    list.innerHTML = '<p class="text-gray-400">No servers configured.</p>';
                    return;
                }
                list.innerHTML = servers.map(server => {
                    const botSettingsHTML = ALL_BOTS_INFO.map(bot => `
                        <div class="flex items-center gap-2">
                            <label class="flex-1 text-sm">${bot.name}</label>
                            <input type="number" value="${server[`heart_threshold_${bot.id.split('_')[1]}`] || 50}" onchange="updateServer('${server.id}')" data-bot-num="${bot.id.split('_')[1]}" data-field="heart_threshold" class="input-field w-20" placeholder="Min ♡">
                            <input type="number" value="${server[`max_heart_threshold_${bot.id.split('_')[1]}`] || 99999}" onchange="updateServer('${server.id}')" data-bot-num="${bot.id.split('_')[1]}" data-field="max_heart_threshold" class="input-field w-20" placeholder="Max ♡">
                            <label class="flex items-center gap-1 cursor-pointer">
                                <input type="checkbox" ${server[`auto_grab_enabled_${bot.id.split('_')[1]}`] ? 'checked' : ''} onchange="updateServer('${server.id}')" data-bot-num="${bot.id.split('_')[1]}" data-field="auto_grab_enabled" class="w-4 h-4 text-blue-600 bg-gray-700 border-gray-600 rounded">
                                <span class="text-sm">Grab</span>
                            </label>
                        </div>
                    `).join('');

                    return `
                        <div class="bg-gray-700 p-3 rounded-lg" id="server-${server.id}">
                            <div class="flex justify-between items-center mb-2">
                                <input type="text" value="${server.name}" onchange="updateServer('${server.id}')" data-field="name" class="input-field font-semibold text-lg bg-transparent border-0 p-1">
                                <button onclick="deleteServer('${server.id}')" class="btn btn-danger text-xs">Delete</button>
                            </div>
                            <div class="grid grid-cols-1 md:grid-cols-2 gap-2 text-sm">
                                <div><strong>Main Channel:</strong> <input type="text" value="${server.main_channel_id}" onchange="updateServer('${server.id}')" data-field="main_channel_id" class="input-field w-full"></div>
                                <div><strong>KTB Channel:</strong> <input type="text" value="${server.ktb_channel_id}" onchange="updateServer('${server.id}')" data-field="ktb_channel_id" class="input-field w-full"></div>
                            </div>
                            <div class="mt-3">
                                <h4 class="font-semibold text-sm mb-2">Bot Grab Settings</h4>
                                <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
                                    ${botSettingsHTML}
                                </div>
                            </div>
                        </div>
                    `;
                }).join('');
            }

            function renderMainBots(bots) {
                const list = document.getElementById('main-bot-list');
                document.getElementById('main-bot-count').textContent = bots.length;
                list.innerHTML = bots.map(bot => {
                    const statusColor = bot.is_rebooting ? 'yellow' : (bot.is_ready ? 'green' : 'red');
                    const nextReboot = bot.reboot_enabled ? `Next in ${formatUptime(bot.next_reboot_time - Date.now()/1000)}` : 'Disabled';
                    return `
                        <div class="bg-gray-700 p-3 rounded-lg">
                            <div class="flex justify-between items-center">
                                <div class="flex items-center gap-2">
                                    <span class="status-dot bg-${statusColor}-500"></span>
                                    <strong class="text-cyan-400">${bot.name}</strong>
                                    ${bot.failures > 0 ? `<span class="text-xs bg-red-600 px-1.5 py-0.5 rounded-full">${bot.failures} fails</span>` : ''}
                                </div>
                                <div class="flex items-center gap-2">
                                    <button onclick="rebootBot('${bot.id}')" class="btn btn-secondary text-xs" ${bot.is_rebooting ? 'disabled' : ''}>Reboot</button>
                                    <label class="flex items-center gap-1 cursor-pointer">
                                        <input type="checkbox" onchange="toggleBot('${bot.id}')" ${bot.active ? 'checked' : ''}>
                                        <span class="text-sm">Active</span>
                                    </label>
                                    <label class="flex items-center gap-1 cursor-pointer">
                                        <input type="checkbox" onchange="toggleWatermelon('${bot.id}')" ${bot.watermelon_grab ? 'checked' : ''}>
                                        <span class="text-sm">🍉</span>
                                    </label>
                                </div>
                            </div>
                            <div class="text-xs text-gray-400 mt-2">
                                <p>Auto Reboot: ${nextReboot} (Delay: ${bot.reboot_delay}s)</p>
                            </div>
                        </div>
                    `;
                }).join('');
            }
            
            function renderSubBots(bots) {
                const list = document.getElementById('sub-bot-list');
                document.getElementById('sub-bot-count').textContent = bots.length;
                list.innerHTML = bots.map(bot => {
                    const statusColor = bot.is_ready ? 'green' : 'red';
                    return `
                        <div class="bg-gray-700 p-3 rounded-lg">
                            <div class="flex justify-between items-center">
                                <div class="flex items-center gap-2">
                                    <span class="status-dot bg-${statusColor}-500"></span>
                                    <strong>${bot.name}</strong>
                                </div>
                                <label class="flex items-center gap-1 cursor-pointer">
                                    <input type="checkbox" onchange="toggleBot('${bot.id}')" ${bot.active ? 'checked' : ''}>
                                    <span class="text-sm">Active</span>
                                </label>
                            </div>
                        </div>
                    `;
                }).join('');
            }

            function renderClanDropSettings(settings, mainBots) {
                document.getElementById('clan-drop-enabled').checked = settings.enabled;
                document.getElementById('clan-drop-channel-id').value = settings.channel_id || '';
                document.getElementById('clan-drop-ktb-channel-id').value = settings.ktb_channel_id || '';
                document.getElementById('clan-drop-cycle-interval').value = settings.cycle_interval || 1800;
                document.getElementById('clan-drop-bot-delay').value = settings.bot_delay || 140;

                const nextCycleTime = (settings.last_cycle_start_time + settings.cycle_interval) - Date.now() / 1000;
                document.getElementById('clan-drop-next-cycle').textContent = settings.enabled && nextCycleTime > 0 ? formatUptime(nextCycleTime) : 'N/A';

                const thresholdsContainer = document.getElementById('clan-drop-thresholds');
                thresholdsContainer.innerHTML = mainBots.map(bot => `
                    <div class="flex items-center gap-2 bg-gray-700 p-2 rounded">
                        <label class="flex-1 text-sm text-cyan-400">${bot.name}</label>
                        <input type="number" value="${settings.heart_thresholds[bot.id] || 50}" onchange="updateClanDropSettings()" data-bot-id="${bot.id}" data-field="heart_thresholds" class="input-field w-20" placeholder="Min ♡">
                        <input type="number" value="${settings.max_heart_thresholds[bot.id] || 99999}" onchange="updateClanDropSettings()" data-bot-id="${bot.id}" data-field="max_heart_thresholds" class="input-field w-20" placeholder="Max ♡">
                    </div>
                `).join('');
            }

            async function fetchStatus() {
                try {
                    const response = await fetch('/status');
                    const data = await response.json();
                    
                    ALL_BOTS_INFO = data.main_bots.map(b => ({id: b.id, name: b.name}));

                    document.getElementById('uptime').textContent = formatUptime(data.uptime);
                    document.getElementById('last-save').textContent = formatTimestamp(data.last_save);
                    document.getElementById('total-bots').textContent = data.main_bots.length + data.sub_bots.length;
                    
                    renderServers(data.servers);
                    renderMainBots(data.main_bots);
                    renderSubBots(data.sub_bots);
                    renderClanDropSettings(data.clan_drop, data.main_bots);

                } catch (error) {
                    console.error('Failed to fetch status:', error);
                    document.getElementById('system-status').textContent = 'Error';
                    document.getElementById('system-status').classList.remove('text-green-400');
                    document.getElementById('system-status').classList.add('text-red-400');
                }
            }
            
            // --- Action Functions ---
            function saveAllSettings() { postUpdate({ action: 'save_settings' }); }
            function toggleBot(bot_id) { postUpdate({ action: 'toggle_bot', bot_id }); }
            function toggleWatermelon(bot_id) { postUpdate({ action: 'toggle_watermelon', bot_id }); }
            function rebootBot(bot_id) { postUpdate({ action: 'reboot_bot', bot_id }); }
            function deleteServer(server_id) { 
                if (confirm('Are you sure you want to delete this server?')) {
                    postUpdate({ action: 'delete_server', server_id }); 
                }
            }

            function addServer() {
                const name = document.getElementById('new-server-name').value;
                const main_channel_id = document.getElementById('new-main-channel-id').value;
                const ktb_channel_id = document.getElementById('new-ktb-channel-id').value;
                if (!name || !main_channel_id) {
                    showToast('Server Name and Main Channel ID are required.', true);
                    return;
                }
                const server = { name, main_channel_id, ktb_channel_id };
                postUpdate({ action: 'add_server', server });
                document.getElementById('new-server-name').value = '';
                document.getElementById('new-main-channel-id').value = '';
                document.getElementById('new-ktb-channel-id').value = '';
            }

            function updateServer(server_id) {
                const serverElement = document.getElementById(`server-${server_id}`);
                const server = { id: server_id };
                serverElement.querySelectorAll('input[data-field]').forEach(input => {
                    const field = input.dataset.field;
                    const botNum = input.dataset.botNum;
                    let value = input.type === 'checkbox' ? input.checked : (input.type === 'number' ? parseInt(input.value) : input.value);
                    
                    if (botNum) {
                        server[`${field}_${botNum}`] = value;
                    } else {
                        server[field] = value;
                    }
                });
                postUpdate({ action: 'update_server', server });
            }

            function updateClanDropSettings() {
                const settings = {
                    enabled: document.getElementById('clan-drop-enabled').checked,
                    channel_id: document.getElementById('clan-drop-channel-id').value,
                    ktb_channel_id: document.getElementById('clan-drop-ktb-channel-id').value,
                    cycle_interval: parseInt(document.getElementById('clan-drop-cycle-interval').value),
                    bot_delay: parseInt(document.getElementById('clan-drop-bot-delay').value),
                    heart_thresholds: {},
                    max_heart_thresholds: {}
                };
                document.getElementById('clan-drop-thresholds').querySelectorAll('input').forEach(input => {
                    const botId = input.dataset.botId;
                    const field = input.dataset.field;
                    settings[field][botId] = parseInt(input.value);
                });
                postUpdate({ action: 'update_clan_drop', settings });
            }

            // Initial load and periodic refresh
            document.addEventListener('DOMContentLoaded', () => {
                fetchStatus();
                setInterval(fetchStatus, 5000); // Refresh every 5 seconds
            });
            // --- END: JAVASCRIPT ĐẦY ĐỦ ---
        </script>
    </body>
    </html>
    """)

@app.route('/status')
def status():
    main_bots_data, sub_bots_data = [], []
    main_bots_info = bot_manager.get_main_bots_info()
    sub_bots_info = bot_manager.get_sub_bots_info()

    for bot_id, bot_data in main_bots_info:
        health = bot_states["health_stats"].get(bot_id, {})
        reboot_settings = bot_states["reboot_settings"].get(bot_id, {})
        main_bots_data.append({
            'id': bot_id,
            'name': get_bot_name(bot_id),
            'active': bot_states["active"].get(bot_id, True),
            'watermelon_grab': bot_states["watermelon_grab"].get(bot_id, False),
            'is_ready': bot_data['instance'].is_ready() if bot_data and bot_data.get('instance') else False,
            'is_rebooting': bot_manager.is_rebooting(bot_id),
            'failures': health.get('consecutive_failures', 0),
            'last_check': health.get('last_check', 0),
            'reboot_enabled': reboot_settings.get('enabled', True),
            'next_reboot_time': reboot_settings.get('next_reboot_time', 0),
            'reboot_delay': reboot_settings.get('delay', 3600),
            'reboot_failures': reboot_settings.get('failure_count', 0),
        })

    for bot_id, bot_data in sub_bots_info:
        sub_bots_data.append({
            'id': bot_id,
            'name': get_bot_name(bot_id),
            'active': bot_states["active"].get(bot_id, True),
            'is_ready': bot_data['instance'].is_ready() if bot_data and bot_data.get('instance') else False,
        })
    
    clan_drop_settings = bot_states["auto_clan_drop"]
    last_save = bot_states.get('last_save_time', 0)

    return jsonify({
        'servers': servers,
        'main_bots': main_bots_data,
        'sub_bots': sub_bots_data,
        'clan_drop': clan_drop_settings,
        'uptime': time.time() - server_start_time,
        'last_save': last_save
    })

@app.route('/update', methods=['POST'])
def update():
    data = request.json
    action = data.get('action')
    
    if action == 'toggle_bot':
        bot_id = data.get('bot_id')
        if bot_id:
            bot_states["active"][bot_id] = not bot_states["active"].get(bot_id, True)
            return jsonify(success=True, message=f"Toggled bot {bot_id}")

    elif action == 'toggle_watermelon':
        bot_id = data.get('bot_id')
        if bot_id:
            bot_states["watermelon_grab"][bot_id] = not bot_states["watermelon_grab"].get(bot_id, False)
            return jsonify(success=True, message=f"Toggled watermelon grab for {bot_id}")

    elif action == 'update_server':
        server_data = data.get('server')
        if server_data:
            for i, s in enumerate(servers):
                if s['id'] == server_data['id']:
                    servers[i].update(server_data)
                    break
            return jsonify(success=True, message="Server updated")

    elif action == 'add_server':
        server_data = data.get('server')
        if server_data:
            server_data['id'] = str(uuid.uuid4())
            servers.append(server_data)
            return jsonify(success=True, message="Server added", server=server_data)

    elif action == 'delete_server':
        server_id = data.get('server_id')
        if server_id:
            servers[:] = [s for s in servers if s['id'] != server_id]
            return jsonify(success=True, message="Server deleted")
            
    elif action == 'save_settings':
        save_settings()
        return jsonify(success=True, message="Settings saved")
        
    elif action == 'reboot_bot':
        bot_id = data.get('bot_id')
        if bot_id:
            threading.Thread(target=safe_reboot_bot, args=(bot_id,)).start()
            return jsonify(success=True, message=f"Reboot initiated for {bot_id}")

    elif action == 'update_reboot_settings':
        bot_id, delay, enabled = data.get('bot_id'), data.get('delay'), data.get('enabled')
        if bot_id:
            settings = bot_states["reboot_settings"].setdefault(bot_id, {})
            if delay is not None: settings['delay'] = int(delay)
            if enabled is not None: settings['enabled'] = bool(enabled)
            return jsonify(success=True, message=f"Reboot settings updated for {bot_id}")

    elif action == 'update_clan_drop':
        clan_settings = data.get('settings')
        if clan_settings:
            bot_states["auto_clan_drop"].update(clan_settings)
            if not clan_settings.get("enabled", False):
                stop_events["clan_drop"].set() # Dừng chu kỳ nếu bị tắt
            else:
                stop_events["clan_drop"].clear() # Cho phép chu kỳ chạy
            return jsonify(success=True, message="Clan drop settings updated")

    return jsonify(success=False, message="Invalid action")

# --- KHỞI TẠO VÀ CHẠY BOT (Cập nhật cho discord.py-self) ---
def initialize_and_run_bot(token, bot_id, is_main, ready_event=None):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    intents = discord.Intents.default()
    intents.messages = True
    intents.message_content = True 
    intents.guilds = True

    bot = discord.Client(intents=intents, self_bot=True)

    @bot.event
    async def on_ready():
        print(f"[Bot] ✅ {get_bot_name(bot_id)} ({bot.user.name}) is ready!", flush=True)
        bot_data = {'instance': bot, 'loop': loop, 'thread': threading.current_thread()}
        bot_manager.add_bot(bot_id, bot_data)
        if ready_event:
            ready_event.set()

    @bot.event
    async def on_message(msg):
        try:
            if not bot_states["active"].get(bot_id, True): return
            if not is_main: return
            
            bot_num_match = re.search(r'_(\d+)', bot_id)
            if not bot_num_match: return
            effective_bot_num = int(bot_num_match.group(1))

            if msg.author.id == int(karuta_id) and "dropping" in msg.content.lower():
                is_clan_drop = bool(msg.mentions)
                if is_clan_drop:
                    await handle_clan_drop(bot, msg, effective_bot_num)
                else:
                    await handle_grab(bot, msg, effective_bot_num)
        except Exception as e:
            print(f"[Bot] ❌ Error in on_message for {bot_id}: {e}\n{traceback.format_exc()}", flush=True)
    
    try:
        loop.run_until_complete(bot.start(token))
    except (discord.LoginFailure, discord.PrivilegedIntentsRequired) as e:
        print(f"[Bot] ❌ Login failed for {get_bot_name(bot_id)}: {e}. Disabling bot.", flush=True)
        bot_states["active"][bot_id] = False
        if bot_id.startswith("main_"):
            bot_states["reboot_settings"].setdefault(bot_id, {})['enabled'] = False
        if ready_event:
            ready_event.set() # Vẫn set để luồng reboot không bị kẹt
    except Exception as e:
        print(f"[Bot] ❌ An unexpected error occurred with {get_bot_name(bot_id)}: {e}", flush=True)
        if ready_event:
            ready_event.set()
    finally:
        print(f"[Bot] 🔌 Bot {get_bot_name(bot_id)} has disconnected.", flush=True)
        loop.close()

# --- HỆ THỐNG SPAM (Không đổi) ---
spam_configs = {}
spam_stop_events = {}
spam_threads = {}

def spam_worker(thread_id, stop_event):
    print(f"[Spam Worker {thread_id}] 🚀 Started.", flush=True)
    while not stop_event.is_set():
        try:
            active_configs = [(bot_id, cfg) for bot_id, cfg in spam_configs.items() if cfg['enabled'] and cfg.get('thread_id') == thread_id]
            if not active_configs:
                stop_event.wait(1)
                continue

            for bot_id, config in active_configs:
                if stop_event.is_set(): break
                now = time.time()
                if now - config.get('last_sent', 0) >= config['delay']:
                    send_message_from_sync(bot_id, config['channel_id'], config['message'])
                    config['last_sent'] = now
            
            time.sleep(0.1) # Giảm tải CPU
        except Exception as e:
            print(f"[Spam Worker {thread_id}] ❌ Error: {e}", flush=True)
            time.sleep(5)
    print(f"[Spam Worker {thread_id}] 🛑 Stopped.", flush=True)

def start_optimized_spam_system(mode="optimized"):
    num_threads = 4 if mode == "optimized" else 1
    print(f"[Spam System] 🚀 Starting in {mode} mode with {num_threads} worker threads.", flush=True)
    for i in range(num_threads):
        thread_id = i + 1
        stop_event = threading.Event()
        spam_stop_events[thread_id] = stop_event
        thread = threading.Thread(target=spam_worker, args=(thread_id, stop_event), daemon=True)
        spam_threads[thread_id] = thread
        thread.start()

# --- MAIN EXECUTION ---
if __name__ == "__main__":
    load_settings()
    
    bot_threads = []
    # Khởi tạo bot chính
    for i, token in enumerate(t for t in main_tokens if t.strip()):
        bot_id = f"main_{i+1}"
        thread = threading.Thread(target=initialize_and_run_bot, args=(token.strip(), bot_id, True), daemon=True)
        bot_threads.append(thread)
        bot_states["active"].setdefault(bot_id, True)
        bot_states["health_stats"].setdefault(bot_id, {'consecutive_failures': 0})
        bot_states["reboot_settings"].setdefault(bot_id, {'delay': 3600, 'enabled': True})

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
    
    # --- CHỈNH SỬA: Khởi động hệ thống spam có lựa chọn chế độ ---
    # Thay đổi mode="optimized" (4 luồng) hoặc mode="ultra" (1 luồng) tại đây
    start_optimized_spam_system(mode="optimized") 
    
    threading.Thread(target=auto_reboot_loop, daemon=True).start()
    threading.Thread(target=auto_clan_drop_loop, daemon=True).start()
    
    port = int(os.environ.get("PORT", 10000))
    print(f"🌐 Web Server running at http://0.0.0.0:{port}", flush=True)
    from waitress import serve
    serve(app, host="0.0.0.0", port=port)
