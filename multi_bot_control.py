# PHIÊN BẢN CHUYỂN ĐỔI SANG DISCORD.PY-SELF - BẢN THỬ NGHIỆM
import discord # THAY ĐỔI: Thư viện chính
import asyncio # THAY ĐỔI: Thư viện bất đồng bộ
import threading, time, os, re, requests, json, random, traceback, uuid
from flask import Flask, request, render_template_string, jsonify
from dotenv import load_dotenv
from datetime import datetime, timedelta

load_dotenv()

# --- CẤU HÌNH (Giữ nguyên) ---
main_tokens = os.getenv("MAIN_TOKENS", "").split(",")
tokens = os.getenv("TOKENS", "").split(",")
karuta_id, karibbit_id = "646937666251915264", "1311684840462225440"
BOT_NAMES = ["xsyx", "sofa", "dont", "ayaya", "owo", "astra", "singo", "dia pox", "clam", "rambo", "domixi", "dogi", "sicula", "mo turn", "jan taru", "kio sama"]
acc_names = [f"Bot-{i:02d}" for i in range(1, 21)]

# --- BIẾN TRẠNG THÁI & KHÓA (Thay đổi Lock) ---
servers = []
bot_states = {
    "reboot_settings": {}, "active": {}, "watermelon_grab": {}, "health_stats": {},
    "auto_clan_drop": {"enabled": False, "channel_id": "", "ktb_channel_id": "", "last_cycle_start_time": 0, "cycle_interval": 1800, "bot_delay": 140, "heart_thresholds": {}, "max_heart_thresholds": {}}
}
# THAY ĐỔI: Dùng asyncio Event thay vì threading Event
stop_events = {"reboot": asyncio.Event(), "clan_drop": asyncio.Event()}
server_start_time = time.time()
main_loop = None # THAY ĐỔI: Biến để giữ event loop chính

# --- QUẢN LÝ BOT (THAY ĐỔI SANG ASYNC) ---
class SafeBotManager:
    def __init__(self):
        self._bots = {}
        self._rebooting = set()
        self._lock = asyncio.Lock() # THAY ĐỔI: Dùng asyncio.Lock

    async def add_bot(self, bot_id, bot_instance):
        async with self._lock:
            self._bots[bot_id] = bot_instance
            print(f"[Bot Manager] ✅ Added bot {bot_id}", flush=True)

    async def remove_bot(self, bot_id):
        async with self._lock:
            bot = self._bots.pop(bot_id, None)
            if bot:
                try:
                    if not bot.is_closed():
                        # THAY ĐỔI: Đóng client bất đồng bộ
                        await bot.close() 
                except Exception as e:
                    print(f"[Bot Manager] ⚠️ Error closing client for {bot_id}: {e}", flush=True)
                print(f"[Bot Manager] 🗑️ Removed bot {bot_id}", flush=True)
    
    async def get_bot(self, bot_id):
        async with self._lock:
            return self._bots.get(bot_id)

    async def get_all_bots(self):
        async with self._lock:
            return list(self._bots.items())
            
    # ... Các hàm khác giữ nguyên logic nhưng có thể cần async nếu truy cập _bots ...
    def is_rebooting(self, bot_id):
        return bot_id in self._rebooting

    def start_reboot(self, bot_id):
        if self.is_rebooting(bot_id): return False
        self._rebooting.add(bot_id)
        return True

    def end_reboot(self, bot_id):
        self._rebooting.discard(bot_id)

bot_manager = SafeBotManager()

# --- LƯU & TẢI CÀI ĐẶT (Giữ nguyên, vì là I/O đồng bộ) ---
# ... (Toàn bộ các hàm save_settings và load_settings giữ nguyên) ...
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
            # Check if servers list is empty before extending
            if not servers:
                servers.extend(settings.get('servers', []))
            
            loaded_bot_states = settings.get('bot_states', {})
            for key, value in loaded_bot_states.items():
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
        return acc_names[b_index] if b_index < len(acc_names) else f"SUB_{b_index+1}"
    except (IndexError, ValueError):
        return bot_id_str.upper()

