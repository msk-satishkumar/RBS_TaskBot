import streamlit as st
from supabase import create_client, Client
import pandas as pd
import re
from datetime import datetime, date

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="RBS TaskHub", layout="wide", page_icon="🚀")

# --- CONFIGURATION ---
COMPANY_DOMAIN = "@rbsgo.com"
ADMIN_EMAIL = "msk@rbsgo.com"

# --- SECURE CONNECTION ---
try:
    SUPABASE_URL = st.secrets["SUPABASE_URL"]
    SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
except FileNotFoundError:
    st.error("🚨 Secrets not found! Please configure secrets on Streamlit Cloud.")
    st.stop()

@st.cache_resource
def init_supabase():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

try:
    supabase = init_supabase()
except Exception as e:
    st.error(f"Failed to connect to Database: {e}")
    st.stop()

# --- DATABASE FUNCTIONS ---

def log_activity(user_email, action, details):
    """Records an action in the history log"""
    try:
        data = {"user_email": user_email, "action": action, "details": details}
        supabase.table("activity_logs").insert(data).execute()
    except Exception as e:
        print(f"Log Error: {e}")

def add_task_to_db(created_by, assigned_to, task_desc, priority, due_date):
    try:
        data = {
            "created_by": created_by,
            "assigned_to": assigned_to,
            "task_desc": task_desc,
            "status": "Open",
            "priority": priority,
            "due_date": str(due_date) if due_date else None,
            "staff_remarks": "",
            "manager_remarks": ""
        }
        supabase.table("tasks").insert(data).execute()
        # Log it
        log_activity(created_by, "Created Task", f"Assigned to {assigned_to}: {task_desc[:30]}...")
        return True
    except Exception as e:
        st.error(f"Error saving task: {e}")
        return False

def get_tasks(user_email, is_admin=False):
    try:
        query = supabase.table("tasks").select("*")
        if not is_admin:
            query = query.eq("assigned_to", user_email)
        
        response = query.order("id", desc=True).execute()
        return pd.DataFrame(response.data) if response.data else pd.DataFrame()
    except Exception as e:
        st.error(f"Database Error: {e}")
        return pd.DataFrame()

def get_activity_logs():
    try:
        response = supabase.table("activity_logs").select("*").order("id", desc=True).limit(20).execute()
        return pd.DataFrame(response.data) if response.data else pd.DataFrame()
    except Exception as e:
        return pd.DataFrame()

def update_task(task_id, status, staff_remark, manager_remark, user_email):
    try:
        data = {
            "status": status,
            "staff_remarks": staff_remark,
            "manager_remarks": manager_remark
        }
        supabase.table("tasks").update(data).eq("id", task_id).execute()
        # Log it
        log_activity(user_email, "Updated Task", f"Task #{task_id} -> {status}")
        return True
    except Exception as e:
        st.error(f"Update failed: {e}")
        return False

# --- PARSING ENGINE ---
def parse_command(command_text, current_user):
    assigned_to = current_user 
    task_detail = command_text
    
    # Team Mapping
    team_map = {
        "praveen": "praveen@rbsgo.com",
        "arjun": "arjun@rbsgo.com",
        "msk": "msk@rbsgo.com",
        "prasanna": "prasanna@rbsgo.com",
        "chris": "chris@rbsgo.com",
        "sarah": "sarah@rbsgo.com"
    }
    
    lower_cmd = command_text.lower()
    for name, email in team_map.items():
        if name in lower_cmd:
            assigned_to = email
            task_detail = re.sub(name, "", task_detail, flags=re.IGNORECASE)
            task_detail = re.sub(r"^(ask|tell|assign|to|request)\s+", "", task_detail, flags=re.IGNORECASE).strip()
            break
            
    return assigned_to, task_detail

