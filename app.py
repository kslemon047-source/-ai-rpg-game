import streamlit as st
import json
import os
import random
import urllib.parse
from io import BytesIO
import google.generativeai as genai
from gtts import gTTS

# ==========================================
# 1. API 與系統設定 (Gemini 版本)
# ==========================================
api_key = st.secrets.get("GEMINI_API_KEY", os.environ.get("GEMINI_API_KEY"))
genai.configure(api_key=api_key)

# 使用 Gemini 1.5 Flash 模型 (速度快且免費額度高)
model = genai.GenerativeModel('gemini-pro')


SYSTEM_PROMPT = """
你是一個嚴格遵守規則的奇幻文字冒險遊戲地下城主。
請根據玩家的選擇推演劇情。若給予玩家裝備，必須依照規定的字典格式。

【規則與限制】
1. 若選項帶有風險，設定 requires_roll 為 true，給予難度 dc (5-18)，並指定判定屬性 check_stat ("STR", "AGI", 或 "INT")。
2. 根據戰鬥或解謎難度，給予對應的 exp_gain (10-50)。無進展給 0。
3. 如果玩家獲得新武器，請在 inventory_add 加入字典格式，例如：{"name": "精鋼劍", "type": "weapon", "bonus_STR": 2, "bonus_AGI": 0, "bonus_INT": 0}

請嚴格使用以下 JSON 格式回覆：
{
    "scene_description": "生動的場景描述...",
    "spoken_text": "將場景濃縮成一句話，用來生成語音(約15-30字)",
    "image_prompt": "給 AI 的英文繪圖提示詞 (請加上 anime visual novel style)，無特別場景留空字串",
    "hp_change": 0,
    "exp_gain": 0,
    "inventory_add": [],
    "options": [
        {
            "id": "A", 
            "text": "選項描述", 
            "requires_roll": true, 
            "dc": 10, 
            "check_stat": "STR"
        }
    ]
}
"""

# ==========================================
# 2. 輔助函式與狀態計算
# ==========================================
def get_total_stat(stat_name):
    total = st.session_state.player_state["base_stats"].get(stat_name, 0)
    weapon = st.session_state.player_state["equipped"]["weapon"]
    if weapon:
        total += weapon.get(f"bonus_{stat_name}", 0)
    return total

def equip_weapon(item_idx):
    player = st.session_state.player_state
    new_weapon = player["inventory"][item_idx]
    if player["equipped"]["weapon"]:
        player["inventory"].append(player["equipped"]["weapon"])
    player["equipped"]["weapon"] = new_weapon
    player["inventory"].pop(item_idx)

# ==========================================
# 3. 遊戲核心推演邏輯 (免費版)
# ==========================================
def generate_next_turn(user_action=None, roll_result_text=""):
    player = st.session_state.player_state
    
    # 組合給 AI 的提示詞
    state_context = f"[當前狀態 - Lv.{player['level']} (HP:{player['hp']})]"
    if user_action:
        user_msg = f"{state_context}\n玩家選擇：{user_action}。\n{roll_result_text}\n(請務必確保輸出為合法 JSON)"
    else:
        user_msg = f"{state_context}\n遊戲開始。我剛進入艾恩葛朗特第一層。請給我開場劇情。(請務必確保輸出為合法 JSON)"
        
    prompt = f"{SYSTEM_PROMPT}\n\n{user_msg}"

    with st.spinner('地下城主正在推演劇情...'):
        try:
            # 1. 呼叫 Gemini 文字模型
            response = model.generate_content(prompt)
            ai_reply = json.loads(response.text)
            
            # 結算 HP 與 EXP
            player["hp"] = min(player["max_hp"], player["hp"] + ai_reply.get("hp_change", 0))
            player["exp"] += ai_reply.get("exp_gain", 0)
            
            # 結算獲得物品
            for item in ai_reply.get("inventory_add", []):
                player["inventory"].append(item)
                
            st.session_state.current_scene = ai_reply
            
            if player["exp"] >= 100:
                st.session_state.pending_level_up = True

            # 2. 生成免費圖片 (Pollinations.ai)
            img_prompt = ai_reply.get("image_prompt", "")
            if img_prompt:
                # 把文字轉成 URL 格式，直接呼叫免金鑰 API
                safe_prompt = urllib.parse.quote(img_prompt + " anime visual novel style highly detailed")
                st.session_state.current_image_url = f"https://image.pollinations.ai/prompt/{safe_prompt}?width=1024&height=1024&nologo=true"
            else:
                st.session_state.current_image_url = None

            # 3. 生成免費語音 (gTTS)
            spoken_text = ai_reply.get("spoken_text", "")
            if spoken_text:
                tts = gTTS(text=spoken_text, lang='zh-tw')
                fp = BytesIO()
                tts.write_to_fp(fp)
                st.session_state.current_audio = fp.getvalue()
            else:
                st.session_state.current_audio = None
                
        except Exception as e:
            st.error(f"系統發生錯誤，請重試: {e}")

