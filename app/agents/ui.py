import streamlit as st
from app.agents.graph import chat 




input_msg = st.text_input("Enter Question here ...")



if input_msg:
    op =  chat(input_msg,"t1")
    st.markdown(op)
    
