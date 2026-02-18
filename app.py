import streamlit as st
from supabase import create_client, Client
import pandas as pd
from datetime import datetime, date, timedelta
from langchain_google_genai import ChatGoogleGenerativeAI
from streamlit_option_menu import option_menu
import time

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="RBS TaskHub", layout="wide", page_icon="🚀")

# --- MSK STYLE CSS (RED BUTTON LABELS & LEFT ALIGN & RESULT CARDS) ---
st.markdown("""
<style>
    .block-container { padding-top: 1rem !important; padding-bottom: 1rem !important; }
    p, .stMarkdown { font-size: 14px !important; margin-bottom: 0px !important; }
    h1, h2, h3 { margin-bottom: 0px !important; margin-top: 0rem !important; }
    
    .streamlit-expanderHeader { 
        padding: 10px 15px !important;
        background-color: #fcfcfc; border-radius: 8px; font-weight: 700;
        border: 1px solid #eee; transition: 0.3s;
    }
    
    .stButton button { border-radius: 6px; font-weight: 600; height: 2.4rem; }
    
    /* RED BUTTON STYLE LABELS - LEFT ALIGNED */
    .compact-label {
        font-weight: 700;
        font-size: 13px;
        color: #ffffff !important;
        background-color: #ff4b4b; /* RBS Red */
        padding: 6px 12px;
        border-radius: 6px;
        margin-top: 5px; 
        text-align: left; /* FIXED: Left Align */
        display: block;
        width: 100%;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        border: none;
    }
    
    /* FANCY CARDS FOR COMM HELPER */
    .result-card { 
        background-color: #f8f9fa; 
        padding: 15px; 
        border-radius: 8px; 
        border-left: 5px solid #ff4b4b; 
        margin-bottom: 15px; 
        box-shadow: 0 2px 5px rgba(0,0,0,0.05); 
    }
    .card-title { 
        font-weight: 800; 
        color: #ff4b4b; 
        margin-bottom: 8px; 
        font-size: 14px; 
        text-transform: uppercase; 
        letter-spacing: 0.5px;
    }
    
    input[type="date"] { text-transform: uppercase; }
    .element-container { margin-bottom: 3px !important; }
</style>
""", unsafe_allow_html=True)

# --- CONFIGURATION ---
COMPANY_DOMAIN = "@rbsgo.com"
try:
    SUPABASE_URL = st.secrets["connections.supabase"]["SUPABASE_URL"]
    SUPABASE_KEY = st.secrets["connections.supabase"]["SUPABASE_KEY"]
except:
    try:
        SUPABASE_URL = st.secrets["SUPABASE_URL"]
        SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
    except:
        st.error("🚨 Secrets not found!"); st.stop()

# --- INIT SUPABASE ---
def init_supabase():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

supabase = init_supabase()

# --- AUTH & MASTERS ---
def verify_user_in_db(email):
    try:
        response = supabase.table("user_master").select("*").eq("email", email).eq("status", "active").execute()
        return response.data[0] if response.data else None
    except: return None

def get_active_users():
    try:
        response = supabase.table("user_master").select("email").eq("status", "active").execute()
        return [u['email'] for u in response.data] if response.data else []
    except: return []

# --- COMM HELPER FUNCTIONS ---
def get_user_comm_prefs(email):
    """Fetch user's default communication styles"""
    try:
        res = supabase.table("user_comm_prefs").select("*").eq("email", email).execute()
        if res.data: return res.data[0]
        return {"email_style": "", "whatsapp_style": ""}
    except Exception:
        return {"email_style": "", "whatsapp_style": ""}

def save_user_comm_prefs(email, e_style, w_style):
    """Save new defaults"""
    try:
        data = {"email": email, "email_style": e_style, "whatsapp_style": w_style}
        supabase.table("user_comm_prefs").upsert(data).execute()
        return True
    except Exception as e:
        err_msg = str(e)
        if "PGRST205" in err_msg or "schema cache" in err_msg:
            st.warning("⚠️ System Syncing: Database is updating. Please wait 1 minute.")
        else:
            st.error(f"Save failed: {e}")
        return False

