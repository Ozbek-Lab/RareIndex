"""
SQL Agent for natural language to SQL conversion using local LLM via Ollama.
Simplified version that works without full LangChain dependencies.
"""
import os
import logging
import requests
import json
from typing import Optional, Dict, Any
from django.conf import settings
from django.db import connection

logger = logging.getLogger(__name__)

class SQLSafetyParser:
    """Parser to ensure only SELECT statements are executed."""
    
    def parse(self, text: str) -> str:
        """Parse and validate SQL query."""
        # Log the original text for debugging
        print(f"SQL Parser - Original text: {repr(text)}")
        logger.info(f"SQL Parser - Original text: {repr(text)}")
        
        # Clean up the text
        sql = text.strip()
        
        # Simple cleanup - remove common markdown and formatting
        if sql.startswith("```sql"):
            sql = sql[6:]
        elif sql.startswith("```{sql}"):
            sql = sql[8:]
        if sql.endswith("```"):
            sql = sql[:-3]
        
        # Remove any leading/trailing whitespace and newlines
        sql = sql.strip()
        
        print(f"SQL Parser - After cleanup: {repr(sql)}")
        logger.info(f"SQL Parser - After cleanup: {repr(sql)}")
        
        # Final check - ensure it's a SELECT statement
        if not sql.lower().startswith("select"):
            raise ValueError(f"Only SELECT statements are allowed. Got: {sql[:50]}...")
        
        return sql

def get_database_connection_string() -> str:
    """Get the database connection string from Django settings."""
    db_settings = settings.DATABASES['default']
    
    if db_settings['ENGINE'] == 'django.db.backends.sqlite3':
        return f"sqlite:///{db_settings['NAME']}"
    elif db_settings['ENGINE'] == 'django.db.backends.postgresql':
        user = db_settings.get('USER', '')
        password = db_settings.get('PASSWORD', '')
        host = db_settings.get('HOST', 'localhost')
        port = db_settings.get('PORT', '5432')
        name = db_settings.get('NAME', '')
        return f"postgresql://{user}:{password}@{host}:{port}/{name}"
    elif db_settings['ENGINE'] == 'django.db.backends.mysql':
        user = db_settings.get('USER', '')
        password = db_settings.get('PASSWORD', '')
        host = db_settings.get('HOST', 'localhost')
        port = db_settings.get('PORT', '3306')
        name = db_settings.get('NAME', '')
        return f"mysql://{user}:{password}@{host}:{port}/{name}"
    else:
        raise ValueError(f"Unsupported database engine: {db_settings['ENGINE']}")

def query_ollama(prompt: str, model: str = "mistral") -> str:
    """
    Query Ollama directly via HTTP API.
    
    Args:
        prompt: The prompt to send to the model
        model: The model name to use
        
    Returns:
        The model's response
    """
    try:
        url = "http://localhost:11434/api/generate"
        data = {
            "model": model,
            "prompt": prompt,
            "stream": False
        }
        
        response = requests.post(url, json=data, timeout=240)
        response.raise_for_status()
        
        result = response.json()
        return result.get("response", "")
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Ollama request failed: {e}")
        raise Exception(f"Failed to connect to Ollama: {e}")
    except Exception as e:
        logger.error(f"Unexpected error querying Ollama: {e}")
        raise

def get_schema_description() -> str:
    """Get a human-readable description of the database schema from Django models."""
    try:
        from django.apps import apps
        from django.db import connection
        
        schema_parts = []
        schema_parts.append("This is a SQLite database. Use SQLite functions like strftime() for date operations.")
        schema_parts.append("")
        schema_parts.append("Tables:")
        schema_parts.append("")
        
        # Get all models from the lab app
        lab_app = apps.get_app_config('lab')
        
        for model in lab_app.get_models():
            table_name = model._meta.db_table
            model_name = model._meta.verbose_name_plural or model._meta.model_name
            
            # Get field information
            fields = []
            for field in model._meta.fields:
                field_name = field.get_attname()  # Get the actual database column name
                field_type = field.get_internal_type()
                if field_type == 'ForeignKey':
                    field_name += f" (-> {field.related_model._meta.db_table}.id)"
                elif field_type == 'ManyToManyField':
                    field_name += f" (M2M -> {field.related_model._meta.db_table})"
                
                fields.append(f"- {field_name}")
            
            # Add table description
            schema_parts.append(f"{table_name} ({model_name}):")
            schema_parts.extend(fields)
            schema_parts.append("")
        
        # Add key relationships
        schema_parts.append("Key relationships:")
        for model in lab_app.get_models():
            for field in model._meta.fields:
                if field.get_internal_type() == 'ForeignKey':
                    schema_parts.append(f"- {model._meta.db_table}.{field.get_attname()} -> {field.related_model._meta.db_table}.id")
        
        return "\n".join(schema_parts)
        
    except Exception as e:
        logger.error(f"Error generating schema description: {e}")
        # Fallback to basic schema
        return """
        This is a SQLite database. Use SQLite functions like strftime() for date operations.
        
        Tables:
        - lab_individual (individuals/patients)
        - lab_sample (biological samples)
        - lab_test (tests performed on samples)
        - lab_pipeline (pipeline results)
        - lab_project (research projects)
        - lab_task (tasks)
        - lab_institution (healthcare institutions)
        - lab_sampletype (sample types)
        - lab_testtype (test types)
        - lab_pipelinetype (pipeline types)
        - lab_status (status tracking)
        """

