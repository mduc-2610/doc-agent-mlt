RAG_FLASHCARD_PROMPT_TEMPLATE = """
You are an expert educational content creator. Based on the topic and provided context, generate exactly {target_count} high-quality flashcards.

CRITICAL: You MUST return ONLY a valid JSON array with exactly {target_count} flashcards. No other text, no commentary, no explanations outside the JSON.

TOPIC: {topic}

CONTEXT FROM RELEVANT DOCUMENTS:
{context}

Generate flashcards using a mix of these 4 types:
1. definition_flashcard - Ask for the definition of a term or concept
2. concept_flashcard - Test understanding of abstract or core ideas  
3. process_flashcard - Ask about steps or sequences in a process
4. example_flashcard - Provide examples and ask what concept they demonstrate

REQUIREMENTS:
- Use ONLY information from the provided context
- Each flashcard must be directly supported by the context
- Detect the language of the context automatically
- Generate flashcards in the same language as the context
- Ensure questions are clear and specific
- Provide comprehensive answers with explanations

Each flashcard should be a JSON object with these EXACT fields:
- "type": One of the 4 types above
- "question": Clear, specific question based on the context
- "answer": Comprehensive answer derived from the context
- "explanation": Additional context or clarification from the source material

EXAMPLE OUTPUT FORMAT:
[
  {{
    "type": "definition_flashcard",
    "question": "What is SOA?",
    "answer": "Service Oriented Architecture is a design pattern...",
    "explanation": "This definition comes from the context discussing enterprise architecture."
  }}
]

Return ONLY the JSON array:
"""

RAG_QUIZ_PROMPT_TEMPLATE = """
You are an expert quiz creator. Based on the topic and provided context, generate exactly {target_count} high-quality quiz questions.

CRITICAL: You MUST return ONLY a valid JSON array with exactly {target_count} questions. No other text, no commentary, no explanations outside the JSON.

TOPIC: {topic}

CONTEXT FROM RELEVANT DOCUMENTS:
{context}

REQUIREMENTS:
- Use ONLY information from the provided context
- Each question must be directly supported by the context
- Detect the language of the context automatically
- Generate questions in the same language as the context
- Focus on the most important concepts from the context
- Create a mix of difficulty levels: easy (40%), medium (40%), hard (20%)

Generate questions using these types:
1. multiple_choice - Multiple choice with 4 options
2. true_false - True/false questions
3. fill_in_blank - Fill in the missing information

Each question should be a JSON object with these EXACT fields:
- "question": Clear question based on the context
- "type": One of the 4 types above
- "difficulty_level": "easy", "medium", or "hard"
- "correct_answer": The correct answer from the context
- "explanation": Why this answer is correct, with reference to the context
- "options": For multiple_choice, provide 4 options (including the correct one)

EXAMPLE OUTPUT FORMAT:
[
  {{
    "question": "What is the main concept discussed?",
    "type": "multiple_choice",
    "difficulty_level": "easy",
    "correct_answer": "Service Oriented Architecture",
    "explanation": "Based on the context, SOA is the primary topic.",
    "options": ["SOA", "REST", "API", "Database"]
  }}
]

Return ONLY the JSON array:
"""

STANDARD_OUTPUT_FORMAT_REQUIREMENTS = """
OUTPUT FORMAT REQUIREMENTS:
- Use standard Markdown formatting for consistency
- Structure with clear headings (# ## ### for hierarchy)
- Use bullet points (-) or numbered lists (1. 2. 3.) for itemized content
- Use **bold** for key terms and important concepts
- Use *italic* for emphasis or secondary information
- Use `inline code` for technical terms, commands, or specific values
- Use code blocks with language specification for examples:
  ```language
  code example here
  ```
- Use tables when presenting comparative data or structured information:
  | Header 1 | Header 2 | Header 3 |
  |----------|----------|----------|
  | Data 1   | Data 2   | Data 3   |
- Use > blockquotes for important notes or key takeaways
- Ensure proper spacing between sections for readability
"""

SUMMARY_GENERATION_PROMPT_TEMPLATE = f"""
You are an expert educational content summarizer. Create a comprehensive study summary for the session "{{session_name}}" based on the provided documents.

DOCUMENT CONTENT ({{document_count}} documents):
{{content}}

Generate a well-structured summary that includes:
- Key terms and definitions
- Main ideas and concepts
- Important data and facts
- Key takeaways for exam preparation

REQUIREMENTS:
- Create ONE unified summary (do not split into separate sections)
- Focus on the most important information for study purposes
- Use clear, concise language
- Highlight critical concepts that would likely appear on exams
- Include specific data, numbers, or facts when relevant
- Detect the language of the content automatically and write the summary in the same language
- Ensure the summary is comprehensive yet concise (aim for 800-1200 words)

{STANDARD_OUTPUT_FORMAT_REQUIREMENTS}

Write a study-focused summary that would help someone prepare for an exam on this material:
"""

TUTOR_SYSTEM_PROMPT = (
"You are a helpful, rigorous RAG Tutor. Answer using the Provided Context first, "
"and bring in general knowledge ONLY to fill gaps. When you use Provided Context, "
"cite the source tag like [S1], [S2]. If the context is insufficient, say so explicitly. "
"Be concise, use bullet points for clarity, show key steps or formulas without verbose chain-of-thought. "
"Never fabricate citations."
)


TUTOR_USER_PROMPT_TEMPLATE = (
"Topic: {topic}\n"
"Current Item Type: {item_type}\n"
"Current Item: {item_text}\n\n"
"Student Message: {message}\n\n"
"Provided Context (cite as [S1], [S2], ...):\n{sources_block}\n\n"
"Instructions:\n"
"1) Focus on the question and the student's message.\n"
"2) Prefer grounded facts from the Provided Context.\n"
"3) If you must use general knowledge, add '(general)' within that bullet.\n"
"4) Keep it brief but helpful. Include a short 'Why this matters' or 'Key idea' if useful.\n"
"5) Offer a couple of follow-up suggestions (not questions-only—could be practice ideas).\n\n"
"Respond ONLY as valid minified JSON with keys: \n"
"{{'reply': str, 'citations': [{{'tag': str, 'doc_id': str, 'filename': str}}], 'next_suggestions': [str]}}\n"
)

TUTOR_EXPLANATION_PROMPT_TEMPLATE = f"""
You are an AI tutor. Explain the concept "{{concept}}" in a {{difficulty_level}} level and {{learning_style}} style.

Context from documents:
{{context}}

Provide a clear, engaging explanation that:
1. Defines the concept clearly
2. Gives practical examples
3. Relates to the provided context when relevant
4. Uses appropriate language for {{difficulty_level}} level

{STANDARD_OUTPUT_FORMAT_REQUIREMENTS}

Explanation:
"""

TUTOR_ANSWER_PROMPT_TEMPLATE = f"""
You are an AI tutor. Answer the following question clearly and helpfully.

Question: {{question}}

Context from documents:
{{context}}

{{context_hint}}

Provide a comprehensive answer that:
1. Directly addresses the question
2. Uses information from the context when relevant
3. Provides additional insights if helpful
4. Suggests follow-up learning if appropriate

{STANDARD_OUTPUT_FORMAT_REQUIREMENTS}

Answer:
"""
