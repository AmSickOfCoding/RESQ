def explain_score(contributions):
    """Provide a breakdown of the factors contributing to the final score."""

    explanation = {}

    for factor, contribution in contributions.items():
        explanation[factor] = contribution

    return explanation

def build_score_explanation(contributions, score, category):
    """Build an  explanation containing contributions, score, and category."""
    
    return {"contributions": contributions,"score": score,"category": category}