# --- KHỞI TẠO BOT (THAY ĐỔI HOÀN TOÀN) ---
async def create_bot(token, bot_identifier, is_main=False):
    bot_id_str = f"main_{bot_identifier}" if is_main else f"sub_{bot_identifier}"
    
    intents = discord.Intents.default()
    intents.messages = True
    intents.guilds = True
    
    client = discord.Client(intents=intents)

    @client.event
    async def on_ready():
        try:
            print(f"[Bot] ✅ Đăng nhập: {client.user.id} ({get_bot_name(bot_id_str)}) - {client.user.name}", flush=True)
            bot_states["health_stats"].setdefault(bot_id_str, {})
            bot_states["health_stats"][bot_id_str].update({
                'created_time': time.time(),
                'consecutive_failures': 0,
            })
        except Exception as e:
            print(f"[Bot] ❌ Error in on_ready for {bot_id_str}: {e}", flush=True)
            
    if is_main:
        @client.event
        async def on_message(message):
            try:
                # message là một object, không phải dict
                author_id = str(message.author.id)
                content = message.content.lower()
                
                if author_id == karuta_id and "dropping" in content:
                    print(f"DEBUG: Karuta drop detected in channel {message.channel.id} by {get_bot_name(bot_id_str)}")
                    # Cần viết lại logic xử lý ở đây
                    # Ví dụ:
                    # handler = handle_clan_drop if message.mentions else handle_grab
                    # asyncio.create_task(handler(client, message, bot_identifier))
                    pass

            except Exception as e:
                print(f"[Bot] ❌ Error in on_message for {bot_id_str}: {e}", flush=True)

    try:
        # THAY ĐỔI: Chạy bot như một tác vụ nền
        asyncio.create_task(client.start(token, bot=False))
        
        # Chờ bot sẵn sàng
        await asyncio.sleep(5) # Cho thời gian để đăng nhập
        if client.is_ready():
            print(f"[Bot] ✅ Client connected for {bot_id_str}", flush=True)
            return client
        else:
            print(f"[Bot] ⚠️ Client connection timeout for {bot_id_str}. Closing.", flush=True)
            await client.close()
            return None
            
    except Exception as e:
        print(f"[Bot] ❌ Lỗi nghiêm trọng khi tạo bot {bot_identifier}: {e}", flush=True)
        traceback.print_exc()
        return None

# --- LOGIC GRAB CARD (CẦN VIẾT LẠI HOÀN TOÀN) ---
# Đây chỉ là khung sườn, logic bên trong cần được thay đổi để dùng discord.py-self objects
async def _find_and_select_card(client, channel_id, last_drop_msg_id, heart_threshold, bot_num, ktb_channel_id, max_heart_threshold=99999):
    print(f"DEBUG: Bắt đầu tìm card trong kênh {channel_id}")
    try:
        channel = await client.fetch_channel(channel_id)
        if not channel:
            print(f"[CARD GRAB] ❌ Không tìm thấy kênh {channel_id}")
            return False

        # Lấy tin nhắn sau tin nhắn drop
        async for msg_item in channel.history(limit=5, after=discord.Object(id=last_drop_msg_id)):
            if str(msg_item.author.id) == karibbit_id:
                # Logic phân tích embed và chọn card cần được viết lại ở đây
                # ...
                print(f"DEBUG: Tìm thấy tin nhắn từ Karibbit: {msg_item.id}")
                # Ví dụ:
                # embeds = msg_item.embeds
                # desc = embeds[0].description if embeds else ""
                # ...
                # Nếu tìm thấy card -> await msg_item.add_reaction(...)
                # -> ktb_channel = await client.fetch_channel(...)
                # -> await ktb_channel.send("kt b")
                return True
    except Exception as e:
        print(f"[CARD GRAB] ❌ Lỗi khi tìm card: {e}")
    return False

