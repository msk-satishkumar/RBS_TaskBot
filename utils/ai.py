import streamlit as st
from langchain_google_genai import ChatGoogleGenerativeAI

def generate_variations(prompt, mode, instructions, api_key):
    try:
        if not api_key: return ["⚠️ AI Key Missing", "⚠️ Check Secrets", "⚠️ Contact Admin"]
        llm = ChatGoogleGenerativeAI(model="gemini-pro", google_api_key=api_key)
        final_prompt = f"""
        You are a top-tier Executive Communication Assistant.
        Task: Rewrite the user's raw input into a perfect {mode} message.
        User's Personal Master Instructions: {instructions}
        Raw Input: "{prompt}"
        Output Requirement: Provide exactly 3 distinct variations separated by '|||'.
        """
        response = llm.invoke(final_prompt)
        return response.content.split('|||')
    except Exception as e:
        return [f"Error: {str(e)}", "Try again", "Check connection"]
