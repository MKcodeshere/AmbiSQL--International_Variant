import streamlit as st
import requests
import json

# Page config
st.set_page_config(page_title="AmbiSQL - Streamlit", layout="wide")

# Initialize session state
if 'session_id' not in st.session_state:
    st.session_state.session_id = None
if 'ambiguities' not in st.session_state:
    st.session_state.ambiguities = []
if 'raw_sql' not in st.session_state:
    st.session_state.raw_sql = None
if 'clarified_sql' not in st.session_state:
    st.session_state.clarified_sql = None
if 'raw_result' not in st.session_state:
    st.session_state.raw_result = None
if 'clarified_result' not in st.session_state:
    st.session_state.clarified_result = None

# API Base URL
API_BASE = "http://localhost:8765/api"

st.title("🔍 AmbiSQL - SQL Ambiguity Resolver")
st.markdown("---")

# Create two columns
col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("① User Input Panel")

    # Question input
    question = st.text_area(
        "Question",
        value="How many drivers born after the end of Vietnam War have been ranked 2?",
        height=100,
        placeholder="Enter your SQL-related question..."
    )

    # Database selectors
    db_col1, db_col2 = st.columns(2)
    with db_col1:
        dialect = st.selectbox(
            "DB Dialect",
            options=["SQLite", "MySQL", "PostgreSQL", "SQL Server", "Oracle"],
            index=0
        )

    with db_col2:
        db_used = st.selectbox(
            "DB used",
            options=["formula_1", "california_schools", "european_football_2",
                    "codebase_community", "superhero"],
            index=0
        )

    # Action buttons
    btn_col1, btn_col2 = st.columns(2)
    with btn_col1:
        if st.button("🧹 Clear", use_container_width=True):
            st.session_state.session_id = None
            st.session_state.ambiguities = []
            st.session_state.raw_sql = None
            st.session_state.clarified_sql = None
            st.session_state.raw_result = None
            st.session_state.clarified_result = None
            st.rerun()

    with btn_col2:
        if st.button("🚀 Submit", type="primary", use_container_width=True):
            with st.spinner("Analyzing question for ambiguities..."):
                try:
                    response = requests.post(
                        f"{API_BASE}/sql/analyze",
                        json={
                            "question": question,
                            "dialect": dialect,
                            "db": db_used,
                            "session_id": st.session_state.session_id
                        }
                    )

                    if response.status_code == 200:
                        data = response.json()
                        st.session_state.session_id = data.get('session_id')
                        ambiguities = data.get('ambiguities') or []
                        st.session_state.ambiguities = ambiguities
                        # Reset clarification list to align with new ambiguities
                        st.session_state.clarification_list = [
                            {"question": amb, "answer": ""} for amb in ambiguities
                        ]
                        st.success(f"✅ Found {len(ambiguities)} ambiguities")
                    else:
                        st.error(f"❌ Error: {response.status_code} - {response.text}")
                except requests.exceptions.RequestException as e:
                    st.error(f"❌ Connection Error: {str(e)}")

    st.markdown("---")

    # Ambiguity Resolution Panel
    st.subheader("② Ambiguity Resolution Panel")

    if st.session_state.ambiguities:
        st.info(f"Please clarify the following {len(st.session_state.ambiguities)} ambiguities:")

        # Maintain clarification list state aligned with ambiguities
        if 'clarification_list' not in st.session_state:
            st.session_state.clarification_list = [
                {"question": amb, "answer": ""} for amb in st.session_state.ambiguities
            ]
        else:
            # If ambiguities changed length, reinitialize to match
            if len(st.session_state.clarification_list) != len(st.session_state.ambiguities):
                st.session_state.clarification_list = [
                    {"question": amb, "answer": ""} for amb in st.session_state.ambiguities
                ]

        for idx, ambiguity in enumerate(st.session_state.ambiguities):
            st.markdown(f"**Question {idx + 1}:** {ambiguity.get('question', '')}")

            choices = ambiguity.get('choices', []) or []
            if choices:
                options = ["Please select an answer"] + choices
                current = st.session_state.clarification_list[idx]["answer"]
                index = options.index(current) if current in options else 0
                sel = st.selectbox(
                    f"Select option for question {idx + 1}",
                    options=options,
                    index=index,
                    key=f"clarification_{idx}"
                )
                st.session_state.clarification_list[idx]["answer"] = (
                    "" if sel == options[0] else sel
                )
            else:
                # Fallback to free text if no choices provided
                val = st.text_input(
                    f"Your answer for question {idx + 1}",
                    value=st.session_state.clarification_list[idx]["answer"],
                    key=f"clarification_text_{idx}"
                )
                st.session_state.clarification_list[idx]["answer"] = val

        additional_info = st.text_area(
            "Any additional info? (optional)",
            key="additional_info"
        )

        if st.button("✨ Submit Clarifications", type="primary", use_container_width=True):
            with st.spinner("Generating SQL with clarifications..."):
                try:
                    response = requests.post(
                        f"{API_BASE}/sql/solve",
                        json={
                            "session_id": st.session_state.session_id,
                            "clarificationList": st.session_state.clarification_list,
                            "additional_info": additional_info or "",
                        }
                    )

                    if response.status_code == 200:
                        data = response.json()
                        # If further ambiguities returned, update and continue
                        if data.get('ambiguities'):
                            st.session_state.ambiguities = data['ambiguities']
                            st.session_state.clarification_list = [
                                {"question": amb, "answer": ""} for amb in data['ambiguities']
                            ]
                            st.info("More clarification needed. Please answer the new questions.")
                            st.rerun()
                        else:
                            st.session_state.raw_sql = data.get('sql_statement_raw')
                            st.session_state.clarified_sql = data.get('sql_statement_clarified')
                            st.success("✅ Clarified SQL generated!")
                            st.rerun()
                    else:
                        st.error(f"❌ Error: {response.status_code} - {response.text}")
                except requests.exceptions.RequestException as e:
                    st.error(f"❌ Connection Error: {str(e)}")
    else:
        st.info("No ambiguities detected. You can still generate SQL.")
        # Allow generating SQL even when no ambiguities were found in analysis
        if st.session_state.session_id and st.button("✨ Generate SQL", type="primary", use_container_width=True):
            with st.spinner("Generating SQL..."):
                try:
                    response = requests.post(
                        f"{API_BASE}/sql/solve",
                        json={
                            "session_id": st.session_state.session_id,
                            "clarificationList": [],
                            "additional_info": "",
                        }
                    )
                    if response.status_code == 200:
                        data = response.json()
                        if data.get('ambiguities'):
                            st.session_state.ambiguities = data['ambiguities']
                            st.session_state.clarification_list = [
                                {"question": amb, "answer": ""} for amb in data['ambiguities']
                            ]
                            st.info("More clarification needed. Please answer the new questions.")
                            st.rerun()
                        else:
                            st.session_state.raw_sql = data.get('sql_statement_raw')
                            st.session_state.clarified_sql = data.get('sql_statement_clarified')
                            st.success("✅ SQL generated!")
                            st.rerun()
                    else:
                        st.error(f"❌ Error: {response.status_code} - {response.text}")
                except requests.exceptions.RequestException as e:
                    st.error(f"❌ Connection Error: {str(e)}")

