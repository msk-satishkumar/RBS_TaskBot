import streamlit as st
from supabase import create_client, Client
import pandas as pd
from datetime import datetime, date, timedelta
from langchain_google_genai import ChatGoogleGenerativeAI
from streamlit_option_menu import option_menu
import time

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="RBS TaskHub", layout="wide", page_icon="🚀")

# --- MSK STYLE CSS ---
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
    
    /* RED BUTTON STYLE LABELS */
    .compact-label {
        font-weight: 700; font-size: 13px; color: #ffffff !important;
        background-color: #ff4b4b; /* RBS Red */
        padding: 6px 12px; border-radius: 6px;
        margin-top: 5px; text-align: left; display: block; width: 100%;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1); border: none;
    }
    
    /* Result Cards */
    .result-card { 
        background-color: #f8f9fa; padding: 15px; border-radius: 8px; 
        border-left: 5px solid #ff4b4b; margin-bottom: 15px; 
        box-shadow: 0 2px 5px rgba(0,0,0,0.05); 
    }
    .card-title { 
        font-weight: 800; color: #ff4b4b; margin-bottom: 8px; 
        font-size: 14px; text-transform: uppercase; letter-spacing: 0.5px; 
    }
    
    input[type="date"] { text-transform: uppercase; }
    .element-container { margin-bottom: 3px !important; }
    
    /* BLINKING OVERDUE ALERT */
    @keyframes blinker {
        50% { opacity: 0; }
    }
    .alert-blink {
        color: #ff4b4b;
        font-weight: 800;
        font-size: 14px;
        text-transform: uppercase;
        animation: blinker 1.5s linear infinite;
        margin-bottom: 5px;
    }
    
    /* Bump Button Specific Style */
    div[data-testid="column"] button[kind="secondary"] {
        border: 1px solid #eee;
        color: #555;
        padding: 0px 10px;
    }

    /* --- TOOLTIP VISIBILITY & BEHAVIOR FIXES --- */
    div[data-testid="stTooltipHoverTarget"] {
        width: 100% !important;
        height: 100% !important;
        display: block !important;
    }
    div[data-testid="column"], 
    div[data-testid="stHorizontalBlock"], 
    div[data-testid="stVerticalBlock"], 
    div[data-testid="stExpanderDetails"], 
    div.element-container {
        overflow: visible !important;
    }
    div[data-testid="stTooltipContent"] {
        z-index: 999999 !important;
    }
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
    try:
        res = supabase.table("user_comm_prefs").select("*").eq("email", email).execute()
        if res.data: return res.data[0]
        return {"email_style": "", "whatsapp_style": ""}
    except Exception:
        return {"email_style": "", "whatsapp_style": ""}

def save_user_comm_prefs(email, e_style, w_style):
    try:
        data = {"email": email, "email_style": e_style, "whatsapp_style": w_style}
        supabase.table("user_comm_prefs").upsert(data).execute()
        return True
    except Exception as e:
        err_msg = str(e)
        if "PGRST205" in err_msg or "schema cache" in err_msg:
            st.warning("⚠️ Database Updating: Please wait 1 minute.")
        else:
            st.error(f"Save failed: {e}")
        return False

