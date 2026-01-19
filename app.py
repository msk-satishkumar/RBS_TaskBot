import streamlit as st
from supabase import create_client, Client
import pandas as pd
from datetime import datetime, date
from streamlit_gsheets import GSheetsConnection

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="RBS TaskHub", layout="wide", page_icon="🚀")

# --- CUSTOM CSS FOR COMPACT "DIARY" LOOK ---
st.markdown("""
<style>
    /* Reduce padding inside task cards */
    div[data-testid="stVerticalBlockBorderWrapper"] > div {
        padding: 12px !important; 
        padding-bottom: 8px !important;
    }
    /* Reduce gap between cards */
    div[data-testid="stVerticalBlock"] > div {
        gap: 0.5rem !important;
    }
    /* Compact Buttons */
    .stButton button {
        height: 35px;
        padding-top: 0px;
        padding-bottom: 0px;
    }
    /* Tighter Text */
    p, h3 {
        margin-bottom: 4px !important;
    }
</style>
""", unsafe_allow_html=True)

# --- CONFIGURATION ---
COMPANY_DOMAIN = "@rbsgo.com"
ADMIN_EMAIL = "msk@rbsgo.com"

TEAM_MEMBERS = ["msk@rbsgo.com", "praveen@rbsgo.com", "arjun@rbsgo.com", 
                "prasanna@rbsgo.com", "chris@rbsgo.com", "sarah@rbsgo.com"]

# --- SECURE CONNECTION ---
try:
    SUPABASE_URL = st.secrets["SUPABASE_URL"]
    SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
except FileNotFoundError:
    st.error("🚨 Secrets not found! Please configure secrets.")
    st.stop()

@st.cache_resource
def init_supabase():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

supabase = init_supabase()

# --- GOOGLE SHEETS SYNC ENGINE ---
def sync_projects():
    try:
        conn = st.connection("gsheets", type=GSheetsConnection)
        # Reading from the 'ROADMAP' tab in your sheet
        df = conn.read(worksheet="ROADMAP") 
        count = 0
        for index, row in df.iterrows():
            data = {
                "name": row['Interface Name'],
                "status": row['Stage'],
                "target_date": str(row['Target Date']),
                "description": row['Description'],
                "client": row['Client']
            }
            # Upsert ensures we don't create duplicates
            supabase.table("projects").upsert(data, on_conflict="name").execute()
            count += 1
        return True, f"Synced {count} Projects!"
    except Exception as e:
        return False, f"Sync Error: {str(e)}"

def get_projects():
    try:
        response = supabase.table("projects").select("name").execute()
        return [row['name'] for row in response.data] if response.data else []
    except:
        return []

# --- DATABASE FUNCTIONS ---
def add_task(created_by, assigned_to, task_desc, priority, due_date, project_ref):
    try:
        final_date = str(due_date) if due_date else str(date.today())
        data = {
            "created_by": created_by,
            "assigned_to": assigned_to,
            "task_desc": task_desc,
            "status": "Open",
            "priority": priority,
            "due_date": final_date,
            "project_ref": project_ref,
            "staff_remarks": "",
            "manager_remarks": ""
        }
        supabase.table("tasks").insert(data).execute()
        return True
    except Exception as e:
        st.error(f"Error: {e}")
        return False

def get_tasks(user_email, is_admin=False):
    query = supabase.table("tasks").select("*")
    if not is_admin:
        query = query.eq("assigned_to", user_email)
    response = query.execute()
    return pd.DataFrame(response.data) if response.data else pd.DataFrame()

def update_task_status(task_id, new_status, remarks=None):
    try:
        data = {"status": new_status}
        if remarks: data["staff_remarks"] = remarks
        supabase.table("tasks").update(data).eq("id", task_id).execute()
        return True
    except:
        return False

