import streamlit as st
import pandas as pd
from datetime import datetime, date, timedelta
from streamlit_option_menu import option_menu

# --- CUSTOM MODULES ---
from utils.styles import apply_custom_styles
from utils.database import (
    verify_user_in_db, get_active_users, fetch_tasks, process_task_data,
    add_task, update_task_status, update_task_full, bump_task_date
)
from utils.ai import generate_variations

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
            nav_mode = option_menu(None, options=["Dashboard", "New Task"], 
                                   icons=["journal-bookmark", "plus-circle"], 
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
                            p_val = sc2.selectbox("Select Project", all_p, index=0, label_visibility="collapsed", key="nt_p_sel")
                    
                    with r1c2:
                        # Side-by-side layout for Type and Status
                        if st.session_state.get("nt_t_sel") == "Project":
                            sc_tt1, sc_tt2, sc_ps1, sc_ps2 = st.columns([0.7, 1.3, 0.7, 1.3])
                            sc_tt1.markdown('<div class="compact-label">Type</div>', unsafe_allow_html=True)
                            t_sel = sc_tt2.selectbox("Type", all_t, index=all_t.index("Project"), label_visibility="collapsed", key="nt_t_sel")
                            sc_ps1.markdown('<div class="compact-label">Status</div>', unsafe_allow_html=True)
                            p_status = sc_ps2.selectbox("Proj Status", ["Yet to start", "In Progress", "On Hold", "Deferred", "Completed"], index=0, label_visibility="collapsed", key="nt_p_status")
                        else:
                            sc_tt1, sc_tt2 = st.columns([1.2, 4])
                            sc_tt1.markdown('<div class="compact-label">Task Type</div>', unsafe_allow_html=True)
                            t_sel = sc_tt2.selectbox("Type", all_t, index=0, label_visibility="collapsed", key="nt_t_sel")
                            p_status = None
                    
                    r2c1, r2c2 = st.columns(2)
                    with r2c1:
                        sc_cl1, sc_cl2, sc_cl3 = st.columns([1.2, 3.5, 0.5])
                        sc_cl1.markdown('<div class="compact-label">Client</div>', unsafe_allow_html=True)
                        
                        is_cl_new = sc_cl3.toggle("New", key="cl_new_tog", label_visibility="collapsed")
                        if is_cl_new:
                            cl_val = sc_cl2.text_input("New Client", placeholder="Type new...", label_visibility="collapsed", key="nt_cl_new")
                        else:
                            cl_val = sc_cl2.selectbox("Select Client", all_client, index=0, label_visibility="collapsed", key="nt_cl_sel")
                    
                    with r2c2: 
                        sc4, sc5, sc6 = st.columns([1.2, 3.5, 0.5])
                        sc4.markdown('<div class="compact-label">Contact</div>', unsafe_allow_html=True)
                        
                        is_c_new = sc6.toggle("New", key="c_new_tog", label_visibility="collapsed")
                        if is_c_new:
                            c_val = sc5.text_input("New Contact", placeholder="Type new...", label_visibility="collapsed", key="nt_c_new")
                        else:
                            c_val = sc5.selectbox("Select Contact", all_c, index=0, label_visibility="collapsed", key="nt_c_sel")

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
                                    st.rerun()

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

                with st.container(height=650):
                    for _, row in final_df.iterrows():
                        is_late = (row['due_date'] < today)
                        icon = "🔴" if is_late else "⚡" if row['due_date'] == today else "📅"
                        ass_tag = f" → {row['assigned_to'].split('@')[0].title()}" if row['assigned_to'] else ""
                        t_label = f"{icon} {'[LATE] ' if is_late and 'Completed' not in sel_filter else ''}{row['due_date'].strftime('%d-%b')} | {row['task_desc']}{ass_tag}"
                        
                        col_exp, col_btn = st.columns([0.92, 0.08]) if "Completed" not in sel_filter else st.columns([1, 0.001])

                        with col_exp:
                            with st.expander(t_label):
                                if is_late and "Completed" not in sel_filter: 
                                    st.markdown('<div class="alert-blink">⚠️ OVERDUE</div>', unsafe_allow_html=True)
                                
                                with st.container(border=True):
                                    r1c1, r1c2 = st.columns(2)
                                    with r1c1:
                                        sc1, sc2, sc3 = st.columns([1.2, 3.5, 0.5])
                                        sc1.markdown('<div class="compact-label">Project</div>', unsafe_allow_html=True)
                                        
                                        # New? Toggle for Project Edit
                                        curr_p = row['project_ref']
                                        is_p_new_edit = sc3.toggle("New", key=f"tog_p_{row['id']}", label_visibility="collapsed")
                                        
                                        if is_p_new_edit:
                                            edit_p_val = sc2.text_input("New P", placeholder="Type new...", label_visibility="collapsed", key=f"tp_{row['id']}")
                                        else:
                                            p_idx = all_p.index(curr_p) if curr_p in all_p else 0
                                            edit_p_val = sc2.selectbox("Sel P", all_p, index=p_idx, label_visibility="collapsed", key=f"sp_{row['id']}")
                                        
                                    with r1c2:
                                        curr_id = row['id']
                                        curr_t = row.get('task_type', 'Task')
                                        # Use session state to keep layout choice reactive
                                        if st.session_state.get(f"tt_{curr_id}") == "Project":
                                            ps_tt1, ps_tt2, ps_ts1, ps_ts2 = st.columns([0.7, 1.3, 0.7, 1.3])
                                            ps_tt1.markdown('<div class="compact-label">Type</div>', unsafe_allow_html=True)
                                            t_sel = ps_tt2.selectbox("Type Edit", all_t, index=all_t.index("Project"), label_visibility="collapsed", key=f"tt_{curr_id}")
                                            
                                            ps_ts1.markdown('<div class="compact-label">Status</div>', unsafe_allow_html=True)
                                            curr_ps = row.get('project_status', 'Yet to start')
                                            ps_list = ["Yet to start", "In Progress", "On Hold", "Deferred", "Completed"]
                                            ps_idx = ps_list.index(curr_ps) if curr_ps in ps_list else 0
                                            edit_ps_val = ps_ts2.selectbox("PS Edit", ps_list, index=ps_idx, label_visibility="collapsed", key=f"ps_{curr_id}")
                                        else:
                                            ps_tt1, ps_tt2 = st.columns([1.2, 4])
                                            ps_tt1.markdown('<div class="compact-label">Task Type</div>', unsafe_allow_html=True)
                                            # Clean lookup for index
                                            t_opts = ["Task", "Followup", "Project"]
                                            t_idx = t_opts.index(curr_t) if curr_t in t_opts else 0
                                            t_sel = ps_tt2.selectbox("Type Edit", t_opts, index=t_idx, label_visibility="collapsed", key=f"tt_{curr_id}")
                                            edit_ps_val = None

                                    r2c1, r2c2 = st.columns(2)
                                    with r2c1:
                                        sc_cl1, sc_cl2, sc_cl3 = st.columns([1.2, 3.5, 0.5])
                                        sc_cl1.markdown('<div class="compact-label">Client</div>', unsafe_allow_html=True)
                                        
                                        # New? Toggle for Client Edit
                                        curr_cl = row.get('client_ref', 'General')
                                        is_cl_new_edit = sc_cl3.toggle("New", key=f"tog_cl_{row['id']}", label_visibility="collapsed")
                                        
                                        if is_cl_new_edit:
                                            edit_cl_val = sc_cl2.text_input("New Cl", placeholder="Type new...", label_visibility="collapsed", key=f"tcl_{row['id']}")
                                        else:
                                            cl_idx = all_client.index(curr_cl) if curr_cl in all_client else 0
                                            edit_cl_val = sc_cl2.selectbox("Sel Cl", all_client, index=cl_idx, label_visibility="collapsed", key=f"scl_{row['id']}")

                                    with r2c2:
                                        sc4, sc5, sc6 = st.columns([1.2, 3.5, 0.5])
                                        sc4.markdown('<div class="compact-label">Contact</div>', unsafe_allow_html=True)
                                        
                                        # New? Toggle for Contact Edit
                                        curr_c = row['coordinator']
                                        is_c_new_edit = sc6.toggle("New", key=f"tog_c_{row['id']}", label_visibility="collapsed")
                                        
                                        if is_c_new_edit:
                                            edit_c_val = sc5.text_input("New C", placeholder="Type new...", label_visibility="collapsed", key=f"tc_{row['id']}")
                                        else:
                                            c_idx = all_c.index(curr_c) if curr_c in all_c else 0
                                            edit_c_val = sc5.selectbox("Sel C", all_c, index=c_idx, label_visibility="collapsed", key=f"sc_{row['id']}")

                                    dc1, dc2 = st.columns([1.2, 8.8])
                                    dc1.markdown('<div class="compact-label">Task</div>', unsafe_allow_html=True)
                                    n_desc = dc2.text_input("Desc Edit", value=row['task_desc'], label_visibility="collapsed", key=f"ndesc_{row['id']}")

                                    r3c1, r3c2, r3c3 = st.columns(3)
                                    with r3c1:
                                        sub1, sub2 = st.columns([1, 2])
                                        sub1.markdown('<div class="compact-label">Priority</div>', unsafe_allow_html=True)
                                        prio_list = ["🔥 High", "⚡ Medium", "🧊 Low"]
                                        n_prio = sub2.selectbox("P Edit", prio_list, index=prio_list.index(row['priority']), label_visibility="collapsed", key=f"nprio_{row['id']}")
                                    with r3c2:
                                        sub3, sub4 = st.columns([1, 2])
                                        sub3.markdown('<div class="compact-label">Due</div>', unsafe_allow_html=True)
                                        n_date = sub4.date_input("D Edit", value=row['due_date'], format="DD/MM/YYYY", label_visibility="collapsed", key=f"ndate_{row['id']}")
                                    with r3c3:
                                        sub5, sub6 = st.columns([1, 2])
                                        sub5.markdown('<div class="compact-label">User</div>', unsafe_allow_html=True)
                                        curr = row['assigned_to'] or "Unassigned"
                                        clean_users = active_users_list
                                        if curr and curr not in clean_users: clean_users = [curr] + clean_users
                                        a_idx = clean_users.index(curr) if curr in clean_users else 0
                                        n_ass = sub6.selectbox("U Edit", clean_users, index=a_idx, label_visibility="collapsed", key=f"nass_{row['id']}")

                                    rc1, rc2 = st.columns([1.2, 8.8])
                                    rc1.markdown('<div class="compact-label">Remarks</div>', unsafe_allow_html=True)
                                    n_rem = rc2.text_input("Rem Edit", value=row.get('staff_remarks', ''), label_visibility="collapsed", key=f"nrem_{row['id']}")

                                    n_pts = st.text_area("Details Edit", value=row.get('points', ''), height=80, label_visibility="collapsed", placeholder="Detailed points...", key=f"npts_{row['id']}")
                                    
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
                                    
                                    if b1.button("💾 Save", type="primary", key=f"save_{row['id']}"):
                                        if update_task_full(row['id'], n_desc, n_date, n_prio, n_rem, n_ass, n_pts, row.get('email_subject', ''), edit_c_val or 'General', edit_p_val or 'General', is_manager, edit_cl_val or 'General', t_sel, edit_ps_val):
                                            fetch_tasks.clear()
                                            st.session_state['show_update_success'] = True
                                            st.rerun()
                                    
                                    if "Completed" not in sel_filter:
                                        with b2:
                                            c_n_input = st.text_input("Close Note", key=f"cn_{row['id']}", placeholder="Closing note...", label_visibility="collapsed")
                                        if b3.button("✅ Close", type="primary", key=f"close_{row['id']}"):
                                            update_task_status(row['id'], "Completed", c_n_input or n_rem or "Closed")
                                            fetch_tasks.clear()
                                            st.session_state['show_update_success'] = True
                                            st.rerun()
                                    else:
                                        if b3.button("🔄 Re-Open", type="primary", key=f"reopen_{row['id']}"): 
                                            update_task_status(row['id'], "Open")
                                            fetch_tasks.clear()
                                            st.session_state['show_update_success'] = True
                                            st.rerun()
                        
                        if "Completed" not in sel_filter:
                            with col_btn:
                                if row['id'] not in st.session_state['bumped_ids']:
                                    if st.button("⬇️", key=f"bump_{row['id']}", help="Move to bottom", type="primary"):
                                        st.session_state['bumped_ids'].add(row['id'])
                                        st.rerun()

            else:
                st.info("👋 No tasks found.")

if __name__ == "__main__":
    main()
