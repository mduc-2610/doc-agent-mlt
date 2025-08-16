RAG_FLASHCARD_PROMPT_TEMPLATE = """
You are an expert educational content creator. Based on the topic and provided context, generate exactly {target_count} high-quality flashcards.

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

Each flashcard should be a JSON object with:
- "type": One of the 4 types above
- "question": Clear, specific question based on the context
- "answer": Comprehensive answer derived from the context
- "explanation": Additional context or clarification from the source material

Return exactly {target_count} flashcards as a JSON array with no additional commentary.
"""

RAG_QUIZ_PROMPT_TEMPLATE = """
You are an expert quiz creator. Based on the topic and provided context, generate exactly {target_count} high-quality quiz questions.

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
3. short_answer - Brief answer questions
4. fill_in_blank - Fill in the missing information

Each question should be a JSON object with:
- "question": Clear question based on the context
- "type": One of the 4 types above
- "difficulty_level": "easy", "medium", or "hard"
- "correct_answer": The correct answer from the context
- "explanation": Why this answer is correct, with reference to the context
- "options": For multiple_choice, provide 4 options (including the correct one)

Return exactly {target_count} questions as a JSON array with no additional commentary.
"""

ANSWER_GENERATION_PROMPT_TEMPLATE = """
Based on the following question and context, generate a comprehensive correct answer with explanation.

QUESTION: {question}
CONTEXT: {context}

Provide a JSON object with:
- "answer": The correct answer based on the context
- "explanation": Detailed explanation of why this is correct, referencing the context
- "source_reference": Brief reference to which part of the context supports this answer

Ensure the answer is directly supported by the provided context.
"""

INCORRECT_ANSWER_PROMPT_TEMPLATE = """
Generate a brief explanation for why this answer is incorrect in the given context.

INCORRECT ANSWER: {incorrect_answer}
CORRECT ANSWER: {correct_answer}
CONTEXT: {context}

Provide a concise explanation (1-2 sentences) of why the incorrect answer is wrong and why the correct answer is right based on the context.
"""

QUALITY_VALIDATION_PROMPT_TEMPLATE = """
Evaluate the quality of this quiz question based on the provided context.

QUESTION: {question}
ANSWER: {answer}
EXPLANATION: {explanation}
CONTEXT: {context}

Rate the question on a scale of 1-10 considering:
1. Clarity and specificity of the question
2. Accuracy of the answer based on context
3. Quality of explanation
4. Relevance to the context
5. Educational value

Provide a JSON object with:
- "score": Number from 1-10
- "feedback": Brief explanation of the score
- "suggestions": Any improvements needed
"""

CONTEXT_RELEVANCE_PROMPT_TEMPLATE = """
Analyze how well this generated content relates to the source context.

GENERATED CONTENT:
Question: {question}
Answer: {answer}

SOURCE CONTEXT:
{context}

Provide a JSON object with:
- "relevance_score": Number from 0-1 (0 = not relevant, 1 = highly relevant)
- "key_concepts_matched": List of key concepts from context that appear in the question/answer
- "missing_context": Important context information not reflected in the generated content
"""

HUMAN_REVIEW_TEMPLATE = """
QUESTION GENERATION BATCH FOR REVIEW

Topic: {topic}
Generated: {created_at}
Model: {model_version}
Status: {status}

CONTEXT USED:
{context}

GENERATED QUESTIONS ({question_count} total):
{questions}

QUALITY METRICS:
- Average validation score: {avg_score}
- High quality questions (score > 8): {high_quality_count}
- Questions needing review (score < 6): {low_quality_count}

REVIEW ACTIONS:
[ ] Approve all questions
[ ] Approve selected questions (specify IDs: _______)
[ ] Reject batch and regenerate
[ ] Request modifications

REVIEWER NOTES:
_________________________________________________
_________________________________________________

Reviewer: _________________ Date: _____________
"""