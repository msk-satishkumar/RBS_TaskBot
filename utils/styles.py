import streamlit as st

def apply_custom_styles():
    st.markdown("""
<style>
    .block-container { padding-top: 1rem !important; padding-bottom: 1rem !important; }
    p, .stMarkdown { font-size: 14px !important; margin-bottom: 0px !important; }
    h1, h2, h3 { margin-bottom: 0px !important; margin-top: 0rem !important; }
    
    .streamlit-expanderHeader { 
        padding: 10px 15px !important;
        background-color: #fcfcfc; border-radius: 8px; font-weight: 700;
        border: 1px solid #eee; transition: 0.3s;
    }
    
    .stButton button { border-radius: 6px; font-weight: 600; height: 2.4rem; }
    
    /* RED BUTTON STYLE LABELS */
    .compact-label {
        font-weight: 700; font-size: 13px; color: #ffffff !important;
        background-color: #ff4b4b; /* RBS Red */
        padding: 6px 12px; border-radius: 6px;
        margin-top: 5px; text-align: left; display: block; width: 100%;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1); border: none;
    }
    
    /* Result Cards */
    .result-card { 
        background-color: #f8f9fa; padding: 15px; border-radius: 8px; 
        border-left: 5px solid #ff4b4b; margin-bottom: 15px; 
        box-shadow: 0 2px 5px rgba(0,0,0,0.05); 
    }
    .card-title { 
        font-weight: 800; color: #ff4b4b; margin-bottom: 8px; 
        font-size: 14px; text-transform: uppercase; letter-spacing: 0.5px; 
    }
    
    input[type="date"] { text-transform: uppercase; }
    .element-container { margin-bottom: 3px !important; }
    
    /* BLINKING OVERDUE ALERT */
    @keyframes blinker {
        50% { opacity: 0; }
    }
    .alert-blink {
        color: #ff4b4b;
        font-weight: 800;
        font-size: 14px;
        text-transform: uppercase;
        animation: blinker 1.5s linear infinite;
        margin-bottom: 5px;
    }
    
    /* Bump Button Specific Style */
    div[data-testid="column"] button[kind="secondary"] {
        border: 1px solid #eee;
        color: #555;
        padding: 0px 10px;
    }

    /* --- TOOLTIP VISIBILITY & BEHAVIOR FIXES --- */
    div[data-testid="stTooltipHoverTarget"] {
        width: 100% !important;
        height: 100% !important;
        display: block !important;
    }
    div[data-testid="column"], 
    div[data-testid="stHorizontalBlock"], 
    div[data-testid="stVerticalBlock"], 
    div[data-testid="stExpanderDetails"], 
    div.element-container {
        overflow: visible !important;
    }
    div[data-testid="stTooltipContent"] {
        z-index: 999999 !important;
    }
</style>
""", unsafe_allow_html=True)
