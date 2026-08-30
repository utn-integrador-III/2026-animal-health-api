"""AI-assisted veterinary risk alert generation."""

from __future__ import annotations

import json
from typing import Any

from ..config import AI_PROVIDER, GEMINI_API_KEY, GEMINI_FALLBACK_MODELS, GEMINI_MODEL


NON_DIAGNOSTIC_WARNING = (
    "AI-generated alerts are informational and do not replace veterinary diagnosis, "
    "clinical examination, or professional judgment."
)


class AIServiceError(RuntimeError):
    """Raised when the AI provider cannot generate a usable response."""


def _extract_json(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`").strip()
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1:
        cleaned = cleaned[start:end + 1]
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise AIServiceError("AI provider returned an invalid JSON response") from exc
    if not isinstance(data, dict):
        raise AIServiceError("AI provider response must be a JSON object")
    return data


def _build_prompt(pet_context: dict[str, Any], language: str) -> str:
    secondary = pet_context.get("breed_secondary") or "None"
    return f"""
You are assisting a licensed veterinarian during a patient review.
Generate breed and age context risk alerts for this pet.
Do not diagnose. Do not prescribe medication. Keep all content concise and practical.
Return only valid JSON using this exact structure:
{{
  "alerts": [
    {{
      "title": "short alert title",
      "description": "breed/age predisposition context",
      "severity": "informational|low|moderate|high",
      "recommendation": "preventive action to consider"
    }}
  ],
  "preventive_recommendations": ["recommendation 1", "recommendation 2"],
  "non_diagnostic_warning": "short non-diagnostic warning"
}}
Language: {language}
Pet name: {pet_context.get('name')}
Species: {pet_context.get('species')}
Primary breed: {pet_context.get('breed_primary')}
Secondary breed: {secondary}
Age: {pet_context.get('age_years')} years, {pet_context.get('age_months')} months, {pet_context.get('age_days')} days
Weight kg: {pet_context.get('weight_kg') or 'Unknown'}
""".strip()


def _build_client_care_prompt(pet_context: dict[str, Any], language: str) -> str:
    secondary = pet_context.get("breed_secondary") or "None"
    return f"""
You are helping a pet owner understand preventive care for their pet.
Generate practical, client-friendly care recommendations based on species, breed, age, and weight.
Do not diagnose. Do not prescribe medication. Do not replace veterinary advice.
Focus on nutrition care, physical activity, and preventive disease care.
Return only valid JSON using this exact structure:
{{
  "nutrition_recommendations": ["recommendation 1", "recommendation 2"],
  "activity_recommendations": ["recommendation 1", "recommendation 2"],
  "preventive_recommendations": ["recommendation 1", "recommendation 2"],
  "non_diagnostic_warning": "short non-diagnostic warning"
}}
Language: {language}
Pet name: {pet_context.get('name')}
Species: {pet_context.get('species')}
Primary breed: {pet_context.get('breed_primary')}
Secondary breed: {secondary}
Age: {pet_context.get('age_years')} years, {pet_context.get('age_months')} months, {pet_context.get('age_days')} days
Weight kg: {pet_context.get('weight_kg') or 'Unknown'}
""".strip()


def _mock_breed_risk_alerts(pet_context: dict[str, Any], language: str) -> dict[str, Any]:
    species = pet_context.get("species", "Pet")
    breed = pet_context.get("breed_primary", "Mixed breed")
    if language == "es":
        return {
            "alerts": [
                {
                    "title": f"Predisposición general para {breed}",
                    "description": f"Los ejemplares de raza {breed} ({species}) se benefician de revisiones periódicas de peso y salud preventiva.",
                    "severity": "informational",
                    "recommendation": "Mantener control veterinario periódico y dieta balanceada.",
                },
                {
                    "title": "Cuidado preventivo dental y articular",
                    "description": "La monitorización rutinaria previene afecciones articulares y dentales en etapas adultas.",
                    "severity": "low",
                    "recommendation": "Realizar higiene bucal periódica y chequeo osteomuscular anual.",
                },
            ],
            "preventive_recommendations": [
                "Mantener el calendario de vacunación y desparasitación al día.",
                "Controlar las porciones de alimentación según su edad y peso.",
            ],
            "non_diagnostic_warning": NON_DIAGNOSTIC_WARNING,
            "generated_by": "mock",
        }
    return {
        "alerts": [
            {
                "title": f"General predisposition for {breed}",
                "description": f"{breed} ({species}) benefit from regular weight and wellness checkups.",
                "severity": "informational",
                "recommendation": "Maintain regular wellness exams and a balanced diet.",
            },
            {
                "title": "Preventive dental and joint care",
                "description": "Routine monitoring helps prevent common dental and mobility issues over time.",
                "severity": "low",
                "recommendation": "Perform regular oral hygiene and annual checkups.",
            },
        ],
        "preventive_recommendations": [
            "Keep vaccination and deworming schedules up to date.",
            "Monitor food portions suited for age and weight.",
        ],
        "non_diagnostic_warning": NON_DIAGNOSTIC_WARNING,
        "generated_by": "mock",
    }


def _mock_pet_care_recommendations(pet_context: dict[str, Any], language: str) -> dict[str, Any]:
    species = pet_context.get("species", "Pet")
    if language == "es":
        return {
            "nutrition_recommendations": [
                f"Proporcionar alimento premium específico para {species.lower()}s acorde a su peso.",
                "Asegurar acceso constante a agua fresca y limpia.",
            ],
            "activity_recommendations": [
                "Realizar actividad física y juegos diarios adaptados a su edad.",
                "Fomentar estimulación mental y enriquecimiento ambiental.",
            ],
            "preventive_recommendations": [
                "Completar el esquema de vacunas y antiparasitarios periódicos.",
                "Consultar al médico veterinario ante cualquier cambio de apetito o ánimo.",
            ],
            "non_diagnostic_warning": NON_DIAGNOSTIC_WARNING,
            "generated_by": "mock",
        }
    return {
        "nutrition_recommendations": [
            f"Provide high-quality nutrition formulated for {species.lower()}s according to weight.",
            "Ensure constant access to fresh, clean water.",
        ],
        "activity_recommendations": [
            "Provide daily age-appropriate physical exercise and play.",
            "Incorporate mental enrichment and interactive toys.",
        ],
        "preventive_recommendations": [
            "Keep vaccination and parasite prevention on schedule.",
            "Consult your veterinarian if you observe any behavioral changes.",
        ],
        "non_diagnostic_warning": NON_DIAGNOSTIC_WARNING,
        "generated_by": "mock",
    }


def generate_breed_risk_alerts(pet_context: dict[str, Any], language: str = "en") -> dict[str, Any]:
    """Generate structured breed risk alerts using Gemini or local intelligent fallback."""
    if AI_PROVIDER == "mock" or not GEMINI_API_KEY:
        return _mock_breed_risk_alerts(pet_context, language)
    if AI_PROVIDER != "gemini":
        raise AIServiceError(f"Unsupported AI provider: {AI_PROVIDER}")

    try:
        from google import genai
    except ImportError as exc:  # pragma: no cover - dependency setup guard
        raise AIServiceError("google-genai is not installed") from exc

    client = genai.Client(api_key=GEMINI_API_KEY)
    prompt = _build_prompt(pet_context, language)
    last_error: Exception | None = None
    response = None

    for model in [GEMINI_MODEL, *GEMINI_FALLBACK_MODELS]:
        try:
            response = client.models.generate_content(
                model=model,
                contents=prompt,
            )
            break
        except Exception as exc:  # pragma: no cover - provider/network runtime
            last_error = exc

    if response is None:
        # Fallback cleanly if network or quota issue occurs during local run
        return _mock_breed_risk_alerts(pet_context, language)

    text = getattr(response, "text", "") or ""
    data = _extract_json(text)

    alerts = data.get("alerts") or []
    recommendations = data.get("preventive_recommendations") or []
    if not isinstance(alerts, list) or not isinstance(recommendations, list):
        raise AIServiceError("AI provider response has an invalid structure")

    return {
        "alerts": alerts,
        "preventive_recommendations": recommendations,
        "non_diagnostic_warning": data.get("non_diagnostic_warning") or NON_DIAGNOSTIC_WARNING,
        "generated_by": "gemini",
    }


def generate_pet_care_recommendations(pet_context: dict[str, Any], language: str = "en") -> dict[str, Any]:
    """Generate structured preventive care recommendations for a client."""
    if AI_PROVIDER == "mock" or not GEMINI_API_KEY:
        return _mock_pet_care_recommendations(pet_context, language)
    if AI_PROVIDER != "gemini":
        raise AIServiceError(f"Unsupported AI provider: {AI_PROVIDER}")

    try:
        from google import genai
    except ImportError as exc:  # pragma: no cover - dependency setup guard
        raise AIServiceError("google-genai is not installed") from exc

    client = genai.Client(api_key=GEMINI_API_KEY)
    prompt = _build_client_care_prompt(pet_context, language)
    last_error: Exception | None = None
    response = None

    for model in [GEMINI_MODEL, *GEMINI_FALLBACK_MODELS]:
        try:
            response = client.models.generate_content(
                model=model,
                contents=prompt,
            )
            break
        except Exception as exc:  # pragma: no cover - provider/network runtime
            last_error = exc

    if response is None:
        # Fallback cleanly if network or quota issue occurs during local run
        return _mock_pet_care_recommendations(pet_context, language)

    text = getattr(response, "text", "") or ""
    data = _extract_json(text)

    nutrition = data.get("nutrition_recommendations") or []
    activity = data.get("activity_recommendations") or []
    preventive = data.get("preventive_recommendations") or []
    if not all(isinstance(items, list) for items in (nutrition, activity, preventive)):
        raise AIServiceError("AI provider response has an invalid structure")

    return {
        "nutrition_recommendations": nutrition,
        "activity_recommendations": activity,
        "preventive_recommendations": preventive,
        "non_diagnostic_warning": data.get("non_diagnostic_warning") or NON_DIAGNOSTIC_WARNING,
        "generated_by": "gemini",
    }
