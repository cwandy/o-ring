"""Streamlit entry point. Run with: streamlit run app/streamlit_app.py"""

from pathlib import Path

import streamlit as st

from oring_designer.i18n import t

PAGES = Path(__file__).resolve().parent / "pages"


st.set_page_config(page_title=t("app.title"), layout="wide")
nav = st.navigation([
    st.Page(str(PAGES / "0_Yuva_Hesaplayici.py"), title=t("ui.page_calc"), icon="🧮", default=True),
    st.Page(str(PAGES / "1_Yuva_Kontrol.py"), title=t("ui.page_check"), icon="🔧"),
    st.Page(str(PAGES / "2_Tolerans_Analizi.py"), title=t("ui.page_tolerance"), icon="📐"),
    st.Page(str(PAGES / "3_Olcu_Oner.py"), title=t("ui.page_size"), icon="📏"),
    st.Page(str(PAGES / "4_Yayli_Conta.py"), title=t("ui.page_se"), icon="🌀"),
])
nav.run()