# --- MAIN APP ---
def main():
    if 'logged_in' not in st.session_state:
        st.session_state['logged_in'] = False

    # --- LOGIN SCREEN ---
    if not st.session_state['logged_in']:
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.title("🚀 RBS TaskHub")
            with st.container(border=True):
                email = st.text_input("Enter Work Email:")
                if st.button("Login", use_container_width=True):
                    if email.endswith(COMPANY_DOMAIN):
                        st.session_state['logged_in'] = True
                        st.session_state['user'] = email
                        st.rerun()
                    else:
                        st.error(f"Restricted Access. {COMPANY_DOMAIN} only.")

    # --- DASHBOARD ---
    else:
        current_user = st.session_state['user']
        is_admin = (current_user == ADMIN_EMAIL)
        
        with st.sidebar:
            st.title("🎛️ Menu")
            st.info(f"👤 {current_user.split('@')[0].title()}")
            
            nav_mode = st.radio("Go To:", ["📔 Your Diary", "➕ Create Task", "🔄 Project Sync"])
            
            st.divider()
            if st.button("Logout", use_container_width=True):
                st.session_state['logged_in'] = False
                st.rerun()

        # --- VIEW: SYNC PROJECTS ---
        if nav_mode == "🔄 Project Sync":
            st.header("🔗 Google Sheets Integration")
            st.info("Pull latest projects from Master DB (ROADMAP Tab)")
            
            if st.button("🚀 Sync Projects Now", type="primary"):
                with st.spinner("Connecting to Google Drive..."):
                    success, msg = sync_projects()
                    if success: st.success(msg)
                    else: st.error(msg)
            
            projects = get_projects()
            if projects:
                st.write(f"**Active Projects ({len(projects)}):**")
                st.dataframe(projects, use_container_width=True)

        # --- VIEW: CREATE TASK ---
        elif nav_mode == "➕ Create Task":
            st.header("✨ Create New Task")
            with st.container(border=True):
                # Project Dropdown
                project_list = get_projects()
                selected_project = st.selectbox("📂 Project / Interface (Optional)", ["General"] + project_list)
                
                c1, c2 = st.columns([1, 3])
                with c1:
                    assign_type = st.radio("Assign To:", ["Myself", "Teammate"], horizontal=True)
                    if assign_type == "Teammate":
                        peers = [m for m in TEAM_MEMBERS if m != current_user]
                        target_user = st.selectbox("Select User", peers)
                    else:
                        target_user = current_user
                
                with c2:
                    desc = st.text_input("Task Description", placeholder="e.g. Fix API Error")
                
                c3, c4 = st.columns(2)
                with c3:
                    prio = st.selectbox("Priority", ["🔥 High", "⚡ Medium", "🧊 Low"])
                with c4:
                    due = st.date_input("Target Date (Default: Today)", value=None)
                
                if st.button("🚀 Add Task", type="primary", use_container_width=True):
                    if desc:
                        if add_task(current_user, target_user, desc, prio, due, selected_project):
                            st.balloons()
                            st.success("✅ Task Added!")
                    else:
                        st.warning("⚠️ Enter a description.")

        # --- VIEW: COMPACT DIARY ---
        elif nav_mode == "📔 Your Diary":
            st.title("📔 Your Diary")

            df = get_tasks(current_user, is_admin)
            
            if not df.empty:
                df['due_date'] = pd.to_datetime(df['due_date'], errors='coerce')
                today_ts = pd.Timestamp.now().normalize()
                
                # Default: Show ALL
                if 'filter_view' not in st.session_state: st.session_state['filter_view'] = 'All'

                # FILTER BUTTONS (Reordered: All First)
                c1, c2, c3, c4 = st.columns(4)
                if c1.button("📂 All Pending"): st.session_state['filter_view'] = 'All'
                if c2.button("⚡ Today"): st.session_state['filter_view'] = 'Today'
                if c3.button("📅 Tomorrow"): st.session_state['filter_view'] = 'Tomorrow'
                if c4.button("🚨 Overdue"): st.session_state['filter_view'] = 'Overdue'

                view = st.session_state['filter_view']
                active_df = df[df['status'] != 'Completed'].copy()
                
                if view == 'Today': 
                    filtered_df = active_df[active_df['due_date'] == today_ts]
                    st.caption("Focus: Today")
                elif view == 'Tomorrow': 
                    filtered_df = active_df[active_df['due_date'] == today_ts + pd.Timedelta(days=1)]
                    st.caption("Focus: Tomorrow")
                elif view == 'Overdue': 
                    filtered_df = active_df[active_df['due_date'] < today_ts]
                    st.caption("Focus: Overdue")
                else: 
                    filtered_df = active_df
                    st.caption("Focus: All Tasks")

                if filtered_df.empty:
                    st.success("🎉 List empty!")
                else:
                    # Sort: Date (soonest first) -> Priority
                    filtered_df = filtered_df.sort_values(by=["due_date", "priority"], ascending=[True, True])
                    
                    for index, row in filtered_df.iterrows():
                        # --- COMPACT CARD LAYOUT ---
                        with st.container(border=True):
                            # Columns: Date(3) | Task(5) | Action(2)
                            c1, c2, c3 = st.columns([3, 5, 2])
                            
                            with c1:
                                # Date & Project Tag
                                date_str = row['due_date'].strftime('%d-%b') if pd.notnull(row['due_date']) else "No Date"
                                st.markdown(f"**📅 {date_str}**")
                                proj_label = row['project_ref'][:15]+".." if row['project_ref'] and len(row['project_ref']) > 15 else (row['project_ref'] or "General")
                                st.caption(f"{row['priority']} | {proj_label}")
                                
                            with c2:
                                # Task & Remarks
                                st.markdown(f"**{row['task_desc']}**")
                                if row['staff_remarks']: st.caption(f"📝 {row['staff_remarks']}")
                                # Invisible label remark box
                                new_rem = st.text_input("Remark", key=f"r_{row['id']}", label_visibility="collapsed", placeholder="Add update...")
                                if new_rem: update_task_status(row['id'], row['status'], new_rem)

                            with c3:
                                # Done Button
                                if st.button("✅ Done", key=f"d_{row['id']}", type="primary", use_container_width=True):
                                    update_task_status(row['id'], "Completed")
                                    st.rerun()
            else:
                st.info("👋 No tasks found.")

if __name__ == "__main__":
    main()
