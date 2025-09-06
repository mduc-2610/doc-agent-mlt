SUMMARY_GENERATION_PROMPT_TEMPLATE = """
Create a comprehensive study summary for session "{session_name}" from the provided documents.

DOCUMENT CONTENT ({document_count} documents):
{content}

Generate a well-structured summary with:
- Key terms and definitions
- Main concepts and ideas
- Important facts and data
- Exam preparation highlights

Use Markdown (as .md syntax) formatting with headings, bullet points, **bold** for key terms, and proper spacing.
Write in the same language as the content. Keep it concise (800-1200 words).

Write an exam-focused summary:
"""


RAG_QUESTION_PROMPT_TEMPLATE = """
Generate EXACTLY {target_count} quiz questions as a JSON array. Be fast and efficient.

Topic: {topic}
Context: {context}

OUTPUT RULES:
- Valid JSON array only
- No extra text
- All fields required

STRUCTURE:
[{{"question": "...", "type": "multiple_choice", "difficulty_level": "medium", "correct_answer": "...", "explanation": "...", "options": ["A", "B", "C", "D"]}}]

QUALITY:
- Questions from context only
- Clear and direct
- 4 options for multiple choice

Generate {target_count} questions:
"""

RAG_FLASHCARD_PROMPT_TEMPLATE = """
Generate EXACTLY {target_count} flashcards as a JSON array. Be fast and efficient.

Topic: {topic}
Context: {context}

OUTPUT RULES:
- Valid JSON array only
- No extra text
- All fields required

STRUCTURE:
[{{"type": "concept_flashcard", "question": "...", "answer": "...", "explanation": "..."}}]

TYPES: definition_flashcard, concept_flashcard, process_flashcard, example_flashcard

Generate {target_count} flashcards:
"""