# ==========================================
# 4. 初始化網頁狀態 (Session State)
# ==========================================
if "initialized" not in st.session_state:
    st.session_state.player_state = {
        "level": 1, "exp": 0, "hp": 100, "max_hp": 100,
        "base_stats": {"STR": 3, "AGI": 1, "INT": -1},
        "equipped": {"weapon": {"name": "生鏽鐵劍", "type": "weapon", "bonus_STR": 1, "bonus_AGI": 0, "bonus_INT": 0}},
        "inventory": [{"name": "微型回血藥水", "type": "consumable"}]
    }
    st.session_state.current_scene = None
    st.session_state.current_image_url = None
    st.session_state.current_audio = None
    st.session_state.pending_level_up = False
    st.session_state.initialized = True

if st.session_state.current_scene is None:
    generate_next_turn()

# ==========================================
# 5. 渲染 Web UI 介面
# ==========================================
st.set_page_config(page_title="AI 奇幻冒險", layout="wide")
player = st.session_state.player_state

with st.sidebar:
    st.title("🗡️ 角色面板")
    st.write(f"**Level:** {player['level']} | **EXP:** {player['exp']}/100")
    st.progress(max(0, min(100, int(player["hp"] / player["max_hp"] * 100))), text=f"HP: {player['hp']} / {player['max_hp']}")
    
    st.write("### 📊 總屬性")
    st.write(f"- 💪 STR: **{get_total_stat('STR')}** | 🏃 AGI: **{get_total_stat('AGI')}** | 🧠 INT: **{get_total_stat('INT')}**")
    
    st.write("---")
    w = player["equipped"]["weapon"]
    st.write("### 🛡️ 裝備: " + (f"{w['name']} (STR+{w.get('bonus_STR',0)})" if w else "空手"))

    st.write("---")
    st.write("### 🎒 背包")
    for idx, item in enumerate(player["inventory"]):
        if isinstance(item, dict) and item.get("type") == "weapon":
            cols = st.columns([2, 1])
            cols[0].write(f"🗡️ {item['name']}")
            if cols[1].button("裝備", key=f"equip_{idx}"):
                equip_weapon(idx)
                st.rerun()
        else:
            name = item['name'] if isinstance(item, dict) else item
            st.write(f"- {name}")
            
    if st.button("🔄 重新開始遊戲"):
        st.session_state.clear()
        st.rerun()

st.title("⚔️ 艾恩葛朗特 AI 引擎 (免費版)")
scene = st.session_state.current_scene

if st.session_state.pending_level_up:
    st.success("🎉 經驗值已滿！你升級了！最大生命值提升 10 點。")
    st.write("### 請選擇你要提升的屬性：")
    cols = st.columns(3)
    if cols[0].button("💪 提升力量 (STR)"):
        player["base_stats"]["STR"] += 1; player["exp"] -= 100; player["level"] += 1; player["max_hp"] += 10; player["hp"] = player["max_hp"]; st.session_state.pending_level_up = False; st.rerun()
    if cols[1].button("🏃 提升敏捷 (AGI)"):
        player["base_stats"]["AGI"] += 1; player["exp"] -= 100; player["level"] += 1; player["max_hp"] += 10; player["hp"] = player["max_hp"]; st.session_state.pending_level_up = False; st.rerun()
    if cols[2].button("🧠 提升智力 (INT)"):
        player["base_stats"]["INT"] += 1; player["exp"] -= 100; player["level"] += 1; player["max_hp"] += 10; player["hp"] = player["max_hp"]; st.session_state.pending_level_up = False; st.rerun()
    st.stop() 

if st.session_state.current_image_url:
    st.image(st.session_state.current_image_url, use_column_width=True)

if st.session_state.current_audio:
    st.audio(st.session_state.current_audio, format="audio/mp3", autoplay=True)
    st.caption(f"🔊 {scene.get('spoken_text', '')}")

st.info(scene.get("scene_description", "系統運算中..."))

if player["hp"] <= 0:
    st.error("💀 你已經死亡，遊戲結束。請點擊側邊欄重新開始。")
else:
    st.write("### 你的行動：")
    cols = st.columns(len(scene.get("options", [])))
    
    for idx, opt in enumerate(scene.get("options", [])):
        with cols[idx]:
            if st.button(opt["text"], key=opt["id"]):
                roll_msg = ""
                if opt.get("requires_roll"):
                    dc = opt.get("dc", 10)
                    stat_name = opt.get("check_stat", "STR")
                    stat_val = get_total_stat(stat_name)
                    roll = random.randint(1, 20)
                    total = roll + stat_val
                    
                    if roll == 20: status = "【大成功🌟】"
                    elif roll == 1: status = "【大失敗💀】"
                    elif total >= dc: status = "【成功】"
                    else: status = "【失敗】"
                    
                    roll_msg = f"系統強制判定：玩家擲骰({roll}) + {stat_name}加成({stat_val}) = {total}。目標難度 {dc}，判定為{status}。請依此推演。"
                    
                generate_next_turn(opt["text"], roll_result_text=roll_msg)
                st.rerun()