# --- HỆ THỐNG REBOOT (THAY ĐỔI SANG ASYNC) ---
# ... (Hàm check_bot_health, handle_reboot_failure giữ nguyên logic) ...

async def safe_reboot_bot(bot_id):
    if not bot_manager.start_reboot(bot_id):
        print(f"[Safe Reboot] ⚠️ Bot {bot_id} đã đang trong quá trình reboot. Bỏ qua.", flush=True)
        return False

    print(f"[Safe Reboot] 🔄 Bắt đầu reboot bot {bot_id}...", flush=True)
    try:
        # ... logic lấy token giữ nguyên ...
        match = re.match(r"main_(\d+)", bot_id)
        bot_index = int(match.group(1)) - 1
        token = main_tokens[bot_index].strip()
        bot_name = get_bot_name(bot_id)

        print(f"[Safe Reboot] 🧹 Cleaning up old bot instance for {bot_name}", flush=True)
        await bot_manager.remove_bot(bot_id)

        # THAY ĐỔI: Dùng asyncio.sleep
        wait_time = random.uniform(20, 40)
        print(f"[Safe Reboot] ⏳ Chờ {wait_time:.1f}s...", flush=True)
        await asyncio.sleep(wait_time)

        print(f"[Safe Reboot] 🏗️ Creating new bot instance for {bot_name}", flush=True)
        # THAY ĐỔI: Gọi hàm create_bot bất đồng bộ
        new_bot = await create_bot(token, bot_identifier=(bot_index + 1), is_main=True)
        if not new_bot:
            raise Exception("Không thể tạo instance bot mới.")

        await bot_manager.add_bot(bot_id, new_bot)
        
        # ... logic cập nhật settings giữ nguyên ...
        print(f"[Safe Reboot] ✅ Reboot thành công {bot_name}", flush=True)
        return True
    except Exception as e:
        print(f"[Safe Reboot] ❌ Reboot thất bại cho {bot_id}: {e}", flush=True)
        # ...
        return False
    finally:
        bot_manager.end_reboot(bot_id)

# --- VÒNG LẶP NỀN (THAY ĐỔI SANG ASYNC) ---
async def auto_reboot_loop():
    print("[Safe Reboot] 🚀 Khởi động luồng tự động reboot.", flush=True)
    while not stop_events["reboot"].is_set():
        try:
            # ... Logic chọn bot để reboot giữ nguyên ...
            # Nếu chọn được bot -> await safe_reboot_bot(bot_to_reboot)
            
            # THAY ĐỔI: Dùng asyncio.sleep
            await asyncio.sleep(60)
        except Exception as e:
            print(f"[Safe Reboot] ❌ Lỗi nghiêm trọng trong reboot loop: {e}", flush=True)
            await asyncio.sleep(120)

# --- SPAM LOOP (CẦN VIẾT LẠI) ---
async def enhanced_spam_loop():
    print("[Enhanced Spam] 🚀 Khởi động hệ thống spam.", flush=True)
    while True:
        try:
            # Logic spam cần được viết lại hoàn toàn để:
            # 1. Lấy danh sách bot async từ bot_manager
            # 2. Lấy đối tượng channel async: channel = await client.fetch_channel(...)
            # 3. Gửi tin nhắn async: await channel.send(...)
            # 4. Dùng await asyncio.sleep()
            pass
        except Exception as e:
            print(f"[Enhanced Spam] ❌ Lỗi nghiêm trọng: {e}", flush=True)
        await asyncio.sleep(10)


