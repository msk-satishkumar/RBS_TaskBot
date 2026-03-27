import streamlit as st
import pandas as pd
from datetime import datetime, date, timedelta
from streamlit_option_menu import option_menu
import json
import os

# --- CUSTOM MODULES ---
from utils.styles import apply_custom_styles
from utils.database import (
    verify_user_in_db, get_active_users, fetch_tasks, process_task_data,
    add_task, update_task_status, update_task_full, bump_task_date
)
from utils.ai import generate_variations

# --- USER PREFERENCES (persist across sessions) ---
_PREFS_FILE = os.path.join(os.path.dirname(__file__), 'user_preferences.json')

def load_user_prefs(email: str) -> dict:
    """Load saved preferences for a user from the local JSON store."""
    try:
        if os.path.exists(_PREFS_FILE):
            with open(_PREFS_FILE, 'r', encoding='utf-8') as f:
                all_prefs = json.load(f)
            return all_prefs.get(email, {})
    except Exception:
        pass
    return {}

def save_user_prefs(email: str, prefs: dict):
    """Persist preferences for a user to the local JSON store."""
    try:
        all_prefs = {}
        if os.path.exists(_PREFS_FILE):
            with open(_PREFS_FILE, 'r', encoding='utf-8') as f:
                all_prefs = json.load(f)
        all_prefs[email] = {**all_prefs.get(email, {}), **prefs}
        with open(_PREFS_FILE, 'w', encoding='utf-8') as f:
            json.dump(all_prefs, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="RBS TaskHub", layout="wide", page_icon="🚀")
apply_custom_styles()

# --- CONFIGURATION ---
COMPANY_DOMAIN = "@rbsgo.com"

# --- HELPER WRAPPERS ---
def load_data(target_email=None):
    """Wrapper for utilities to fetch and process task data."""
    raw = fetch_tasks(target_email)
    return process_task_data(raw)

# --- CALLBACKS ---
def reset_search():
    st.session_state["omni_search_input"] = ""

def reset_bumps():
    st.session_state['bumped_ids'] = set()

