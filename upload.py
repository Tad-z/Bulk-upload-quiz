from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional
import pandas as pd
import io

app = FastAPI()

# Allow CORS for frontend testing
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/upload/quiz")
async def parse_quiz_excel(
    file: UploadFile = File(...),
    type: str = Form(...),
    require_option_format: bool = Form(True),
):
    """
    Parse an Excel file containing quiz questions.

    Parameters:
    - file: Excel file with quiz questions
    - type: Either "objective" or "tag"
    - require_option_format: If True, enforces the "text-true/false" or "text-tag" format.
                            If False, allows plain text options for flexibility.

    Returns:
    - JSON object with parsed questions and options
    """
    # Validate file type
    allowed_types = [
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.ms-excel",
    ]

    if file.content_type not in allowed_types:
        return JSONResponse(
            status_code=400,
            content={"error": "Invalid file type. Only Excel files are allowed."},
        )

    # Validate quiz type
    if type not in ["objective", "tag-based"]:
        return JSONResponse(
            status_code=400,
            content={"error": "Invalid quiz type. Must be 'objective' or 'tag'."},
        )

    try:
        contents = await file.read()
        df = pd.read_excel(io.BytesIO(contents))
    except Exception as e:
        return JSONResponse(
            status_code=400, content={"error": f"Error reading Excel file: {str(e)}"}
        )

    # Ensure required 'question' column exists
    if "question" not in df.columns:
        return JSONResponse(
            status_code=400,
            content={"error": "Excel file must contain a 'question' column."},
        )

    questions = []

    for index, row in df.iterrows():
        try:
            raw_question = row.get("question", "")
            if pd.isna(raw_question) or not str(raw_question).strip():
                continue  # Skip empty questions

            question_text = str(raw_question).strip()
            options = []

            for col in df.columns:
                if col == "question":
                    continue

                option_raw = row.get(col)
                if pd.isna(option_raw) or not str(option_raw).strip():
                    continue  # Skip empty option cells

                option_text = str(option_raw).strip()

                if require_option_format:
                    try:
                        # Always take last part as extra (e.g., true/false or tag)
                        *value_parts, extra = option_text.rsplit("-", 1)
                        value = "-".join(value_parts).strip()
                        extra = extra.strip()

                        if not value or not extra:
                            raise ValueError("Empty value or property")

                        if type == "objective":
                            if extra.lower() not in ["true", "false"]:
                                raise ValueError("Property must be 'true' or 'false'")

                            options.append(
                                {"text": value, "isCorrect": extra.lower() == "true"}
                            )
                        else:  # tag mode
                            options.append({"text": value, "tag": extra})

                    except Exception as e:
                        row_num = index + 2
                        return JSONResponse(
                            status_code=400,
                            content={
                                "error": f"Invalid option format in row {row_num}, column '{col}': '{option_text}'. Error: {str(e)}"
                            },
                        )
                else:
                    # No format required — handle gracefully
                    if type == "objective":
                        options.append({"text": option_text, "isCorrect": False})
                    else:
                        options.append(
                            {"text": option_text, "tag": col}  # fallback tag
                        )

            if not options:
                continue  # skip if no options

            if type == "objective" and require_option_format:
                if not any(option["isCorrect"] for option in options):
                    row_num = index + 2
                    return JSONResponse(
                        status_code=400,
                        content={
                            "error": f"Objective question in row {row_num} must have at least one correct answer."
                        },
                    )

            questions.append({"question": question_text, "options": options})

        except Exception as e:
            row_num = index + 2
            return JSONResponse(
                status_code=400,
                content={"error": f"Error processing row {row_num}: {str(e)}"},
            )

    if not questions:
        return JSONResponse(
            status_code=400,
            content={"error": "No valid questions found in the Excel file."},
        )

    return {"questions": questions, "count": len(questions)}


@app.get("/")
async def root():
    return {"message": "Welcome to the Quiz Parser API!"}


@app.get("/healthcheck")
async def healthcheck():
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
