import streamlit as st
from supabase import create_client, Client
import pandas as pd
import re

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="RBS TaskHub", layout="wide")

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
def add_task_to_db(created_by, assigned_to, task_desc):
    try:
        data = {
            "created_by": created_by,
            "assigned_to": assigned_to,
            "task_desc": task_desc,
            "status": "Open",
            "staff_remarks": "",
            "manager_remarks": ""
        }
        supabase.table("tasks").insert(data).execute()
        return True
    except Exception as e:
        st.error(f"Error saving task: {e}")
        return False

def get_tasks(user_email, is_admin=False):
    try:
        if is_admin:
            response = supabase.table("tasks").select("*").neq("status", "Completed").execute()
        else:
            response = supabase.table("tasks").select("*").eq("assigned_to", user_email).neq("status", "Completed").execute()
            
        if response.data:
            return pd.DataFrame(response.data)
        else:
            return pd.DataFrame()
    except Exception as e:
        st.error(f"Database Error: {e}")
        return pd.DataFrame()

def update_task_status(task_id, new_status, staff_remark, manager_remark):
    try:
        data = {
            "status": new_status,
            "staff_remarks": staff_remark,
            "manager_remarks": manager_remark
        }
        supabase.table("tasks").update(data).eq("id", task_id).execute()
        return True
    except Exception as e:
        st.error(f"Update failed: {e}")
        return False

# --- PARSING ENGINE ---
def parse_command(command_text, current_user):
    assigned_to = current_user 
    task_detail = command_text
    
    # Simple Team Map (We can make this dynamic later)
    team_map = {
        "praveen": "praveen@rbsgo.com",
        "arjun": "arjun@rbsgo.com",
        "msk": "msk@rbsgo.com",
        "prasanna": "prasanna@rbsgo.com",
        "chris": "chris@rbsgo.com"
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
        st.title("☁️ RBS TaskHub")
        st.caption("Secure Internal System")
        
        col1, col2 = st.columns(2)
        with col1:
            email = st.text_input("Enter Work Email:")
            if st.button("Login"):
                if email.endswith(COMPANY_DOMAIN):
                    st.session_state['logged_in'] = True
                    st.session_state['user'] = email
                    st.rerun()
                else:
                    st.error(f"Restricted Access. Only {COMPANY_DOMAIN} allowed.")

    # --- DASHBOARD ---
    else:
        current_user = st.session_state['user']
        is_admin = (current_user == ADMIN_EMAIL)
        
        with st.sidebar:
            st.info(f"👤 {current_user}")
            if is_admin:
                st.warning("⚡ HEAD MODE")
            
            if st.button("Logout"):
                st.session_state['logged_in'] = False
                st.rerun()

        st.title("✅ Collaborative Task Board")

        # 1. NEW TASK INPUT
        with st.container(border=True):
            col1, col2 = st.columns([4, 1])
            with col1:
                cmd = st.text_input("New Task Command", placeholder="e.g. 'Ask Praveen to prepare the EOD report'")
            with col2:
                if st.button("Assign Task", type="primary", use_container_width=True):
                    if cmd:
                        who, what = parse_command(cmd, current_user)
                        if add_task_to_db(current_user, who, what):
                            st.toast(f"✅ Assigned to {who}")
                            st.rerun()

        # 2. TASK LIST
        st.divider()
        df = get_tasks(current_user, is_admin)

        if df.empty:
            st.info("No active tasks found. You are all caught up!")
        else:
            st.subheader(f"📋 Pending Tasks ({len(df)})")
            # Sort: Newest IDs first
            df = df.sort_values(by="id", ascending=False)

            for index, row in df.iterrows():
                with st.container(border=True):
                    c1, c2, c3, c4 = st.columns([2, 2, 2, 1])
                    
                    with c1:
                        st.markdown(f"**{row['task_desc']}**")
                        st.caption(f"From: {row['created_by']} | To: {row['assigned_to']}")
                    
                    with c2:
                        curr_rem = row['staff_remarks'] if row['staff_remarks'] else ""
                        new_rem = st.text_input("Remark", value=curr_rem, key=f"r_{row['id']}")
                    
                    with c3:
                        mgr_rem = row['manager_remarks'] if row['manager_remarks'] else ""
                        new_mgr = st.text_input("Head Reply", value=mgr_rem, key=f"m_{row['id']}", disabled=not is_admin)
                    
                    with c4:
                        status_opts = ["Open", "In Progress", "Pending Info", "Completed"]
                        try:
                            s_idx = status_opts.index(row['status'])
                        except:
                            s_idx = 0
                        new_stat = st.selectbox("Status", status_opts, index=s_idx, key=f"s_{row['id']}", label_visibility="collapsed")
                        
                        if st.button("Update", key=f"b_{row['id']}"):
                            update_task_status(row['id'], new_stat, new_rem, new_mgr)
                            st.rerun()

if __name__ == "__main__":
    main()
