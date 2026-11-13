"""Streamlit entry point. Run with: streamlit run app/streamlit_app.py"""

import streamlit as st

from oring_designer import __version__
from oring_designer.i18n import t

st.set_page_config(page_title=t("app.title"), layout="wide")
st.title(t("app.title"))
st.write(t("app.hello"))
st.caption(t("app.version", version=__version__))
