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

# --- MSK STYLE CSS (PROFESSIONAL ALIGNMENT) ---
st.markdown("""
<style>
    .block-container { padding-top: 1rem !important; padding-bottom: 1rem !important; }
    p, .stMarkdown { font-size: 14px !important; margin-bottom: 0px !important; }
    h1, h2, h3 { margin-bottom: 0.5rem !important; margin-top: 0rem !important; }
    
    .streamlit-expanderHeader { 
        padding: 10px 15px !important;
        background-color: #f8f9fa; border-radius: 8px; font-weight: bold;
        border: 1px solid #e9ecef;
    }
    
    /* Sexy form alignment */
    .stForm { background-color: #ffffff; border: none !important; padding: 0 !important; }
    .stTextInput input, .stSelectbox select, .stTextArea textarea {
        background-color: #fdfdfd !important;
        border: 1px solid #e0e0e0 !important;
        border-radius: 6px !important;
    }

    .stButton button { width: 100%; border-radius: 5px; height: 2.5rem; font-weight: 600; }
    
    /* Alert Text */
    .alert-text-overdue { color: #dc3545; font-weight: 800; font-size: 13px; margin-bottom: 10px; display: block; }
    
    /* Search Bar Professional Overlay */
    .search-highlight {
        background-color: #f1f3f4;
        padding: 15px;
        border-radius: 12px;
        margin-bottom: 25px;
        border-left: 5px solid #ff4b4b;
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
        st.error("🚨 Secrets not found!"); st.stop()

@st.cache_resource
def init_supabase():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

supabase = init_supabase()

# --- MASTERS & AUTH ---
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

def create_new_user(email, name, role):
    try:
        exists = supabase.table("user_master").select("*").eq("email", email).execute()
        if exists.data: return False, "User already exists!"
        supabase.table("user_master").insert({"email": email, "name": name, "role": role, "status": "active"}).execute()
        return True, "User added successfully!"
    except Exception as e: return False, str(e)

def toggle_user_status(email, current_status):
    new_s = "inactive" if current_status == "active" else "active"
    supabase.table("user_master").update({"status": new_s}).eq("email", email).execute()

def sync_projects():
    try:
        conn = st.connection("gsheets", type=GSheetsConnection)
        df = conn.read(worksheet="ROADMAP", ttl=0) 
        if df.empty: return False, "Sheet empty."
        df = df.fillna("").astype(str)
        for _, row in df.iterrows():
            if row.get('Interface Name', '').strip() == '': continue
            data = { "name": row.get('Interface Name').strip(), "status": row.get('Status').strip(), 
                     "description": row.get('Particulars').strip(), "vendor": row.get('Vendor').strip() }
            supabase.table("projects").upsert(data, on_conflict="name").execute()
        get_projects_master.clear(); return True, "Synced!"
    except Exception as e: return False, str(e)

@st.cache_data(ttl=300)
def get_projects_master():
    try:
        res = supabase.table("projects").select("name").execute()
        return [r['name'] for r in res.data] if res.data else []
    except: return []

def load_data_efficiently(target_email=None):
    query = supabase.table("tasks").select("*").order("due_date", desc=False)
    if target_email: query = query.eq("assigned_to", target_email)
    res = query.execute()
    df = pd.DataFrame(res.data) if res.data else pd.DataFrame()
    if not df.empty:
        df['due_date'] = pd.to_datetime(df['due_date'], errors='coerce').dt.date
        used_coords = df['coordinator'].dropna().unique().tolist()
        used_projs = df['project_ref'].dropna().unique().tolist()
    else: used_coords, used_projs = [], []
    all_p = sorted(list(set(get_projects_master() + used_projs + ["General"])))
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

# --- CALLBACKS (ERROR PROTECTION) ---
def reset_search():
    st.session_state["omni_search_input"] = ""

# --- MAIN APP ---
def main():
    if 'logged_in' not in st.session_state: st.session_state['logged_in'] = False
    if 'omni_search_input' not in st.session_state: st.session_state['omni_search_input'] = ""

    if not st.session_state['logged_in']:
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.title("🚀 RBS TaskHub")
            with st.container(border=True):
                email_input = st.text_input("Enter Work Email:")
                if st.button("Login", use_container_width=True):
                    email = email_input.lower().strip()
                    user_record = verify_user_in_db(email)
                    if user_record:
                        st.session_state.update({'logged_in': True, 'user': user_record['email'], 
                                               'user_role': user_record['role'], 'user_name': user_record['name']})
                        st.rerun()
                    else: st.error("🚫 Access Denied.")
    else:
        current_user, user_role, user_name = st.session_state['user'], st.session_state['user_role'], st.session_state['user_name']
        is_manager = (user_role == 'manager')
        
        with st.sidebar:
            st.markdown(f"### 💼 RBS Workspace\n**{user_name}** ({user_role.title()})")
            nav_mode = option_menu(None, options=["Dashboard", "New Task"] + (["Team Master"] if is_manager else []), 
                                   icons=["journal-bookmark", "plus-circle", "people-fill"],
                                   styles={"nav-link-selected": {"background-color": "#ff4b4b"}})
            if st.button("Logout", use_container_width=True): st.session_state['logged_in'] = False; st.rerun()

        if nav_mode == "Team Master":
            st.title("👥 Team Master")
            # ... (Team management code preserved as per your source)
            users = supabase.table("user_master").select("*").order("name").execute().data
            for u in users:
                with st.container(border=True):
                    c1, c2, c3 = st.columns([3, 3, 1])
                    c1.write(f"**{u['name']}**"); c2.write(f"`{u['email']}`")
                    if c3.button("Toggle", key=f"t_{u['email']}"): toggle_user_status(u['email'], u['status']); st.rerun()

        elif nav_mode == "New Task":
            st.header("✨ Create New Task")
            _, all_p, all_c = load_data_efficiently(None)
            t_desc = st.text_input("Description")
            c1, c2 = st.columns(2)
            # Sexy Hybrid Inputs for RBS
            with c1: proj = st.selectbox("Project Reference", all_p + ["Add New..."])
            if proj == "Add New...": proj = st.text_input("Type New Project Name")
            with c2: coord = st.selectbox("Point of Contact", all_c + ["Add New..."])
            if coord == "Add New...": coord = st.text_input("Type New Contact Name")
            
            c3, c4 = st.columns(2)
            e_sub = c3.text_input("Email Subject")
            pts = c4.text_area("Detailed Points")
            
            c5, c6, c7 = st.columns(3)
            ass_to = c5.selectbox("Assign To", ["Unassigned"] + get_active_users())
            prio = c6.selectbox("Priority", ["🔥 High", "⚡ Medium", "🧊 Low"])
            due = c7.date_input("Due Date", value=date.today())
            if st.button("🚀 Create Task", type="primary"):
                if add_task(current_user, ass_to if ass_to != "Unassigned" else None, t_desc, prio, due, proj, coord, e_sub, pts):
                    st.toast("Task Created!"); st.rerun()

        elif nav_mode == "Dashboard":
            view_email = None
            if is_manager:
                c_filter, c_title = st.columns([1, 3])
                view_target = c_filter.selectbox("View User:", ["All Users"] + get_active_users())
                if view_target != "All Users": view_email = view_target
                c_title.title("📔 Operational Diary")
            else: st.title("📔 My Diary"); view_email = current_user
            
            df, all_p, all_c = load_data_efficiently(view_email)

            # --- SEARCH BAR (FIXED LOGIC) ---
            st.markdown('<div class="search-highlight">', unsafe_allow_html=True)
            sc1, sc2 = st.columns([5, 1])
            search_q = sc1.text_input("🔍 Omni-Search", placeholder="Search task, project, or person...", 
                                      label_visibility="collapsed", key="omni_search_input")
            if sc2.button("🧹 Clear", on_click=reset_search): st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)

            if not df.empty:
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
                        t_label = f"{icon} {'[LATE] ' if is_late and 'Completed' not in sel_filter else ''}{row['due_date'].strftime('%d-%b')} | {row['task_desc']}"
                        
                        with st.expander(t_label):
                            if is_late and "Completed" not in sel_filter: st.markdown('<div class="alert-text-overdue">⚠️ ACTION REQUIRED: OVERDUE</div>', unsafe_allow_html=True)
                            
                            with st.form(key=f"edit_{row['id']}"):
                                # ROW 1: Project and Coordinator (PROFESSIONAL Hybrid)
                                r1c1, r1c2 = st.columns(2)
                                edit_p = r1c1.selectbox("Project Reference", all_p + ["New Entry..."], 
                                                        index=all_p.index(row['project_ref']) if row['project_ref'] in all_p else 0)
                                if edit_p == "New Entry...": edit_p = r1c1.text_input("Type Project Name", value=row['project_ref'], key=f"np_{row['id']}")
                                
                                edit_c = r1c2.selectbox("Point of Contact", all_c + ["New Entry..."],
                                                        index=all_c.index(row['coordinator']) if row['coordinator'] in all_c else 0)
                                if edit_c == "New Entry...": edit_c = r1c2.text_input("Type Contact Name", value=row['coordinator'], key=f"nc_{row['id']}")

                                # ROW 2: Description, Priority, Date
                                r2c1, r2c2, r2c3 = st.columns([5, 2, 2])
                                n_desc = r2c1.text_input("Task Description", value=row['task_desc'])
                                n_prio = r2c2.selectbox("Prio", ["🔥 High", "⚡ Medium", "🧊 Low"], index=["🔥 High", "⚡ Medium", "🧊 Low"].index(row['priority']))
                                n_date = r2c3.date_input("Due Date", value=row['due_date'])
                                
                                # ROW 3: Remarks and Points
                                n_rem = st.text_input("Recent Update / Remarks", value=row['staff_remarks'])
                                n_pts = st.text_area("Detailed History / Email Body", value=row.get('points', ''), height=100)
                                
                                # ROW 4: Action Buttons
                                b1, b2, b3 = st.columns([1, 2, 1])
                                if b1.form_submit_button("💾 Save Update"):
                                    if update_task_full(row['id'], n_desc, n_date, n_prio, n_rem, row['assigned_to'], n_pts, row['email_subject'], edit_c, edit_p, is_manager):
                                        st.toast("Stabilized!"); st.rerun()
                                if "Completed" not in sel_filter:
                                    c_note = b2.text_input("Final Closing Remark", key=f"cn_{row['id']}")
                                    if b3.form_submit_button("✅ Close Task", type="primary"):
                                        if c_note: update_task_status(row['id'], "Completed", c_note); st.rerun()
                                        else: st.warning("Note required to close.")
                                else:
                                    if b3.form_submit_button("🔄 Re-Open"): update_task_status(row['id'], "Open"); st.rerun()
            else: st.info("👋 Logic clear. No tasks found.")

if __name__ == "__main__": main()