def generate_variations(prompt, mode, instructions, api_key):
    """Call AI to generate 3 variations"""
    try:
        if not api_key: return ["⚠️ AI Key Missing", "⚠️ Check Secrets", "⚠️ Contact Admin"]
        
        llm = ChatGoogleGenerativeAI(model="gemini-pro", google_api_key=api_key)
        
        final_prompt = f"""
        You are a top-tier Executive Communication Assistant.
        Task: Rewrite the user's raw input into a perfect {mode} message.
        
        User's Personal Master Instructions: {instructions}
        
        Raw Input: "{prompt}"
        
        Output Requirement:
        Provide exactly 3 distinct variations separated by '|||'.
        1. Professional/Safe
        2. Persuasive/Action-Oriented
        3. Short/Punchy (CEO Style)
        
        Do not add introductory text. Just the 3 variations separated by |||.
        """
        
        response = llm.invoke(final_prompt)
        return response.content.split('|||')
    except Exception as e:
        return [f"Error: {str(e)}", "Try again", "Check connection"]

# --- DATA LOADING ---
def load_data_efficiently(target_email=None):
    query = supabase.table("tasks").select("*")
    if target_email: query = query.eq("assigned_to", target_email)
    res = query.execute()
    df = pd.DataFrame(res.data) if res.data else pd.DataFrame()
    
    if not df.empty:
        df['due_date'] = pd.to_datetime(df['due_date'], errors='coerce').dt.date
        df['due_date'] = df['due_date'].fillna(date.today())
        # Default Sort: Due Date Ascending
        df = df.sort_values(by="due_date", ascending=True)
        used_coords = sorted(df['coordinator'].dropna().unique().tolist())
        used_projs = sorted(df['project_ref'].dropna().unique().tolist())
    else:
        used_coords, used_projs = [], []
        
    all_p = sorted(list(set(used_projs + ["General"])))
    all_c = sorted(list(set(["Sales Team", "Client", "Support Team", "Internal", "Management"] + used_coords)))
    return df, all_p, all_c

def add_task(created_by, assigned_to, task_desc, priority, due_date, project_ref, coordinator, email_subject, points):
    data = { "created_by": created_by, "assigned_to": assigned_to, "task_desc": task_desc,
             "status": "Open", "priority": priority, "due_date": str(due_date),
             "project_ref": project_ref or "General", "coordinator": coordinator or "General",
             "email_subject": email_subject, "points": points }
    supabase.table("tasks").insert(data).execute()
    return True

def update_task_status(task_id, new_status, remarks=None):
    data = {"status": new_status}
    if remarks: data["staff_remarks"] = remarks
    supabase.table("tasks").update(data).eq("id", task_id).execute()
    return True

def update_task_full(task_id, new_desc, new_date, new_prio, new_remarks, new_assign, new_points, new_subject, new_coord, new_proj, is_manager):
    data = { "task_desc": new_desc, "due_date": str(new_date), "priority": new_prio,
             "staff_remarks": new_remarks, "points": new_points, "email_subject": new_subject,
             "coordinator": new_coord, "project_ref": new_proj }
    if is_manager and new_assign: data["assigned_to"] = new_assign
    supabase.table("tasks").update(data).eq("id", task_id).execute()
    return True

# --- NEW: BUMP DATE FUNCTION ---
def bump_task_date(task_id, current_date):
    """Moves the task to tomorrow"""
    new_date = current_date + timedelta(days=1)
    supabase.table("tasks").update({"due_date": str(new_date)}).eq("id", task_id).execute()
    return True

# --- CALLBACKS ---
def reset_search():
    st.session_state["omni_search_input"] = ""

