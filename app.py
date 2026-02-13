import streamlit as st
from supabase import create_client, Client
import pandas as pd
from datetime import datetime, date, timedelta
from streamlit_gsheets import GSheetsConnection
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
    h1, h2, h3 { margin-bottom: 0.5rem !important; margin-top: 0rem !important; }
    
    .streamlit-expanderHeader { 
        padding-top: 8px !important; padding-bottom: 8px !important; 
        background-color: #f0f2f6; border-radius: 8px; font-weight: bold;
        border: 1px solid #e0e0e0;
    }
    
    .stButton button { width: 100%; border-radius: 5px; height: 2.2rem; }
    section[data-testid="stSidebar"] .block-container { padding-top: 2rem; }
    
    div[data-testid="column"] { padding-bottom: 5px; }
    
    div[data-testid="stVerticalBlock"] > div[style*="overflow"]::-webkit-scrollbar { width: 6px; }
    div[data-testid="stVerticalBlock"] > div[style*="overflow"]::-webkit-scrollbar-thumb { background-color: #ccc; border-radius: 3px; }
    
    div[data-testid="stCheckbox"] { margin-top: 28px; }
    
    .alert-text-overdue { color: #d32f2f; font-weight: 800; font-size: 14px; margin-bottom: 5px; display: block; }
    .alert-text-today { color: #2e7d32; font-weight: 800; font-size: 14px; margin-bottom: 5px; display: block; }

    /* Fancy Search Bar Overlay */
    .search-highlight {
        background-color: #fff3cd;
        padding: 10px;
        border-radius: 10px;
        border: 1px solid #ffeeba;
        margin-bottom: 20px;
    }
</style>
""", unsafe_allow_html=True)

# --- CONFIGURATION ---
COMPANY_DOMAIN = "@rbsgo.com"

# --- SECURE CONNECTION ---
try:
    SUPABASE_URL = st.secrets["connections.supabase"]["SUPABASE_URL"]
    SUPABASE_KEY = st.secrets["connections.supabase"]["SUPABASE_KEY"]
except:
    try:
        SUPABASE_URL = st.secrets["SUPABASE_URL"]
        SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
    except:
        st.error("🚨 Secrets not found!")
        st.stop()

@st.cache_resource
def init_supabase():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

supabase = init_supabase()

# --- AUTHENTICATION & MASTERS ---
def verify_user_in_db(email):
    try:
        response = supabase.table("user_master").select("*").eq("email", email).eq("status", "active").execute()
        if response.data: return response.data[0]
        return None
    except: return None

def get_active_users():
    try:
        response = supabase.table("user_master").select("email").eq("status", "active").execute()
        return [u['email'] for u in response.data] if response.data else []
    except: return []

def create_new_user(email, name, role):
    try:
        exists = supabase.table("user_master").select("*").eq("email", email).execute()
        if exists.data: return False, "User already exists!"
        data = {"email": email, "name": name, "role": role, "status": "active"}
        supabase.table("user_master").insert(data).execute()
        return True, "User added successfully!"
    except Exception as e: return False, str(e)

def toggle_user_status(email, current_status):
    try:
        new_status = "inactive" if current_status == "active" else "active"
        supabase.table("user_master").update({"status": new_status}).eq("email", email).execute()
        return True
    except: return False

# --- GEMINI AI ---
def get_ai_summary(task_dataframe):
    try:
        if "GOOGLE_API_KEY" in st.secrets:
            api_key = st.secrets["GOOGLE_API_KEY"]
        else: return "⚠️ Google API Key missing."
        llm = ChatGoogleGenerativeAI(model="gemini-pro", google_api_key=api_key)
        task_text = task_dataframe.to_string(index=False)
        prompt = f"Act as PM. Summarize Bottlenecks and Focus for tasks: {task_text}"
        response = llm.invoke(prompt)
        return response.content
    except Exception as e: return f"AI Error: {str(e)}"

# --- SYNC LOGIC ---
def sync_projects():
    try:
        conn = st.connection("gsheets", type=GSheetsConnection)
        df = conn.read(worksheet="ROADMAP", ttl=0) 
        if df.empty: return False, "⚠️ Sheet empty."
        df = df.fillna("").astype(str)
        count = 0
        for _, row in df.iterrows():
            if row.get('Interface Name', '').strip() == '': continue
            data = { "name": row.get('Interface Name').strip(), "status": row.get('Status').strip(), 
                     "description": row.get('Particulars').strip(), "vendor": row.get('Vendor').strip() }
            supabase.table("projects").upsert(data, on_conflict="name").execute()
            count += 1
        get_projects_master.clear()
        return True, f"✅ Synced {count} Projects!"
    except Exception as e: return False, f"❌ Sync Error: {str(e)}"

# --- OPTIMIZED DATA LOADING ---
@st.cache_data(ttl=300)
def get_projects_master():
    try:
        response = supabase.table("projects").select("name").execute()
        return [row['name'] for row in response.data] if response.data else []
    except: return []

def load_data_efficiently(target_email=None):
    query = supabase.table("tasks").select("*").order("due_date", desc=False)
    if target_email: query = query.eq("assigned_to", target_email)
    response = query.execute()
    df = pd.DataFrame(response.data) if response.data else pd.DataFrame()
    if not df.empty:
        df['due_date'] = pd.to_datetime(df['due_date'], errors='coerce')
        df['due_date'] = df['due_date'].fillna(pd.Timestamp.now().normalize())
        used_coords = df['coordinator'].dropna().unique().tolist()
        used_projs = df['project_ref'].dropna().unique().tolist()
    else: used_coords, used_projs = [], []
    all_projects = sorted(list(set(get_projects_master() + used_projs + ["General"])))
    all_coords = sorted(list(set(["Sales Team", "Client", "Support Team", "Internal", "Management"] + used_coords)))
    return df, all_projects, all_coords

# --- TASK FUNCTIONS ---
def add_task(created_by, assigned_to, task_desc, priority, due_date, project_ref, coordinator, email_subject, points):
    try:
        data = { "created_by": created_by, "assigned_to": assigned_to, "task_desc": task_desc,
                 "status": "Open", "priority": priority, "due_date": str(due_date or date.today()),
                 "project_ref": project_ref or "General", "staff_remarks": "", "coordinator": coordinator or "General",
                 "email_subject": email_subject, "points": points }
        supabase.table("tasks").insert(data).execute()
        return True
    except Exception as e: st.error(f"Error: {e}"); return False

def update_task_status(task_id, new_status, remarks=None):
    try:
        data = {"status": new_status}
        if remarks: data["staff_remarks"] = remarks
        supabase.table("tasks").update(data).eq("id", task_id).execute()
        return True
    except: return False

def update_task_full(task_id, new_desc, new_date, new_prio, new_remarks, new_assign, new_points, new_subject, new_coord, new_proj, is_manager):
    try:
        data = { "task_desc": new_desc, "due_date": str(new_date), "priority": new_prio,
                 "staff_remarks": new_remarks, "points": new_points, "email_subject": new_subject,
                 "coordinator": new_coord, "project_ref": new_proj }
        if is_manager and new_assign: data["assigned_to"] = new_assign
        supabase.table("tasks").update(data).eq("id", task_id).execute()
        return True
    except Exception as e: st.error(f"Update failed: {e}"); return False

# --- MAIN APP ---
def main():
    if 'logged_in' not in st.session_state: st.session_state['logged_in'] = False
    if 'user_role' not in st.session_state: st.session_state['user_role'] = None
    if 'user_name' not in st.session_state: st.session_state['user_name'] = None

    login_placeholder = st.empty()

    if not st.session_state['logged_in']:
        with login_placeholder.container():
            col1, col2, col3 = st.columns([1, 2, 1])
            with col2:
                st.title("🚀 RBS TaskHub")
                with st.container(border=True):
                    email_input = st.text_input("Enter Work Email:")
                    if st.button("Login", use_container_width=True):
                        email = email_input.lower().strip()
                        if email.endswith(COMPANY_DOMAIN):
                            user_record = verify_user_in_db(email)
                            if user_record:
                                st.session_state.update({'logged_in': True, 'user': user_record['email'], 
                                                       'user_role': user_record['role'], 'user_name': user_record['name']})
                                login_placeholder.empty(); st.rerun()
                            else: st.error("🚫 Access Denied.")
                        else: st.error(f"🚫 Restricted Access. {COMPANY_DOMAIN} only.")
    else:
        current_user, user_role, user_name = st.session_state['user'], st.session_state['user_role'], st.session_state['user_name']
        is_manager = (user_role == 'manager')
        
        with st.sidebar:
            st.markdown(f"### 💼 RBS Workspace\n{user_name} ({'Manager' if is_manager else 'Team Member'})")
            menu_options = ["Dashboard", "New Task"]
            menu_icons = ["journal-bookmark", "plus-circle"]
            if is_manager: menu_options.append("Team Master"); menu_icons.append("people-fill")
            nav_mode = option_menu(None, options=menu_options, icons=menu_icons, default_index=0,
                                   styles={"nav-link-selected": {"background-color": "#ff4b4b"}})
            st.divider()
            if st.button("Logout", use_container_width=True): st.session_state['logged_in'] = False; st.rerun()

        if nav_mode == "Team Master" and is_manager:
            st.title("👥 Team Master")
            with st.expander("➕ Add New User", expanded=True):
                with st.form("add_user", clear_on_submit=True):
                    c1, c2, c3 = st.columns(3)
                    new_n, new_e, new_r = c1.text_input("Name"), c2.text_input("Email"), c3.selectbox("Role", ["member", "manager"])
                    if st.form_submit_button("Add User", type="primary"):
                        if new_e.endswith("@rbsgo.com"):
                            success, msg = create_new_user(new_e.lower().strip(), new_n, new_r)
                            if success: st.toast(msg); time.sleep(1); st.rerun()
                            else: st.error(msg)

            users = supabase.table("user_master").select("*").order("name").execute().data
            for u in users:
                with st.container(border=True):
                    c1, c2, c3, c4 = st.columns([2, 3, 1, 1])
                    c1.write(f"**{u['name']}**"); c2.write(f"`{u['email']}`"); c3.caption(f"_{u['role']}_")
                    if c4.button("Toggle Status", key=f"tog_{u['email']}"): toggle_user_status(u['email'], u['status']); st.rerun()

        elif nav_mode == "New Task":
            st.header("✨ Create New Task")
            _, all_projects, all_coords = load_data_efficiently(None)
            task_desc = st.text_input("Description", key="nt_desc")
            c2, c3 = st.columns(2)
            with c2:
                if st.checkbox("New Project", key="nt_p_chk"): s_proj = st.text_input("Project", key="nt_p_txt")
                else: s_proj = st.selectbox("Project", all_projects, key="nt_p_sel")
            with c3:
                if st.checkbox("New Coordinator", key="nt_c_chk"): f_coord = st.text_input("Coordinator", key="nt_c_txt")
                else: f_coord = st.selectbox("Coordinator", all_coords, key="nt_c_sel")
            c4, c5 = st.columns(2)
            e_sub, pts = c4.text_input("Email Subject"), c5.text_area("Points")
            c6, c7, c8 = st.columns(3)
            ass_to = c6.selectbox("Assign To", ["Unassigned"] + get_active_users())
            prio, due = c7.selectbox("Prio", ["🔥 High", "⚡ Medium", "🧊 Low"]), c8.date_input("Due", value=date.today())
            if st.button("🚀 Add Task", type="primary"):
                if add_task(current_user, ass_to if ass_to != "Unassigned" else None, task_desc, prio, due, s_proj, f_coord, e_sub, pts):
                    st.toast("✅ Added!"); st.rerun()

        elif nav_mode == "Dashboard":
            view_email = None
            if is_manager:
                c_filter, c_title = st.columns([1, 3])
                view_target = c_filter.selectbox("View For:", ["All Users"] + get_active_users())
                if view_target != "All Users": view_email = view_target
                c_title.title("📔 Operational Diary")
            else: st.title("📔 My Diary"); view_email = current_user
            
            df, all_projects, all_coords = load_data_efficiently(view_email)

            # --- OMNI SEARCH SECTION (STABILIZED CLEAR) ---
            st.markdown('<div class="search-highlight">', unsafe_allow_html=True)
            search_col, clear_col = st.columns([5, 1])
            search_q = search_col.text_input(
                "🔍 Omni-Search (Find tasks, projects, or people instantly...)", 
                placeholder="Type to filter logic...", 
                label_visibility="collapsed",
                key="omni_search_input"
            )
            if clear_col.button("🧹 Clear Search"):
                st.session_state["omni_search_input"] = ""
                st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)

            with st.expander("➕ Create New Task", expanded=False):
                d_desc = st.text_input("Task Description", key="d_desc")
                c2, c3 = st.columns(2)
                with c2:
                    if st.checkbox("New Proj", key="d_p_chk"): d_proj = st.text_input("Project", key="d_p_txt")
                    else: d_proj = st.selectbox("Project", all_projects, key="d_p_sel")
                with c3:
                    if st.checkbox("New Coord", key="d_c_chk"): d_coord = st.text_input("Coordinator", key="d_c_txt")
                    else: d_coord = st.selectbox("Coordinator", all_coords, key="d_c_sel")
                c4, c5 = st.columns(2)
                d_sub, d_pts = c4.text_input("Email Subj", key="d_sub"), c5.text_area("Points", key="d_pts")
                c6, c7, c8 = st.columns(3)
                d_ass = c6.selectbox("Assign", ["Unassigned"] + get_active_users(), key="d_ass")
                d_prio, d_due = c7.selectbox("Prio", ["🔥 High", "⚡ Medium", "🧊 Low"], key="d_pri"), c8.date_input("Due", value=date.today(), key="d_due")
                if st.button("🚀 Add", key="d_add_btn"):
                    if add_task(current_user, d_ass if d_ass != "Unassigned" else None, d_desc, d_prio, d_due, d_proj, d_coord, d_sub, d_pts):
                        st.toast("✅ Added!"); st.rerun()

            if not df.empty:
                today_ts = pd.Timestamp.now().normalize()
                active_df, completed_df = df[df['status'] != 'Completed'], df[df['status'] == 'Completed']
                
                selected_filter = option_menu(None, options=[f"Pending ({len(active_df)})", "Today", "Tomorrow", "Overdue", f"Completed ({len(completed_df)})"],
                                             icons=["folder", "lightning", "calendar", "exclamation", "check"], orientation="horizontal")
                
                temp_df = completed_df if "Completed" in selected_filter else \
                          active_df[active_df['due_date'] == today_ts] if "Today" in selected_filter else \
                          active_df[active_df['due_date'] == today_ts + timedelta(days=1)] if "Tomorrow" in selected_filter else \
                          active_df[active_df['due_date'] < today_ts] if "Overdue" in selected_filter else active_df

                # Apply Omni-Search Filter
                if search_q:
                    q = search_q.lower()
                    final_view_df = temp_df[temp_df.apply(lambda r: q in str(r['task_desc']).lower() or q in str(r['project_ref']).lower() or q in str(r['coordinator']).lower(), axis=1)]
                else: final_view_df = temp_df

                with st.container(height=600):
                    for _, row in final_view_df.iterrows():
                        is_today, is_overdue = (row['due_date'] == today_ts), (row['due_date'] < today_ts)
                        icon = "🔴" if is_overdue else "⚡" if is_today else "📅"
                        title = f"{icon} {'[LATE] ' if is_overdue and 'Completed' not in selected_filter else ''}{row['due_date'].strftime('%d-%b')} | {row['task_desc']} ({row['project_ref']})"
                        
                        with st.expander(title):
                            if is_overdue and "Completed" not in selected_filter: st.markdown('<div class="alert-text-overdue">⚠️ OVERDUE TASK</div>', unsafe_allow_html=True)
                            
                            pc1, pc2, _ = st.columns([3, 3, 3])
                            with pc1:
                                if st.checkbox("Nw", key=f"np_{row['id']}"): final_p = st.text_input("P", key=f"tp_{row['id']}", value=row['project_ref'])
                                else: final_p = st.selectbox("P", all_projects, index=all_projects.index(row['project_ref']) if row['project_ref'] in all_projects else 0, key=f"sp_{row['id']}")
                            with pc2:
                                if st.checkbox("Nw", key=f"nc_{row['id']}"): final_c = st.text_input("C", key=f"tc_{row['id']}", value=row['coordinator'])
                                else: final_c = st.selectbox("C", all_coords, index=all_coords.index(row['coordinator']) if row['coordinator'] in all_coords else 0, key=f"sc_{row['id']}")

                            with st.form(key=f"edit_{row['id']}"):
                                c1, c2, c3 = st.columns([5, 2, 2])
                                n_desc, n_prio, n_date = c1.text_input("Desc", value=row['task_desc']), c2.selectbox("Prio", ["🔥 High", "⚡ Medium", "🧊 Low"], index=["🔥 High", "⚡ Medium", "🧊 Low"].index(row['priority'])), c3.date_input("Date", value=row['due_date'])
                                n_rem, n_pts = st.text_input("Remarks", value=row['staff_remarks']), st.text_area("Details", value=row.get('points', ''))
                                b1, b2, b3 = st.columns([1, 2, 1])
                                if b1.form_submit_button("💾 Save"):
                                    if update_task_full(row['id'], n_desc, n_date, n_prio, n_rem, row['assigned_to'], n_pts, row['email_subject'], final_c, final_p, is_manager):
                                        st.toast("Saved!"); st.rerun()
                                if "Completed" not in selected_filter:
                                    c_rem = b2.text_input("Close Note", key=f"crm_{row['id']}")
                                    if b3.form_submit_button("✅ Close", type="primary"):
                                        if c_rem: update_task_status(row['id'], "Completed", c_rem); st.rerun()
                                        else: st.warning("Note required")
                                else:
                                    if b3.form_submit_button("🔄 Reinstate"): update_task_status(row['id'], "Open", row['staff_remarks']); st.rerun()
            else: st.info("👋 No tasks found.")

if __name__ == "__main__": main()
