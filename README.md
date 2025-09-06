# dblab-question-generation

A question generation system for database lab activities.

## Setup and Installation

Follow these steps to set up and run the project:

### 1. Create Virtual Environment
```bash
python -m venv env
```

### 2. Activate Virtual Environment
```bash
env\Scripts\activate
```

### 3. Install Dependencies
```bash
python -m pip install -r requirements.txt
```

### 4. Configure Environment
Copy the example environment file and configure your settings:
```bash
copy .env.example .env
```
Edit the `.env` file with your specific configuration.

### 5. Run the Application
```bash
python main.py
```

## Project Structure

- `app/` - Main application code
  - `api/` - API route handlers
  - `models/` - Database models
  - `processors/` - Content and question processing
  - `services/` - Business logic services
  - `utils/` - Utility functions
- `document_files/` - Document storage and processing
- `requirements.txt` - Python dependencies
- `main.py` - Application entry point
