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

        # --- NEW TASK SCREEN ---
        if nav_mode == "New Task":
            st.header("✨ Create New Task")
            
            if st.session_state['show_creation_success']:
                st.success("✅ Task Created Successfully!")
                st.session_state['show_creation_success'] = False
                
            # Load master data for dropdowns
            _, all_p, all_c, all_client, all_t = load_data(None)

            # --- USING STREAMLIT FORM WITH NATIVE CLEAR ---
            with st.form("new_task_form", clear_on_submit=True):
                r1c1, r1c2 = st.columns(2)
                with r1c1: 
                    sc1, sc2, sc3 = st.columns([1.2, 2, 2])
                    sc1.markdown('<div class="compact-label">Project</div>', unsafe_allow_html=True)
                    p_sel = sc2.selectbox("Select Project", all_p, index=None, label_visibility="collapsed")
                    p_new = sc3.text_input("New Project", placeholder="Type new...", label_visibility="collapsed")
                with r1c2:
                    col_tt_lbl, col_tt_val = st.columns([1.2, 4])
                    col_tt_lbl.markdown('<div class="compact-label">Task Type</div>', unsafe_allow_html=True)
                    t_sel = col_tt_val.selectbox("Type", all_t, index=0, label_visibility="collapsed")
                    
                r2c1, r2c2 = st.columns(2)
                with r2c1:
                    sc_cl1, sc_cl2, sc_cl3 = st.columns([1.2, 2, 2])
                    sc_cl1.markdown('<div class="compact-label">Client</div>', unsafe_allow_html=True)
                    cl_sel = sc_cl2.selectbox("Select Client", all_client, index=None, label_visibility="collapsed")
                    cl_new = sc_cl3.text_input("New Client", placeholder="Type new...", label_visibility="collapsed")
                with r2c2: 
                    sc4, sc5, sc6 = st.columns([1.2, 2, 2])
                    sc4.markdown('<div class="compact-label">Contact</div>', unsafe_allow_html=True)
                    c_sel = sc5.selectbox("Select Contact", all_c, index=0, label_visibility="collapsed")
                    c_new = sc6.text_input("New Contact", placeholder="Type new...", label_visibility="collapsed")

                c4_lbl, c4_val = st.columns([1.2, 8.8])
                c4_lbl.markdown('<div class="compact-label">Task</div>', unsafe_allow_html=True)
                t_desc = c4_val.text_input("Task Description", placeholder="Enter task summary...", label_visibility="collapsed")

                r4c1, r4c2, r4c3 = st.columns(3)
                with r4c1:
                    sub1, sub2 = st.columns([1, 2])
                    sub1.markdown('<div class="compact-label">Priority</div>', unsafe_allow_html=True)
                    prio = sub2.selectbox("Pr", ["🔥 High", "⚡ Medium", "🧊 Low"], index=1, label_visibility="collapsed")
                with r4c2:
                    sub3, sub4 = st.columns([1, 2])
                    sub3.markdown('<div class="compact-label">Due</div>', unsafe_allow_html=True)
                    due = sub4.date_input("Dt", value=date.today(), format="DD/MM/YYYY", label_visibility="collapsed")
                with r4c3:
                    sub5, sub6 = st.columns([1, 2])
                    sub5.markdown('<div class="compact-label">User</div>', unsafe_allow_html=True)
                    ass_to = sub6.selectbox("Assign", active_users_list, index=default_user_idx, label_visibility="collapsed")

                pt1, pt2 = st.columns([1.2, 8.8])
                pt1.markdown('<div class="compact-label">Points</div>', unsafe_allow_html=True)
                pts = pt2.text_area("Points", height=100, label_visibility="collapsed", placeholder="Detailed breakdown of tasks...")
                
                # --- LIVE PREVIEW (The "Super" Option) ---
                prev_p = p_new.strip() if p_new.strip() else (p_sel or "General")
                prev_cl = cl_new.strip() if cl_new.strip() else (cl_sel or "General")
                prev_c = c_new.strip() if c_new.strip() else (c_sel or "General")
                
                st.markdown(f"""
                <div style="background-color: #f0f2f6; padding: 10px; border-radius: 5px; border-left: 5px solid #ff4b4b; margin-top: 10px;">
                    <span style="font-weight: bold; color: #555;">📝 Saving as:</span> 
                    Project: <span style="color: #ff4b4b; font-weight: bold;">{prev_p}</span> | 
                    Client: <span style="color: #ff4b4b; font-weight: bold;">{prev_cl}</span> | 
                    Contact: <span style="color: #ff4b4b; font-weight: bold;">{prev_c}</span>
                </div>
                """, unsafe_allow_html=True)

                submitted = st.form_submit_button("🚀 Create Task", type="primary", use_container_width=True)

            if submitted:
                final_p = p_new.strip() if p_new.strip() else (p_sel or "General")
                final_cl = cl_new.strip() if cl_new.strip() else (cl_sel or "General")
                final_c = c_new.strip() if c_new.strip() else (c_sel or "General")
                
                if not ass_to:
                    st.error("⚠️ Please assign the task to a user.")
                elif not t_desc.strip():
                    st.error("⚠️ Please enter a task description.")
                else:
                    if add_task(current_user, ass_to, t_desc, prio, due, final_p, final_c, "", pts, final_cl, t_sel):
                        fetch_tasks.clear() # Clear cache for fresh data
                        st.session_state['show_creation_success'] = True
                        st.rerun()

        # --- DASHBOARD SCREEN ---
        elif nav_mode == "Dashboard":
            view_email = None
            if is_manager:
                c_filter, c_title = st.columns([1, 3])
                view_target = c_filter.selectbox("View User:", ["All Users"] + get_active_users())
                if view_target != "All Users": view_email = view_target
                c_title.title("📔 Operational Diary")
            else:
                st.title("📔 My Diary")
                view_email = current_user
            
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
                                        sc1, sc2, sc3 = st.columns([1.2, 2, 2])
                                        sc1.markdown('<div class="compact-label">Project</div>', unsafe_allow_html=True)
                                        curr_p = row['project_ref']
                                        p_idx = all_p.index(curr_p) if curr_p in all_p else 0
                                        sel_p = sc2.selectbox("Proj Select", all_p, index=p_idx, label_visibility="collapsed", key=f"sp_{row['id']}")
                                        def_txt_p = curr_p if curr_p not in all_p else ""
                                        text_p = sc3.text_input("Proj New", value=def_txt_p, placeholder="Override...", label_visibility="collapsed", key=f"tp_{row['id']}")
                                        final_edit_p = text_p.strip() if text_p.strip() else sel_p
                                        
                                    with r1c2:
                                        c_ttl, c_ttv = st.columns([1.2, 4])
                                        c_ttl.markdown('<div class="compact-label">Task Type</div>', unsafe_allow_html=True)
                                        curr_t = row.get('task_type', 'Task')
                                        t_idx = ["Task", "Followup"].index(curr_t) if curr_t in ["Task", "Followup"] else 0
                                        t_sel = c_ttv.selectbox("Type Edit", ["Task", "Followup"], index=t_idx, label_visibility="collapsed", key=f"tt_{row['id']}")

                                    r2c1, r2c2 = st.columns(2)
                                    with r2c1:
                                        sc_cl1, sc_cl2, sc_cl3 = st.columns([1.2, 2, 2])
                                        sc_cl1.markdown('<div class="compact-label">Client</div>', unsafe_allow_html=True)
                                        curr_cl = row.get('client_ref', 'General')
                                        cl_idx = all_client.index(curr_cl) if curr_cl in all_client else 0
                                        sel_cl = sc_cl2.selectbox("Client Select", all_client, index=cl_idx, label_visibility="collapsed", key=f"scl_{row['id']}")
                                        def_txt_cl = curr_cl if curr_cl not in all_client else ""
                                        text_cl = sc_cl3.text_input("Client New", value=def_txt_cl, placeholder="Override...", label_visibility="collapsed", key=f"tcl_{row['id']}")
                                        final_edit_cl = text_cl.strip() if text_cl.strip() else sel_cl
                                    with r2c2:
                                        sc4, sc5, sc6 = st.columns([1.2, 2, 2])
                                        sc4.markdown('<div class="compact-label">Contact</div>', unsafe_allow_html=True)
                                        curr_c = row['coordinator']
                                        c_idx = all_c.index(curr_c) if curr_c in all_c else 0
                                        sel_c = sc5.selectbox("Contact Select", all_c, index=c_idx, label_visibility="collapsed", key=f"sc_{row['id']}")
                                        def_txt_c = curr_c if curr_c not in all_c else ""
                                        text_c = sc6.text_input("Contact New", value=def_txt_c, placeholder="Override...", label_visibility="collapsed", key=f"tc_{row['id']}")
                                        final_edit_c = text_c.strip() if text_c.strip() else sel_c

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
                                    
                                    b1, b2, b3 = st.columns([1, 2, 1])
                                    
                                    if b1.button("💾 Save", type="primary", key=f"save_{row['id']}"):
                                        if update_task_full(row['id'], n_desc, n_date, n_prio, n_rem, n_ass, n_pts, row.get('email_subject', ''), final_edit_c, final_edit_p, is_manager, final_edit_cl, t_sel):
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
