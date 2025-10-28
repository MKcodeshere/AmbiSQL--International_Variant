import os
import uuid
import json
import time
import re
import sys
from openai import OpenAI
import os

import pandas as pd
import warnings
warnings.simplefilter(action='ignore', category=pd.errors.SettingWithCopyWarning)

import argparse
import asyncio 
import functools
from typing import Callable, Any, TypeVar, Awaitable
from datetime import datetime
from flask import Flask, request, jsonify
from flask_cors import CORS
from pathlib import Path

from question_rewriter import QuestionRewriter
from schema_generator import SchemaGenerator
from utils import format_message, parse_schema_text, add_semicolon_if_missing, sanitize_sql
from prompts.xiyan_template_prompt import xiyan_template_en
from db_utils import execute_query
# from text2sql.udf_exec_json import LLMEnhancedDBExecutor

CURR_DIR = Path(__file__).resolve().parent
PARENT_DIR = CURR_DIR.parent
sys.path.insert(0, str(PARENT_DIR))

db_path = str((CURR_DIR / "../minidev/dev_databases").resolve())
app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}}, supports_credentials=True)

# memory-resident session related data
sessions = {}

def sql_generator(question, evidence, schema):
    #base_url = 'https://api-inference.modelscope.cn/v1'
    api_key = 'YOUR_API_KEY'
    if not api_key:
        raise PermissionError("Missing MODELSCOPE_API_KEY for SQL generation")
    client = OpenAI(
        api_key=api_key  # ModelScope API_KEY
    )

    prompt_raw = xiyan_template_en.format(
        dialect="SQLite",
        question=question,
        db_schema=schema,
        evidence= None
    )
    
    prompt_with_evidence = xiyan_template_en.format(
        dialect="SQLite",
        question=question,
        db_schema=schema,
        evidence= evidence
    )
    
    response_raw = client.chat.completions.create(
        model='gpt-4.1', # ModelScope Model-Id
        messages=[
            {
                'role': 'system',
                'content': 'You are a helpful assistant.'
            },
            {
                'role': 'user',
                'content': prompt_raw
            }
        ]
    )
    sql_raw = response_raw.choices[0].message.content
    
    response_clarified = client.chat.completions.create(
        model='gpt-4.1',
        messages=[
            {
                'role': 'system',
                'content': 'You are a helpful assistant.'
            },
            {
                'role': 'user',
                'content': prompt_with_evidence
            }
        ]
    )
    sql_clarified = response_clarified.choices[0].message.content
    return sql_raw, sql_clarified
    
    
class ChatSession:
    def __init__(self, session_id):
        self.session_id = session_id
        self.db_name = None
        self.question = None
        self.created_at = datetime.now().isoformat()
        self.last_accessed = datetime.now().isoformat()
        self.messages = []
        self.question_rewriter_instance = None  # QuestionRewriter Instance
        self.text2sql_agent = None
        # Store generated SQL for comparison endpoint
        self.sql_raw = None
        self.sql_clarified = None

    def add_message(self, role, content):
        """Add message to session history"""
        timestamp = datetime.now().isoformat()
        message = {
            "id": str(uuid.uuid4()),
            "role": role,
            "content": content,
            "timestamp": timestamp,
        }
        self.messages.append(message)
        self.last_accessed = timestamp
        return message

    def get_history(self):
        """Get session history"""
        return self.messages

    def clear(self):
        """Clear session history"""
        self.messages = []
        self.last_accessed = datetime.now().isoformat()

    def to_dict(self):
        """transform session object to dict"""
        return {
            "session_id": self.session_id,
            "created_at": self.created_at,
            "last_accessed": self.last_accessed,
            "message_count": len(self.messages),
        }


