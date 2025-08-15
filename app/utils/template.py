FLASHCARD_PROMPT_TEMPLATE = """
Based on the following text, generate exactly {target_count} flashcards using a mix of these 4 types:
1. definition_flashcard  
2. concept_flashcard  
3. process_flashcard  
4. example_flashcard  

Each flashcard should be a JSON object with:
- "type": "definition_flashcard" | "concept_flashcard" | "process_flashcard" | "example_flashcard"  
- "question": "The front of the flashcard (what the learner sees)"  
- "answer": "The back of the flashcard (correct answer or explanation)"  
- "explanation": "Brief explanation to clarify or reinforce the answer"

Definitions:
- definition_flashcard: Ask for the definition of a term or phrase  
- concept_flashcard: Test understanding of abstract or core ideas  
- process_flashcard: Ask about steps or sequences in a process or procedure  
- example_flashcard: Provide examples and ask what concept they demonstrate, or vice versa

Important:
- Detect the language of the input text automatically.
- Generate the flashcards in the same language as the input.

Text: {text}

Return the flashcards as a JSON array, with no additional commentary.
"""


QUIZ_PROMPT_TEMPLATE = """
Based on the following text, generate exactly {target_count} flashcards using a mix of these 4 types:
1. definition_flashcard  
2. concept_flashcard  
3. process_flashcard  
4. example_flashcard  

Each flashcard should be a JSON object with:
- "type": "definition_flashcard" | "concept_flashcard" | "process_flashcard" | "example_flashcard"  
- "question": "The front of the flashcard (what the learner sees)"  
- "answer": "The back of the flashcard (correct answer or explanation)"  
- "explanation": "Brief explanation to clarify or reinforce the answer"

Definitions:
- definition_flashcard: Ask for the definition of a term or phrase  
- concept_flashcard: Test understanding of abstract or core ideas  
- process_flashcard: Ask about steps or sequences in a process or procedure  
- example_flashcard: Provide examples and ask what concept they demonstrate, or vice versa

Important:
- Detect the language of the input text automatically.
- Generate the flashcards in the same language as the input.

Text: {text}

Return the flashcards as a JSON array, with no additional commentary.
"""   
