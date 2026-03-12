import streamlit as st
import pandas as pd
from supabase import create_client
from datetime import date, timedelta

# --- INIT SUPABASE ---
def init_supabase():
    try:
        # Check nested connections first (standard for Streamlit)
        if "connections" in st.secrets and "supabase" in st.secrets["connections"]:
            url = st.secrets["connections"]["supabase"]["SUPABASE_URL"]
            key = st.secrets["connections"]["supabase"]["SUPABASE_KEY"]
        else:
            url = st.secrets["SUPABASE_URL"]
            key = st.secrets["SUPABASE_KEY"]
        return create_client(url, key)
    except Exception as e:
        st.error(f"🚨 Failed to initialize Supabase: {e}")
        st.stop()

supabase = init_supabase()

# --- STATUS MAPPING HELPERS ---
def map_db_status(ui_status):
    if not ui_status: return None
    mapping = {
        "Yet start": "Yet to Start", 
        "On Hold": "Hold",
        "Complated": "Completed"
    }
    return mapping.get(ui_status, ui_status)

def map_ui_status(db_status):
    if not db_status: return "Yet start"
    mapping = {
        "Yet to Start": "Yet start",
        "Yet To Start": "Yet start", 
        "Hold": "On Hold",
        "Completed": "Complated"
    }
    return mapping.get(db_status, db_status)

# --- AUTH & MASTERS ---
def verify_user_in_db(email):
    try:
        response = supabase.table("user_master").select("*").eq("email", email).eq("status", "active").execute()
        return response.data[0] if response.data else None
    except Exception as e:
        st.error(f"🚨 Auth Error: {e}")
        return None

def get_active_users():
    try:
        response = supabase.table("user_master").select("email").eq("status", "active").execute()
        return [u['email'] for u in response.data] if response.data else []
    except Exception as e:
        st.error(f"🚨 Master Data Error (Users): {e}")
        return []

# --- COMM PREFS ---
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

# --- DATA LOADING ---
@st.cache_data(show_spinner=False, ttl=60)
def fetch_tasks(target_email=None):
    """Fetches raw task data from Supabase."""
    try:
        query = supabase.table("tasks").select("*")
        if target_email: query = query.eq("assigned_to", target_email)
        res = query.execute()
        return res.data if res.data else []
    except Exception as e:
        st.error(f"🚨 Data Fetch Error: {e}")
        return []

def process_task_data(raw_data):
    """Processes raw task data into a clean DataFrame and derives master lists."""
    if not raw_data:
        return pd.DataFrame(), ["General"], ["General"], ["General"], ["Task", "Followup", "Project"]

    df = pd.DataFrame(raw_data)
    df['due_date'] = pd.to_datetime(df['due_date'], errors='coerce').dt.date
    df['due_date'] = df['due_date'].fillna(date.today())
    
    if 'client_ref' not in df.columns: df['client_ref'] = 'General'
    if 'task_type' not in df.columns: df['task_type'] = 'Task'
    
    df = df.sort_values(by="due_date", ascending=True)
    
    # Deriving master lists from existing records
    used_coords = sorted(df['coordinator'].dropna().unique().tolist())
    used_projs = sorted(df['project_ref'].dropna().unique().tolist())
    used_clients = sorted(df['client_ref'].dropna().unique().tolist())

    all_p = sorted(list(set(used_projs + ["General"])))
    all_c = sorted(list(set(["Sales Team", "Client", "Support Team", "Internal", "Management"] + used_coords)))
    all_client = sorted(list(set(used_clients + ["General"])))
    all_t = ["Task", "Followup", "Project"]

    return df, all_p, all_c, all_client, all_t

# --- DATABASE WRITES ---
def add_task(created_by, assigned_to, task_desc, priority, due_date, project_ref, coordinator, email_subject, points, client_ref=None, task_type="Task", project_status=None):
    def safe_str(val):
        return str(val) if val is not None and not pd.isna(val) else ""

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
        "client_ref": safe_str(client_ref) or "General",
        "task_type": safe_str(task_type) or "Task",
        "project_status": safe_str(project_status) if task_type == "Project" else None
    }
    
    try:
        supabase.table("tasks").insert(data).execute()
        return True
    except Exception as e:
        st.error(f"🚨 DB Error during Insert: {e}")
        return False

def update_task_status(task_id, new_status, remarks=None):
    data = {"status": new_status}
    if remarks: data["staff_remarks"] = remarks
    
    try:
        clean_id = int(float(task_id))
    except (ValueError, TypeError):
        clean_id = str(task_id)
        
    try:
        supabase.table("tasks").update(data).eq("id", clean_id).execute()
        return True
    except Exception as e:
        st.error(f"🚨 DB Error during Status Update: {e}")
        return False

def update_task_full(task_id, new_desc, new_date, new_prio, new_remarks, new_assign, new_points, new_subject, new_coord, new_proj, is_manager, new_client=None, task_type="Task", project_status=None):
    def safe_str(val):
        return str(val) if val is not None and not pd.isna(val) else ""

    data = { 
        "task_desc": safe_str(new_desc), 
        "due_date": str(new_date), 
        "priority": safe_str(new_prio),
        "staff_remarks": safe_str(new_remarks), 
        "points": safe_str(new_points), 
        "email_subject": safe_str(new_subject),
        "coordinator": safe_str(new_coord) or "General", 
        "project_ref": safe_str(new_proj) or "General",
        "client_ref": safe_str(new_client) or "General",
        "task_type": safe_str(task_type) or "Task",
        "project_status": safe_str(project_status) if task_type == "Project" else None
    }
    
    if is_manager and new_assign: 
        data["assigned_to"] = safe_str(new_assign)
        
    try:
        clean_id = int(float(task_id))
    except (ValueError, TypeError):
        clean_id = str(task_id)
        
    try:
        supabase.table("tasks").update(data).eq("id", clean_id).execute()
        return True
    except Exception as e:
        st.error(f"🚨 DB Error during Edit Update: {e}")
        return False

def bump_task_date(task_id, current_date):
    new_date = current_date + timedelta(days=1)
    try:
        clean_id = int(float(task_id))
    except (ValueError, TypeError):
        clean_id = str(task_id)
        
    try:
        supabase.table("tasks").update({"due_date": str(new_date)}).eq("id", clean_id).execute()
        return True
    except Exception as e:
        st.error(f"🚨 DB Error during Bump: {e}")
        return False
