import streamlit as st
import google.generativeai as genai
import os

def generate_variations(prompt, mode, instructions, api_key):
    try:
        if not api_key: return ["⚠️ AI Key Missing", "⚠️ Check Secrets", "⚠️ Contact Admin"]
        genai.configure(api_key=api_key)
        # Using the exact same model name as identified in Smart Writer
        model = genai.GenerativeModel('gemini-2.5-flash')
        
        final_prompt = f"""
        You are a top-tier Executive Communication Assistant.
        Task: Rewrite the user's raw input into a perfect {mode} message.
        User's Personal Master Instructions: {instructions}
        Raw Input: "{prompt}"
        Output Requirement: Provide exactly 3 distinct variations separated by '|||'.
        """
        response = model.generate_content(final_prompt)
        return response.text.split('|||')
    except Exception as e:
        return [f"Error: {str(e)}", "Try again", "Check connection"]

def generate_meta_prompt(raw_input, header_instructions, target_llm, api_key):
    try:
        if not api_key: return "⚠️ AI Key Missing"
        genai.configure(api_key=api_key)
        # Using the exact same model name as identified in Smart Writer
        model = genai.GenerativeModel('gemini-2.5-flash')
        
        # Define LLM specific system persona and template
        if target_llm == "ChatGPT":
            system_persona = "You are a ChatGPT prompt engineering expert. Your task is to transform raw input into a highly structured, instruction-driven, and constraint-based prompt for ChatGPT."
            template = "Format the following raw content into a clear, numbered prompt with 'Act as...', 'Context:', 'Task:', 'Constraints:', and 'Output Format:' sections."
        elif target_llm == "Gemini":
            system_persona = "You are a Gemini optimization expert. Your task is to transform raw input into a context-aware, precise, and conversational prompt for Google Gemini."
            template = "Apply the most effective Gemini-specific prompting techniques to the following content, focusing on clarity and reasoning chain-of-thought."
        elif target_llm == "Antigravity":
            system_persona = "You are an Antigravity Meta-Prompting expert. Your task is to transform raw input into a creative, abstract, and high-leverage prompt architecture."
            template = "Create a sophisticated, multi-layered meta-prompt that explores the philosophical and technical depths of the input. Use creative terminology and abstract frameworks."
        else:
            system_persona = "You are a Prompt Engineering Assistant."
            template = "Refine and optimize the following raw input into a professional prompt."

        final_prompt = f"""
        SYSTEM PERSONA: {system_persona}
        Global Header Instructions (THESE RULES ALWAYS APPLY FIRST): {header_instructions}
        
        Specific Template Role: {template}
        
        User's Raw Input: "{raw_input}"
        
        Output Requirement: Return ONLY the final optimized prompt. No conversational filler.
        """
        response = model.generate_content(final_prompt)
        return response.text
    except Exception as e:
        return f"Error: {str(e)}"
