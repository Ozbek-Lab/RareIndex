# Natural Language Search for RareIndex

This feature allows users to query the RareIndex database using natural language, powered by local LLMs via Ollama.

## 🚀 Features

- **Natural Language Queries**: Ask questions in plain English
- **Local LLM Support**: Uses Ollama for privacy and control
- **SQL Safety**: Only SELECT statements are allowed
- **HTMX Integration**: Real-time search results without page reloads
- **Multiple Model Support**: Choose from different AI models
- **Schema-Aware**: Understands your database structure

## 📋 Prerequisites

1. **Python Dependencies**: Already installed in your virtual environment
2. **Ollama**: Local LLM server (see installation below)
3. **Django**: Your existing Django setup

## 🛠️ Installation

### 1. Install Ollama

```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Start Ollama service
ollama serve
```

### 2. Download a Model

```bash
# Recommended: SQLCoder (specialized for SQL generation)
ollama pull sqlcoder

# Alternative models
ollama pull mistral
ollama pull llama2
ollama pull codellama
```

### 3. Test the Setup

```bash
# Run the test script
python test_sql_agent.py
```

## 🎯 Usage

### 1. Start Django Server

```bash
python manage.py runserver
```

### 2. Access the Search Interface

Visit: `http://localhost:8000/lab/nl-search/page/`

Or navigate via the sidebar: Click "AI Search" in the left navigation.

### 3. Ask Questions

Try these example queries:

- **"Show me all samples collected in 2024"**
- **"How many individuals have samples?"**
- **"List all tests performed last month"**
- **"Show individuals with more than 3 samples"**
- **"What are the most common sample types?"**
- **"Show all pending tasks"**

## 🔧 Configuration

### Model Selection

You can choose from different AI models in the dropdown:

- **SQLCoder** (Recommended): Specialized for SQL generation
- **Mistral**: Good general-purpose model
- **Llama2**: Meta's open-source model
- **CodeLlama**: Specialized for code generation

### Database Schema

The system automatically understands your database structure:

- `lab_individual`: Patients/individuals
- `lab_sample`: Biological samples
- `lab_test`: Tests performed on samples
- `lab_analysis`: Analysis results
- `lab_project`: Research projects
- `lab_task`: Tasks and workflows
- `lab_family`: Family information
- `lab_institution`: Healthcare institutions
- And more...

## 🛡️ Security Features

- **SQL Injection Protection**: Only SELECT statements are allowed
- **Query Validation**: All SQL is parsed and validated before execution
- **Result Limiting**: Results are limited to prevent overwhelming responses
- **Error Handling**: Graceful error messages for failed queries

## 🔍 How It Works

1. **User Input**: User types a natural language question
2. **LLM Processing**: Ollama converts the question to SQL
3. **SQL Validation**: System validates the generated SQL
4. **Query Execution**: Safe SQL is executed against the database
5. **Result Formatting**: Results are formatted for display
6. **HTMX Update**: Results appear instantly without page reload

## 🐛 Troubleshooting

### Common Issues

1. **"Failed to connect to Ollama"**
   - Make sure Ollama is running: `ollama serve`
   - Check if the model is installed: `ollama list`

2. **"Model not found"**
   - Install the model: `ollama pull sqlcoder`
   - Try a different model from the dropdown

3. **"No results found"**
   - Rephrase your question more simply
   - Check that your question relates to available data
   - Try a different AI model

4. **"Only SELECT statements are allowed"**
   - The system only allows read-only queries for security
   - Rephrase your question to ask for information, not to modify data

### Debug Mode

To see more detailed error information, check the Django logs:

```bash
python manage.py runserver --verbosity=2
```

## 📁 File Structure

```
lab/
├── sql_agent.py              # Core SQL agent functionality
├── views.py                  # Django views for search
├── urls.py                   # URL routing
└── templates/lab/
    ├── nl_search.html        # Main search interface
    └── partials/
        ├── nl_search_result.html    # Results display
        └── nl_search_error.html     # Error display
```

## 🔄 API Endpoints

- `GET /lab/nl-search/page/` - Main search page
- `POST /lab/nl-search/` - Process search queries (HTMX)

## 🚀 Future Enhancements

- **Query History**: Save and reuse previous queries
- **Export Results**: Download results as CSV/Excel
- **Advanced Filtering**: Combine with existing filters
- **Query Templates**: Pre-built query templates
- **Performance Optimization**: Query caching and optimization
- **Multi-language Support**: Support for other languages

## 🤝 Contributing

To enhance the natural language search:

1. **Add New Models**: Update the model selection dropdown
2. **Improve Prompts**: Enhance the prompt engineering in `sql_agent.py`
3. **Add Features**: Extend the UI or backend functionality
4. **Optimize Performance**: Improve query execution and formatting

## 📞 Support

If you encounter issues:

1. Check the troubleshooting section above
2. Verify Ollama is running and models are installed
3. Check Django logs for detailed error messages
4. Test with simple queries first

---

**Note**: This feature requires Ollama to be running locally. For production deployment, consider using a managed LLM service or deploying Ollama on a dedicated server. 