def query_natural_language(prompt: str, model_name: str = "mistral") -> Dict[str, Any]:
    """
    Convert natural language to SQL and execute it safely.
    
    Args:
        prompt: Natural language query
        model_name: Ollama model name to use
        
    Returns:
        Dictionary with results and metadata
    """
    try:
        # Get the schema description
        schema_desc = get_schema_description()
        
        # Create the prompt for the model
        enhanced_prompt = f"""
        You are a SQL expert. Generate ONLY a SQL SELECT query.

        Database schema:
        {schema_desc}

        Question: {prompt}

        RULES:
        - Return ONLY the SQL query, nothing else
        - Start with SELECT
        - No explanations, no markdown, no formatting
        - No comments, no notes
        - Just the pure SQL query

        SQL:
        """
        
        # Log the full prompt for debugging
        print(f"\n{'='*80}")
        print(f"FULL PROMPT SENT TO LLM:")
        print(f"{'='*80}")
        print(f"Prompt: {repr(enhanced_prompt)}")
        print(f"{'='*80}\n")
        
        logger.info(f"Full prompt sent to LLM: {enhanced_prompt}")
        
        # Query the model
        sql_response = query_ollama(enhanced_prompt, model_name)
        
        # Log the full response for debugging
        print(f"\n{'='*80}")
        print(f"FULL LLM RESPONSE FOR QUERY: '{prompt}'")
        print(f"{'='*80}")
        print(f"Response: {repr(sql_response)}")
        print(f"{'='*80}\n")
        
        logger.info(f"Full LLM response for query '{prompt}':")
        logger.info(f"Response: {repr(sql_response)}")
        
        # Parse and validate the SQL
        parser = SQLSafetyParser()
        safe_sql = parser.parse(sql_response)
        
        # Execute the SQL
        result = execute_safe_sql(safe_sql)
        
        if result["success"]:
            # Format the results for display
            formatted_result = format_sql_results(result)
            
            return {
                "success": True,
                "query": prompt,
                "sql": safe_sql,
                "result": formatted_result,
                "error": None
            }
        else:
            return {
                "success": False,
                "query": prompt,
                "sql": safe_sql,
                "result": None,
                "error": result["error"]
            }
        
    except Exception as e:
        logger.error(f"Error in natural language query: {e}")
        return {
            "success": False,
            "query": prompt,
            "sql": None,
            "result": None,
            "error": str(e)
        }

def execute_safe_sql(sql: str) -> Dict[str, Any]:
    """
    Execute a SQL query safely (SELECT only).
    
    Args:
        sql: SQL query to execute
        
    Returns:
        Dictionary with results
    """
    try:
        # Validate SQL
        parser = SQLSafetyParser()
        safe_sql = parser.parse(sql)
        
        # Execute query
        with connection.cursor() as cursor:
            cursor.execute(safe_sql)
            
            # Get column names
            columns = [col[0] for col in cursor.description]
            
            # Get results
            rows = cursor.fetchall()
            
            return {
                "success": True,
                "sql": safe_sql,
                "columns": columns,
                "rows": rows,
                "count": len(rows),
                "error": None
            }
            
    except Exception as e:
        logger.error(f"Error executing SQL: {e}")
        return {
            "success": False,
            "sql": sql,
            "columns": [],
            "rows": [],
            "count": 0,
            "error": str(e)
        }

def format_sql_results(result: Dict[str, Any]) -> str:
    """
    Format SQL results for display.
    
    Args:
        result: Result dictionary from execute_safe_sql
        
    Returns:
        Formatted string for display
    """
    if not result["success"]:
        return f"Error: {result['error']}"
    
    if result["count"] == 0:
        return "No results found."
    
    # Format as a simple table
    output = []
    output.append(f"Found {result['count']} result(s):\n")
    
    # Add column headers
    headers = " | ".join(str(col) for col in result["columns"])
    output.append(headers)
    output.append("-" * len(headers))
    
    # Add rows
    for row in result["rows"][:10]:  # Limit to first 10 rows
        row_str = " | ".join(str(val) if val is not None else "NULL" for val in row)
        output.append(row_str)
    
    if result["count"] > 10:
        output.append(f"\n... and {result['count'] - 10} more results")
    
    return "\n".join(output) 