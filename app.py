這是一份將前面所有討論功能（狀態記憶、擲骰判定、屬性配點、裝備替換、DALL-E 3 繪圖、語音配音、Streamlit Web 介面）整合在一起的完整終極版程式碼。
為了適應網頁的互動邏輯，我將「裝備更換」與「升級配點」整合進了 Streamlit 的側邊欄與專屬 UI 中。
請將以下程式碼存成 app.py，並使用 streamlit run app.py 執行：
import streamlit as st
import json
import os
import random
from openai import OpenAI

# ==========================================
# 1. API 與系統設定
# ==========================================
# 自動從 Streamlit Secrets 或本機環境變數讀取金鑰
api_key = st.secrets.get("OPENAI_API_KEY", os.environ.get("OPENAI_API_KEY"))
client = OpenAI(api_key=api_key)

SYSTEM_PROMPT = """
你是一個嚴格遵守規則的奇幻文字冒險遊戲地下城主。
請根據玩家的選擇推演劇情。若給予玩家裝備，必須依照規定的字典格式。

【規則與限制】
1. 若選項帶有風險，設定 requires_roll 為 true，給予難度 dc (5-18)，並指定判定屬性 check_stat ("STR", "AGI", 或 "INT")。
2. 根據戰鬥或解謎難度，給予對應的 exp_gain (10-50)。無進展給 0。
3. 如果玩家獲得新武器，請在 inventory_add 加入字典格式，例如：{"name": "精鋼劍", "type": "weapon", "bonus_STR": 2, "bonus_AGI": 0, "bonus_INT": 0}

請嚴格使用以下 JSON 格式回覆：
{
    "scene_description": "生動的場景描述或戰鬥結果...",
    "spoken_text": "將場景濃縮成一句充滿情緒的旁白或對話，用來生成語音(約15-30字)",
    "image_prompt": "給 DALL-E 3 的英文繪圖提示詞，如果無特別場景請留空字串",
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
    """計算：基礎屬性 + 裝備加成"""
    total = st.session_state.player_state["base_stats"].get(stat_name, 0)
    weapon = st.session_state.player_state["equipped"]["weapon"]
    if weapon:
        total += weapon.get(f"bonus_{stat_name}", 0)
    return total

def equip_weapon(item_idx):
    """處理裝備替換邏輯"""
    player = st.session_state.player_state
    new_weapon = player["inventory"][item_idx]
    
    # 將舊武器放回背包
    if player["equipped"]["weapon"]:
        player["inventory"].append(player["equipped"]["weapon"])
    
    # 裝備新武器並從背包移除
    player["equipped"]["weapon"] = new_weapon
    player["inventory"].pop(item_idx)

# ==========================================
# 3. 遊戲核心推演邏輯
# ==========================================
def generate_next_turn(user_action=None, roll_result_text=""):
    player = st.session_state.player_state
    
    if user_action:
        # 將玩家最新狀態與選擇組合傳給 AI
        state_context = f"[當前狀態 - Lv.{player['level']} (HP:{player['hp']}), 屬性(STR:{get_total_stat('STR')}, AGI:{get_total_stat('AGI')}, INT:{get_total_stat('INT')})]"
        user_msg = f"{state_context}\n我選擇：{user_action}。\n{roll_result_text}"
        st.session_state.chat_history.append({"role": "user", "content": user_msg})
    else:
        # 開場
        st.session_state.chat_history.append({
            "role": "user", 
            "content": f"[當前狀態 - Lv.1 (HP:100)]\n遊戲開始。我剛進入艾恩葛朗特第一層。請給我開場劇情。"
        })

    with st.spinner('地下城主正在推演劇情並繪製場景...'):
        # --- A. 呼叫文字模型 ---
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={ "type": "json_object" }, 
            messages=st.session_state.chat_history,
            temperature=0.7
        )
        
        ai_reply = json.loads(response.choices[0].message.content)
        st.session_state.chat_history.append({"role": "assistant", "content": response.choices[0].message.content})
        
        # 結算 HP 與 EXP
        player["hp"] = min(player["max_hp"], player["hp"] + ai_reply.get("hp_change", 0))
        player["exp"] += ai_reply.get("exp_gain", 0)
        
        # 結算獲得物品
        for item in ai_reply.get("inventory_add", []):
            player["inventory"].append(item)
            
        st.session_state.current_scene = ai_reply
        
        # 檢查是否觸發升級
        if player["exp"] >= 100:
            st.session_state.pending_level_up = True

        # --- B. 呼叫繪圖模型 ---
        img_prompt = ai_reply.get("image_prompt", "")
        if img_prompt:
            try:
                img_res = client.images.generate(
                    model="dall-e-3", # 若要省錢可改為 dall-e-2
                    prompt=img_prompt + ", anime fantasy visual novel style, highly detailed",
                    size="1024x1024",
                    quality="standard",
                    n=1,
                )
                st.session_state.current_image_url = img_res.data[0].url
            except Exception as e:
                st.error(f"繪圖失敗: {e}")
                st.session_state.current_image_url = None
        else:
            st.session_state.current_image_url = None

        # --- C. 呼叫語音模型 ---
        spoken_text = ai_reply.get("spoken_text", "")
        if spoken_text:
            try:
                audio_res = client.audio.speech.create(
                    model="tts-1",
                    voice="nova", # 女性聲音
                    input=spoken_text
                )
                st.session_state.current_audio = audio_res.content
            except Exception as e:
                st.error(f"語音失敗: {e}")
                st.session_state.current_audio = None
        else:
            st.session_state.current_audio = None

# ==========================================
# 4. 初始化網頁狀態 (Session State)
# ==========================================
if "initialized" not in st.session_state:
    st.session_state.chat_history = [{"role": "system", "content": SYSTEM_PROMPT}]
    st.session_state.player_state = {
        "level": 1,
        "exp": 0,
        "hp": 100,
        "max_hp": 100,
        "base_stats": {"STR": 3, "AGI": 1, "INT": -1},
        "equipped": {
            "weapon": {"name": "生鏽鐵劍", "type": "weapon", "bonus_STR": 1, "bonus_AGI": 0, "bonus_INT": 0}
        },
        "inventory": [
            {"name": "微型回血藥水", "type": "consumable"}
        ]
    }
    st.session_state.current_scene = None
    st.session_state.current_image_url = None
    st.session_state.current_audio = None
    st.session_state.pending_level_up = False
    st.session_state.initialized = True

# 如果遊戲剛開啟，自動生成第一回合
if st.session_state.current_scene is None:
    generate_next_turn()

# ==========================================
# 5. 渲染 Web UI 介面
# ==========================================
st.set_page_config(page_title="AI 奇幻冒險", layout="wide")
player = st.session_state.player_state

# --- 側邊欄：角色狀態與背包 ---
with st.sidebar:
    st.title("🗡️ 角色面板")
    st.write(f"**Level:** {player['level']} | **EXP:** {player['exp']}/100")
    st.progress(max(0, min(100, int(player["hp"] / player["max_hp"] * 100))), text=f"HP: {player['hp']} / {player['max_hp']}")
    
    st.write("### 📊 總屬性")
    st.write(f"- 💪 力量 (STR): **{get_total_stat('STR')}**")
    st.write(f"- 🏃 敏捷 (AGI): **{get_total_stat('AGI')}**")
    st.write(f"- 🧠 智力 (INT): **{get_total_stat('INT')}**")
    
    st.write("---")
    st.write("### 🛡️ 當前裝備")
    w = player["equipped"]["weapon"]
    if w:
        st.success(f"{w['name']} (STR+{w.get('bonus_STR',0)} AGI+{w.get('bonus_AGI',0)})")
    else:
        st.warning("空手")

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
            
    st.write("---")
    if st.button("🔄 重新開始遊戲"):
        st.session_state.clear()
        st.rerun()

# --- 主畫面：劇情渲染 ---
st.title("⚔️ 艾恩葛朗特 AI 引擎")
scene = st.session_state.current_scene

# 1. 處理升級配點畫面 (攔截遊戲進度)
if st.session_state.pending_level_up:
    st.success("🎉 經驗值已滿！你升級了！最大生命值提升 10 點並完全恢復。")
    st.write("### 請選擇你要提升的屬性：")
    cols = st.columns(3)
    if cols[0].button("💪 提升力量 (STR)"):
        player["base_stats"]["STR"] += 1
        player["exp"] -= 100
        player["level"] += 1
        player["max_hp"] += 10
        player["hp"] = player["max_hp"]
        st.session_state.pending_level_up = (player["exp"] >= 100)
        st.rerun()
    if cols[1].button("🏃 提升敏捷 (AGI)"):
        player["base_stats"]["AGI"] += 1
        player["exp"] -= 100
        player["level"] += 1
        player["max_hp"] += 10
        player["hp"] = player["max_hp"]
        st.session_state.pending_level_up = (player["exp"] >= 100)
        st.rerun()
    if cols[2].button("🧠 提升智力 (INT)"):
        player["base_stats"]["INT"] += 1
        player["exp"] -= 100
        player["level"] += 1
        player["max_hp"] += 10
        player["hp"] = player["max_hp"]
        st.session_state.pending_level_up = (player["exp"] >= 100)
        st.rerun()
        
    st.stop() # 暫停渲染後續劇情，強迫玩家先配點

# 2. 顯示圖片與音訊
if st.session_state.current_image_url:
    st.image(st.session_state.current_image_url, use_column_width=True)

if st.session_state.current_audio:
    st.audio(st.session_state.current_audio, format="audio/mp3", autoplay=True)
    st.caption(f"🔊 {scene.get('spoken_text', '')}")

# 3. 顯示劇情文字
st.info(scene["scene_description"])

# 4. 判斷生死與行動選項
if player["hp"] <= 0:
    st.error("💀 你已經死亡，遊戲結束。請點擊側邊欄重新開始。")
else:
    st.write("### 你的行動：")
    cols = st.columns(len(scene.get("options", [])))
    
    for idx, opt in enumerate(scene.get("options", [])):
        with cols[idx]:
            if st.button(opt["text"], key=opt["id"]):
                roll_msg = ""
                # 執行擲骰判定
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
                    
                    roll_msg = f"系統強制判定：玩家擲骰({roll}) + {stat_name}加成({stat_val}) = {total}。目標難度 {dc}，結果判定為{status}。請嚴格依此推演。"
                    
                generate_next_turn(opt["text"], roll_result_text=roll_msg)
                st.rerun()

