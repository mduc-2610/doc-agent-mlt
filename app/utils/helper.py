import re
import json
from fastapi import HTTPException, UploadFile
from typing import List, Dict, Any

def clean_json_response(response_text: str) -> str:
    """Clean and extract JSON from model response"""
    response_text = re.sub(r'```json\s*', '', response_text)
    response_text = re.sub(r'```\s*', '', response_text)

    start_idx = response_text.find('[')
    end_idx = response_text.rfind(']') + 1
    
    if start_idx != -1 and end_idx != -1:
        return response_text[start_idx:end_idx]
    return response_text.strip()

def detect_url_type(url: str) -> str:
    """Detect the type of URL for processing"""
    if "youtube.com" in url or "youtu.be" in url:
        return "youtube"
    return "web"

def detect_file_type(file: UploadFile) -> str:
    """Detect file type for processing"""
    audio_types = ['audio/mpeg', 'audio/wav', 'audio/mp3']
    video_types = ['video/mp4', 'video/avi', 'video/quicktime', 'video/x-msvideo']
    document_types = ['application/pdf', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document']
    image_types = ['image/jpeg', 'image/png', 'image/gif', 'image/bmp', 'image/tiff']
    
    if file.content_type in audio_types + video_types:
        return "audio_video"
    elif file.content_type in document_types + image_types:
        return "document"
    else:
        raise HTTPException(status_code=400, detail="Unsupported file type")

def validate_json_structure(data: Dict[str, Any], required_fields: List[str]) -> bool:
    """Validate that JSON contains required fields"""
    for field in required_fields:
        if field not in data:
            return False
    return True

def calculate_readability_score(text: str) -> float:
    """Calculate simple readability score based on sentence and word length"""
    sentences = text.split('.')
    words = text.split()
    
    if len(sentences) == 0 or len(words) == 0:
        return 0.0
    
    avg_sentence_length = len(words) / len(sentences)
    avg_word_length = sum(len(word) for word in words) / len(words)
    
    # Simple readability formula (lower is more readable)
    readability = (avg_sentence_length * 0.39) + (avg_word_length * 11.8) - 15.59
    
    # Convert to 0-1 scale (1 = most readable)
    return max(0.0, min(1.0, (100 - readability) / 100))

def extract_key_concepts(text: str, max_concepts: int = 10) -> List[str]:
    """Extract key concepts from text using simple frequency analysis"""
    # Remove common words
    stop_words = {
        'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 
        'of', 'with', 'by', 'is', 'are', 'was', 'were', 'be', 'been', 'have', 
        'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could', 'should',
        'this', 'that', 'these', 'those', 'it', 'its', 'they', 'them', 'their'
    }
    
    # Extract words and count frequency
    words = re.findall(r'\b[a-zA-Z]{3,}\b', text.lower())
    word_freq = {}
    
    for word in words:
        if word not in stop_words:
            word_freq[word] = word_freq.get(word, 0) + 1
    
    # Sort by frequency and return top concepts
    sorted_concepts = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)
    return [concept[0] for concept in sorted_concepts[:max_concepts]]

def format_context_for_display(context: str, max_length: int = 500) -> str:
    """Format context text for display in UI"""
    if len(context) <= max_length:
        return context
    
    # Try to cut at sentence boundary
    truncated = context[:max_length]
    last_period = truncated.rfind('.')
    
    if last_period > max_length * 0.8:  # If we can cut reasonably close to the end
        return truncated[:last_period + 1] + "..."
    else:
        return truncated + "..."

def sanitize_question_content(content: str) -> str:
    """Sanitize question content to remove unwanted characters"""
    # Remove extra whitespace
    content = re.sub(r'\s+', ' ', content)
    
    # Remove special characters that might cause issues
    content = re.sub(r'[^\w\s\.\?\!\,\;\:\-\(\)\"\'\/]', '', content)
    
    return content.strip()

def validate_answer_options(options: List[str], correct_answer: str) -> bool:
    """Validate that answer options are valid and include correct answer"""
    if len(options) < 2:
        return False
    
    if correct_answer not in options:
        return False
    
    # Check for duplicate options
    if len(set(options)) != len(options):
        return False
    
    return True