# --- MAIN APP ---
def main():
    # Session State Initialization
    if 'logged_in' not in st.session_state: st.session_state['logged_in'] = False
    if 'omni_search_input' not in st.session_state: st.session_state['omni_search_input'] = ""
    if 'bumped_ids' not in st.session_state: st.session_state['bumped_ids'] = set()
    if 'show_update_success' not in st.session_state: st.session_state['show_update_success'] = False
    if 'show_creation_success' not in st.session_state: st.session_state['show_creation_success'] = False
    # Sticky context after task creation (persist project/client/contact/type across reruns)
    if 'sticky_project' not in st.session_state: st.session_state['sticky_project'] = None
    if 'sticky_client' not in st.session_state: st.session_state['sticky_client'] = None
    if 'sticky_contact' not in st.session_state: st.session_state['sticky_contact'] = None
    if 'sticky_type' not in st.session_state: st.session_state['sticky_type'] = None
    if 'sticky_p_status' not in st.session_state: st.session_state['sticky_p_status'] = None
    # Dashboard generation counter: incrementing forces all expanders to reset/close
    if 'dashboard_gen' not in st.session_state: st.session_state['dashboard_gen'] = 0
    if 'highlight_task_id' not in st.session_state: st.session_state['highlight_task_id'] = None

    login_container = st.empty()

    if not st.session_state['logged_in']:
        with login_container.container():
            col1, col2, col3 = st.columns([1, 2, 1])
            with col2:
                st.title("🚀 RBS TaskHub")
                with st.container(border=True):
                    e_in = st.text_input("Enter Work Email:")
                    # Temporarily skipping password implementation as per user request
                    if st.button("Login", use_container_width=True):
                        email = e_in.lower().strip()
                        user = verify_user_in_db(email)
                        if user:
                            st.session_state.update({
                                'logged_in': True, 
                                'user': user['email'], 
                                'user_role': user['role'], 
                                'user_name': user['name']
                            })
                            st.rerun()
                        else:
                            st.error("🚫 Access Denied.")
    else:
        login_container.empty()
        current_user, user_role, user_name = st.session_state['user'], st.session_state['user_role'], st.session_state['user_name']
        is_manager = (user_role == 'manager')
        active_users_list = get_active_users()
        default_user_idx = active_users_list.index(current_user) if current_user in active_users_list else 0
        
        with st.sidebar:
            st.markdown(f"### 💼 RBS Workspace\n**{user_name}** ({user_role.title()})")
            nav_mode = option_menu(None, options=["Dashboard", "Projects", "New Task", "AI Smart Writer"], 
                                   icons=["journal-bookmark", "collection-play", "plus-circle", "magic"], 
                                   styles={"nav-link-selected": {"background-color": "#ff4b4b"}})
            if st.button("Logout", use_container_width=True):
                st.session_state['logged_in'] = False
                st.rerun()

        # --- MAIN VIEW CONTAINER (To avoid Ghosting) ---
        main_view = st.container()

        # --- NEW TASK SCREEN ---
        if nav_mode == "New Task":
            with main_view:
                st.header("✨ Create New Task")
                
                if st.session_state['show_creation_success']:
                    st.success("✅ Task Created Successfully!")
                    st.session_state['show_creation_success'] = False
                    
                # Load master data for dropdowns
                _, all_p, all_c, all_client, all_t = load_data(None)

                # --- Read sticky context (set after previous save) then clear ---
                sticky_p = st.session_state.pop('sticky_project', None)
                sticky_cl = st.session_state.pop('sticky_client', None)
                sticky_c = st.session_state.pop('sticky_contact', None)
                sticky_t = st.session_state.pop('sticky_type', None)
                sticky_ps = st.session_state.pop('sticky_p_status', None)

                # --- USING REACTIVE CONTAINER (For "Super" Experience) ---
                with st.container(border=True):
                    r1c1, r1c2 = st.columns(2)
                    with r1c1: 
                        sc1, sc2, sc3 = st.columns([1.2, 3.5, 0.5])
                        sc1.markdown('<div class="compact-label">Project</div>', unsafe_allow_html=True)
                        
                        is_p_new = sc3.toggle("New", key="p_new_tog", label_visibility="collapsed")
                        if is_p_new:
                            p_val = sc2.text_input("New Project", placeholder="Type new...", label_visibility="collapsed", key="nt_p_new")
                        else:
                            p_default_idx = all_p.index(sticky_p) if sticky_p and sticky_p in all_p else 0
                            p_val = sc2.selectbox("Select Project", all_p, index=p_default_idx, label_visibility="collapsed", key="nt_p_sel")
                    
                    with r1c2:
                        # Fixed 4-column layout for stable UI (No jumps)
                        sc_tt, sc_tt_val, sc_ps, sc_ps_val = st.columns([0.7, 1.3, 0.7, 1.3])
                        
                        sc_tt.markdown('<div class="compact-label">Type</div>', unsafe_allow_html=True)
                        t_opts = ["Task", "Followup", "Project"]
                        t_default_idx = t_opts.index(sticky_t) if sticky_t and sticky_t in t_opts else 0
                        t_sel = sc_tt_val.selectbox("Type", t_opts, index=t_default_idx, label_visibility="collapsed", key="nt_t_sel")
                        
                        is_p = (t_sel == "Project")
                        ps_list = ["Yet to start", "In Progress", "On Hold", "Deferred", "Completed"]
                        sc_ps.markdown('<div class="compact-label">Status</div>', unsafe_allow_html=True)
                        ps_default_idx = ps_list.index(sticky_ps) if sticky_ps and sticky_ps in ps_list else 0
                        p_status = sc_ps_val.selectbox(
                            "Proj Status", 
                            ps_list, 
                            index=ps_default_idx, 
                            label_visibility="collapsed", 
                            key="nt_p_status",
                            disabled=not is_p
                        )
                        if not is_p: p_status = None
                    
                    r2c1, r2c2 = st.columns(2)
                    with r2c1:
                        sc_cl1, sc_cl2, sc_cl3 = st.columns([1.2, 3.5, 0.5])
                        sc_cl1.markdown('<div class="compact-label">Client</div>', unsafe_allow_html=True)
                        
                        is_cl_new = sc_cl3.toggle("New", key="cl_new_tog", label_visibility="collapsed")
                        if is_cl_new:
                            cl_val = sc_cl2.text_input("New Client", placeholder="Type new...", label_visibility="collapsed", key="nt_cl_new")
                        else:
                            cl_default_idx = all_client.index(sticky_cl) if sticky_cl and sticky_cl in all_client else 0
                            cl_val = sc_cl2.selectbox("Select Client", all_client, index=cl_default_idx, label_visibility="collapsed", key="nt_cl_sel")
                    
                    with r2c2: 
                        sc4, sc5, sc6 = st.columns([1.2, 3.5, 0.5])
                        sc4.markdown('<div class="compact-label">Contact</div>', unsafe_allow_html=True)
                        
                        is_c_new = sc6.toggle("New", key="c_new_tog", label_visibility="collapsed")
                        if is_c_new:
                            c_val = sc5.text_input("New Contact", placeholder="Type new...", label_visibility="collapsed", key="nt_c_new")
                        else:
                            c_default_idx = all_c.index(sticky_c) if sticky_c and sticky_c in all_c else 0
                            c_val = sc5.selectbox("Select Contact", all_c, index=c_default_idx, label_visibility="collapsed", key="nt_c_sel")

                    c4_lbl, c4_val = st.columns([1.2, 8.8])
                    c4_lbl.markdown('<div class="compact-label">Task</div>', unsafe_allow_html=True)
                    t_desc = c4_val.text_input("Task Description", placeholder="Enter task summary...", label_visibility="collapsed", key="nt_desc")

                    r4c1, r4c2, r4c3 = st.columns(3)
                    with r4c1:
                        sub1, sub2 = st.columns([1, 2])
                        sub1.markdown('<div class="compact-label">Priority</div>', unsafe_allow_html=True)
                        prio = sub2.selectbox("Pr", ["🔥 High", "⚡ Medium", "🧊 Low"], index=1, label_visibility="collapsed", key="nt_prio")
                    with r4c2:
                        sub3, sub4 = st.columns([1, 2])
                        sub3.markdown('<div class="compact-label">Due</div>', unsafe_allow_html=True)
                        due = sub4.date_input("Dt", value=date.today(), format="DD/MM/YYYY", label_visibility="collapsed", key="nt_due")
                    with r4c3:
                        sub5, sub6 = st.columns([1, 2])
                        sub5.markdown('<div class="compact-label">User</div>', unsafe_allow_html=True)
                        ass_to = sub6.selectbox("Assign", active_users_list, index=default_user_idx, label_visibility="collapsed", key="nt_ass")

                    pt1, pt2 = st.columns([1.2, 8.8])
                    pt1.markdown('<div class="compact-label">Points</div>', unsafe_allow_html=True)
                    pts = pt2.text_area("Points", height=100, label_visibility="collapsed", placeholder="Detailed breakdown of tasks...", key="nt_pts")
                    
                    # --- LIVE PREVIEW ---
                    st.markdown(f"""
                    <div style="background-color: #f8f9fa; padding: 12px; border-radius: 8px; border-left: 5px solid #ff4b4b; margin: 15px 0px; box-shadow: 0 2px 5px rgba(0,0,0,0.05);">
                        <div style="font-weight: 800; color: #ff4b4b; font-size: 12px; text-transform: uppercase; margin-bottom: 5px;">🎯 Save Preview</div>
                        <div style="font-size: 14px; color: #333;">
                            Project: <b>{p_val or 'General'}</b> | 
                            Client: <b>{cl_val or 'General'}</b> | 
                            Contact: <b>{c_val or 'General'}</b> |
                            Type: <b>{t_sel}</b> {f'| Status: <b>{p_status}</b>' if t_sel == 'Project' else ''}
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

                    if st.button("🚀 Create Task", type="primary", use_container_width=True):
                        if not ass_to:
                            st.error("⚠️ Please assign the task to a user.")
                        elif not t_desc.strip():
                            st.error("⚠️ Please enter a task description.")
                        else:
                            with st.status("Adding Task...", expanded=True) as status:
                                if add_task(current_user, ass_to, t_desc, prio, due, p_val or "General", c_val or "General", "", pts, cl_val or "General", t_sel, p_status):
                                    fetch_tasks.clear() 
                                    status.update(label="Task Added!", state="complete", expanded=False)
                                    st.session_state['show_creation_success'] = True
                                    # --- Persist context fields for the next task entry ---
                                    st.session_state['sticky_project'] = p_val or "General"
                                    st.session_state['sticky_client'] = cl_val or "General"
                                    st.session_state['sticky_contact'] = c_val or "General"
                                    st.session_state['sticky_type'] = t_sel
                                    st.session_state['sticky_p_status'] = p_status
                                    st.rerun()

        # --- PROJECTS SCREEN ---
        elif nav_mode == "Projects":
            with main_view:
                st.header("🗂️ Active Projects Overview")
                
                with st.spinner("📦 Fetching Projects..."):
                    df, all_p, all_c, all_client, all_t = load_data(None)
                
                if df.empty:
                    st.info("👋 No data found.")
                else:
                    # Filter to only show tasks marked as "Project"
                    proj_df = df[df['task_type'] == 'Project'].copy()
                    
                    if proj_df.empty:
                        st.info("👋 No active projects found.")
                    else:
                        # Improved User Filter (Matches Dashboard Style)
                        c_filter, _ = st.columns([1, 2])
                        all_users_in_projects = sorted(proj_df['assigned_to'].dropna().unique().tolist())
                        view_target = c_filter.selectbox("👥 View User Projects:", ["All Users"] + all_users_in_projects)
                        
                        st.markdown("---")
                        
                        # Filter dataframe based on selection
                        if view_target != "All Users":
                            proj_df = proj_df[proj_df['assigned_to'] == view_target]

                        if proj_df.empty:
                            st.warning(f"No projects found for {view_target}.")
                        else:
                            # Display grouped by User using compact dataframes and zero-margin custom headers
                            users_to_show = [view_target] if view_target != "All Users" else all_users_in_projects
                            
                            for i, user_req in enumerate(users_to_show):
                                user_projects = proj_df[proj_df['assigned_to'] == user_req]
                                
                                if not user_projects.empty:
                                    # Create a custom, zero-margin header for the user
                                    user_name_display = user_req.split('@')[0].replace('.', ' ').title()
                                    margin_top = "0px" if i == 0 else "15px" # Only tiny spacing between tables
                                    st.markdown(
                                        f"<div style='margin-top: {margin_top}; margin-bottom: 5px; font-weight: 600; font-size: 16px; color: #2c3e50;'>"
                                        f"👤 {user_name_display} <span style='font-size: 13px; font-weight: 400; color: #666;'>({len(user_projects)} Projects)</span>"
                                        f"</div>", 
                                        unsafe_allow_html=True
                                    )
                                    
                                    # Prepare dataframe for display
                                    display_df = user_projects[['project_ref', 'task_desc', 'project_status']].copy()
                                    display_df.columns = ['Project Ref', 'Project Description', 'Status']
                                    
                                    # Render compact, professional dataframe
                                    st.dataframe(
                                        display_df,
                                        use_container_width=True,
                                        hide_index=True,
                                        column_config={
                                            "Project Ref": st.column_config.TextColumn(width="medium"),
                                            "Project Description": st.column_config.TextColumn(width="large"),
                                            "Status": st.column_config.TextColumn(width="small")
                                        }
                                    )

        # --- DASHBOARD SCREEN ---
        elif nav_mode == "Dashboard":
            with main_view:
                view_email = None
                if is_manager:
                    c_filter, c_title = st.columns([1, 3])
                    view_target = c_filter.selectbox("View User:", ["All Users"] + get_active_users())
                    if view_target != "All Users": view_email = view_target
                    c_title.title("📔 Operational Diary")
                else:
                    st.title("📔 My Diary")
                    view_email = current_user
                
                with st.spinner("📦 Syncing with RBS Cloud..."):
                    df, all_p, all_c, all_client, all_t = load_data(view_email)

            if st.session_state['show_update_success']:
                st.toast("✅ Updated Successfully!", icon="🎉")
                st.session_state['show_update_success'] = False 

            sc1, sc2, sc3 = st.columns([6, 1, 2])
            search_q = sc1.text_input("🔍 Omni-Search", label_visibility="collapsed", key="omni_search_input", placeholder="Search task, project, client...")
            
            sc2.button("🧹 Clear", help="Clear Search", use_container_width=True, type="primary", on_click=reset_search)
            
            if sc3.button("📅 Sort: Due Date", help="Reset list and sort by Due Date", use_container_width=True, type="primary"):
                reset_bumps() 

            if not df.empty:
                df['is_bumped'] = df['id'].apply(lambda x: 1 if x in st.session_state['bumped_ids'] else 0)
                df = df.sort_values(by=['is_bumped', 'due_date'], ascending=[True, True])

                today = date.today()
                active_df, done_df = df[df['status'] != 'Completed'], df[df['status'] == 'Completed']
                sel_filter = option_menu(None, options=[f"Pending ({len(active_df)})", "Today", "Tomorrow", "Overdue", f"Completed ({len(done_df)})"],
                                         icons=["folder", "lightning", "calendar", "exclamation", "check"], orientation="horizontal")
                
                temp_df = (done_df if "Completed" in sel_filter else 
                          active_df[active_df['due_date'] == today] if "Today" in sel_filter else 
                          active_df[active_df['due_date'] == today + timedelta(days=1)] if "Tomorrow" in sel_filter else 
                          active_df[active_df['due_date'] < today] if "Overdue" in sel_filter else active_df)

                if search_q:
                    q = search_q.lower()
                    final_df = temp_df[temp_df.apply(lambda r: q in str(r['task_desc']).lower() or q in str(r['project_ref']).lower() or q in str(r.get('client_ref', '')).lower() or q in str(r.get('task_type', '')).lower() or q in str(r['coordinator']).lower(), axis=1)]
                else: final_df = temp_df

                # Generation key suffix — changes after each save to force expanders closed
                gen = st.session_state.get('dashboard_gen', 0)
                hl_id = st.session_state.get('highlight_task_id', None)

                with st.container(height=650):
                    for _, row in final_df.iterrows():
                        is_late = (row['due_date'] < today)
                        icon = "🔴" if is_late else "⚡" if row['due_date'] == today else "📅"
                        ass_tag = f" → {row['assigned_to'].split('@')[0].title()}" if row['assigned_to'] else ""
                        # Add invisible zero-width spaces tied to `gen` to force Streamlit to treat as a new closed expander
                        t_label = f"{icon} {'[LATE] ' if is_late and 'Completed' not in sel_filter else ''}{row['due_date'].strftime('%d-%b')} | {row['task_desc']}{ass_tag}" + ("\u200b" * gen)
                        
                        col_exp, col_btn = st.columns([0.92, 0.08]) if "Completed" not in sel_filter else st.columns([1, 0.001])

                        with col_exp:
                            # Highlight border on recently saved task (Rendered INSIDE the column so it stays attached to THIS task)
                            is_highlighted = (hl_id is not None and str(row['id']) == str(hl_id))
                            if is_highlighted:
                                st.markdown(
                                    f'<div style="border-left: 5px solid #28a745; border-radius: 4px; '
                                    f'padding: 2px 8px; margin-bottom: 2px; background: #eafaf1; '
                                    f'font-size:12px; color:#28a745; font-weight:700;">✅ Just updated</div>',
                                    unsafe_allow_html=True
                                )

                            with st.expander(t_label, expanded=False):
                                if is_late and "Completed" not in sel_filter: 
                                    st.markdown('<div class="alert-blink">⚠️ OVERDUE</div>', unsafe_allow_html=True)
                                
                                with st.container(border=True):
                                    r1c1, r1c2 = st.columns(2)
                                    with r1c1:
                                        sc1, sc2, sc3 = st.columns([1.2, 3.5, 0.5])
                                        sc1.markdown('<div class="compact-label">Project</div>', unsafe_allow_html=True)
                                        
                                        # New? Toggle for Project Edit
                                        curr_p = row['project_ref']
                                        is_p_new_edit = sc3.toggle("New", key=f"tog_p_{row['id']}_{gen}", label_visibility="collapsed")
                                        
                                        if is_p_new_edit:
                                            edit_p_val = sc2.text_input("New P", placeholder="Type new...", label_visibility="collapsed", key=f"tp_{row['id']}_{gen}")
                                        else:
                                            p_idx = all_p.index(curr_p) if curr_p in all_p else 0
                                            edit_p_val = sc2.selectbox("Sel P", all_p, index=p_idx, label_visibility="collapsed", key=f"sp_{row['id']}_{gen}")
                                        
                                    with r1c2:
                                        curr_id = row['id']
                                        curr_t = row.get('task_type', 'Task')
                                        
                                        # Fixed 4-column layout for stable UI in expanders
                                        c1, c2, c3, c4 = st.columns([0.7, 1.3, 0.7, 1.3])
                                        
                                        c1.markdown('<div class="compact-label">Type</div>', unsafe_allow_html=True)
                                        t_opts = ["Task", "Followup", "Project"]
                                        t_idx = t_opts.index(curr_t) if curr_t in t_opts else 0
                                        t_sel = c2.selectbox("Type Edit", t_opts, index=t_idx, label_visibility="collapsed", key=f"tt_{curr_id}_{gen}")
                                        
                                        is_p_edit = (t_sel == "Project")
                                        c3.markdown('<div class="compact-label">Status</div>', unsafe_allow_html=True)
                                        
                                        ps_list = ["Yet to start", "In Progress", "On Hold", "Deferred", "Completed"]
                                        curr_ps = row.get('project_status', 'Yet to start')
                                        ps_idx = ps_list.index(curr_ps) if curr_ps in ps_list else 0
                                        
                                        edit_ps_val = c4.selectbox(
                                            "PS Edit", 
                                            ps_list, 
                                            index=ps_idx, 
                                            label_visibility="collapsed", 
                                            key=f"ps_{curr_id}_{gen}",
                                            disabled=not is_p_edit
                                        )
                                        if not is_p_edit: edit_ps_val = None

                                    r2c1, r2c2 = st.columns(2)
                                    with r2c1:
                                        sc_cl1, sc_cl2, sc_cl3 = st.columns([1.2, 3.5, 0.5])
                                        sc_cl1.markdown('<div class="compact-label">Client</div>', unsafe_allow_html=True)
                                        
                                        # New? Toggle for Client Edit
                                        curr_cl = row.get('client_ref', 'General')
                                        is_cl_new_edit = sc_cl3.toggle("New", key=f"tog_cl_{row['id']}_{gen}", label_visibility="collapsed")
                                        
                                        if is_cl_new_edit:
                                            edit_cl_val = sc_cl2.text_input("New Cl", placeholder="Type new...", label_visibility="collapsed", key=f"tcl_{row['id']}_{gen}")
                                        else:
                                            cl_idx = all_client.index(curr_cl) if curr_cl in all_client else 0
                                            edit_cl_val = sc_cl2.selectbox("Sel Cl", all_client, index=cl_idx, label_visibility="collapsed", key=f"scl_{row['id']}_{gen}")

                                    with r2c2:
                                        sc4, sc5, sc6 = st.columns([1.2, 3.5, 0.5])
                                        sc4.markdown('<div class="compact-label">Contact</div>', unsafe_allow_html=True)
                                        
                                        # New? Toggle for Contact Edit
                                        curr_c = row['coordinator']
                                        is_c_new_edit = sc6.toggle("New", key=f"tog_c_{row['id']}_{gen}", label_visibility="collapsed")
                                        
                                        if is_c_new_edit:
                                            edit_c_val = sc5.text_input("New C", placeholder="Type new...", label_visibility="collapsed", key=f"tc_{row['id']}_{gen}")
                                        else:
                                            c_idx = all_c.index(curr_c) if curr_c in all_c else 0
                                            edit_c_val = sc5.selectbox("Sel C", all_c, index=c_idx, label_visibility="collapsed", key=f"sc_{row['id']}_{gen}")

                                    dc1, dc2 = st.columns([1.2, 8.8])
                                    dc1.markdown('<div class="compact-label">Task</div>', unsafe_allow_html=True)
                                    n_desc = dc2.text_input("Desc Edit", value=row['task_desc'], label_visibility="collapsed", key=f"ndesc_{row['id']}_{gen}")

                                    r3c1, r3c2, r3c3 = st.columns(3)
                                    with r3c1:
                                        sub1, sub2 = st.columns([1, 2])
                                        sub1.markdown('<div class="compact-label">Priority</div>', unsafe_allow_html=True)
                                        prio_list = ["🔥 High", "⚡ Medium", "🧊 Low"]
                                        n_prio = sub2.selectbox("P Edit", prio_list, index=prio_list.index(row['priority']), label_visibility="collapsed", key=f"nprio_{row['id']}_{gen}")
                                    with r3c2:
                                        sub3, sub4 = st.columns([1, 2])
                                        sub3.markdown('<div class="compact-label">Due</div>', unsafe_allow_html=True)
                                        n_date = sub4.date_input("D Edit", value=row['due_date'], format="DD/MM/YYYY", label_visibility="collapsed", key=f"ndate_{row['id']}_{gen}")
                                    with r3c3:
                                        sub5, sub6 = st.columns([1, 2])
                                        sub5.markdown('<div class="compact-label">User</div>', unsafe_allow_html=True)
                                        curr = row['assigned_to'] or "Unassigned"
                                        clean_users = active_users_list
                                        if curr and curr not in clean_users: clean_users = [curr] + clean_users
                                        a_idx = clean_users.index(curr) if curr in clean_users else 0
                                        n_ass = sub6.selectbox("U Edit", clean_users, index=a_idx, label_visibility="collapsed", key=f"nass_{row['id']}_{gen}")

                                    rc1, rc2 = st.columns([1.2, 8.8])
                                    rc1.markdown('<div class="compact-label">Remarks</div>', unsafe_allow_html=True)
                                    n_rem = rc2.text_input("Rem Edit", value=row.get('staff_remarks', ''), label_visibility="collapsed", key=f"nrem_{row['id']}_{gen}")

                                    n_pts = st.text_area("Details Edit", value=row.get('points', ''), height=80, label_visibility="collapsed", placeholder="Detailed points...", key=f"npts_{row['id']}_{gen}")
                                    
                                    # --- EDIT LIVE PREVIEW ---
                                    st.markdown(f"""
                                    <div style="background-color: #f8f9fa; padding: 10px; border-radius: 6px; border-left: 5px solid #ff4b4b; margin-bottom: 15px;">
                                        <div style="font-weight: 800; color: #ff4b4b; font-size: 11px; text-transform: uppercase;">🎯 Edit Preview</div>
                                        <div style="font-size: 13px; color: #333;">
                                            Project: <b>{edit_p_val or 'General'}</b> | 
                                            Client: <b>{edit_cl_val or 'General'}</b> | 
                                            Contact: <b>{edit_c_val or 'General'}</b> |
                                            Type: <b>{t_sel}</b> {f'| Status: <b>{edit_ps_val}</b>' if t_sel == 'Project' else ''}
                                         </div>
                                    </div>
                                    """, unsafe_allow_html=True)

                                    b1, b2, b3 = st.columns([1, 2, 1])
                                    
                                    if b1.button("💾 Save", type="primary", key=f"save_{row['id']}_{gen}"):
                                        if update_task_full(row['id'], n_desc, n_date, n_prio, n_rem, n_ass, n_pts, row.get('email_subject', ''), edit_c_val or 'General', edit_p_val or 'General', is_manager, edit_cl_val or 'General', t_sel, edit_ps_val):
                                            fetch_tasks.clear()
                                            st.session_state['show_update_success'] = True
                                            st.session_state['dashboard_gen'] += 1
                                            st.session_state['highlight_task_id'] = row['id']
                                            st.rerun()
                                    
                                    if "Completed" not in sel_filter:
                                        with b2:
                                            c_n_input = st.text_input("Close Note", key=f"cn_{row['id']}_{gen}", placeholder="Closing note...", label_visibility="collapsed")
                                        if b3.button("✅ Close", type="primary", key=f"close_{row['id']}_{gen}"):
                                            update_task_status(row['id'], "Completed", c_n_input or n_rem or "Closed")
                                            fetch_tasks.clear()
                                            st.session_state['show_update_success'] = True
                                            st.session_state['dashboard_gen'] += 1
                                            st.session_state['highlight_task_id'] = row['id']
                                            st.rerun()
                                    else:
                                        if b3.button("🔄 Re-Open", type="primary", key=f"reopen_{row['id']}_{gen}"):
                                            update_task_status(row['id'], "Open")
                                            fetch_tasks.clear()
                                            st.session_state['show_update_success'] = True
                                            st.session_state['dashboard_gen'] += 1
                                            st.session_state['highlight_task_id'] = row['id']
                                            st.rerun()
                        
                        if "Completed" not in sel_filter:
                            with col_btn:
                                if row['id'] not in st.session_state['bumped_ids']:
                                    if st.button("⬇️", key=f"bump_{row['id']}", help="Move to bottom", type="primary"):
                                        st.session_state['bumped_ids'].add(row['id'])
                                        st.rerun()

            else:
                st.info("👋 No tasks found.")

        # --- SETTINGS SCREEN ---
        elif nav_mode == "Settings":
            with main_view:
                st.header("⚙️ User Settings")
                st.info("User settings configuration will go here.")

        # --- AI SMART WRITER SCREEN ---
        elif nav_mode == "AI Smart Writer":
            with main_view:
                # Header row: title + audience selector side by side
                hdr_col, aud_col = st.columns([3, 1])
                with hdr_col:
                    st.header("🪄 AI Smart Writer")
                    st.caption("Transform rough notes into professional messages instantly")
                with aud_col:
                    st.markdown("<div style='margin-top: 18px;'></div>", unsafe_allow_html=True)
                    audience = st.selectbox(
                        "🎯 Writing To",
                        options=["Colleague", "Management", "Client", "Vendor"],
                        help="Who is this message going to? The AI will adjust its tone accordingly."
                    )
                
                # --- Load saved Master Instructions from prefs file into session state ---
                if 'master_instructions_loaded' not in st.session_state:
                    saved_prefs = load_user_prefs(current_user)
                    st.session_state['master_instructions_input'] = saved_prefs.get('master_instructions', '')
                    st.session_state['master_instructions_loaded'] = True
                
                # Master Instructions — collapsed by default, but shows active status
                saved_mi = st.session_state.get('master_instructions_input', '')
                expander_label = "⚙️ Master Instructions " + ("✅ Active" if saved_mi.strip() else "(click to set your personal AI style)")
                with st.expander(expander_label, expanded=False):
                    st.markdown("_Set your preferences once — saved permanently. The AI follows these rules in every response._")
                    new_mi = st.text_area(
                        "Your Master Instructions:",
                        key="master_instructions_input",
                        value=saved_mi,
                        placeholder="Examples:\n- Always greet with 'Good morning' or 'Hi', never 'Hey'\n- Do not use emojis\n- I am a Project Manager at RBS. Always be concise and action-oriented.\n- Always sign off emails with 'Kind regards, M. Satish Kumar'\n- I prefer bullet points over paragraphs.",
                        height=130,
                        label_visibility="collapsed"
                    )
                    save_col, status_col = st.columns([1, 3])
                    with save_col:
                        if st.button("💾 Save Instructions", type="primary", use_container_width=True):
                            save_user_prefs(current_user, {'master_instructions': new_mi})
                            st.toast("✅ Instructions saved! They will load automatically every time.", icon="💾")
                            st.rerun()
                    with status_col:
                        if new_mi.strip():
                            st.info(f"**Active rules:** {new_mi[:120]}{'...' if len(new_mi) > 120 else ''}")
                        else:
                            st.caption("No instructions saved yet. The AI will use default professional tone.")
                
                # Use saved master instructions for all prompts
                master_instructions = st.session_state.get('master_instructions_input', '')

                # Setup Gemini
                import google.generativeai as genai
                import os
                
                # Attempt to find API key in environment or secrets
                api_key = os.environ.get("GEMINI_API_KEY", "")
                if not api_key:
                    # Check for direct keys in st.secrets
                    for k in ["GEMINI_API_KEY", "GOOGLE_API_KEY"]:
                        if k in st.secrets:
                            api_key = st.secrets[k]
                            break
                    
                    # Fallback to nested connections if still not found
                    if not api_key:
                        try:
                            api_key = st.secrets["connections"]["supabase"]["GOOGLE_API_KEY"]
                        except (KeyError, FileNotFoundError):
                            api_key = ""
                
                # If no built-in key, allow user to provide one dynamically
                if not api_key:
                    st.warning("⚠️ Google Gemini API Key Required")
                    st.info("To power the AI formatting, a Google Gemini API Key is needed. Get a free one from [Google AI Studio](https://aistudio.google.com/app/apikey).")
                    api_key = st.text_input("Enter your Gemini API Key here:", type="password")
                    if not api_key:
                        st.stop()
                
                try:
                    genai.configure(api_key=api_key)
                    model = genai.GenerativeModel('gemini-2.5-flash')
                except Exception as e:
                    st.error(f"Failed to initialize AI model: {e}")
                    st.stop()
                    
                audience_tone = {
                    "Colleague": "The recipient is a colleague at the same level. Use a friendly, collaborative, and direct tone.",
                    "Management": "The recipient is senior management or leadership. Use a formal, respectful, and concise tone that highlights impact and decisions needed.",
                    "Client": "The recipient is an external client. Use a professional, courteous, and confidence-inspiring tone. Be clear about next steps.",
                    "Vendor": "The recipient is a vendor or supplier. Use a firm but polite professional tone, focusing on deliverables, timelines, and expectations.",
                }

                st.markdown("<div style='margin-top: 6px;'></div>", unsafe_allow_html=True)


                # --- 3-column layout: Input | Actions | Output ---
                col_in, col_mid, col_out = st.columns([4, 2, 4], gap="medium")
                
                with col_in:
                    st.markdown("#### 📝 Draft Input")
                    draft_input = st.text_area("Draft Input:", height=380, 
                                               placeholder="Type your quickly jotted thoughts here without worrying about formatting...\n\nExample:\nclient meeting went well. they want the proposal by tomorrow instead of friday. total budget is 10k. please update the slide deck.", label_visibility="collapsed")
                    
                with col_mid:
                    st.markdown("<div style='text-align: center; margin-top: 8px; margin-bottom: 15px; font-weight: bold; color: #444;'>✨ Quick Actions</div>", unsafe_allow_html=True)
                    
                    action_triggered = None
                    action_label = ""
                    format_instruction = ""
                    
                    if st.button("✉️ Email", use_container_width=True, type="primary"):
                        action_triggered = True
                        action_label = "Email"
                        format_instruction = (
                            "Rewrite the following text into THREE distinct professional versions. "
                            "Label them clearly as 'Option 1 (Quick & Direct)', 'Option 2 (Standard)', and 'Option 3 (Detailed)':\n\n"
                            "1. **Option 1 (Quick & Direct):** An ultra-minimalist, professional version that exactly reflects the user's intent without adding ANY extra context, reason, or 'fluff' (e.g., 'Dear Sir, Could we connect at 2pm? Kindly confirm.').\n"
                            "2. **Option 2 (Standard):** A professional and balanced email with a clear subject and body.\n"
                            "3. **Option 3 (Detailed):** A more formal version including professional nuances.\n\n"
                            "General Rules:\n"
                            "- Greet professionally (e.g., 'Dear Sir,' or 'Hi [Name],').\n"
                            "- Do not use emojis.\n"
                            "- Use 'Kind regards, M. Satish Kumar' as default sign-off.\n"
                            "- Provide a suitable Subject line for each option."
                        )

                    if st.button("📱 WhatsApp (Casual)", use_container_width=True):
                        action_triggered = True
                        action_label = "WhatsApp (Casual)"
                        format_instruction = (
                            "Rewrite the following text into a friendly, clear WhatsApp message. "
                            "Greet with 'Hi' or 'Hello', never 'Hey'. Use a few appropriate emojis, "
                            "keep it concise, and highlight any required actions clearly."
                        )
                    if st.button("🏢 WhatsApp (Formal)", use_container_width=True):
                        action_triggered = True
                        action_label = "WhatsApp (Formal)"
                        format_instruction = (
                            "Rewrite the following text into an ultra-brief, professional WhatsApp message. "
                            "Greet with 'Dear Sir,' or 'Hi' and state only the message. "
                            "No extra fluff, no emojis."
                        )
                    if st.button("📑 Summarize", use_container_width=True):
                        action_triggered = True
                        action_label = "Summary"
                        format_instruction = "Extract the key information from the following text and summarize it into clear, concise bullet points."

                    st.markdown("<hr style='margin: 16px 0px;'>", unsafe_allow_html=True)
                    st.markdown("<div style='text-align: center; margin-bottom: 10px; font-weight: bold; color: #444;'>⚙️ Custom</div>", unsafe_allow_html=True)
                    custom_prompt = st.text_input("Custom Instruction:", placeholder="e.g., Make it urgent", label_visibility="collapsed")
                    if st.button("🪄 Run Custom", use_container_width=True, type="primary"):
                        if custom_prompt:
                            action_triggered = True
                            action_label = "Custom"
                            format_instruction = custom_prompt
                        else:
                            st.warning("Please type an instruction.")
                    
                with col_out:
                    st.markdown("#### 📤 Formatted Output")
                    
                    if action_triggered:
                        if not draft_input.strip():
                            st.warning("⚠️ Please type some draft text first.")
                        else:
                            # Build the full compound prompt
                            system_context = ""
                            if master_instructions.strip():
                                system_context += f"MASTER INSTRUCTIONS (always follow these):\n{master_instructions.strip()}\n\n"
                            system_context += f"AUDIENCE CONTEXT:\n{audience_tone[audience]}\n\n"
                            system_context += f"FORMAT TASK:\n{format_instruction}\n\n"
                            system_context += f"RAW TEXT TO REWRITE:\n---\n{draft_input}"

                            with st.spinner(f"Writing {action_label} for {audience}..."):
                                try:
                                    response = model.generate_content(system_context)
                                    response_text = response.text
                                    # Store in session state so copy button persists
                                    st.session_state['last_ai_output'] = response_text
                                    st.session_state['last_ai_label'] = action_label
                                    st.session_state['last_ai_audience'] = audience
                                except Exception as e:
                                    error_msg = str(e)
                                    if "API_KEY_INVALID" in error_msg or "API key not valid" in error_msg:
                                        st.error("🚫 Invalid API Key. Please check your secrets configuration.")
                                    elif "429" in error_msg or "quota" in error_msg.lower() or "exceeded" in error_msg.lower():
                                        st.warning("⏳ **Rate limit reached** — The AI is temporarily throttled (Google free-tier limit). Please wait **30–60 seconds** and try again.")
                                    else:
                                        st.error(f"⚠️ AI Error: {error_msg[:300]}")
                    # Render output from session state (persists across button clicks)
                    last_output = st.session_state.get('last_ai_output', '')
                    last_label = st.session_state.get('last_ai_label', '')
                    last_audience = st.session_state.get('last_ai_audience', '')
                    
                    if last_output:
                        # Display the beautiful output box
                        st.markdown(
                            f"""<div style="padding: 18px; border-radius: 8px; border: 1px solid #e0e0e0; background: linear-gradient(180deg, #f8f9fa 0%, #ffffff 100%); height: 330px; overflow-y: auto; white-space: pre-wrap; font-size: 14px; box-shadow: 0 4px 6px rgba(0,0,0,0.05); color: #333;">{last_output}</div>""",
                            unsafe_allow_html=True
                        )
                        st.caption(f"✅ Formatted as **{last_label}** for **{last_audience}**")
                        
                        # Copy to clipboard button using JS
                        import streamlit.components.v1 as components
                        safe_text = last_output.replace('`', r'\`').replace('\\', '\\\\').replace('$', r'\$')
                        components.html(f"""
                        <button id="copyBtn" onclick="copyToClipboard()" style="
                            background: #e8f4fd; color: #1a73e8; border: 1px solid #1a73e8;
                            padding: 7px 18px; border-radius: 6px; font-size: 13px; font-weight: 600;
                            cursor: pointer; transition: all 0.2s; margin-top: 4px;">
                            📋 Copy to Clipboard
                        </button>
                        <script>
                        function copyToClipboard() {{
                            const text = `{safe_text}`;
                            navigator.clipboard.writeText(text).then(() => {{
                                const btn = document.getElementById('copyBtn');
                                btn.textContent = '✅ Copied!';
                                btn.style.background = '#e6f4ea';
                                btn.style.color = '#1e8e3e';
                                btn.style.borderColor = '#1e8e3e';
                                setTimeout(() => {{
                                    btn.textContent = '📋 Copy to Clipboard';
                                    btn.style.background = '#e8f4fd';
                                    btn.style.color = '#1a73e8';
                                    btn.style.borderColor = '#1a73e8';
                                }}, 2000);
                            }}).catch(() => {{
                                alert('Copy failed. Please select and copy manually.');
                            }});
                        }}
                        </script>""", height=50)
                    else:
                        audience_icons = {"Colleague": "🤝", "Management": "📊", "Client": "🏆", "Vendor": "📦"}
                        st.markdown(
                            f"""<div style="padding: 20px; border-radius: 8px; border: 2px dashed #e0e0e0; background-color: #fdfdfd; height: 380px; color: #a0a0a0; display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center;">
                                <div style="font-size: 42px; margin-bottom: 10px;">✨</div>
                                <div><b>Awaiting Input</b><br/><br/>Type your draft on the left, choose your audience <b>{audience_icons[audience]} {audience}</b>,<br/>then click a Quick Action.</div>
                               </div>""",
                            unsafe_allow_html=True
                        )


        else:
            st.info("👋 Select an option from the sidebar.")

if __name__ == "__main__":
    main()