# Ambiguity Identification
@app.route("/api/sql/analyze", methods=["POST"])
def analyze_sql_query():
    try:
        data = request.json
        client_session_id = data.get("session_id") 

        session_id = None
        current_session = None

        if client_session_id and client_session_id in sessions:
            session_id = client_session_id
            current_session = sessions[session_id]
            current_session.last_accessed = datetime.now().isoformat() 
            print(f"Using existing session: {session_id}")
        else:
            session_id = str(uuid.uuid4())
            current_session = ChatSession(session_id)
            sessions[session_id] = current_session
            print(f"Created new session: {session_id}")

        question = data.get("question", "")
        dialect = data.get("dialect", "SQLite")
        db_name = data.get("db", "")
        current_session.db_name = db_name
        current_session.question = question
        model = "gpt"

        # Get or create session
        if session_id not in sessions:
            sessions[session_id] = ChatSession(session_id)
        current_session = sessions[session_id]

        # Create QuestionRewriter instance and store it to session
        qr_instance = QuestionRewriter(db_name, db_path, question, model)
        print("qr created")  
        current_session.question_rewriter_instance = qr_instance

        # parse schema
        schema_text = qr_instance.schema_generator.db_schema
        parsed_schema = parse_schema_text(schema_text)

        response_json = qr_instance.ambi_detection()
        print(response_json)

        response = json.loads(response_json)
        question_set = response["question_set"]

        response_data = {
            "session_id": session_id,
            "suggested_schema": parsed_schema,
            "analysis": "Schema analysis completed",
            "dialect_info": dialect,
            "ambiguities": question_set,
        }
        return jsonify(response_data), 200

    except Exception as e:
        msg = str(e)
        status = 500
        if isinstance(e, PermissionError) or "invalid_api_key" in msg.lower() or "incorrect api key" in msg.lower():
            status = 401
        return (jsonify({"error": msg, "message": "Error processing schema analysis"}), status)

@app.route("/api/sql/solve", methods=["POST"])
def solve_ambiguities():
    print("[Solve] Entered solve_ambiguities route.") 
    try:
        # session management
        data = request.json
        print(f"[Solve] Request JSON data: {data}") 
        session_id = data.get('session_id')
        print(f"[Solve] Session ID: {session_id}") 

        if not session_id:
            print("[Solve] No session_id provided, returning 400.") 
            return jsonify({"error": "session_id is required"}), 400

        current_session = sessions.get(session_id)
        print(f"[Solve] Current session object: {current_session}") 
        if not current_session:
            print("[Solve] Session not found or expired, returning 404.") 
            return jsonify({"error": "Session not found or expired"}), 404

        # residual ambiguity identification and question rewrite
        qr_instance = current_session.question_rewriter_instance
        text2sql_agent = current_session.text2sql_agent
        print(f"[Solve] QuestionRewriter instance from session: {qr_instance}") 
        if not qr_instance:
            print("[Solve] QuestionRewriter instance not found in session, returning 400.") 
            return jsonify({"error": "QuestionRewriter instance not found in session. Please call /analyze first."}), 400

        clarification_list = data.get('clarificationList', [])
        print(f"[Solve] Clarification List: {clarification_list}") 
        
        qa_set = []
        for item in clarification_list:
            q_data = item.get('question', {})
            ans = item.get('answer', '')
            qa_set.append({
                "level_1_label": q_data.get('level_1_label', None),
                "level_2_label": q_data.get('level_2_label', None),
                "question": q_data.get('question', None),
                "answer": ans
            })
        print(f"[Solve] Prepared QA Set: {qa_set}") 
            
        additional_info = data.get('additional_info', '')
        print(f"[Solve] Additional Info: {additional_info}")

        formatted_message = format_message(qa_set, additional_info)
        print(f"[Solve] Formatted message: {formatted_message}")

        print("[Solve] Calling qr_instance.process_message for clarification...")
        response_json = qr_instance.ambi_correction(message = formatted_message)
        print(f"[Solve] process_message returned: {response_json}")
         
        parsed_response = json.loads(response_json) 
        print(f"[Solve]Parsed response: {parsed_response}") 
        
        response_data = None
        
        if "has_ambiguity" in parsed_response or parsed_response['is_clarified'] == False:
            response_data = {
                "is_clarified": "False",
                "session_id": session_id,
                "ambiguities": parsed_response['question_set'],
            }
        else:
            # Generate raw SQL from the original question (no evidence),
            # and clarified SQL from the refined question with evidence.
            original_q = current_session.question or ""
            refined_q = parsed_response.get('question', original_q)
            # Raw: original question, no evidence
            sql_raw, _ = sql_generator(original_q, None, qr_instance.schema_generator.formatted_full_schema)
            # Clarified: refined question, with evidence
            _, sql_clarified = sql_generator(refined_q, parsed_response.get('evidence'), qr_instance.schema_generator.formatted_full_schema)
            # Clean up any markdown formatting and ensure statement termination
            sql_raw = add_semicolon_if_missing(sanitize_sql(sql_raw))
            sql_clarified = add_semicolon_if_missing(sanitize_sql(sql_clarified))
            print(f"Raw SQL parsed: {sql_raw}")
            print(f"Clarified SQL parsed: {sql_clarified}")
            # persist to session for later comparison
            current_session.sql_raw = sql_raw
            current_session.sql_clarified = sql_clarified
            response_data = {
                "session_id": session_id,
                "is_clarified": "True",
                "sql_statement_raw": sql_raw,
                # "result_raw": raw_result,
                "sql_statement_clarified": sql_clarified,
                # "result_clarified": clarified_reuslt
            }

        return jsonify(response_data), 200 
    
    except Exception as e:
        print(f"[Solve Error] An exception occurred: {e}") 
        import traceback
        traceback.print_exc() # print complete traceback
        msg = str(e)
        status = 500
        if isinstance(e, PermissionError) or "invalid_api_key" in msg.lower() or "incorrect api key" in msg.lower():
            status = 401
        return jsonify({
            "error": msg,
            "message": "Error processing ambiguity resolution"
        }), status