def calculate_difficulty_score(question: str, answer: str, context: str) -> str:
    """Calculate difficulty level based on question complexity"""
    question_words = len(question.split())
    answer_words = len(answer.split())
    
    # Check for complex concepts (basic heuristic)
    complex_indicators = ['analyze', 'evaluate', 'compare', 'synthesize', 'explain why', 'how does']
    basic_indicators = ['what is', 'define', 'list', 'name', 'identify']
    
    question_lower = question.lower()
    
    complexity_score = 0
    
    # Question length factor
    if question_words > 20:
        complexity_score += 2
    elif question_words > 10:
        complexity_score += 1
    
    # Answer length factor
    if answer_words > 30:
        complexity_score += 2
    elif answer_words > 15:
        complexity_score += 1
    
    # Concept complexity
    if any(indicator in question_lower for indicator in complex_indicators):
        complexity_score += 3
    elif any(indicator in question_lower for indicator in basic_indicators):
        complexity_score -= 1
    
    # Context dependency
    question_context_overlap = len(set(question.lower().split()) & set(context.lower().split()))
    if question_context_overlap < 3:
        complexity_score += 1  # Requires more inference
    
    if complexity_score >= 5:
        return "hard"
    elif complexity_score >= 2:
        return "medium"
    else:
        return "easy"

def merge_similar_contexts(contexts: List[Dict[str, Any]], similarity_threshold: float = 0.7) -> List[Dict[str, Any]]:
    """Merge similar context chunks to avoid redundancy"""
    if len(contexts) <= 1:
        return contexts
    
    merged = []
    used_indices = set()
    
    for i, context1 in enumerate(contexts):
        if i in used_indices:
            continue
        
        current_content = context1['content']
        merged_chunks = [context1]
        used_indices.add(i)
        
        for j, context2 in enumerate(contexts[i+1:], i+1):
            if j in used_indices:
                continue
            
            # Simple similarity check based on word overlap
            words1 = set(current_content.lower().split())
            words2 = set(context2['content'].lower().split())
            
            if len(words1) > 0 and len(words2) > 0:
                overlap = len(words1 & words2)
                union = len(words1 | words2)
                similarity = overlap / union
                
                if similarity > similarity_threshold:
                    merged_chunks.append(context2)
                    used_indices.add(j)
        
        # Combine similar chunks
        if len(merged_chunks) > 1:
            combined_content = " ".join([chunk['content'] for chunk in merged_chunks])
            combined_context = {
                'content': combined_content,
                'similarity_score': sum([chunk.get('similarity_score', 0) for chunk in merged_chunks]) / len(merged_chunks),
                'source_chunks': len(merged_chunks)
            }
            merged.append(combined_context)
        else:
            merged.append(context1)
    
    return merged

def generate_review_summary(questions: List[Dict[str, Any]], flashcards: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Generate summary for human review"""
    total_items = len(questions) + len(flashcards)
    
    if total_items == 0:
        return {"error": "No content to review"}
    
    # Calculate quality metrics
    question_scores = [q.get('validation_score', 0) for q in questions if 'validation_score' in q]
    flashcard_scores = [f.get('validation_score', 0) for f in flashcards if 'validation_score' in f]
    all_scores = question_scores + flashcard_scores
    
    avg_score = sum(all_scores) / len(all_scores) if all_scores else 0
    high_quality_count = len([score for score in all_scores if score > 0.8])
    low_quality_count = len([score for score in all_scores if score < 0.6])
    
    # Difficulty distribution for questions
    difficulty_dist = {}
    for q in questions:
        diff = q.get('difficulty_level', 'unknown')
        difficulty_dist[diff] = difficulty_dist.get(diff, 0) + 1
    
    return {
        "total_items": total_items,
        "questions_count": len(questions),
        "flashcards_count": len(flashcards),
        "average_quality_score": round(avg_score, 2),
        "high_quality_items": high_quality_count,
        "low_quality_items": low_quality_count,
        "difficulty_distribution": difficulty_dist,
        "review_recommendation": "approve" if avg_score > 0.7 and low_quality_count < total_items * 0.2 else "review_needed"
    }