def generate_variations(prompt, mode, instructions, api_key):
    try:
        if not api_key: return ["⚠️ AI Key Missing", "⚠️ Check Secrets", "⚠️ Contact Admin"]
        llm = ChatGoogleGenerativeAI(model="gemini-pro", google_api_key=api_key)
        final_prompt = f"""
        You are a top-tier Executive Communication Assistant.
        Task: Rewrite the user's raw input into a perfect {mode} message.
        User's Personal Master Instructions: {instructions}
        Raw Input: "{prompt}"
        Output Requirement: Provide exactly 3 distinct variations separated by '|||'.
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
        
        # Ensure task_type and project_status exist in DataFrame for seamless handling
        if 'task_type' not in df.columns: df['task_type'] = 'Task'
        if 'project_status' not in df.columns: df['project_status'] = 'Yet to Start'
        
        # Base sort
        df = df.sort_values(by="due_date", ascending=True)
        used_coords = sorted(df['coordinator'].dropna().unique().tolist())
        used_projs = sorted(df['project_ref'].dropna().unique().tolist())
    else:
        used_coords, used_projs = [], []
        
    all_p = sorted(list(set(used_projs + ["General"])))
    all_c = sorted(list(set(["Sales Team", "Client", "Support Team", "Internal", "Management"] + used_coords)))
    return df, all_p, all_c

# --- UPDATED DATABASE FUNCTIONS FOR TASK TYPE / PROJECT STATUS ---
def add_task(created_by, assigned_to, task_desc, priority, due_date, project_ref, coordinator, email_subject, points, task_type="Task", project_status=None):
    # FIX: Safely convert NaN/None values to strings to prevent PostgREST JSON API Errors
    def safe_str(val):
        if pd.isna(val) or val is None: return ""
        return str(val)

    data = { 
        "created_by": safe_str(created_by), 
        "assigned_to": safe_str(assigned_to), 
        "task_desc": safe_str(task_desc),
        "status": "Open", 
        "priority": safe_str(priority), 
        "due_date": str(due_date),
        "project_ref": safe_str(project_ref) or "General", 
        "coordinator": safe_str(coordinator) or "General",
        "email_subject": safe_str(email_subject), 
        "points": safe_str(points),
        "task_type": safe_str(task_type) or "Task"
    }
    
    if task_type == "Project":
        data["project_status"] = safe_str(project_status) if safe_str(project_status) else "Yet to Start"
    else:
        data["project_status"] = None
             
    supabase.table("tasks").insert(data).execute()
    return True

def update_task_status(task_id, new_status, remarks=None):
    data = {"status": new_status}
    if remarks: data["staff_remarks"] = remarks
    supabase.table("tasks").update(data).eq("id", task_id).execute()
    return True

def update_task_full(task_id, new_desc, new_date, new_prio, new_remarks, new_assign, new_points, new_subject, new_coord, new_proj, is_manager, task_type="Task", project_status=None):
    # FIX: Safely convert NaN/None values to strings to prevent PostgREST JSON API Errors
    def safe_str(val):
        if pd.isna(val) or val is None: return ""
        return str(val)

    data = { 
        "task_desc": safe_str(new_desc), 
        "due_date": str(new_date), 
        "priority": safe_str(new_prio),
        "staff_remarks": safe_str(new_remarks), 
        "points": safe_str(new_points), 
        "email_subject": safe_str(new_subject),
        "coordinator": safe_str(new_coord), 
        "project_ref": safe_str(new_proj),
        "task_type": safe_str(task_type) or "Task"
    }
    
    if task_type == "Project":
        data["project_status"] = safe_str(project_status) if safe_str(project_status) else "Yet to Start"
    else:
        data["project_status"] = None
        
    if is_manager and new_assign: 
        data["assigned_to"] = safe_str(new_assign)
        
    supabase.table("tasks").update(data).eq("id", task_id).execute()
    return True

# --- NEW: BUMP DATE FUNCTION ---
def bump_task_date(task_id, current_date):
    """Moves the task to tomorrow (DB Update)"""
    new_date = current_date + timedelta(days=1)
    supabase.table("tasks").update({"due_date": str(new_date)}).eq("id", task_id).execute()
    return True

# --- CALLBACKS ---
def reset_search():
    st.session_state["omni_search_input"] = ""

def reset_bumps():
    """Clears the bumped tasks list"""
    st.session_state['bumped_ids'] = set()

# --- MAIN APP ---
def main():
    if 'logged_in' not in st.session_state: st.session_state['logged_in'] = False
    if 'omni_search_input' not in st.session_state: st.session_state['omni_search_input'] = ""
    # Init bumped IDs set to track what we moved to the bottom temporarily
    if 'bumped_ids' not in st.session_state: st.session_state['bumped_ids'] = set()
    # Init success message flag
    if 'show_update_success' not in st.session_state: st.session_state['show_update_success'] = False

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
        active_users_list = get_active_users()
        default_user_idx = active_users_list.index(current_user) if current_user in active_users_list else 0
        
        with st.sidebar:
            st.markdown(f"### 💼 RBS Workspace\n**{user_name}** ({user_role.title()})")
            # --- ADDED 'Projects' TO NAV MENU ---
            nav_mode = option_menu(None, options=["Dashboard", "Projects", "New Task"], 
                                   icons=["journal-bookmark", "briefcase", "plus-circle"], 
                                   styles={"nav-link-selected": {"background-color": "#ff4b4b"}})
            if st.button("Logout", use_container_width=True): st.session_state['logged_in'] = False; st.rerun()

        # --- NEW TASK SCREEN ---
        if nav_mode == "New Task":
            st.header("✨ Create New Task")
            _, all_p, all_c = load_data_efficiently(None)
            
            # Put Task Type outside the form to enable dynamic UI updates without full form submission
            task_type_sel = st.radio("Task Type", ["Task", "Project"], horizontal=True)

            with st.form("new_task_page_form", clear_on_submit=True):
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
                
                c3, c4 = st.columns([1, 9])
                c3.markdown('<div class="compact-label">Task</div>', unsafe_allow_html=True)
                t_desc = c4.text_input("Desc", placeholder="Task Description", label_visibility="collapsed")

                c5, c6 = st.columns([1, 9])
                c5.markdown('<div class="compact-label">Subject</div>', unsafe_allow_html=True)
                e_sub = c6.text_input("Subj", placeholder="Email Subject", label_visibility="collapsed")

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

                pt1, pt2 = st.columns([1, 9])
                pt1.markdown('<div class="compact-label">Points</div>', unsafe_allow_html=True)
                pts = pt2.text_area("Points", height=100, label_visibility="collapsed")
                
                # Dynamic Project Status Options
                p_stat_val = None
                if task_type_sel == "Project":
                    ps1, ps2 = st.columns([1, 9])
                    ps1.markdown('<div class="compact-label">Status</div>', unsafe_allow_html=True)
                    p_stat_val = ps2.selectbox("Project Status", ["Yet to Start", "In Progress", "Hold", "Completed"], label_visibility="collapsed")
                
                submitted = st.form_submit_button("🚀 Add Task", type="primary", use_container_width=True)

            if submitted:
                if not ass_to: st.error("⚠️ Please assign the task to a user.")
                else:
                    if add_task(current_user, ass_to, t_desc, prio, due, final_p, final_c, e_sub, pts, task_type_sel, p_stat_val):
                        st.success("✅ Task Created Successfully!")
                        time.sleep(0.5)
                        st.rerun()    

        # --- PROJECTS SCREEN ---
        elif nav_mode == "Projects":
            st.title("📁 Project Listing")
            
            df, all_p, all_c = load_data_efficiently(None)
            
            if not df.empty and 'task_type' in df.columns:
                proj_df = df[df['task_type'] == 'Project']
            else:
                proj_df = pd.DataFrame()
                
            if proj_df.empty:
                st.info("👋 No projects found.")
            else:
                users_with_projects = sorted(proj_df['assigned_to'].dropna().unique().tolist())
                
                c_filt, _ = st.columns([1, 3])
                filter_user = c_filt.selectbox("Filter by User:", ["All Users"] + users_with_projects)
                
                st.markdown("---")
                
                if filter_user == "All Users":
                    for u in users_with_projects:
                        st.subheader(f"👤 {u.split('@')[0].title()}")
                        u_df = proj_df[proj_df['assigned_to'] == u]
                        for _, row in u_df.iterrows():
                            with st.container(border=True):
                                st.markdown(f"**Project Ref:** {row['project_ref']} &nbsp;|&nbsp; **Task:** {row['task_desc']}")
                                st.markdown(f"**Status:** `{row.get('project_status', 'Yet to Start')}` &nbsp;|&nbsp; **Due Date:** {row['due_date']} &nbsp;|&nbsp; **Priority:** {row['priority']}")
                else:
                    st.subheader(f"👤 {filter_user.split('@')[0].title()}")
                    u_df = proj_df[proj_df['assigned_to'] == filter_user]
                    for _, row in u_df.iterrows():
                        with st.container(border=True):
                            st.markdown(f"**Project Ref:** {row['project_ref']} &nbsp;|&nbsp; **Task:** {row['task_desc']}")
                            st.markdown(f"**Status:** `{row.get('project_status', 'Yet to Start')}` &nbsp;|&nbsp; **Due Date:** {row['due_date']} &nbsp;|&nbsp; **Priority:** {row['priority']}")

        # --- DASHBOARD SCREEN ---
        elif nav_mode == "Dashboard":
            view_email = None
            if is_manager:
                c_filter, c_title = st.columns([1, 3])
                view_target = c_filter.selectbox("View User:", ["All Users"] + get_active_users())
                if view_target != "All Users": view_email = view_target
                c_title.title("📔 Operational Diary")
            else: st.title("📔 My Diary"); view_email = current_user
            
            df, all_p, all_c = load_data_efficiently(view_email)

            # Show success message if a task was just updated
            if st.session_state['show_update_success']:
                st.toast("✅ Task Updated Successfully!", icon="🎉")
                st.session_state['show_update_success'] = False # Reset flag

            # --- HEADER: SEARCH | CLEAR | SORT (RED BUTTONS) ---
            sc1, sc2, sc3 = st.columns([6, 1, 2])
            search_q = sc1.text_input("🔍 Omni-Search", label_visibility="collapsed", key="omni_search_input", placeholder="Search task, project, or person...")
            
            # Use on_click callback to prevent StreamlitAPIException
            sc2.button("🧹 Clear", help="Clear Search", use_container_width=True, type="primary", on_click=reset_search)
            
            if sc3.button("📅 Sort: Due Date", help="Reset list and sort by Due Date", use_container_width=True, type="primary"):
                reset_bumps() 

            if not df.empty:
                # Default Sort Logic
                df['is_bumped'] = df['id'].apply(lambda x: 1 if x in st.session_state['bumped_ids'] else 0)
                df = df.sort_values(by=['is_bumped', 'due_date'], ascending=[True, True])

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
                        
                        # --- LIST ITEM LAYOUT ---
                        if "Completed" not in sel_filter:
                            col_exp, col_btn = st.columns([0.92, 0.08])
                        else:
                            col_exp, col_btn = st.columns([1, 0.001]) 

                        with col_exp:
                            with st.expander(t_label):
                                # BLINKING ALERT LOGIC
                                if is_late and "Completed" not in sel_filter: 
                                    st.markdown('<div class="alert-blink">⚠️ OVERDUE</div>', unsafe_allow_html=True)
                                
                                with st.form(key=f"edit_{row['id']}"):
                                    
                                    # Fetch existing dynamic values for the task, safeguarding against NaN
                                    curr_t_type = row.get('task_type', 'Task')
                                    if pd.isna(curr_t_type) or not curr_t_type: curr_t_type = "Task"
                                        
                                    curr_p_stat = row.get('project_status', 'Yet to Start')
                                    if pd.isna(curr_p_stat) or not curr_p_stat: curr_p_stat = "Yet to Start"
                                    
                                    # --- TASK TYPE / STATUS ROW ---
                                    type_col1, type_col2 = st.columns(2)
                                    with type_col1:
                                        st.markdown('<div class="compact-label">Task Type</div>', unsafe_allow_html=True)
                                        t_type_edit = st.selectbox("Type", ["Task", "Project"], index=0 if curr_t_type == "Task" else 1, label_visibility="collapsed", key=f"tt_edit_{row['id']}")
                                    
                                    p_stat_edit = None 
                                    if t_type_edit == "Project":
                                        with type_col2:
                                            st.markdown('<div class="compact-label">Project Status</div>', unsafe_allow_html=True)
                                            stat_opts = ["Yet to Start", "In Progress", "Hold", "Completed"]
                                            idx = stat_opts.index(curr_p_stat) if curr_p_stat in stat_opts else 0
                                            p_stat_edit = st.selectbox("Status", stat_opts, index=idx, label_visibility="collapsed", key=f"ps_edit_{row['id']}")
                                    
                                    # --- EXISTING EDIT FIELDS ---
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
                                    
                                    # Scrub Remarks to prevent NaN rendering physically
                                    safe_rem = row['staff_remarks'] if pd.notna(row.get('staff_remarks')) else ""
                                    n_rem = rc2.text_input("Rem", value=safe_rem, label_visibility="collapsed")

                                    safe_pts = row.get('points', '') if pd.notna(row.get('points')) else ""
                                    n_pts = st.text_area("Details", value=safe_pts, height=80, label_visibility="collapsed", placeholder="Detailed points...")
                                    
                                    # --- FORM FOOTER RESTORED WITH CLOSING NOTE ---
                                    b1, b2, b3 = st.columns([1, 2, 1])
                                    
                                    # Save Button
                                    if b1.form_submit_button("💾 Save", type="primary"):
                                        safe_subject = row['email_subject'] if pd.notna(row.get('email_subject')) else ""
                                            
                                        if update_task_full(row['id'], n_desc, n_date, n_prio, n_rem, final_ass, n_pts, safe_subject, final_edit_c, final_edit_p, is_manager, t_type_edit, p_stat_edit):
                                            st.session_state['show_update_success'] = True
                                            st.rerun()
                                    
                                    # Logic for Close vs Re-Open
                                    if "Completed" not in sel_filter:
                                        with b2:
                                            # Restored Closing Note Input
                                            c_n_input = st.text_input("Close Note", key=f"cn_{row['id']}", placeholder="Closing note...", label_visibility="collapsed")
                                        
                                        if b3.form_submit_button("✅ Close", type="primary"):
                                            final_note = c_n_input if c_n_input else (n_rem if n_rem else "Closed")
                                            update_task_status(row['id'], "Completed", final_note)
                                            st.session_state['show_update_success'] = True
                                            st.rerun()
                                    else:
                                        if b3.form_submit_button("🔄 Re-Open", type="primary"): 
                                            update_task_status(row['id'], "Open")
                                            st.session_state['show_update_success'] = True
                                            st.rerun()
                        
                        # --- BUMP BUTTON (RED & OUTSIDE) ---
                        if "Completed" not in sel_filter:
                            with col_btn:
                                if row['id'] not in st.session_state['bumped_ids']:
                                    if st.button("⬇️", key=f"bump_{row['id']}", help="Move to bottom", type="primary"):
                                        st.session_state['bumped_ids'].add(row['id'])
                                        st.rerun()

            else: st.info("👋 No tasks found.")

        # --- COMM HELPER SCREEN ---
        # Note: Unreachable from UI currently as requested, but logic is preserved.
        elif nav_mode == "Comm Helper":
            st.title("💬 Intelligent Comm Helper")
            prefs = get_user_comm_prefs(current_user)
            with st.expander("⚙️ Configure Your Style (Master Instructions)"):
                st.info("💡 Tell the AI how you like to sound. It will remember this forever!")
                c1, c2 = st.columns(2)
                new_w_style = c1.text_area("My WhatsApp Style", value=prefs.get('whatsapp_style', ''), height=100, placeholder="e.g., Short, no hello/hi, use emojis...")
                new_e_style = c2.text_area("My Email Style", value=prefs.get('email_style', ''), height=100, placeholder="e.g., Professional, always start with 'Dear Team'...")
                if st.button("💾 Update My Master Instructions", type="primary"):
                    if save_user_comm_prefs(current_user, new_e_style, new_w_style):
                        st.toast("✅ Style Updated Successfully!"); time.sleep(1); st.rerun()

            st.markdown("### ✍️ Draft Your Message")
            raw_text = st.text_area("Type your raw thought here...", height=120, placeholder="e.g., tell client meeting is moved to tuesday due to flight delay")
            c1, c2 = st.columns(2)
            gen_wa = c1.button("🟢 Generate for WhatsApp", use_container_width=True)
            gen_em = c2.button("🔵 Generate for Email", use_container_width=True)
            
            if raw_text and (gen_wa or gen_em):
                mode = "WhatsApp" if gen_wa else "Email"
                style_instruction = prefs.get('whatsapp_style') if gen_wa else prefs.get('email_style')
                try: api_key = st.secrets["GOOGLE_API_KEY"]
                except: api_key = ""
                with st.spinner(f"✨ Crafting your {mode} magic..."):
                    variations = generate_variations(raw_text, mode, style_instruction, api_key)
                st.markdown("---")
                st.subheader(f"🚀 {mode} Variations")
                if len(variations) >= 3:
                    st.markdown('<div class="result-card"><div class="card-title">Option 1: Professional / Safe</div>', unsafe_allow_html=True)
                    st.code(variations[0].strip(), language=None); st.markdown('</div>', unsafe_allow_html=True)
                    st.markdown('<div class="result-card"><div class="card-title">Option 2: Persuasive / Action</div>', unsafe_allow_html=True)
                    st.code(variations[1].strip(), language=None); st.markdown('</div>', unsafe_allow_html=True)
                    st.markdown('<div class="result-card"><div class="card-title">Option 3: Short / Punchy (CEO Mode)</div>', unsafe_allow_html=True)
                    st.code(variations[2].strip(), language=None); st.markdown('</div>', unsafe_allow_html=True)
                else: st.error("Could not generate variations. Please check API Key.")

if __name__ == "__main__": main()
