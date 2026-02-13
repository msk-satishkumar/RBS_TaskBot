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

# --- MSK STYLE CSS (STABILIZED & FLUSH ALIGNMENT) ---
st.markdown("""
<style>
    .block-container { padding-top: 1rem !important; padding-bottom: 1rem !important; }
    p, .stMarkdown { font-size: 14px !important; margin-bottom: 0px !important; }
    h1, h2, h3 { margin-bottom: 0px !important; margin-top: 0rem !important; }
    
    .streamlit-expanderHeader { 
        padding: 12px 20px !important;
        background-color: #fcfcfc; border-radius: 10px; font-weight: 700;
        border: 1px solid #eee; transition: 0.3s;
    }
    
    .stButton button { border-radius: 8px; font-weight: 600; height: 2.8rem; }
    
    /* Sexy Professional Search Box Overlay - Margin-top removed to kill extra line gap */
    .search-highlight {
        background-color: #f1f3f4;
        padding: 12px 15px; border-radius: 12px;
        margin-top: 0px !important; 
        margin-bottom: 15px; border-left: 6px solid #ff4b4b;
    }
</style>
""", unsafe_allow_html=True)

# --- CONFIGURATION & CONNECTION ---
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

@st.cache_resource
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

# --- STABILIZED DATA LOADING ---
def load_data_efficiently(target_email=None):
    query = supabase.table("tasks").select("*").order("due_date", desc=False)
    if target_email: query = query.eq("assigned_to", target_email)
    res = query.execute()
    df = pd.DataFrame(res.data) if res.data else pd.DataFrame()
    
    if not df.empty:
        df['due_date'] = pd.to_datetime(df['due_date'], errors='coerce').dt.date
        df['due_date'] = df['due_date'].fillna(date.today())
        used_coords = df['coordinator'].dropna().unique().tolist()
        used_projs = df['project_ref'].dropna().unique().tolist()
    else:
        used_coords, used_projs = [], []
        
    master_projs = supabase.table("projects").select("name").execute().data
    all_p = sorted(list(set([r['name'] for r in master_projs] + used_projs + ["General"])))
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

# --- CALLBACKS ---
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
                e_in = st.text_input("Enter Work Email:")
                if st.button("Login", use_container_width=True):
                    email = e_in.lower().strip()
                    user = verify_user_in_db(email)
                    if user:
                        st.session_state.update({'logged_in': True, 'user': user['email'], 'user_role': user['role'], 'user_name': user['name']})
                        st.rerun()
                    else: st.error("🚫 Access Denied.")
    else:
        current_user, user_role, user_name = st.session_state['user'], st.session_state['user_role'], st.session_state['user_name']
        is_manager = (user_role == 'manager')
        
        with st.sidebar:
            st.markdown(f"### 💼 RBS Workspace\n**{user_name}** ({user_role.title()})")
            nav_mode = option_menu(None, options=["Dashboard", "New Task"], 
                                   icons=["journal-bookmark", "plus-circle"], styles={"nav-link-selected": {"background-color": "#ff4b4b"}})
            if st.button("Logout", use_container_width=True): st.session_state['logged_in'] = False; st.rerun()

        if nav_mode == "New Task":
            st.header("✨ Create New Task")
            _, all_p, all_c = load_data_efficiently(None)
            t_desc = st.text_input("Description")
            c1, c2 = st.columns(2)
            with c1: 
                p_ref = st.selectbox("Project Reference", all_p + ["New..."])
                if p_ref == "New...": p_ref = st.text_input("Type Project Name")
            with c2: 
                p_coord = st.selectbox("Point of Contact", all_c + ["New..."])
                if p_coord == "New...": p_coord = st.text_input("Type Contact Name")
            c3, c4 = st.columns(2)
            e_sub, pts = c3.text_input("Email Subject"), c4.text_area("Detailed Points")
            c5, c6, c7 = st.columns(3)
            ass_to = c5.selectbox("Assign To", ["Unassigned"] + get_active_users())
            prio, due = c6.selectbox("Priority", ["🔥 High", "⚡ Medium", "🧊 Low"]), c7.date_input("Due Date", value=date.today())
            if st.button("🚀 Create Task", type="primary"):
                if add_task(current_user, ass_to if ass_to != "Unassigned" else None, t_desc, prio, due, p_ref, p_coord, e_sub, pts):
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

            # --- SEARCH BAR (GAP FIXED: Margin-top and Extra spacing removed) ---
            st.markdown('<div class="search-highlight">', unsafe_allow_html=True)
            sc1, sc2 = st.columns([5, 1])
            search_q = sc1.text_input("🔍 Omni-Search", label_visibility="collapsed", key="omni_search_input", placeholder="Search task, project, or person...")
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
                                r1c1, r1c2 = st.columns(2)
                                edit_p = r1c1.selectbox("Project Reference", all_p + ["New..."], index=all_p.index(row['project_ref']) if row['project_ref'] in all_p else 0)
                                if edit_p == "New...": edit_p = r1c1.text_input("New Name", value=row['project_ref'], key=f"np_{row['id']}")
                                edit_c = r1c2.selectbox("Point of Contact", all_c + ["New..."], index=all_c.index(row['coordinator']) if row['coordinator'] in all_c else 0)
                                if edit_c == "New...": edit_c = r1c2.text_input("New Name", value=row['coordinator'], key=f"nc_{row['id']}")

                                r2c1, r2c2, r2c3 = st.columns([5, 2, 2])
                                n_desc = r2c1.text_input("Task Description", value=row['task_desc'])
                                n_prio = r2c2.selectbox("Prio", ["🔥 High", "⚡ Medium", "🧊 Low"], index=["🔥 High", "⚡ Medium", "🧊 Low"].index(row['priority']))
                                n_date = r2c3.date_input("Due Date", value=row['due_date'])
                                n_rem = st.text_input("Remarks", value=row['staff_remarks'])
                                n_pts = st.text_area("Detailed Body", value=row.get('points', ''), height=100)
                                
                                b1, b2, b3 = st.columns([1, 2, 1])
                                if b1.form_submit_button("💾 Save Update"):
                                    if update_task_full(row['id'], n_desc, n_date, n_prio, n_rem, row['assigned_to'], n_pts, row['email_subject'], edit_c, edit_p, is_manager):
                                        st.toast("Saved!"); st.rerun()
                                if "Completed" not in sel_filter:
                                    c_n = b2.text_input("Note", key=f"cn_{row['id']}", placeholder="Closing note...")
                                    if b3.form_submit_button("✅ Close", type="primary"):
                                        if c_n: update_task_status(row['id'], "Completed", c_n); st.rerun()
                                else:
                                    if b3.form_submit_button("🔄 Re-Open"): update_task_status(row['id'], "Open"); st.rerun()
            else: st.info("👋 No tasks found.")

if __name__ == "__main__": main()