# --- MAIN APP ---
def main():
    if 'logged_in' not in st.session_state:
        st.session_state['logged_in'] = False

    # --- LOGIN SCREEN ---
    if not st.session_state['logged_in']:
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.title("🚀 RBS TaskHub")
            st.markdown("### Secure Internal Workspace")
            with st.container(border=True):
                email = st.text_input("Work Email Address")
                if st.button("Access Dashboard", type="primary", use_container_width=True):
                    if email.endswith(COMPANY_DOMAIN):
                        st.session_state['logged_in'] = True
                        st.session_state['user'] = email
                        st.rerun()
                    else:
                        st.error(f"🚫 Access Denied. {COMPANY_DOMAIN} only.")

    # --- DASHBOARD ---
    else:
        current_user = st.session_state['user']
        is_admin = (current_user == ADMIN_EMAIL)
        
        # Sidebar with Live Activity Feed
        with st.sidebar:
            st.title(f"👤 {current_user.split('@')[0].title()}")
            if is_admin:
                st.info("⚡ HEAD MODE")
            
            st.divider()
            st.subheader("📡 Live Activity")
            logs = get_activity_logs()
            if not logs.empty:
                for _, row in logs.iterrows():
                    # Format timestamp
                    ts = row['timestamp'][:16].replace("T", " ")
                    st.caption(f"**{row['user_email'].split('@')[0]}** {row['action']}")
                    st.text(f"{row['details']}")
                    st.markdown("---")
            
            if st.button("Logout", use_container_width=True):
                st.session_state['logged_in'] = False
                st.rerun()

        # MAIN TABS
        st.title("Task Command Center")
        tab1, tab2, tab3 = st.tabs(["📝 My Workspace", "👥 Team Overview", "📊 Analytics"])

        # --- TAB 1: CREATE & MANAGE ---
        with tab1:
            with st.expander("➕ Create New Task", expanded=True):
                c1, c2, c3, c4 = st.columns([3, 1, 1, 1])
                with c1:
                    cmd = st.text_input("Task Description / Command", placeholder="e.g. Ask Praveen to check logs")
                with c2:
                    priority = st.selectbox("Priority", ["🔥 High", "⚡ Medium", "🧊 Low"], index=1)
                with c3:
                    due_date = st.date_input("Due Date", min_value=date.today())
                with c4:
                    st.write("")
                    st.write("")
                    if st.button("Assign", type="primary", use_container_width=True):
                        if cmd:
                            who, what = parse_command(cmd, current_user)
                            if add_task_to_db(current_user, who, what, priority, due_date):
                                st.toast(f"Assigned to {who}")
                                st.rerun()

            # Load Tasks
            df = get_tasks(current_user, is_admin)
            
            if not df.empty:
                st.subheader("My Active Tasks")
                # Filter for non-completed if user prefers, or show all
                active_df = df.sort_values(by=["id"], ascending=False)

                for index, row in active_df.iterrows():
                    # Visual Card
                    border_color = "red" if "High" in row['priority'] else "grey"
                    with st.container(border=True):
                        col_a, col_b, col_c, col_d = st.columns([3, 2, 2, 1])
                        with col_a:
                            st.markdown(f"**{row['task_desc']}**")
                            st.caption(f"👤 {row['assigned_to']} | 📅 {row['due_date']} | {row['priority']}")
                        with col_b:
                            curr_rem = row['staff_remarks'] if row['staff_remarks'] else ""
                            new_rem = st.text_input("My Update", value=curr_rem, key=f"r_{row['id']}")
                        with col_c:
                            mgr_rem = row['manager_remarks'] if row['manager_remarks'] else ""
                            new_mgr = st.text_input("Feedback", value=mgr_rem, key=f"m_{row['id']}", disabled=not is_admin)
                        with col_d:
                            status_opts = ["Open", "In Progress", "Pending Info", "Completed"]
                            try:
                                s_idx = status_opts.index(row['status'])
                            except:
                                s_idx = 0
                            new_stat = st.selectbox("Status", status_opts, index=s_idx, key=f"s_{row['id']}", label_visibility="collapsed")
                            
                            if st.button("Save", key=f"b_{row['id']}"):
                                update_task(row['id'], new_stat, new_rem, new_mgr, current_user)
                                st.rerun()
            else:
                st.info("No tasks found.")

        # --- TAB 2: TEAM OVERVIEW (Admin Only) ---
        with tab2:
            if is_admin:
                st.subheader("Global Task List")
                st.dataframe(df, use_container_width=True)
            else:
                st.warning("Restricted to Head of Department.")

        # --- TAB 3: ANALYTICS ---
        with tab3:
            st.subheader("Team Performance Metrics")
            if not df.empty:
                c1, c2 = st.columns(2)
                
                with c1:
                    st.markdown("#### 🏆 Workload Distribution")
                    # Count tasks per person
                    task_counts = df['assigned_to'].value_counts()
                    st.bar_chart(task_counts)
                
                with c2:
                    st.markdown("#### 🚦 Status Breakdown")
                    status_counts = df['status'].value_counts()
                    st.bar_chart(status_counts, color="#ffaa00") # Custom color
            else:
                st.info("Not enough data for analytics yet.")

if __name__ == "__main__":
    main()