# --- FLASK APP (Cần Chạy Trong Thread Riêng) ---
app = Flask(__name__)
# ... (Toàn bộ HTML_TEMPLATE giữ nguyên) ...
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
        /* === STYLE MỚI ĐƯỢC THÊM VÀO === */
        .heart-input {
            flex-grow: 0 !important; /* Không cho phép tự động dãn ra */
            width: 100px; /* Chiều rộng cố định */
            text-align: center; /* Căn giữa số */
        }
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
                         <div>⏱️ Min Reboot Interval: 10 minutes | Max Failures: 5 attempts</div>
                         <div>🎯 Reboot Strategy: Priority-based, one-at-a-time with cleanup delay</div>
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
                    if (!updatedBotIds.has(child.id)) {
                        child.remove();
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
                'btn-toggle-state': () => postData('/api/toggle_bot_state', { target: button.dataset.target }),
                'clan-drop-toggle-btn': () => postData('/api/clan_drop_toggle'),
                'clan-drop-save-btn': () => {
                    const thresholds = {}, maxThresholds = {};
                    document.querySelectorAll('.clan-drop-threshold').forEach(i => { thresholds[i.dataset.node] = parseInt(i.value, 10); });
                    document.querySelectorAll('.clan-drop-max-threshold').forEach(i => { maxThresholds[i.dataset.node] = parseInt(i.value, 10); });
                    postData('/api/clan_drop_update', { 
                        channel_id: document.getElementById('clan-drop-channel-id').value, 
                        ktb_channel_id: document.getElementById('clan-drop-ktb-channel-id').value, 
                        heart_thresholds: thresholds,
                        max_heart_thresholds: maxThresholds
                    });
                },
                'watermelon-toggle': () => postData('/api/watermelon_toggle', { node: button.dataset.node }),
                'harvest-toggle': () => serverId && postData('/api/harvest_toggle', { 
                    server_id: serverId, 
                    node: button.dataset.node, 
                    threshold: serverPanel.querySelector(`.harvest-threshold[data-node="${button.dataset.node}"]`).value,
                    max_threshold: serverPanel.querySelector(`.harvest-max-threshold[data-node="${button.dataset.node}"]`).value 
                }),
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
# ... (Các route của Flask giữ nguyên, nhưng cần chỉnh sửa để tương tác với asyncio) ...
# Để đơn giản, phần route được giữ nguyên nhưng cần có cơ chế đặc biệt
# để gọi các hàm async từ route đồng bộ của Flask.
# Ví dụ: asyncio.run_coroutine_threadsafe(some_async_function(), main_loop)
def run_flask():
    port = int(os.environ.get("PORT", 10000))
    print(f"🌐 Web Server running at http://0.0.0.0:{port}", flush=True)
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

# --- MAIN EXECUTION (THAY ĐỔI HOÀN TOÀN) ---
async def main():
    global main_loop
    main_loop = asyncio.get_running_loop()

    print("🚀 Shadow Network Control - V3 (discord.py-self conversion) Starting...", flush=True)
    load_settings()

    print("🔌 Initializing bots using Safe Bot Manager...", flush=True)
    
    # Khởi tạo bot chính
    main_bot_tasks = []
    for i, token in enumerate(t for t in main_tokens if t.strip()):
        bot_num = i + 1
        bot_id = f"main_{bot_num}"
        # THAY ĐỔI: Dùng await để gọi hàm async
        bot = await create_bot(token.strip(), bot_identifier=bot_num, is_main=True)
        if bot:
            # THAY ĐỔI: Dùng await để gọi hàm async
            await bot_manager.add_bot(bot_id, bot)
        # ... logic set default state giữ nguyên ...

    # Khởi tạo bot phụ
    sub_bot_tasks = []
    for i, token in enumerate(t for t in tokens if t.strip()):
        bot_id = f"sub_{i}"
        bot = await create_bot(token.strip(), bot_identifier=i, is_main=False)
        if bot:
            await bot_manager.add_bot(bot_id, bot)
        # ...

    print("🔧 Starting background tasks...", flush=True)
    # THAY ĐỔI: Chạy các vòng lặp nền như các tác vụ asyncio
    # asyncio.create_task(auto_reboot_loop())
    # asyncio.create_task(enhanced_spam_loop())
    # asyncio.create_task(auto_clan_drop_loop())
    # ... (Các task khác tương tự) ...

    # Chạy Flask trong một luồng riêng vì nó là ứng dụng đồng bộ
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    # Giữ cho chương trình chính (asyncio) chạy mãi mãi
    await asyncio.Event().wait()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("🛑 Shutting down...")