@app.route("/")
def health_check():
    """Server API checkpoint"""
    return "Chat API is running. Use endpoints: /api/chat/start, /api/chat/send, /api/chat/history"


@app.route("/api/sql/compare", methods=["POST"])
def compare_sql():
    try:
        data = request.json
        session_id = data.get("session_id")
        if not session_id:
            return jsonify({"error": "session_id is required"}), 400

        current_session = sessions.get(session_id)
        if not current_session:
            return jsonify({"error": "Session not found or expired"}), 404

        # Ensure we have SQLs to execute
        raw_sql = sanitize_sql(current_session.sql_raw) if current_session.sql_raw else None
        clarified_sql = sanitize_sql(current_session.sql_clarified) if current_session.sql_clarified else None
        if not raw_sql and not clarified_sql:
            return jsonify({"error": "No SQL statements available for comparison. Solve ambiguities first."}), 400

        db_name = current_session.db_name
        # Execute queries
        raw_rows = execute_query(db_path, db_name, raw_sql) if raw_sql else []
        clarified_rows = execute_query(db_path, db_name, clarified_sql) if clarified_sql else []

        raw_payload = {
            "success": True,
            "rows": raw_rows,
            "row_count": len(raw_rows) if isinstance(raw_rows, list) else 0,
        }
        clarified_payload = {
            "success": True,
            "rows": clarified_rows,
            "row_count": len(clarified_rows) if isinstance(clarified_rows, list) else 0,
        }

        return jsonify({
            "raw_sql": raw_sql,
            "clarified_sql": clarified_sql,
            "raw_result": raw_payload,
            "clarified_result": clarified_payload,
        }), 200
    except Exception as e:
        print(f"[Compare Error] {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e), "message": "Error processing SQL comparison"}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8765))
    app.run(host="0.0.0.0", port=port, debug=True)