# --- MAIN APP ---
def main():
    if 'logged_in' not in st.session_state: st.session_state['logged_in'] = False
    if 'omni_search_input' not in st.session_state: st.session_state['omni_search_input'] = ""

    login_container = st.empty()

    if not st.session_state['logged_in']:
        with login_container.container():
            col1, col2, col3 = st.columns([1, 2, 1])
            with col2:
                st.title("🚀 RBS TaskHub")
                with st.container(border=True):
                    e_in = st.text_input("Enter Work Email:")
                    if st.button("Login", use_container_width=True):
                        email = e_in.lower().strip()
                        user = verify_user_in_db(email)
                        if user:
                            st.session_state.update({'logged_in': True, 'user': user['email'], 'user_role': user['role'], 'user_name': user['name']})
                            login_container.empty()
                            st.rerun()
                        else: st.error("🚫 Access Denied.")
    else:
        login_container.empty()
        current_user, user_role, user_name = st.session_state['user'], st.session_state['user_role'], st.session_state['user_name']
        is_manager = (user_role == 'manager')
        
        # PREPARE USER LIST FOR ASSIGNMENT (Defaults to Current User)
        active_users_list = get_active_users()
        if current_user in active_users_list:
            default_user_idx = active_users_list.index(current_user)
        else:
            default_user_idx = 0
        
        with st.sidebar:
            st.markdown(f"### 💼 RBS Workspace\n**{user_name}** ({user_role.title()})")
            nav_mode = option_menu(None, options=["Dashboard", "New Task", "Comm Helper"], 
                                   icons=["journal-bookmark", "plus-circle", "chat-quote"], 
                                   styles={"nav-link-selected": {"background-color": "#ff4b4b"}})
            if st.button("Logout", use_container_width=True): st.session_state['logged_in'] = False; st.rerun()

        if nav_mode == "New Task":
            st.header("✨ Create New Task")
            _, all_p, all_c = load_data_efficiently(None)
            
            # --- FORM WRAPPER TO PREVENT LAG AND AUTO-CLEAR ---
            with st.form("new_task_page_form", clear_on_submit=True):
                # --- ROW 1: Project | Contact (Select or Override) ---
                c1, c2 = st.columns(2)
                with c1: 
                    sc1, sc2, sc3 = st.columns([1, 2, 2])
                    sc1.markdown('<div class="compact-label">Project</div>', unsafe_allow_html=True)
                    p_sel = sc2.selectbox("Select", all_p, key="n_p_sel", label_visibility="collapsed")
                    p_new = sc3.text_input("New", placeholder="Type to override...", key="n_p_txt", label_visibility="collapsed")
                    final_p = p_new if p_new.strip() else p_sel
                with c2: 
                    sc4, sc5, sc6 = st.columns([1, 2, 2])
                    sc4.markdown('<div class="compact-label">Contact</div>', unsafe_allow_html=True)
                    c_sel = sc5.selectbox("Select", all_c, key="n_c_sel", label_visibility="collapsed")
                    c_new = sc6.text_input("New", placeholder="Type to override...", key="n_c_txt", label_visibility="collapsed")
                    final_c = c_new if c_new.strip() else c_sel
                
                # --- ROW 2: Task Description ---
                c3, c4 = st.columns([1, 9])
                c3.markdown('<div class="compact-label">Task</div>', unsafe_allow_html=True)
                t_desc = c4.text_input("Desc", placeholder="Task Description", label_visibility="collapsed")

                # --- ROW 3: Email Subject ---
                c5, c6 = st.columns([1, 9])
                c5.markdown('<div class="compact-label">Subject</div>', unsafe_allow_html=True)
                e_sub = c6.text_input("Subj", placeholder="Email Subject", label_visibility="collapsed")

                # --- ROW 4: Priority | Due | User ---
                r4c1, r4c2, r4c3 = st.columns(3)
                with r4c1:
                    sub1, sub2 = st.columns([1, 2])
                    sub1.markdown('<div class="compact-label">Priority</div>', unsafe_allow_html=True)
                    prio = sub2.selectbox("Pr", ["🔥 High", "⚡ Medium", "🧊 Low"], label_visibility="collapsed")
                with r4c2:
                    sub3, sub4 = st.columns([1, 2])
                    sub3.markdown('<div class="compact-label">Due</div>', unsafe_allow_html=True)
                    due = sub4.date_input("Dt", value=date.today(), format="DD/MM/YYYY", label_visibility="collapsed")
                with r4c3:
                    sub5, sub6 = st.columns([1, 2])
                    sub5.markdown('<div class="compact-label">User</div>', unsafe_allow_html=True)
                    ass_to = sub6.selectbox("User", active_users_list, index=default_user_idx, label_visibility="collapsed")

                # --- ROW 5: Points ---
                pt1, pt2 = st.columns([1, 9])
                pt1.markdown('<div class="compact-label">Points</div>', unsafe_allow_html=True)
                pts = pt2.text_area("Points", height=100, label_visibility="collapsed")
                
                # --- SUBMIT BUTTON ---
                submitted = st.form_submit_button("🚀 Add Task", type="primary", use_container_width=True)

            if submitted:
                if not ass_to: 
                    st.error("⚠️ Please assign the task to a user.")
                else:
                    if add_task(current_user, ass_to, t_desc, prio, due, final_p, final_c, e_sub, pts):
                        st.success("✅ Task Created Successfully!")
                        time.sleep(0.5) 
                        st.rerun()    

        elif nav_mode == "Dashboard":
            view_email = None
            if is_manager:
                c_filter, c_title = st.columns([1, 3])
                view_target = c_filter.selectbox("View User:", ["All Users"] + get_active_users())
                if view_target != "All Users": view_email = view_target
                c_title.title("📔 Operational Diary")
            else: st.title("📔 My Diary"); view_email = current_user
            
            df, all_p, all_c = load_data_efficiently(view_email)

            sc1, sc2 = st.columns([5, 1])
            search_q = sc1.text_input("🔍 Omni-Search", label_visibility="collapsed", key="omni_search_input", placeholder="Search task, project, or person...")
            if sc2.button("🧹 Clear", on_click=reset_search): st.rerun()

            # --- DASHBOARD CREATE EXPANDER ---
            with st.expander("➕ Create New Task", expanded=False):
                with st.form("dashboard_create_form", clear_on_submit=True):
                    c1, c2 = st.columns(2)
                    with c1:
                        sc1, sc2, sc3 = st.columns([1, 2, 2])
                        sc1.markdown('<div class="compact-label">Project</div>', unsafe_allow_html=True)
                        d_p_sel = sc2.selectbox("Select", all_p, key="d_p_sel", label_visibility="collapsed")
                        d_p_new = sc3.text_input("New", placeholder="Override...", key="d_p_txt", label_visibility="collapsed")
                        final_dp = d_p_new if d_p_new.strip() else d_p_sel
                    with c2:
                        sc4, sc5, sc6 = st.columns([1, 2, 2])
                        sc4.markdown('<div class="compact-label">Contact</div>', unsafe_allow_html=True)
                        d_c_sel = sc5.selectbox("Select", all_c, key="d_c_sel", label_visibility="collapsed")
                        d_c_new = sc6.text_input("New", placeholder="Override...", key="d_c_txt", label_visibility="collapsed")
                        final_dc = d_c_new if d_c_new.strip() else d_c_sel
                    
                    dc1, dc2 = st.columns([1, 9])
                    dc1.markdown('<div class="compact-label">Task</div>', unsafe_allow_html=True)
                    d_desc = dc2.text_input("Desc", key="d_desc", label_visibility="collapsed")

                    r3c1, r3c2, r3c3 = st.columns(3)
                    with r3c1:
                        sub1, sub2 = st.columns([1, 2])
                        sub1.markdown('<div class="compact-label">Priority</div>', unsafe_allow_html=True)
                        d_prio = sub2.selectbox("Pr", ["🔥 High", "⚡ Medium", "🧊 Low"], key="d_pri_dash", label_visibility="collapsed")
                    with r3c2:
                        sub3, sub4 = st.columns([1, 2])
                        sub3.markdown('<div class="compact-label">Due</div>', unsafe_allow_html=True)
                        d_due = sub4.date_input("Dt", value=date.today(), format="DD/MM/YYYY", key="d_due_dash", label_visibility="collapsed")
                    with r3c3:
                        sub5, sub6 = st.columns([1, 2])
                        sub5.markdown('<div class="compact-label">User</div>', unsafe_allow_html=True)
                        d_ass = sub6.selectbox("User", active_users_list, index=default_user_idx, key="d_ass_dash", label_visibility="collapsed")

                    ds1, ds2 = st.columns([1, 9])
                    ds1.markdown('<div class="compact-label">Subject</div>', unsafe_allow_html=True)
                    d_sub = ds2.text_input("Subj", placeholder="Optional Subject...", key="d_sub_dash", label_visibility="collapsed")

                    dp1, dp2 = st.columns([1, 9])
                    dp1.markdown('<div class="compact-label">Points</div>', unsafe_allow_html=True)
                    d_pts = dp2.text_area("Pts", height=80, key="d_pts_dash", label_visibility="collapsed")
                    
                    d_submitted = st.form_submit_button("🚀 Add Task", type="primary")

                if d_submitted:
                    if not d_ass:
                            st.error("⚠️ Please assign the task to a user.")
                    else:
                        if add_task(current_user, d_ass, d_desc, d_prio, d_due, final_dp, final_dc, d_sub, d_pts):
                            st.success("✅ Task Created Successfully!")
                            time.sleep(0.5)
                            st.rerun()

            if not df.empty:
                # --- SORTING TOGGLE ---
                sort_col, _ = st.columns([1, 4])
                sort_mode = sort_col.radio("Sort By:", ["📅 Due Date", "🆔 Created Order"], horizontal=True, label_visibility="collapsed")
                
                if sort_mode == "📅 Due Date":
                    df = df.sort_values(by="due_date", ascending=True)
                else:
                    df = df.sort_values(by="id", ascending=False) # Newest ID first

                today = date.today()
                active_df, done_df = df[df['status'] != 'Completed'], df[df['status'] == 'Completed']
                sel_filter = option_menu(None, options=[f"Pending ({len(active_df)})", "Today", "Tomorrow", "Overdue", f"Completed ({len(done_df)})"],
                                         icons=["folder", "lightning", "calendar", "exclamation", "check"], orientation="horizontal")
                
                temp_df = done_df if "Completed" in sel_filter else \
                          active_df[active_df['due_date'] == today] if "Today" in sel_filter else \
                          active_df[active_df['due_date'] == today + timedelta(days=1)] if "Tomorrow" in sel_filter else \
                          active_df[active_df['due_date'] < today] if "Overdue" in sel_filter else active_df

                if search_q:
                    q = search_q.lower()
                    final_df = temp_df[temp_df.apply(lambda r: q in str(r['task_desc']).lower() or q in str(r['project_ref']).lower() or q in str(r['coordinator']).lower(), axis=1)]
                else: final_df = temp_df

                with st.container(height=650):
                    for _, row in final_df.iterrows():
                        is_late = (row['due_date'] < today)
                        icon = "🔴" if is_late else "⚡" if row['due_date'] == today else "📅"
                        ass_tag = f" → {row['assigned_to'].split('@')[0].title()}" if row['assigned_to'] else ""
                        t_label = f"{icon} {'[LATE] ' if is_late and 'Completed' not in sel_filter else ''}{row['due_date'].strftime('%d-%b')} | {row['task_desc']}{ass_tag}"
                        
                        with st.expander(t_label):
                            if is_late and "Completed" not in sel_filter: st.markdown('<div class="alert-text-overdue">⚠️ OVERDUE</div>', unsafe_allow_html=True)
                            with st.form(key=f"edit_{row['id']}"):
                                c1, c2 = st.columns(2)
                                with c1:
                                    sc1, sc2, sc3 = st.columns([1, 2, 2])
                                    sc1.markdown('<div class="compact-label">Project</div>', unsafe_allow_html=True)
                                    curr_p = row['project_ref']
                                    p_idx = all_p.index(curr_p) if curr_p in all_p else 0
                                    sel_p = sc2.selectbox("Select", all_p, index=p_idx, label_visibility="collapsed", key=f"sp_{row['id']}")
                                    def_txt_p = curr_p if curr_p not in all_p else ""
                                    text_p = sc3.text_input("New", value=def_txt_p, placeholder="Override...", label_visibility="collapsed", key=f"tp_{row['id']}")
                                    final_edit_p = text_p if text_p.strip() else sel_p

                                with c2:
                                    sc4, sc5, sc6 = st.columns([1, 2, 2])
                                    sc4.markdown('<div class="compact-label">Contact</div>', unsafe_allow_html=True)
                                    curr_c = row['coordinator']
                                    c_idx = all_c.index(curr_c) if curr_c in all_c else 0
                                    sel_c = sc5.selectbox("Select", all_c, index=c_idx, label_visibility="collapsed", key=f"sc_{row['id']}")
                                    def_txt_c = curr_c if curr_c not in all_c else ""
                                    text_c = sc6.text_input("New", value=def_txt_c, placeholder="Override...", label_visibility="collapsed", key=f"tc_{row['id']}")
                                    final_edit_c = text_c if text_c.strip() else sel_c

                                dc1, dc2 = st.columns([1, 9])
                                dc1.markdown('<div class="compact-label">Task</div>', unsafe_allow_html=True)
                                n_desc = dc2.text_input("Desc", value=row['task_desc'], label_visibility="collapsed")

                                r3c1, r3c2, r3c3 = st.columns(3)
                                with r3c1:
                                    sub1, sub2 = st.columns([1, 2])
                                    sub1.markdown('<div class="compact-label">Priority</div>', unsafe_allow_html=True)
                                    n_prio = sub2.selectbox("Pr", ["🔥 High", "⚡ Medium", "🧊 Low"], index=["🔥 High", "⚡ Medium", "🧊 Low"].index(row['priority']), label_visibility="collapsed")
                                with r3c2:
                                    sub3, sub4 = st.columns([1, 2])
                                    sub3.markdown('<div class="compact-label">Due</div>', unsafe_allow_html=True)
                                    n_date = sub4.date_input("Dt", value=row['due_date'], format="DD/MM/YYYY", label_visibility="collapsed")
                                with r3c3:
                                    sub5, sub6 = st.columns([1, 2])
                                    sub5.markdown('<div class="compact-label">User</div>', unsafe_allow_html=True)
                                    curr = row['assigned_to'] if row['assigned_to'] else "Unassigned"
                                    clean_users = active_users_list
                                    if curr and curr not in clean_users: clean_users = [curr] + clean_users
                                    a_idx = clean_users.index(curr) if curr in clean_users else 0
                                    n_ass = sub6.selectbox("User", clean_users, index=a_idx, label_visibility="collapsed")
                                    final_ass = n_ass

                                rc1, rc2 = st.columns([1, 9])
                                rc1.markdown('<div class="compact-label">Remarks</div>', unsafe_allow_html=True)
                                n_rem = rc2.text_input("Rem", value=row['staff_remarks'], label_visibility="collapsed")

                                n_pts = st.text_area("Details", value=row.get('points', ''), height=80, label_visibility="collapsed", placeholder="Detailed points...")
                                
                                b1, b2, b3 = st.columns([1, 2, 1])
                                if b1.form_submit_button("💾 Save", type="primary"):
                                    if update_task_full(row['id'], n_desc, n_date, n_prio, n_rem, final_ass, n_pts, row['email_subject'], final_edit_c, final_edit_p, is_manager):
                                        st.toast("Saved!"); st.rerun()
                                if "Completed" not in sel_filter:
                                    # --- BUMP BUTTON ADDED ---
                                    if b2.form_submit_button("⬇️ Bump", type="secondary"):
                                        if bump_task_date(row['id'], row['due_date']):
                                            st.toast("Moved to Tomorrow!"); st.rerun()
                                            
                                    if b3.form_submit_button("✅ Close", type="primary"):
                                        c_n = n_rem if n_rem else "Closed"
                                        update_task_status(row['id'], "Completed", c_n); st.rerun()
                                else:
                                    if b3.form_submit_button("🔄 Re-Open", type="primary"): update_task_status(row['id'], "Open"); st.rerun()
            else: st.info("👋 No tasks found.")

        # --- COMM HELPER SCREEN ---
        elif nav_mode == "Comm Helper":
            st.title("💬 Intelligent Comm Helper")
            
            # 1. Fetch User Preferences (Graceful fallback)
            prefs = get_user_comm_prefs(current_user)
            
            # 2. Configuration Expander
            with st.expander("⚙️ Configure Your Style (Master Instructions)"):
                st.info("💡 Tell the AI how you like to sound. It will remember this forever!")
                c1, c2 = st.columns(2)
                new_w_style = c1.text_area("My WhatsApp Style", value=prefs.get('whatsapp_style', ''), height=100, placeholder="e.g., Short, no hello/hi, use emojis...")
                new_e_style = c2.text_area("My Email Style", value=prefs.get('email_style', ''), height=100, placeholder="e.g., Professional, always start with 'Dear Team'...")
                
                if st.button("💾 Update My Master Instructions", type="primary"):
                    if save_user_comm_prefs(current_user, new_e_style, new_w_style):
                        st.toast("✅ Style Updated Successfully!")
                        time.sleep(1)
                        st.rerun()

            # 3. Main Input Area
            st.markdown("### ✍️ Draft Your Message")
            raw_text = st.text_area("Type your raw thought here...", height=120, placeholder="e.g., tell client meeting is moved to tuesday due to flight delay")
            
            # 4. Action Buttons
            c1, c2 = st.columns(2)
            gen_wa = c1.button("🟢 Generate for WhatsApp", use_container_width=True)
            gen_em = c2.button("🔵 Generate for Email", use_container_width=True)
            
            # 5. Generation Logic
            if raw_text and (gen_wa or gen_em):
                mode = "WhatsApp" if gen_wa else "Email"
                style_instruction = prefs.get('whatsapp_style') if gen_wa else prefs.get('email_style')
                
                try: api_key = st.secrets["GOOGLE_API_KEY"]
                except: api_key = ""
                
                with st.spinner(f"✨ Crafting your {mode} magic..."):
                    variations = generate_variations(raw_text, mode, style_instruction, api_key)
                
                # 6. Display Results
                st.markdown("---")
                st.subheader(f"🚀 {mode} Variations")
                
                if len(variations) >= 3:
                    # Variation 1
                    st.markdown('<div class="result-card"><div class="card-title">Option 1: Professional / Safe</div>', unsafe_allow_html=True)
                    st.code(variations[0].strip(), language=None)
                    st.markdown('</div>', unsafe_allow_html=True)

                    # Variation 2
                    st.markdown('<div class="result-card"><div class="card-title">Option 2: Persuasive / Action</div>', unsafe_allow_html=True)
                    st.code(variations[1].strip(), language=None)
                    st.markdown('</div>', unsafe_allow_html=True)

                    # Variation 3
                    st.markdown('<div class="result-card"><div class="card-title">Option 3: Short / Punchy (CEO Mode)</div>', unsafe_allow_html=True)
                    st.code(variations[2].strip(), language=None)
                    st.markdown('</div>', unsafe_allow_html=True)
                else:
                    st.error("Could not generate variations. Please check API Key.")

if __name__ == "__main__": main()
