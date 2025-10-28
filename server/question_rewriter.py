from prompts.ambiguity_detection_prompt import (
    QuestionRefine_prompt,
    AmbiguityDetection_prompt,
    RewriteClarificationQuestion_prompt
)
from schema_generator import SchemaGenerator
from preference_index import PreferenceTree
from utils import format_response, parse_json_response

import time
import json
import re

class QuestionRewriter:
    def __init__(self, db_name, path, question, model):
        self.db_name = db_name
        self.path = path
        self.question = question
        self.model = model
        self.schema_generator = SchemaGenerator(db_name, path, question, model)
        self.intention_model = PreferenceTree(model)
        
    def ambi_detection(self):
        flag, question_set = self.check_ambiguity('')
        if flag:          
            question_set = self.rewrite_clarification_question(question_set)
            return format_response(is_clarified=False, q_set=question_set)
        else:
            return self.format_response(self.question, self.intention_model)
        

    def ambi_correction(self, message):
        flag = None
        message_parsed = json.loads(message)
        self.intention_model.update_tree(message_parsed["qa_set"])

        additional_info = (message_parsed.get('additional_info') or '').strip()

        # Do NOT trigger a new ambiguity round on additional_info.
        # Incorporate the info by refining the question and finalize.
        if additional_info:
            self.question = self.question_refine(additional_info)
            return self.format_response(self.question, self.intention_model)

        # No additional info: finalize based on current intention model
        flag = False

        if flag:
            question_set = self.rewrite_clarification_question(question_set)
            return format_response(is_clarified=False, q_set=question_set)
        else:
            return self.format_response(self.question, self.intention_model)
        
    def check_ambiguity(self, message):
        ambiguity_detection_prompt = ""

        if message == '':
            ambiguity_detection_prompt = AmbiguityDetection_prompt.format(
                question=self.question,
                schema=self.schema_generator.db_schema_json,
                evidence=None,
            )
        else:
            message_dict = json.loads(message)
            
            self.question = self.question_refine(message_dict["additional_info"])
            
            ambiguity_detection_prompt = AmbiguityDetection_prompt.format(
                question=message_dict["additional_info"],
                schema=self.schema_generator.db_schema_json,
                evidence=self.intention_model.traverse(),
            )
        query = [
            {
                "role": "system",
                "content": "You are a helpful assistant to find out inherent ambiguity in a natural language statement. Return only the result with no explanation.",
            },
            {"role": "user", "content": ambiguity_detection_prompt},
        ]
        # print(ambiguity_detection_prompt)
        response = self.schema_generator.llm_model.call(query)
        print(response)
        res = parse_json_response(response)

        if res["has_ambiguity"]:
            return res["has_ambiguity"], res["question_set"]
        else:
            return res["has_ambiguity"], None

    def question_refine(self, additional_info):
        # Rewrite question based on new additional info
        question_refine_prompt = QuestionRefine_prompt.format(
            question=self.question, additional_info=additional_info
        )
        query = [
            {
                "role": "system",
                "content": (
                    "You are an expert AI assistant specializing in query refinement. Your purpose is to merge and consolidate user questions with new information."
                    "Respond ONLY with the refined question. Do not add any explanation, formatting, or extra text."
                ),
            },
            {"role": "user", "content": question_refine_prompt},
        ]
        response = self.schema_generator.llm_model.call(query)
        print(response)
        return response

    def rewrite_clarification_question(self, question_set):
        def _parse_choices(text: str):
            """Robustly extract a list of choice strings from an LLM response.

            Accepts:
            - JSON fenced with ```json ... ```
            - Raw JSON (list[str] or {choices|options: list[str]})
            - Fenced code without json tag
            - Bullet or numbered lists in plain text
            - Fallback: split by ' or ' if it seems like disjunctive options
            """
            try_text = text.strip()
            # Extract from fenced code blocks first
            if "```" in try_text:
                # Prefer ```json...``` block
                m = re.search(r"```json\s*(.*?)```", try_text, re.DOTALL | re.IGNORECASE)
                if not m:
                    m = re.search(r"```\s*(.*?)```", try_text, re.DOTALL)
                if m:
                    try_text = m.group(1).strip()

            # Try parsing JSON forms
            try:
                parsed = json.loads(try_text)
                if isinstance(parsed, list) and all(isinstance(x, str) for x in parsed):
                    return [s.strip() for s in parsed if s and s.strip()]
                if isinstance(parsed, dict):
                    for key in ("choices", "options"):
                        val = parsed.get(key)
                        if isinstance(val, list) and all(isinstance(x, str) for x in val):
                            return [s.strip() for s in val if s and s.strip()]
            except Exception:
                pass

            # Try to parse bullet/numbered lists
            lines = [ln.strip(" \t-*") for ln in try_text.splitlines() if ln.strip()]
            bullet_candidates = []
            for ln in lines:
                if re.match(r"^([0-9]+[\).]|[-*])\s+", ln):
                    # Remove leading token
                    bullet_candidates.append(re.sub(r"^([0-9]+[\).]|[-*])\s+", "", ln).strip())
                elif ln.startswith("-") or ln.startswith("*"):
                    bullet_candidates.append(ln.lstrip("-* ").strip())
            if bullet_candidates:
                return [s for s in bullet_candidates if s]

            # Fallback: split by ' or ' if sentence appears to enumerate options
            if " or " in try_text:
                parts = [p.strip(" .") for p in try_text.split(" or ")]
                if len(parts) > 1:
                    return [p for p in parts if p]

            return []

        for item in question_set:
            description_str = ""
            if isinstance(item.get('description'), dict):
                description_str = json.dumps(item['description'], indent=2)
            elif isinstance(item.get('description'), str):
                description_str = item['description']

            rewrite_clarification_question_prompt = RewriteClarificationQuestion_prompt.format(
                question=item['question'], description=description_str
            )

            query = [
                {
                    "role": "system",
                    "content": (
                        "You are an AI assistant that strictly follows instructions. "
                        "Your sole task is to output a single, valid JSON object containing a list of strings, "
                        "without any additional text, comments, or markdown."
                    ),
                },
                {"role": "user", "content": rewrite_clarification_question_prompt},
            ]

            try:
                response_str = self.schema_generator.llm_model.call(query)
                choices_list = _parse_choices(response_str)

                # Fallback: derive options directly from the ambiguity question text
                if (not choices_list) and isinstance(item.get('question'), str):
                    qtxt = item['question'].strip()
                    # Remove leading prompt phrasing like "Do you mean" and trailing punctuation
                    qtxt = re.sub(r"^do you mean\s*", "", qtxt, flags=re.IGNORECASE).strip(" ?.")

                    # Normalize separators: turn " or " into commas for uniform split
                    norm = re.sub(r"\s+or\s+", ", ", qtxt, flags=re.IGNORECASE)
                    # Split at commas that are followed by typical comparative keywords
                    parts = re.split(r",\s*(?=(after|before|on|in|from|to)\b)", norm)
                    # re.split keeps delimiters; rebuild segments
                    if parts:
                        rebuilt = []
                        i = 0
                        while i < len(parts):
                            if i + 1 < len(parts) and parts[i+1] in {"after","before","on","in","from","to"}:
                                rebuilt.append((parts[i] + ", " + parts[i+1] + parts[i+2] if i+2 < len(parts) else parts[i]).strip())
                                i += 3
                            else:
                                rebuilt.append(parts[i].strip())
                                i += 1
                        # Filter to meaningful segments
                        cand = [seg.strip(" .") for seg in rebuilt if seg and any(k in seg.lower() for k in ["after","before","on","in","from","to"]) ]
                        # If still poor, do a simpler split by commas
                        if not cand:
                            cand = [seg.strip(" .") for seg in norm.split(",") if seg.strip()]
                        # Capitalize first letter for nicer display
                        choices_list = [seg[0].upper() + seg[1:] if seg else seg for seg in cand]

                if isinstance(choices_list, list) and all(isinstance(c, str) for c in choices_list):
                    item['choices'] = choices_list
                else:
                    print(f"Warning: Could not parse choices from LLM response or question text. Raw: {response_str}")
                    item['choices'] = []
            except Exception as e:
                print(f"An unexpected error occurred parsing LLM choices: {e}")
                # Final fallback: keep no choices; frontend will use free text input
                item['choices'] = []

        return question_set
    
    def format_response(self, question, intention_model):
        response = {
            "is_clarified" : True,
            "question": question,
            "question_set" : None,
            "evidence": intention_model.traverse()
        }
        return json.dumps(response, ensure_ascii=False) 
