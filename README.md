# AI Code Review Agent 🤖

An AI-powered autonomous code review system that analyzes GitHub Python repositories using AST parsing and Large Language Models (Groq LLM) to generate structured code review findings with confidence scoring and an interactive Streamlit dashboard.

---

## Features

✅ Clone and analyze public GitHub repositories  
✅ Scan Python source files automatically  
✅ Parse code using Python AST  
✅ Extract functions, classes, and async functions  
✅ AI-powered code review using Groq LLM  
✅ Severity classification (Low / Medium / High)  
✅ Confidence scoring with verification labels  
✅ CSV and JSON export support  
✅ Interactive Streamlit dashboard  
✅ Visual analytics with charts and filters  

---

## Tech Stack

### Backend
- Python
- AST (Abstract Syntax Tree)
- Groq API (Llama 3.3 70B)

### Frontend
- Streamlit
- Plotly
- Pandas

### Utilities
- GitPython
- python-dotenv

---

## Project Architecture

```text
GitHub Repository URL
        ↓
Repository Cloner
        ↓
Python File Scanner
        ↓
AST Parser
        ↓
Code Chunk Extractor
        ↓
AI Review Engine (Groq LLM)
        ↓
Confidence Classifier
        ↓
CSV Report Generator
        ↓
Streamlit Dashboard
```

---

## Project Structure

```text
ai-code-review-agent/
│
├── core/
│   ├── clone_repo.py
│   ├── file_scanner.py
│   ├── parser.py
│   ├── reviewer.py
│   ├── confidence.py
│   └── pipeline.py
│
├── outputs/
│   └── review_results.csv
│
├── app.py
├── main.py
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md
```

---

## Installation

### Clone repository

```bash
git clone https://github.com/YOUR_USERNAME/ai-code-review-agent.git
cd ai-code-review-agent
```

---

### Create virtual environment

Windows:

```bash
python -m venv venv
venv\Scripts\activate
```

---

### Install dependencies

```bash
pip install -r requirements.txt
```

---

### Configure environment variables

Create `.env`

```env
GROQ_API_KEY=your_actual_api_key_here
```

---

## Usage

### Run backend pipeline

```bash
python main.py
```

---

### Run Streamlit frontend

```bash
streamlit run app.py
```

---

## Dashboard Features

- Repository URL input
- Severity filtering
- Confidence threshold filtering
- Interactive charts
- Review findings explorer
- Low confidence verification section
- CSV report export
- JSON report export

---

## Example Output

```json
{
  "file": "src/flask/app.py",
  "line": 73,
  "type": "function",
  "name": "_make_timedelta",
  "issue": "Missing input validation",
  "severity": "medium",
  "confidence": 80,
  "confidence_label": "High Confidence",
  "suggestion": "Add validation for negative input values",
  "category": "reliability"
}
```

---

## Limitations

- Currently supports Python repositories only
- Public GitHub repositories only
- Free-tier API quota limitations
- Large repositories may require chunk limiting

---

## Future Improvements

- Multi-language support
- GitHub Pull Request integration
- Authentication for private repos
- PDF report export
- Batch repository scanning
- AI explanation mode

---

## Demo Workflow

1. Enter GitHub repository URL
2. Click Analyze
3. AI scans repository
4. AST parser extracts code chunks
5. LLM reviews code
6. Findings displayed in dashboard
7. Export reports

---

## Author

**Yuvraj Singh Dhama**  
BTech Computer Science Engineering  
AI / Full Stack / DevOps Enthusiast

---

## License

MIT License