with col2:
    st.subheader("③ SQL Generation Panel")

    # Raw SQL (without clarification)
    st.markdown("**Text2SQL Output Without AmbiSQL**")
    if st.session_state.raw_sql:
        st.code(st.session_state.raw_sql, language="sql")
        if st.session_state.raw_result:
            if isinstance(st.session_state.raw_result, dict) and st.session_state.raw_result.get('success'):
                rows = st.session_state.raw_result.get('rows')
                count = st.session_state.raw_result.get('row_count', 0)
                st.info(f"Rows: {count}")
                if isinstance(rows, list) and len(rows) > 0:
                    st.dataframe(rows)
            elif isinstance(st.session_state.raw_result, dict):
                st.error(f"❌ Evaluation: Failed - {st.session_state.raw_result.get('error', '')}")
            else:
                st.dataframe(st.session_state.raw_result)
    else:
        st.info("Raw SQL will appear here after submission")

    st.markdown("---")

    # Clarified SQL (with AmbiSQL)
    st.markdown("**Text2SQL Output with AmbiSQL**")
    if st.session_state.clarified_sql:
        st.code(st.session_state.clarified_sql, language="sql")
        if st.session_state.clarified_result:
            if isinstance(st.session_state.clarified_result, dict) and st.session_state.clarified_result.get('success'):
                rows = st.session_state.clarified_result.get('rows')
                count = st.session_state.clarified_result.get('row_count', 0)
                st.info(f"Rows: {count}")
                if isinstance(rows, list) and len(rows) > 0:
                    st.dataframe(rows)
            elif isinstance(st.session_state.clarified_result, dict):
                st.error(f"❌ Evaluation: Failed - {st.session_state.clarified_result.get('error', '')}")
            else:
                st.dataframe(st.session_state.clarified_result)
    else:
        st.info("Clarified SQL will appear here after clarification")

    st.markdown("---")

    # Compare button
    if st.button("🔄 Compare SQLs", use_container_width=True,
                disabled=not st.session_state.session_id):
        with st.spinner("Executing and comparing SQLs..."):
            try:
                response = requests.post(
                    f"{API_BASE}/sql/compare",
                    json={"session_id": st.session_state.session_id}
                )

                if response.status_code == 200:
                    data = response.json()
                    st.session_state.raw_sql = data.get('raw_sql')
                    st.session_state.clarified_sql = data.get('clarified_sql')
                    st.session_state.raw_result = data.get('raw_result')
                    st.session_state.clarified_result = data.get('clarified_result')
                    st.success("✅ Comparison complete!")
                    st.rerun()
                else:
                    st.error(f"❌ Error: {response.status_code} - {response.text}")
            except requests.exceptions.RequestException as e:
                st.error(f"❌ Connection Error: {str(e)}")

# Footer with examples
st.markdown("---")
st.subheader("📚 Examples")

examples_data = [
    {
        "question": "How many drivers born after the end of Vietnam War have been ranked 2?",
        "database": "formula_1",
        "dialect": "SQLite"
    },
    {
        "question": "Name all drivers in the 2010 Singapore Grand Prix order by their position stands.",
        "database": "formula_1",
        "dialect": "SQLite"
    }
]

st.table(examples_data)

st.markdown("---")
st.caption("🤖 AmbiSQL - Streamlit Frontend for Backend Testing")
