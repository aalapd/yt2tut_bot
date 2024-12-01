TUTORIAL_PROMPT = """Create a comprehensive tutorial based on the provided transcript. Begin by analyzing the content of the transcript thoroughly to identify its core themes, key concepts, and main points.

Break down the information into logical sections or chapters that flow in a structured and coherent manner. Ensure each section focuses on one main idea or topic to maintain clarity and engagement.

Use simple and precise language to explain each complex idea. Start each section with an overview and end with a summary or key takeaways or insights.

Conclude with a recap of the entire tutorial, highlighting the main points and encouraging readers to apply their newfound knowledge. Include actionable steps or exercises at the end to reinforce learning and provide practical applications.

Ensure the tutorial is easy to navigate by using subheadings and providing a logical progression of topics. Use plaintext formatting only. Do not format the headings or subheadings. Use plain numbered lists.

Transcript: {transcript_text}"""

def get_tutorial_prompt(transcript_text: str) -> str:
    """
    Returns the formatted tutorial prompt with the given transcript.
    
    Args:
        transcript_text (str): The video transcript to include in the prompt
        
    Returns:
        str: The complete formatted prompt
    """
    return TUTORIAL_PROMPT.format(transcript_text=transcript_text)