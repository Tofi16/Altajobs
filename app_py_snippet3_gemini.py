# ---------------------------------------------------------------------------
# REPLACE the entire existing `_generate_cv_payload` function with the two
# functions below (a new Gemini-backed refiner, plus the updated payload
# builder that calls it and falls back to the original heuristic text when
# no GEMINI_API_KEY is set or the API call fails for any reason).
# ---------------------------------------------------------------------------

def refine_cv_with_gemini(raw_full_name, raw_target_role, raw_summary,
                           raw_experience, raw_achievements, raw_skills,
                           want_cover_letter):
    """Calls the free-tier Gemini 1.5 Flash model with a hidden system
    instruction that positions it as an elite corporate CV writer, and asks
    for a structured JSON response. Returns a dict with keys
    {summary, achievements (list), skills (list), cover_letter (str|None)}
    on success, or None if Gemini isn't configured or the call fails -
    callers must fall back to the existing heuristic writer on None."""
    if not GEMINI_API_KEY:
        return None

    system_instruction = (
        "You are an elite corporate CV writer and career coach with 20 years "
        "of experience placing candidates at top companies. Rewrite the "
        "user's raw, informal input into polished, professional, error-free, "
        "action-verb-heavy CV prose. Never invent facts, numbers, or "
        "employers that were not implied by the input. "
        + ("Also write a concise, tailored 3-paragraph cover letter. "
           if want_cover_letter else "Do not write a cover letter. ")
        + "Respond with ONLY raw JSON (no markdown fences, no preamble) "
        "matching exactly this shape: "
        '{"summary": string, "achievements": [string, ...], '
        '"skills": [string, ...], "cover_letter": string or null}'
    )

    user_payload = {
        "full_name": raw_full_name,
        "target_role": raw_target_role,
        "summary_notes": raw_summary,
        "experience": raw_experience,
        "achievements_notes": raw_achievements,
        "skills_notes": raw_skills,
    }

    try:
        import json as _json
        import requests

        resp = requests.post(
            GEMINI_ENDPOINT,
            params={"key": GEMINI_API_KEY},
            json={
                "system_instruction": {"parts": [{"text": system_instruction}]},
                "contents": [{"role": "user", "parts": [{"text": _json.dumps(user_payload)}]}],
                "generationConfig": {
                    "temperature": 0.6,
                    "response_mime_type": "application/json",
                },
            },
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        parsed = _json.loads(text)

        achievements = [a.strip() for a in parsed.get("achievements", []) if a and a.strip()]
        skills = [s.strip() for s in parsed.get("skills", []) if s and s.strip()]
        return {
            "summary": (parsed.get("summary") or "").strip() or None,
            "achievements": achievements or None,
            "skills": skills or None,
            "cover_letter": (parsed.get("cover_letter") or "").strip() or None
                            if want_cover_letter else None,
        }
    except Exception as e:
        print(f"⚠️ Gemini CV refinement failed ({e}); using fallback heuristic writer.")
        return None


def _generate_cv_payload(form_data, photo=None, want_cover_letter=False):
    full_name = (form_data.get("full_name") or "").strip() or "Your Name"
    target_role = (form_data.get("target_role") or "").strip() or "Professional"
    summary = (form_data.get("summary") or "").strip()
    experience = (form_data.get("experience") or "").strip() or "3+ years of proven impact"
    achievements = [item.strip() for item in (form_data.get("achievements") or "").split("\n") if item.strip()]
    skills = [item.strip() for item in (form_data.get("skills") or "").split(",") if item.strip()]

    # --- Try the Gemini "AI Magic Refiner" first ---
    gemini_result = refine_cv_with_gemini(
        full_name, target_role, summary, experience,
        form_data.get("achievements") or "", form_data.get("skills") or "",
        want_cover_letter,
    )

    cover_letter = None
    if gemini_result:
        summary = gemini_result["summary"] or summary
        achievements = gemini_result["achievements"] or achievements
        skills = gemini_result["skills"] or skills
        cover_letter = gemini_result["cover_letter"]

    # --- Fallback heuristics for anything still empty (no Gemini / partial result) ---
    if not achievements:
        achievements = [
            "Led cross-functional execution with measurable outcomes",
            "Built strong stakeholder relationships and reliable delivery",
        ]
    if not skills:
        skills = ["Communication", "Leadership", "Problem solving", "Teamwork"]
    if not summary:
        summary = (
            f"{full_name} is a {target_role} focused on delivering high-impact work with "
            f"professionalism, clarity, and measurable results. With {experience}, they "
            f"bring a balanced blend of execution, collaboration, and growth mindset."
        )
    if want_cover_letter and not cover_letter:
        cover_letter = (
            f"Dear Hiring Manager,\n\nI am writing to express my interest in the "
            f"{target_role} position. {summary}\n\nIn my most recent experience "
            f"({experience}), I have consistently delivered results such as "
            f"{achievements[0].lower() if achievements else 'strong, measurable outcomes'}. "
            f"I would welcome the opportunity to bring this same energy to your team.\n\n"
            f"Sincerely,\n{full_name}"
        )

    return {
        "full_name": full_name,
        "target_role": target_role,
        "summary": summary,
        "experience": experience,
        "skills": skills,
        "achievements": achievements,
        "photo": photo,
        "cover_letter": cover_letter,
    }
